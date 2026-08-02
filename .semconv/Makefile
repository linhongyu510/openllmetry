# Vendors the upstream GenAI semantic conventions and resolves them to JSON.
# All Docker invocation lives here. Nothing else in the repo runs weaver.
include versions.env

SELF_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
BUILD    := .build
REGISTRY := registry
UPSTREAM := $(BUILD)/sc-upstream-$(SEMCONV_VERSION)
FILTERED := $(BUILD)/sc-upstream-filtered

WEAVER := docker run --rm -u $(shell id -u):$(shell id -g) \
	-v "$(SELF_DIR):/w" -w /w -e HOME=/tmp otel/weaver:$(WEAVER_VERSION)

.PHONY: vendor resolve generate check clean

## Fetch the pinned registry into registry/ .
vendor:
	rm -rf $(REGISTRY) $(BUILD)
	mkdir -p $(BUILD)
	git clone -q $(SEMCONV_GENAI_REPO) $(BUILD)/genai
	cd $(BUILD)/genai && git checkout -q $(SEMCONV_GENAI_REF)
	cp -r $(BUILD)/genai/model $(REGISTRY)
	rm -rf $(BUILD)/genai
	@echo "vendored $(SEMCONV_GENAI_REF) -> $(REGISTRY)/"

## Build the filtered upstream dependency the registry manifest points at.
$(FILTERED):
	mkdir -p $(BUILD)
	git clone -q --depth 1 --branch $(SEMCONV_VERSION) \
		https://github.com/open-telemetry/semantic-conventions.git $(UPSTREAM)
	mkdir -p $(dir $(FILTERED))
	cp -r $(UPSTREAM)/model $(FILTERED)
	cd $(FILTERED) && rm -rf gen-ai mcp openai

## Resolve the registry to a single JSON document.
resolve: $(FILTERED)
	$(WEAVER) registry resolve -r $(REGISTRY) --format json -o /w/$(BUILD)/resolved.json
	@echo "resolved -> $(BUILD)/resolved.json"

## Regenerate the committed contract module.
generate: resolve
	cd ../packages/opentelemetry-semantic-conventions-ai && uv run python -m \
		opentelemetry.semconv_ai._contract._generator \
		--resolved ../../.semconv/$(BUILD)/resolved.json \
		--out opentelemetry/semconv_ai/_contract/generated.py

## Fail if the committed artifact is stale.
check: generate
	cd .. && git diff --exit-code -- \
		packages/opentelemetry-semantic-conventions-ai/opentelemetry/semconv_ai/_contract/generated.py

clean:
	rm -rf $(BUILD) $(REGISTRY)/.build
