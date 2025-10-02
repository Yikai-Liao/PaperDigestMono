# CLI command test expansion plan (2025-10-07)

## Context
- Current Typer-based CLI has regression coverage limited to `status` dry-run flows.
- Remaining commands (`summarize`, `serve`, `ingest`, `embed`, `config check`, `config explain`) rely on external services and were untested.
- User feedback highlighted the need to finish the CLI testing suite instead of deferring items to TODOs.

## Goals
- Provide automated tests that exercise every CLI command entry point without touching live services.
- Validate critical behaviours: dry-run paths, argument plumbing, error handling, and output formatting.
- Maintain clean code standards by isolating helper utilities for test scaffolding.

## Approach
1. Design reusable fixtures/helpers to synthesise an `AppConfig` object with minimal viable sub-configurations for each command.
2. Use `monkeypatch` to stub service classes (`SummaryPipeline`, `SchedulerService`, `IngestionService`, `EmbeddingService`, `uvicorn.run`, config inspectors) to avoid I/O and observe interactions.
3. Capture log output via Loguru to assert expected status messages while ensuring exit codes propagate correctly through `papersys.cli.main`.
4. Extend existing CLI test suite with targeted cases per command, covering both default and flag-driven behaviours (e.g., backlog processing, JSON formatting).

## Risks & Mitigations
- **Risk:** Tight coupling to implementation details may cause brittle tests if CLI wiring changes.
  - *Mitigation:* Focus assertions on observable behaviour (calls, exit codes, log statements) rather than internal attribute states.
- **Risk:** Complex fixture setup could obscure intent.
  - *Mitigation:* Keep helpers compact and document their purpose; prefer explicit per-test configuration when it improves clarity.

## Test Plan
- `uv run --no-progress pytest tests/cli/test_cli_status.py`
- `uv run --no-progress pytest tests/cli/test_cli_commands.py`
- `uv run --no-progress pytest`

## Rollback Strategy
- Revert the new tests and helper utilities if they introduce instability, retaining the documented plan for future iteration.

## Follow-up Notes
- Future work: integrate CLI command tests into CI smoke suite to prevent regressions.

## Execution Log
- Implemented shared CLI testing utilities for Loguru capture and in-memory AppConfig fabrication.
- Added comprehensive command coverage in `tests/cli/test_cli_commands.py`, including summarize, serve, ingest, embed, and config subcommands.
- Introduced `tests/cli/__init__.py` to enable package-relative imports and reused helpers in existing status tests.
- Test runs:
  - `uv run --no-progress pytest tests/cli/test_cli_commands.py`
  - `uv run --no-progress pytest tests/cli/test_cli_status.py`
  - `uv run --no-progress pytest`
