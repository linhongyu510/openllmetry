from opentelemetry.semconv_ai._contract.extensions import (
    EXTENSION_RATIONALE,
    EXTENSIONS,
)
from opentelemetry.semconv_ai._contract.generated import SPANS


class TestExtensions:
    def test_every_extension_has_a_rationale(self):
        assert set(EXTENSIONS) == set(EXTENSION_RATIONALE)

    def test_rationales_are_non_empty(self):
        assert all(v.strip() for v in EXTENSION_RATIONALE.values())

    def test_all_extensions_are_in_the_gen_ai_namespace(self):
        # Anything outside gen_ai.* needs no declaration; the harness ignores it.
        assert all(name.startswith("gen_ai.") for name in EXTENSIONS)

    def test_no_extension_shadows_a_contract_attribute(self):
        """An extension that upstream has since defined must be removed, not kept.

        This is the mechanism that stops the extension list becoming permanent:
        when a pin bump adds one of these upstream, this test fails and forces
        us to delete the extension and conform.
        """
        contract_names = {
            attr.name for spec in SPANS.values() for attr in spec.attributes
        }
        shadowed = sorted(set(EXTENSIONS) & contract_names)
        assert not shadowed, (
            f"these are now defined by the contract and must be removed from "
            f"EXTENSIONS: {shadowed}"
        )

    def test_known_openllmetry_extensions_are_declared(self):
        for name in (
            "gen_ai.usage.total_tokens",
            "gen_ai.user",
            "gen_ai.headers",
            "gen_ai.is_streaming",
            "gen_ai.completion",
        ):
            assert name in EXTENSIONS
