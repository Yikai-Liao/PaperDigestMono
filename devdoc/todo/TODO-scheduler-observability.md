# TODO: Scheduler Observability Enhancements

## Summary
- Instrument `SchedulerService` to expose structured execution logs and runtime metrics.
- Provide visibility into cron triggers, runtime durations, failure counts, and next-run schedules without altering existing job semantics.

## Deliverables
1. Structured Loguru logging with clear context (job id, run id, status, latency) routed to both console and rotating file sinks.
2. A lightweight metrics exporter (e.g., FastAPI endpoint `/metrics` or Prometheus-compatible generator) that reports job stats updated after each execution.
3. Unit tests covering the metrics collector and log formatting helpers.
4. Documentation updates explaining how to enable/consume the new observability features.

## Constraints & Notes
- Keep concurrency concerns minimal: rely on in-memory aggregation guarded by simple locks if needed.
- Ensure the solution stays dependency-light; prefer standard library + existing packages (FastAPI, Loguru) over new observability stacks.
- Preserve dry-run behavior: metrics/logging should still emit simulated runs without side effects.

## Suggested Branch Name
`feat/scheduler-observability`

## Prompt
```
请按照 #file:rules.md 要求执行以下任务：
1. 在 `papersys/scheduler/service.py` 内为作业执行添加结构化日志与指标收集，支持 Prometheus 友好的数据暴露。
2. 在 FastAPI 层增加 `/metrics` 或等效端点返回最新作业统计。
3. 为核心逻辑补充 pytest 单测，覆盖正常执行、dry-run、失败计数等场景。
4. 更新相关文档，说明如何启用与使用该功能。
```
