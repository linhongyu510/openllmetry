"""Check emitted spans against the OpenTelemetry GenAI semantic-convention contract.

`check_attributes` is pure — it takes a mapping, not an OTel object — so it can
be tested without a tracer. `assert_conforms` is the pytest-facing adapter.

Scope: only the `gen_ai.*` namespace is checked. Attributes in other namespaces
(`traceloop.*`, `llm.*`, `db.*`) are outside this contract and ignored.
"""

import warnings
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Mapping, Optional

from opentelemetry.semconv_ai._contract import SpanSpec
from opentelemetry.semconv_ai._contract.generated import SPANS

GEN_AI_PREFIX = "gen_ai."


class ConformanceWarning(UserWarning):
    """Raised as a warning while a package is still in warn-only mode."""


@dataclass(frozen=True)
class Violation:
    kind: str  # missing_required | undeclared_gen_ai | bad_enum_value
    attribute: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.attribute}: {self.detail}"


def check_attributes(
    attributes: Mapping[str, Any],
    spec: SpanSpec,
    extensions: FrozenSet[str] = frozenset(),
) -> List[Violation]:
    """Return every way `attributes` violates `spec`. Empty list means conforming."""
    violations: List[Violation] = []

    for attr in spec.required():
        if attr.name not in attributes:
            violations.append(
                Violation(
                    "missing_required",
                    attr.name,
                    f"required by {spec.id} but not present on the span",
                )
            )

    for name, value in attributes.items():
        if not name.startswith(GEN_AI_PREFIX):
            continue  # outside the contract's namespace

        declared = spec.by_name(name)
        if declared is None:
            if name in extensions:
                continue
            violations.append(
                Violation(
                    "undeclared_gen_ai",
                    name,
                    "not defined by the contract for this span. Either use a "
                    "contract attribute or declare it in _contract/extensions.py",
                )
            )
            continue

        if declared.enum_members and value not in declared.enum_members:
            violations.append(
                Violation(
                    "bad_enum_value",
                    name,
                    f"value {value!r} not in {list(declared.enum_members)}",
                )
            )

    violations.sort(key=lambda v: (v.attribute, v.kind))
    return violations


def assert_conforms(
    span: Any,
    group_id: str,
    *,
    enforcing: bool,
    extensions: FrozenSet[str] = frozenset(),
    _spans: Optional[Dict[str, SpanSpec]] = None,
) -> List[Violation]:
    """Check one span against a contract group.

    Enforcing mode fails the test on any violation. Warn-only mode emits a
    ConformanceWarning and returns the violations, so a package can adopt the
    harness before it is clean. `_spans` is a seam for testing this module.
    """
    table = SPANS if _spans is None else _spans
    if group_id not in table:
        raise KeyError(f"no such span group in the contract: {group_id!r}")

    violations = check_attributes(
        dict(span.attributes or {}), table[group_id], extensions
    )
    if not violations:
        return []

    report = "\n".join(f"  {v}" for v in violations)
    message = (
        f"span {getattr(span, 'name', '<unnamed>')!r} violates {group_id}:\n{report}"
    )

    if enforcing:
        raise AssertionError(message)

    warnings.warn(message, ConformanceWarning, stacklevel=2)
    return violations


__all__ = [
    "ConformanceWarning",
    "Violation",
    "assert_conforms",
    "check_attributes",
]
