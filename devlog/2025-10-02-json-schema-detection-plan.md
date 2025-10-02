# JSON schema capability auto-detection plan

## Current situation
- `LLMConfig` includes a `native_json_schema` flag that must be maintained manually in every configuration and test fixture.
- `SummaryGenerator` always relies on free-form prompts and does not leverage LiteLLM's structured output helpers.
- Example TOML, CLI fixtures, and docs still reference the manual flag, increasing the chance of configuration drift.

## Risks
- Removing the manual flag touches configuration, docs, and multiple tests; mistakes can break config parsing.
- Auto-detection depends on LiteLLM helpers; incorrect provider inference could disable JSON mode for supported models.
- JSON schema enforcement changes the request payload and could surface incompatibilities with certain providers.

## Plan
1. Update `LLMConfig` to drop the `native_json_schema` field and adjust configs/tests accordingly.
2. Enhance `_LiteLLMClient` to detect `response_format` and JSON schema support via LiteLLM utilities, applying schema enforcement when available and falling back otherwise.
3. Refresh example configuration, summary-related tests, and documentation to reflect automatic detection.
4. Add targeted tests covering the detection path and ensure existing summary pipeline tests still pass.
5. Run relevant pytest suites to confirm the changes.

## Rollback strategy
- Reintroduce the `native_json_schema` field and revert to the previous prompt-only workflow if detection proves unreliable.
- Restore prior versions of updated files from version control and rerun the summary pipeline tests to verify stability.

## Execution notes
- Removed the manual `native_json_schema` flag from `LLMConfig`, example config, and related tests.
- Added automatic response-format probing in `_LiteLLMClient`, including JSON schema enforcement when supported and JSON-object fallback otherwise.
- Introduced dedicated unit tests covering LiteLLM capability detection scenarios.

## Test results
- `uv run --no-progress pytest tests/config/test_llm_config.py tests/summary/test_generator_detection.py tests/summary/test_summary_pipeline.py tests/summary/test_cli.py tests/summary/test_cli_summarize.py tests/cli/test_cli_config.py`
