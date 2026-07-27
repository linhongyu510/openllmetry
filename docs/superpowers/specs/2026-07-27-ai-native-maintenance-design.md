# AI-Native Maintenance System — Design

**Date:** 2026-07-27
**Status:** Approved, pending implementation plans
**Repo:** `traceloop/openllmetry`

## Goal

Make the repository maintainable primarily by AI agents: agents take issues, produce
verified fixes, and iterate on review feedback. Humans approve PRs and make product
decisions. Nothing else is delegated away from humans.

## Repository baseline (measured 2026-07-27)

| Fact | Value |
|---|---|
| Python packages under Nx + uv | 35 (32 instrumentations) |
| Open issues | 110 (22 opened in last 90d, 39 closed) |
| Open PRs | 499 (33 merged in last 90d) |
| Packages with any semconv-compliance test | 5 of 32 |
| Packages dual-emitting `gen_ai.*` and legacy `llm.*`/`traceloop.*` | 21 |
| References to upstream weaver / `semantic-conventions-genai` | 0 |
| Existing agent config | one flat `CLAUDE.md`; no skills, agents, or AI workflows |

Two findings drive the design:

**Issue inflow is not the constraint.** ~7 issues/month arrive; the PR queue is 499 deep
and drains at ~11/month. Autonomous issue-solving adds supply to the flooded side of the
pipeline. The system must therefore be verification-heavy, throughput-limited, and must
not enable auto-merge.

**The semconv contract is enforced in 15% of the places it applies.** Open bugs #4362
(anthropic drops `finish_reasons`), #4192 (ollama missing inference metadata), #4234
(bedrock wrong vendor attribute) and #4378 (agent name leaking) are not four bugs. They
are one bug — an unenforced contract — reported four times. Fixing them individually is
32x the work of making the contract executable.

## Decisions

| Decision | Choice |
|---|---|
| First target | Knowledge substrate + autonomous issue→PR authoring |
| Runtime | GitHub Actions, in-repo, versioned |
| Cassette policy | Agent records live, behind a fail-closed scrubbing gate |
| Substrate form | Executable contract + layered docs/skills + accumulated lessons |
| Autonomy gate | Triage agent tiers issues; only tier 1 is auto-attempted |
| Contract source | `github.com/open-telemetry/semantic-conventions-genai`, pinned SHA |
| Fix methodology | Mandatory TDD, mechanically enforced RED→GREEN |

## Architecture

Three layers. Governing principle: **knowledge that can fail CI beats knowledge written
as prose.**

### Layer 1 — Knowledge substrate

```
.semconv/
  versions.env              SEMCONV_GENAI_REF=<pinned sha>   # deliberate bumps only
  registry/                 vendored model/ from semantic-conventions-genai
packages/opentelemetry-semantic-conventions-ai/
  .../_generated/contract.py    weaver-generated: required/recommended attrs per
                                span kind, enum values, payload JSON Schemas
  .../conformance.py            hand-written harness consuming contract.py
CLAUDE.md                   thin router, not a dumping ground
packages/*/CLAUDE.md        per-SDK quirks: streaming shapes, response oddities,
                            cassette notes
.claude/skills/             triage-issue/, fix-instrumentation-bug/,
                            add-instrumentation/, record-cassette/,
                            semconv-conformance/
docs/ai/lessons/            accumulated maintainer taste, one file per lesson,
                            written by responder, merged only via human-reviewed PR
```

### Layer 2 — Agent roles (`.claude/agents/`)

| Agent | Responsibility |
|---|---|
| `triage` | Classify tier 1/2/3, dedupe, write repro hypothesis, label package |
| `fixer` | Failing test → fix → self-verify → draft PR |
| `recorder` | **Isolated.** Holds provider keys. Never reads issue or PR text. |
| `reviewer` | Adversarial pass attempting to refute the fix, before a human sees it |
| `responder` | Applies maintainer review feedback; writes the lesson file |

`recorder` is a separate agent by architectural necessity, not convenience. It is the only
component holding live provider keys and must be structurally incapable of reading
attacker-controlled issue text. `fixer` declares the interaction it needs via a committed
`.recording-manifest.yaml`; `recorder` reads only that manifest. Collapsing the two agents
reopens the exfiltration path.

### Layer 3 — Orchestration (`.github/workflows/`)

| Workflow | Trigger |
|---|---|
| `ai-triage.yml` | `issues[opened, reopened]` |
| `ai-fix.yml` | label `ai:tier1` |
| `ai-record.yml` | label `ai:needs-recording` — **GitHub Environment, human-approved** |
| `ai-review.yml` | PR ready / fixer push |
| `ai-review-response.yml` | `pull_request_review[submitted]` with `changes_requested` |
| `ai-conformance-sweep.yml` | `schedule` |

## The contract

The conformance suite is **generated from upstream, not written by hand.**

Upstream `semantic-conventions-genai` is a Weaver registry (`WEAVER_VERSION=v0.25.0`)
containing `registry.yaml`, `spans.yaml`, `metrics.yaml`, `events.yaml`, and JSON Schemas
for payload shapes (`gen-ai-input-messages.json`, `gen-ai-output-messages.json`,
`gen-ai-tool-definitions.json`, …). It also ships per-provider docs (`anthropic.md`,
`openai.md`, `aws-bedrock.md`, `mcp.md`, `azure-ai-inference.md`) mapping nearly 1:1 onto
openllmetry packages. It declares itself the canonical home for GenAI conventions,
superseding the gen-ai directories in the main semconv repo.

`_generated/contract.py` is **committed to the repo**, not generated at test time. CI
regenerates and fails on diff. This makes every contract change a reviewable line-level
diff rather than an invisible behavioural shift, and keeps test runs offline.

Each instrumentation package gets one test importing the shared harness, parametrized over
the spans it emits. The harness validates emitted attributes against the generated
contract and validates message payloads against upstream's JSON Schemas directly.

Why generation:

- Four reported bugs plus the ~28 unreported instances collapse into one red test.
- Upstream drift becomes a reviewable PR: bump pin → regenerate → CI diff names exactly
  which packages fell out of compliance.
- The `gen_ai.*` vs `llm.*` dual-emit migration gets an end condition: assert-required on
  the contract namespace, warn-only on legacy.

Two hard constraints:

- Upstream is `stability: development`, `schema_url: .../gen-ai-dev/1.42.0-dev`, with **no
  tags**. Pin a SHA and bump deliberately. Tracking `main` would red-CI all 32 packages on
  a third party's merge.
- The harness lands **warn-only**, flipping to enforcing per-package as each is fixed.
  Enabling enforcement repo-wide on day one red-CIs the entire repository. Enforcement
  state is declared per package in its `project.json` under
  `tags: ["semconv:enforcing"]` vs `tags: ["semconv:warn"]`, so the migration frontier is
  visible in one `grep` and flipping a package is a one-line reviewable change.

## The TDD gate

"Write a failing test first" as a prompt instruction is unverifiable — the agent will claim
compliance and CI cannot tell. It is enforced structurally instead.

`fixer` must produce exactly two commits:

```
test: reproduce #4362 — streaming drops finish_reasons      # test files only
fix(anthropic): emit finish_reasons on empty-content turns  # source files only
```

CI enforces:

| Step | Check | On violation |
|---|---|---|
| 1 | Checkout **test commit only**, run the new test | must **FAIL** — else block: test reproduces nothing |
| 2 | Capture failure output verbatim | posted into PR body as RED evidence |
| 3 | Run new test at HEAD | must **PASS** |
| 4 | Run full affected suite at HEAD | must **PASS** — no collateral breakage |
| 5 | Commit 1 touches no `packages/*/opentelemetry/**` | else block: fix smuggled into test commit |

Step 1 carries the weight. It catches the three ways autonomous agents fake completion: a
test that asserts nothing, a test that passes trivially, and a "fix" for a bug that was
never real. Human review then begins from proof the bug existed rather than the agent's
claim that it did.

## Flows

### Flow A — issue to merged PR

1. `issues[opened]` → `triage`: dedupe against open and closed-in-90d; classify.
   Tier 1 (mechanical: a defect or enhancement whose correct behaviour is determined by
   the semconv contract, an existing test, or explicit upstream SDK behaviour) gets
   `ai:tier1` + `pkg:<name>` + a repro hypothesis. Tier 2
   (needs maintainer decision) gets the options drafted and the maintainer @-mentioned —
   **no PR**. Tier 3 is answered or closed.
2. `ai:tier1` → `fixer`: loads root `CLAUDE.md` → package `CLAUDE.md` → relevant skill →
   lessons index. Writes commit 1 (failing test). If a new cassette is required, writes
   `packages/<pkg>/tests/.recording-manifest.yaml` — declaring the target module, call,
   and arguments to record, and nothing free-form — applies `ai:needs-recording`, and
   stops at draft.
   Otherwise writes commit 2 and opens a draft PR.
3. `ai:needs-recording` → `recorder` in a human-approved GitHub Environment: reads only the
   manifest, records with live keys, runs the deterministic scrubber, secret-scans
   (fail closed), commits the cassette, re-triggers `fixer`.
4. TDD gate + normal CI.
5. `reviewer` attempts to refute the fix. A hole found means comment and re-trigger
   `fixer`. Clean means the PR goes ready-for-review and the maintainer is requested.
6. Maintainer approves and merges, or requests changes.

### Flow B — review feedback to durable lesson

`changes_requested` → `responder` applies the change, preserving test-first discipline for
any new behavior, then classifies the comment as one-off or generalizable. Generalizable
feedback becomes `docs/ai/lessons/<slug>.md` **in the same PR**, so knowledge enters the
substrate only through normal human review. Nothing self-modifies unreviewed. This loop is
what stops the same correction being needed thirty times.

### Flow C — scheduled conformance sweep

Bump pin → regenerate → run harness across all 32 packages → file one pre-diagnosed
`ai:tier1` issue per gap, carrying the exact failing assertion. **Rate-limited to 10 issues
per run, weekly.** First enable will find well over a hundred gaps; unthrottled it buries
the queue.

The sweep is the only actor permitted to modify `.semconv/`, and it does so in a dedicated
PR that changes nothing else. This is deliberately not an exception to the `fixer` path
guard below — it is a different workflow with a different, narrower write scope.

## Guardrails

| Risk | Control |
|---|---|
| Robot-authored 499 backlog | Max 5 in-flight AI PRs, enforced pre-flight |
| Infinite retry burn | 2 attempts per issue, then `ai:needs-human` and stop |
| Blast radius | CI path guard: `fixer` may not touch `.github/**`, `.claude/**`, `.semconv/**`, release config, or version fields |
| Prompt injection | Untrusted text passed as delimited data with explicit preamble; `recorder` never receives it |
| Secret leak via cassette | gitleaks + provider-key patterns, fail closed |
| Runaway spend | Per-run token cap; provider keys used by `recorder` carry their own monthly spend limit set at the provider, not in CI |
| Systemic failure | Repo variable `AI_MAINTAINER_ENABLED=false`, checked at top of every workflow |
| Trust laundering | Dedicated bot identity, `ai-authored` label, **auto-merge never enabled** |

Guardrails are enforced in CI, not by prompt instruction. A prompt asking an agent not to
touch `.github/` is a request; a CI path check is a control.

## Build order

Four specs, each independently valuable.

1. **Contract** — no agents. Vendor registry, weaver codegen, conformance harness,
   warn-only rollout, land the 5 packages that already have compliance tests. Ships real
   value even if work stops here.
2. **Substrate** — root `CLAUDE.md` as router, 32 per-package `CLAUDE.md` (agent-bootstrapped,
   human-reviewed), skills, lessons index.
3. **Fix loop** — TDD gate CI, `fixer` + `recorder`, path guard, scrub gate. Piloted
   manually on 3 hand-picked issues before any trigger is wired.
4. **Autonomy** — `triage`, `reviewer`, `responder`, sweep, concurrency and budget guardrails.

Spec 3's verification story rests entirely on spec 1 existing. Spec 4 earns trust only
because spec 3 has a track record. Building spec 4 first is the standard failure mode for
this class of project.

**Sequencing constraint:** Flow C's sweep stays disabled until spec 3 has merged ~10 PRs
successfully. A sweep filing 100+ correct issues into an unproven fix loop produces 100
bad PRs.

## Explicitly out of scope

- The existing 499-PR backlog. Acknowledged as the larger constraint; deferred by decision.
- Auto-merge, at any tier.
- Agent authority over releases, versioning, or `.github` configuration.
