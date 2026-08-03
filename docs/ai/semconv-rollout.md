# Semconv conformance rollout state

This tracks the rollout of warn-only conformance checks (`test_conformance.py`)
against the OTel GenAI semantic-convention contract
(`packages/opentelemetry-semantic-conventions-ai/opentelemetry/semconv_ai/_contract`),
across OpenLLMetry's instrumentation packages.

## Tags

Every instrumented package that has a `tests/test_conformance.py` is tagged in
its `project.json`:

- `semconv:warn` — conformance is checked on every test run, but violations
  only produce a `ConformanceWarning`; the test never fails. This is the
  starting state for every package in this rollout.
- `semconv:enforcing` — violations in `BLOCKING_KINDS`
  (`missing_required`, `missing_expected`, `undeclared_gen_ai`) fail the test.
  No package has reached this state yet.

List packages by tag:

```bash
npx nx show projects --with-tag semconv:warn
npx nx show projects --with-tag semconv:enforcing
```

## Flipping a package to enforcing

1. Fix every violation the warn-mode test currently reports for that package
   (missing required/expected attributes, undeclared `gen_ai.*` attributes not
   covered by `extensions.py`). This is instrumentation-source work, not test
   work — out of scope for the batch that merely adds the warn-only test.
2. Set `ENFORCING = True` in the package's `tests/test_conformance.py`.
3. Change the package's tag in `project.json` from `semconv:warn` to
   `semconv:enforcing`.
4. Run `uv run pytest tests/test_conformance.py -v` and the package's full
   suite (`uv run pytest tests/ -q`) and confirm both pass.

**Never flip a package that still warns.** If step 4 turns up new violations,
go back to step 1 — do not weaken `EXPECTED` or add names to `extensions.py`
just to make the test pass.

## Rollout status

### Batch 1 (merged)

alephalpha, google-generativeai, cohere, mistralai, ollama, replicate — all
tagged `semconv:warn`.

### Batch 2 (this batch)

All six wired, all tagged `semconv:warn`:

| Package | Contract group | Notes |
|---|---|---|
| writer | `span.gen_ai.inference.client` | Legacy-only attributes (`gen_ai.system`, `gen_ai.usage.completion_tokens`/`prompt_tokens`); no `gen_ai.operation.name`/`gen_ai.provider.name`. Keyed on `gen_ai.system`. |
| langchain | `span.gen_ai.inference.client` | Framework package; a chain invocation emits task/agent/workflow spans alongside the real inference span, all keyed on `gen_ai.operation.name`. |
| llamaindex | `span.gen_ai.inference.client` | Framework package; `StructuredLLM.workflow` span alongside the real `openai.chat` inference span. |
| openai-agents | `openai.inference.client` | Framework package; agent/tool spans alongside the real `openai.response` span. `gen_ai.request.model` is notably absent from the response span. |
| together | `span.gen_ai.inference.client` | No `gen_ai.operation.name`/`gen_ai.provider.name`; keyed on `gen_ai.system`, like ollama/writer. |
| sagemaker | `aws.bedrock.inference.client` (closest available; no dedicated SageMaker group exists) | Minimal instrumentation — the only `gen_ai.*` span attribute at all is `gen_ai.request.model`; keyed on that instead of the default. |

## Out of scope

Vector-store instrumentations emit `db.*` attributes, which the GenAI
contract does not cover at all — there is no meaningful conformance check to
write for them:

chromadb, pinecone, qdrant, weaviate, milvus, marqo, lancedb.

## No coverage

Packages that emit `gen_ai.*` but have no conformance test yet:

- **crewai, litellm, transformers, vertexai** — genuinely have **zero**
  cassettes anywhere under `tests/`. Wiring these up requires recording new
  cassettes first, which needs real API keys — out of scope for a
  cassette-reuse-only batch.
- **bedrock, groq, openai, watsonx** — originally assumed to have zero
  cassettes too, but that turned out to be wrong: each already has cassettes
  under `tests/traces/cassettes/` and/or `tests/metrics/cassettes/` (a
  `tests/traces` + `tests/metrics` split rather than the flat `tests/cassettes`
  layout batches 1–2 used). These four do **not** need new recordings and are
  good candidates for the next batch — verify this if you pick them up, this
  note reflects one point-in-time check.

## Known gaps: `gen_ai.response.finish_reasons` not emitted

This is the #4362 failure mode: the attribute is only `recommended` by the
registry, so nothing short of a package's own `EXPECTED` declaration catches
it going missing. Packages found NOT to emit it as a top-level span attribute:

- From batch 1: **ollama, mistralai, replicate, alephalpha**
- From batch 2: **writer, together, sagemaker**
  - **sagemaker** is a total gap: not emitted on the span *or* in log events
    (`event_emitter.py` hardcodes the log event's `finish_reason` to the
    literal string `"unknown"`).
- **langchain** (batch 2) is provider-dependent: the OpenAI-backed span
  (`ChatOpenAI.chat`) emits it, but the Anthropic-backed span
  (`ChatAnthropic.chat`) does not — langchain only ever nests a raw
  `finish_reason` inside `gen_ai.output.messages` for Anthropic, never
  promoting it to the top-level attribute. `EXPECTED` includes the attribute
  to lock in the OpenAI-path behavior; the Anthropic test's resulting warning
  is intentional, not a mistake.
- **llamaindex** and **openai-agents** (batch 2) both emit it correctly — no
  gap.
