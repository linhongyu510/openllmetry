import importlib.util
import sys

from opentelemetry.semconv_ai._contract import Level
from opentelemetry.semconv_ai._contract._generator import build_specs, render


RESOLVED_FIXTURE = {
    "registry_url": "registry",
    "groups": [
        {
            "id": "span.gen_ai.inference.client",
            "type": "span",
            "span_kind": "client",
            "attributes": [
                {"name": "gen_ai.operation.name", "requirement_level": "required",
                 "type": {"members": [{"id": "chat", "value": "chat"},
                                      {"id": "embeddings", "value": "embeddings"}]}},
                {"name": "gen_ai.request.model",
                 "requirement_level": {"conditionally_required": "If available."},
                 "type": "string"},
                {"name": "gen_ai.input.messages", "requirement_level": "opt_in",
                 "type": "any"},
            ],
        },
        {
            "id": "registry.gen_ai",
            "type": "attribute_group",
            "attributes": [{"name": "ignored", "requirement_level": "required"}],
        },
    ],
}


class TestBuildSpecs:
    def test_keeps_only_span_groups(self):
        specs = build_specs(RESOLVED_FIXTURE)
        assert set(specs) == {"span.gen_ai.inference.client"}

    def test_captures_span_kind(self):
        specs = build_specs(RESOLVED_FIXTURE)
        assert specs["span.gen_ai.inference.client"].span_kind == "client"

    def test_normalises_requirement_levels(self):
        spec = build_specs(RESOLVED_FIXTURE)["span.gen_ai.inference.client"]
        assert spec.by_name("gen_ai.operation.name").level is Level.REQUIRED
        assert spec.by_name("gen_ai.request.model").level is Level.CONDITIONALLY_REQUIRED
        assert spec.by_name("gen_ai.request.model").condition == "If available."
        assert spec.by_name("gen_ai.input.messages").level is Level.OPT_IN

    def test_captures_enum_members(self):
        spec = build_specs(RESOLVED_FIXTURE)["span.gen_ai.inference.client"]
        assert spec.by_name("gen_ai.operation.name").enum_members == ("chat", "embeddings")
        assert spec.by_name("gen_ai.request.model").enum_members is None

    def test_attributes_are_sorted_for_stable_diffs(self):
        spec = build_specs(RESOLVED_FIXTURE)["span.gen_ai.inference.client"]
        names = [a.name for a in spec.attributes]
        assert names == sorted(names)

    def test_group_without_requirement_level_defaults_to_recommended(self):
        resolved = {"groups": [{
            "id": "span.x", "type": "span", "span_kind": "client",
            "attributes": [{"name": "a.b", "type": "string"}],
        }]}
        spec = build_specs(resolved)["span.x"]
        assert spec.by_name("a.b").level is Level.RECOMMENDED


class TestRender:
    def test_output_is_importable_and_round_trips(self, tmp_path):
        specs = build_specs(RESOLVED_FIXTURE)
        out = tmp_path / "generated.py"
        out.write_text(render(specs, ref="deadbeef"))

        sys.path.insert(0, str(tmp_path))
        spec_mod = importlib.util.spec_from_file_location("generated", out)
        mod = importlib.util.module_from_spec(spec_mod)
        spec_mod.loader.exec_module(mod)

        assert mod.CONTRACT_REF == "deadbeef"
        assert set(mod.SPANS) == {"span.gen_ai.inference.client"}
        got = mod.SPANS["span.gen_ai.inference.client"]
        assert got.by_name("gen_ai.operation.name").level is Level.REQUIRED
        assert got.by_name("gen_ai.operation.name").enum_members == ("chat", "embeddings")

    def test_is_deterministic(self):
        specs = build_specs(RESOLVED_FIXTURE)
        assert render(specs, ref="x") == render(specs, ref="x")

    def test_carries_do_not_edit_banner(self):
        out = render(build_specs(RESOLVED_FIXTURE), ref="x")
        assert "DO NOT EDIT" in out
