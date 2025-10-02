# TODO: Scheduler Observability Enhancements

## Summary
- Instrument `SchedulerService` to expose structured execution logs and runtime metrics.
- Provide visibility into cron triggers, runtime durations, failure counts, and next-run schedules without altering existing job semantics.

## Deliverables
1. ✅ Structured Loguru logging with clear context (job id, run id, status, latency) routed to both console and rotating file sinks.
2. ✅ A lightweight metrics exporter (FastAPI `/metrics` endpoint) that reports job stats updated after each execution.
3. ✅ Unit tests covering the metrics collector, Prometheus exporter, and dry-run/success/failure scenarios.
4. ✅ Documentation updates explaining how to enable/consume the new observability features.

## Constraints & Notes
- Keep concurrency concerns minimal: rely on in-memory aggregation guarded by simple locks if needed.
- Ensure the solution stays dependency-light; prefer standard library + existing packages (FastAPI, Loguru) over new observability stacks.
- Preserve dry-run behavior: metrics/logging should still emit simulated runs without side effects.

## Completion Notes
- `SchedulerService` 现已在每次作业执行时输出结构化日志（JSON 序列化到 `logs/scheduler.log`），并通过 `SchedulerMetricsRegistry` 跟踪成功/失败/干跑次数、最近一次耗时和下一次调度时间。
- FastAPI 应用新增 `/metrics` 端点，返回 Prometheus 文本格式，可直接被 Prometheus/Grafana 抓取。
- 新增 pytest 覆盖成功、失败、dry-run、Prometheus 输出以及 FastAPI metrics 端点。
- 架构文档同步更新，记录使用方式与指标内容。

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
