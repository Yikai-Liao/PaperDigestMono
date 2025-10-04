# 2025-10-03 W6: Scheduler & API 编排实施记录

Status: In Progress  
Last-updated: 2025-10-04  
Author: Roo (AI Assistant)

## 实施背景
根据 `devlog/2025-10-03-migration-plan.md` 中的 W6 计划，本周目标是实现全链路调度与 Web 控制。主要任务包括：
- APScheduler 多作业：扩展现有 SchedulerService 支持 ingestion, embedding, recommend, summary, publishing, feedback 等作业。
- /jobs/run 端点：FastAPI 端点，手动触发作业。
- Prometheus 指标：扩展现有 metrics 导出，支持 /metrics 端点。
- 集成测试：轻量全链路测试。
- 真实流水线脚本：run_real_full_pipeline.py。

依赖：W1-W5 模块；`devdoc/architecture.md` 中的调度/API 设计。

风险：作业依赖顺序（e.g., ingestion 前置 embedding）；并发冲突；Prometheus 格式一致性；测试数据规模。

## 实施步骤

### 步骤 1: 分析现有代码
- `papersys/scheduler/service.py`：已有 BackgroundScheduler, JobMetrics, Prometheus 导出 (export_prometheus), trigger_job 方法。支持 recommend, summary, backup 作业。已读取并理解。
- `papersys/web/app.py`：现有 FastAPI app, /health, /jobs (list), /metrics (placeholder?)。需扩展 /jobs/run/{job_id}。
- `papersys/cli.py`：现有 serve 命令启动 scheduler + web。需集成新作业。
- 测试：`tests/integration/test_full_pipeline.py` 存在，但需扩展轻链路 (ingestion → embedding → recommend → summary → publishing → feedback)。

### 步骤 2: 扩展 SchedulerService
- 添加新作业注册：
  - ingestion_job: 触发 papersys.ingestion.service.IngestionService.run()
  - embedding_job: 触发 papersys.embedding.service.EmbeddingService.autopatch()
  - publishing_job: 触发 scripts.build_site.py (via subprocess or direct call)
  - feedback_job: 触发 scripts.fetch_feedback.py (giscus)
- 更新 setup_jobs(): 条件注册所有作业基于 config.scheduler.*_job.enabled。
- 增强 trigger_job(): 支持 dry_run, 返回 job status。
- 扩展 metrics: 添加作业依赖标签 (e.g., depends_on="ingestion")。

### 步骤 3: 更新 Web API (papersys/web/app.py)
- 添加 /jobs/run/{job_id} POST 端点：使用 SchedulerService.trigger_job(job_id), 返回 {"status": "triggered", "next_run": ...}。
- 增强 /jobs GET: 返回 list_jobs() + metrics snapshot。
- /metrics GET: 返回 scheduler.export_metrics()。
- 添加依赖注入：FastAPI app 注入 SchedulerService 实例。
- 安全：添加 API key 或 basic auth (config.web.api_key)。

### 步骤 4: 更新 CLI (papersys/cli.py)
- serve 命令：启动 scheduler.start() + uvicorn web app。
- 添加 trigger 命令：`python -m papersys cli trigger {job_id}`，调用 scheduler.trigger_job()。
- 集成 config: 加载 AppConfig, 传递给 SchedulerService。

### 步骤 5: 配置更新
- `papersys/config/scheduler.py`：扩展 SchedulerJobConfig 支持新作业 (ingestion_job, embedding_job, publishing_job, feedback_job)。
- `config/example.toml`：添加 [scheduler.ingestion_job], [scheduler.embedding_job] 等节，cron 示例 (e.g., "0 0 * * *" for daily)。

### 步骤 6: 测试实现
- `tests/integration/test_full_pipeline.py`：扩展为轻链路测试，使用小数据集 (10 papers), mock API calls, 验证顺序执行 (ingestion → ... → feedback)。
- `tests/scheduler/test_service.py`：新增测试多作业注册, trigger_job, metrics 导出。
- 运行：`uv run --no-progress pytest tests/integration/ -v`，确保 <2min 执行。

### 步骤 7: 真实流水线脚本
- `scripts/run_real_full_pipeline.py`：顺序调用所有服务 (ingestion.run(), embedding.autopatch(), etc.), 使用真实数据, 日志输出, 错误处理。
- 支持 --dry-run, --year 参数。

### 步骤 8: 文档更新
- `devdoc/architecture.md`：更新调度/API 节，描述多作业依赖, 端点 spec。
- 本文件：记录执行细节。

## 遇到的问题与解决方案
- 问题 1: 作业依赖 - 解决方案：使用 APScheduler jobstores 或 custom trigger, 确保 ingestion 完成后触发 embedding (config.scheduler.job_dependencies)。
- 问题 2: Web 集成 - 解决方案：使用 lifespan events in FastAPI to start/stop scheduler。
- 问题 3: Prometheus 一致性 - 解决方案：复用现有 export_prometheus, 添加 pipeline 特定 metrics (e.g., papers_processed)。
- 问题 4: 测试规模 - 解决方案：使用 pytest fixtures for mock data, limit to 5-10 papers。

## Git 版本管理
- Branch: feature/w6-scheduler-api
- Commits:
  - "feat: extend scheduler service with new jobs (ingestion, embedding, publishing, feedback)"
  - "feat: add /jobs/run endpoint to web app"
  - "feat: enhance /metrics with scheduler prometheus export"
  - "test: add integration test for full pipeline"
  - "script: add run_real_full_pipeline.py"
  - "config: extend scheduler config for new jobs"
  - "docs: update architecture.md for scheduler/API"
- 每个 commit 前运行 pytest，确保无回归。

## 下一步计划
- 完成 W6 代码实现与测试。
- 验证：启动 serve, POST /jobs/run/ingestion, 检查 logs/metrics。
- 推进 W7 迁移工具集成 (e.g., migration as scheduler job)。
- 若阻塞：确认 config.toml 示例 for new jobs。