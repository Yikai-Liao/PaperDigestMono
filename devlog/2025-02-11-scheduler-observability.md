# Scheduler Observability Enhancements Plan

## Background
The scheduler service currently registers APScheduler jobs and exposes a minimal FastAPI layer. It lacks structured logging, runtime metrics, and a metrics endpoint. Tests focus on job registration/start/trigger behavior without observability validation. Documentation and TODO items are not updated to reflect new requirements.

## Scope & Impacted Components
- `papersys/scheduler/service.py`: add instrumentation, metrics aggregation, and structured logging/file sink handling.
- `papersys/web/app.py`: expose `/metrics` endpoint returning Prometheus-friendly text.
- Potential new helper structures within scheduler package for metrics state.
- Tests under `tests/scheduler/` and `tests/web/` for metrics correctness.
- Documentation in `devdoc/architecture.md` and TODO tracker `devdoc/todo/TODO-scheduler-observability.md`.

## Risks & Mitigations
1. **Thread-safety of metrics updates**: APScheduler jobs run on background threads. We'll guard shared metrics state with `threading.Lock` and avoid heavy operations.
2. **Log sink duplication**: Configuring Loguru file sinks might duplicate logs if service instantiated multiple times. We'll track sink IDs and ensure we only add once per instance, removing on shutdown.
3. **Prometheus format correctness**: Manual string construction could break scraping. We'll follow the text exposition format (help, type, metric lines) and add tests verifying output.
4. **Test flakiness due to scheduler threads**: We'll avoid running the scheduler and instead call instrumentation wrappers directly in unit tests.
5. **File system permissions for log sink**: We'll default to creating `logs/` under repo root if writeable; fallback gracefully with warning when directory can't be created.

## Implementation Plan
1. **Metrics Model**: Implement `JobMetrics` dataclass and `SchedulerMetricsRegistry` to store counts (total runs, successes, failures), last durations, and timestamps. Provide `record_start`, `record_success`, `record_failure`, `snapshot`, and `export_prometheus` helpers.
2. **Structured Logging**: Wrap job execution in `_execute_job` helper binding `logger` with job context (job_id, run_id). Configure console + rotating file sink (e.g., `logs/scheduler.log`). File sink rotation by size/time using `logger.add` with retention; store sink IDs for cleanup.
3. **Job Registration**: Modify `_register_job` to schedule wrapper function that calls `_execute_job` with actual callable; ensure manual triggers reuse same wrapper.
4. **FastAPI Metrics Endpoint**: Extend `create_app` to depend on scheduler service metrics snapshot and expose `/metrics` returning `PlainTextResponse` with Prometheus exposition.
5. **Testing**: Add tests verifying metrics updates for success/failure/dry-run, log binding context, and HTTP metrics endpoint output. Use `SchedulerMetricsRegistry` directly and `TestClient` for API.
6. **Documentation**: Update architecture doc with observability instructions and TODO file progress summary.

## Validation Plan
- Run `uv run pytest tests/scheduler/test_service.py` and `uv run pytest tests/web/test_app.py` (or overall test suite if reasonable).
- Manually inspect generated metrics snapshot and log sink behavior via tests.

## Contingency
If log sink creation fails due to filesystem restrictions, leave console logging active and emit warning; metrics remain functional. If Prometheus formatting tests fail, adjust exporter to match expected format.
