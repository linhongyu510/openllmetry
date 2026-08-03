"""Shared conformance-check helper for instrumentation package test suites.

Mirrors the existing `_testing.py` pattern: each package imports one function
and supplies its own fixtures, so the check logic lives in exactly one place.

    from opentelemetry.semconv_ai._testing_conformance import check_exported_spans

    def test_conforms(span_exporter):
        check_exported_spans(span_exporter, "anthropic.inference.client",
                             enforcing=False)
"""

from typing import Any, FrozenSet, List

from opentelemetry.semconv_ai._contract.extensions import EXTENSIONS
from opentelemetry.semconv_ai.conformance import Violation, assert_conforms

GEN_AI_OPERATION = "gen_ai.operation.name"


def gen_ai_spans(span_exporter: Any) -> List[Any]:
    """Finished spans that carry GenAI attributes, i.e. those the contract covers."""
    return [
        span
        for span in span_exporter.get_finished_spans()
        if (span.attributes or {}).get(GEN_AI_OPERATION) is not None
    ]


def check_exported_spans(
    span_exporter: Any,
    group_id: str,
    *,
    enforcing: bool,
    expected: FrozenSet[str] = frozenset(),
    extensions: FrozenSet[str] = EXTENSIONS,
    require_spans: bool = True,
) -> List[Violation]:
    """Check every exported GenAI span against one contract group.

    `expected` names the attributes this package promises to emit. Registry
    requirement levels alone are far too weak to rely on — only ~9% of contract
    attributes are `required`, and `gen_ai.response.finish_reasons` is merely
    `recommended` — so a package's own declared promise is what actually catches
    a dropped attribute. Pass it; do not rely on the contract alone.

    Returns the accumulated violations. In enforcing mode the first span with a
    blocking violation raises instead.
    """
    spans = gen_ai_spans(span_exporter)
    if require_spans:
        assert spans, (
            f"expected at least one span carrying {GEN_AI_OPERATION}; "
            "the instrumentation emitted none, so this test would pass vacuously"
        )

    violations: List[Violation] = []
    for span in spans:
        violations.extend(
            assert_conforms(
                span,
                group_id,
                enforcing=enforcing,
                expected=expected,
                extensions=extensions,
            )
        )
    return violations


__all__ = ["check_exported_spans", "gen_ai_spans"]
