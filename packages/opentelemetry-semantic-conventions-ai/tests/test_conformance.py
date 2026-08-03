import pytest

from opentelemetry.semconv_ai._contract import AttributeSpec, Level, SpanSpec
from opentelemetry.semconv_ai.conformance import (
    ConformanceWarning,
    assert_conforms,
    check_attributes,
)

SPEC = SpanSpec(
    id="span.gen_ai.inference.client",
    span_kind="client",
    attributes=(
        AttributeSpec("gen_ai.operation.name", Level.REQUIRED, None, ("chat", "embeddings")),
        AttributeSpec("gen_ai.request.model", Level.CONDITIONALLY_REQUIRED, "If available.", None),
        AttributeSpec("gen_ai.usage.input_tokens", Level.RECOMMENDED, None, None),
        AttributeSpec("gen_ai.input.messages", Level.OPT_IN, None, None),
    ),
)


class TestCheckAttributes:
    def test_conforming_span_yields_no_violations(self):
        attrs = {"gen_ai.operation.name": "chat", "gen_ai.request.model": "claude-opus-4"}
        assert check_attributes(attrs, SPEC) == []

    def test_missing_required_is_a_violation(self):
        violations = check_attributes({"gen_ai.request.model": "x"}, SPEC)
        assert [v.kind for v in violations] == ["missing_required"]
        assert violations[0].attribute == "gen_ai.operation.name"

    def test_missing_conditionally_required_is_not_a_violation(self):
        # The condition is prose the harness cannot evaluate, so absence is tolerated.
        violations = check_attributes({"gen_ai.operation.name": "chat"}, SPEC)
        assert violations == []

    def test_missing_recommended_and_opt_in_are_not_violations(self):
        violations = check_attributes({"gen_ai.operation.name": "chat"}, SPEC)
        assert violations == []

    def test_undeclared_gen_ai_attribute_is_a_violation(self):
        attrs = {"gen_ai.operation.name": "chat", "gen_ai.is_streaming": True}
        violations = check_attributes(attrs, SPEC)
        assert [v.kind for v in violations] == ["undeclared_gen_ai"]
        assert violations[0].attribute == "gen_ai.is_streaming"

    def test_declared_extension_is_tolerated(self):
        attrs = {"gen_ai.operation.name": "chat", "gen_ai.is_streaming": True}
        violations = check_attributes(attrs, SPEC, extensions=frozenset({"gen_ai.is_streaming"}))
        assert violations == []

    def test_non_gen_ai_namespace_is_ignored(self):
        # traceloop.*, llm.*, db.* are outside the contract's scope entirely.
        attrs = {"gen_ai.operation.name": "chat", "traceloop.workflow.name": "w", "llm.vendor": "x"}
        assert check_attributes(attrs, SPEC) == []

    def test_bad_enum_value_is_a_violation(self):
        attrs = {"gen_ai.operation.name": "definitely-not-a-real-operation"}
        violations = check_attributes(attrs, SPEC)
        assert [v.kind for v in violations] == ["bad_enum_value"]

    def test_violations_are_sorted_by_attribute_for_stable_output(self):
        attrs = {"gen_ai.zzz": 1, "gen_ai.aaa": 1}
        violations = check_attributes(attrs, SPEC)
        names = [v.attribute for v in violations]
        assert names == sorted(names)


class FakeSpan:
    def __init__(self, attributes):
        self.attributes = attributes
        self.name = "fake"


class TestAssertConforms:
    def test_enforcing_mode_raises_on_violation(self):
        with pytest.raises(AssertionError, match="missing_required"):
            assert_conforms(
                FakeSpan({"gen_ai.request.model": "x"}),
                "span.gen_ai.inference.client",
                enforcing=True,
                _spans={"span.gen_ai.inference.client": SPEC},
            )

    def test_warn_mode_warns_and_returns_violations(self):
        with pytest.warns(ConformanceWarning, match="gen_ai.operation.name"):
            violations = assert_conforms(
                FakeSpan({"gen_ai.request.model": "x"}),
                "span.gen_ai.inference.client",
                enforcing=False,
                _spans={"span.gen_ai.inference.client": SPEC},
            )
        assert [v.kind for v in violations] == ["missing_required"]

    def test_warn_mode_is_silent_when_conforming(self, recwarn):
        violations = assert_conforms(
            FakeSpan({"gen_ai.operation.name": "chat"}),
            "span.gen_ai.inference.client",
            enforcing=False,
            _spans={"span.gen_ai.inference.client": SPEC},
        )
        assert violations == []
        assert not [w for w in recwarn if issubclass(w.category, ConformanceWarning)]

    def test_unknown_group_id_raises_regardless_of_mode(self):
        with pytest.raises(KeyError, match="no such span group"):
            assert_conforms(FakeSpan({}), "span.nope", enforcing=False, _spans={})
