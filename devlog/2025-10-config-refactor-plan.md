# 配置拆分与管线落地开发计划（2025-10-02）

## 1. 背景与目标

在 `devdoc/architecture.md` 与 `devlog/2025-10-architecture-review.md` 中已经完成了新架构蓝图与初步实现（`papersys` 包骨架、基础配置加载、CLI 入口）。接下来需要将历史仓库（`reference/PaperDigest`, `reference/PaperDigestAction`）中的推荐与摘要管线逐步迁移到单例化架构中，同时扩展配置体系，使业务逻辑可以通过强类型的 Pydantic 模型直接访问配置字段。

本阶段目标：

1. **配置分层落地**：把推荐、摘要、LLM 等模块的配置拆分为独立的模型，保持类型安全与清晰的模块边界。
2. **核心服务封装**：将推荐与摘要管线重构为可复用模块，支持后续调度与控制台调用。
3. **调度与控制台基建**：建立本地调度器与轻量 Web/API 控制台，为远程触发与状态查看打基础。
4. **数据迁移 & 集成验证**：设计数据目录迁移脚本，并完成最小化的端到端集成测试流程。

## 2. 任务拆分与验收标准

| ID | TODO | 交付物 | 验收方式 | 状态 |
| --- | --- | --- | --- | --- |
| T5 | 迁移推荐/摘要/LLM 配置模型，扩展示例配置 | `papersys/config/recommend.py`、`summary.py`、`llm.py` 等；更新 `config/example.toml`；扩充测试 | `uv run --no-progress pytest tests/config/test_load_config.py` 通过；文档同步说明配置层级 | ✅ |
| T6 | 封装推荐管线模块（数据加载、训练、预测） | `papersys/recommend/*.py`；最小数据 fixture & 单测 | `uv run --no-progress pytest tests/recommend/test_trainer.py` 等通过；CLI 能输出推荐模块状态 | ✅ |
| T7 | 构建摘要流水线骨架（PDF 获取、LLM 调用、渲染接口） | `papersys/summary/*.py`；异步/重试策略；日志接口 | `uv run --no-progress pytest tests/summary/test_pipeline.py`；CLI `summarize --dry-run` 输出模块状态 | ✅ |
| T8 | 实现调度服务与本地控制台（FastAPI + APScheduler） | `papersys/scheduler/service.py`、`papersys/web/app.py`；CLI 新增 `serve` 子命令 | `uv run --no-progress python -m papersys.cli serve --dry-run` 成功输出监听信息；新增 API 健康检查测试 | ✅ |
| T9 | 数据目录整理与迁移脚本 | `scripts/migrate_data.py`；支持 `--dry-run`；更新文档 | 在临时目录执行脚本输出目标结构；脚本测试通过 | |
| T10 | 集成测试：凑齐"抓取→嵌入→推荐→摘要→输出" 验证链路 | `tests/system/test_pipeline.py`；CLI `pipeline --dry-run` | `uv run --no-progress pytest tests/system/test_pipeline.py` 通过；命令正确串联模块 | |


## 3. 风险与对策

| 风险 | 描述 | 缓解策略 |
| ---- | ---- | ---- |
| 配置迁移不一致 | TOML 示例与模型字段不匹配，导致运行失败 | 单元测试覆盖所有配置模型；为示例文件写额外断言 |
| 历史脚本依赖众多 | 引入过多第三方库、增加复杂度 | 优先复用现有依赖；必要时拆分为可选模块，控制依赖范围 |
| 调度与控制台耦合过紧 | 首版实现难以扩展远程触发 | 控制台先实现 `--dry-run`、健康检查；将后续功能列入 TODO，不一次性做完 |
| 集成测试耗时长 | 端到端流程涉及外部服务 | 构造最小离线样本或 mock；确保 CI 可快速执行 |

## 4. 校验流程

1. 每个任务完成后，更新 `devlog/2025-10-architecture-review.md` 与本文件的状态（如有新增风险或变更计划需同步）；记录可回滚的 git 提交哈希。
2. 统一使用 `uv run --no-progress` 执行所有命令，保证环境一致性。
3. 在 `devdoc/architecture.md` 中补充落地后的结构变化或新增的模块说明。
4. 每个阶段结束前执行 `git status`、`git add`、`git commit`、`git push`，并在日志中记录提交 ID。

## 5. 当前仓库基线

- 初始提交：`154a52f`（配置拆分开发计划）
- T5 完成提交：`2fd9da3`（配置模型迁移完成）
- 本计划生效时间：2025-10-02

## 6. T5 执行记录（2025-10-02）

### 交付物
- 新增配置模型：
  - `papersys/config/llm.py`：LLMConfig 包含 alias/name/base_url/api_key/temperature/top_p/num_workers/reasoning_effort/native_json_schema 字段。
  - `papersys/config/recommend.py`：LogisticRegressionConfig、TrainerConfig、DataConfig、PredictConfig、RecommendPipelineConfig，覆盖推荐管线全配置节点。
  - `papersys/config/summary.py`：PdfConfig、SummaryPipelineConfig，管理摘要流水线参数。
- 更新顶层配置：
  - `papersys/config/app.py`：AppConfig 添加 recommend_pipeline、summary_pipeline、llms 字段，保留 data_root/scheduler_enabled/embedding_models/logging_level 历史兼容。
  - `papersys/config/__init__.py`：导出所有新模型。
- 扩展示例配置：`config/example.toml` 包含 recommend_pipeline/summary_pipeline/llms 完整示例。
- 单元测试扩充：
  - `tests/config/test_llm_config.py`：测试单 LLM 配置加载、reasoning_effort 可选字段、extra 字段拒绝。
  - `tests/config/test_recommend_config.py`：测试最小与完整推荐配置、默认值填充、嵌套字段校验。
  - `tests/config/test_summary_config.py`：测试摘要配置加载与严格性。
  - `tests/config/test_load_config.py`：新增对 AppConfig 完整读取的校验（包含 pipeline 与 llms）。
- CLI 增强：`papersys/cli.py` 的 `_report_system_status` 现输出推荐管线、摘要管线、LLM 配置详细状态。
- 文档更新：`devdoc/architecture.md` 新增"配置模块层级（已落地）"段落，同步配置字段与测试覆盖说明。

### 验收结果
- `uv run --no-progress pytest tests/config/ -v`：12 个测试全部通过（包含 T5 新增 9 个测试）。
- `uv run --no-progress python -m papersys.cli --dry-run`：成功输出 General/Recommendation Pipeline/Summary Pipeline/LLM Configurations 四大板块详细状态。
- 文档同步完成：`devdoc/architecture.md` 已补充配置层级说明。

### Git 基线
- T5 提交：`2fd9da3`
- 已推送到远程：✅

---

> 后续将从 T5 开始执行，若在推进过程中发现新的风险或依赖调整，会同步更新此计划和架构文档。

## 7. T6 执行记录（2025-10-02）

### 交付物
- 新增推荐流水线核心模块：`papersys/recommend/data.py`、`trainer.py`、`predictor.py`、`pipeline.py`，并在 `papersys/recommend/__init__.py` 暴露统一入口。
- 扩展 CLI：`papersys/cli.py` 的状态输出增加推荐数据源检查，能够提示缺失目录信息。
- 更新依赖：`pyproject.toml` 与 `uv.lock` 新增 `polars`、`numpy`、`scikit-learn` 等推荐模块所需依赖。
- 集成测试：`tests/recommend/test_pipeline.py` 构建完整的加载→训练→预测流程，覆盖类别过滤、负样本采样、流水线打通。

### 验收结果
- `uv run --no-progress pytest tests/recommend/ -v`：3 项推荐集成测试全部通过。
- 推荐数据加载器针对缺失列、缺失目录的处理逻辑已在测试中验证。

### Git 基线
- 相关代码仍在工作区，待与 T7 任务合并后统一提交。

## 8. T7 执行记录（2025-10-02）

### 交付物
- 新建摘要流水线模块：`papersys/summary/models.py`、`pdf.py`、`generator.py`、`renderer.py`、`pipeline.py`，并在 `__init__.py` 中导出主要实体。
- 引入 Markdown 渲染模板与占位 PDF 生成逻辑，使流水线可在本地离线运行。
- CLI 扩展：`papersys/cli.py` 新增 `summarize --dry-run` 子命令，复用配置加载并检查数据目录。
- 依赖更新：添加 `jinja2` 以支持 Markdown 渲染模板。
- 测试覆盖：新增 `tests/summary/test_summary_pipeline.py`（流水线）与 `tests/summary/test_cli.py`（CLI 子命令），验证目录创建、LLM 配置校验及全流程执行。

### 验收结果
- `uv run --no-progress pytest tests/recommend/ tests/summary/ -v`：7 项推荐与摘要测试全部通过。
- `uv run --no-progress pytest tests/summary/test_cli.py -v` 单独执行通过，CLI dry-run 会创建目标目录。
- 手动 `uv run --no-progress python -m papersys.cli summarize --dry-run`（在测试中确认）可输出摘要管线检查日志。

### Git 基线
- 当前改动尚未提交，与 T6 相关改动合并后统一处理。

## 9. T8 开发规划（2025-10-02）

### 目标
- 引入调度服务与本地 Web 控制台，为推荐/摘要管线提供定时运行能力与状态可视化。
- 使用 APScheduler 管理周期作业，FastAPI 提供健康检查与手动触发接口。

### 拆解任务
1. **配置层更新**：新增 `SchedulerConfig` 与作业粒度配置类，扩展 `AppConfig`、示例 TOML 及相关单测。
2. **调度服务实现**：在 `papersys/scheduler/service.py` 中封装 APScheduler，支持注册推荐/摘要作业、手动触发、优雅关闭。
3. **Web 控制台骨架**：构建 `papersys/web/app.py`（FastAPI），提供 `/health`、`/jobs`、`/scheduler/run/{job_id}` 等接口，并在 CLI `serve` 子命令中串联。
4. **测试与验证**：补充调度与 Web 层单测，增强 CLI 测试覆盖 `serve --dry-run`，全量运行 `uv run --no-progress pytest tests/{config,recommend,summary,scheduler,web}/`。

### 风险与缓解
- **依赖增多**：FastAPI/APScheduler 引入体积较大，需确认无冗余；通过 `uv add --no-progress` 统一管理。
- **调度线程副作用**：单测中采用暂停启动与显式 shutdown，确保不会遗留后台线程。
- **作业执行失败**：dry-run 默认仅校验管线，实际运行另行配置；为非 dry-run 模式补充日志与错误传播。

### 交付准则
- CLI `serve --dry-run` 能列出所有已配置作业并成功退出。
- Web 控制台单测验证健康检查与作业触发均返回成功响应。
- devlog/architecture 文档同步调度架构要点（T8 完成后更新执行记录）。

## 10. T8 阶段进展记录（2025-10-02 晚间）

### 今日交付
- **配置层扩展**：新增 `papersys/config/scheduler.py`（`SchedulerConfig`/`SchedulerJobConfig`）并接入 `AppConfig`；同步导出入口。
- **示例配置更新**：`config/example.toml` 填充调度总线、推荐/摘要作业默认参数，帮助后续 CLI/服务读取。
- **测试覆盖**：`tests/config/test_load_config.py` 新增调度字段断言；`uv run pytest tests/config/test_load_config.py` 与 `uv run pytest tests` 均通过。
- **pytest 配置收敛**：在 `pyproject.toml` 配置 `addopts = "--ignore=reference"`，默认排除参考目录，避免误触无关测试。
- **依赖同步**：为主仓添加调度与参考依赖（`apscheduler`、`fastapi`、`uvicorn`、`toml`、`filelock`、`huggingface-hub[hf-xet]`、`latex2json`、`openai`、`timeout-decorator` 等），确保后续模块和必要示例可运行。

### 遇到的问题 & 处理
- 全量 `pytest` 会触发 `reference/` 目录缺失配置导致失败 → 通过 pytest 默认忽略机制解决。
- `reference/PaperDigestAction` 中老代码依赖第三方 `toml` 包 → 按原实现保留 `toml` 并安装依赖，避免改动历史逻辑。

### 明日待办
- 实现 `SchedulerService`（注册推荐/摘要作业、dry-run 验证、优雅关闭）。
- 构建 FastAPI 控制台骨架与 `/health`、`/jobs`、手动触发接口。
- CLI 新增 `serve` 子命令并编写单测，覆盖 dry-run 行为。
- 补充调度/控制台文档片段至 `devdoc/architecture.md`。

---

## 11. T8 执行记录（2025-10-02 夜间）

### 交付物
- **SchedulerService (`papersys/scheduler/service.py`)**：基于 `APScheduler` 的调度服务，支持按 `cron` 表达式注册作业，遵循配置时区；提供作业清单、dry-run 校验以及手动触发接口。
- **FastAPI Web 应用 (`papersys/web/app.py`)**：实现 `/health`、`/jobs`、`/scheduler/run/{job_id}` 三个端点，并改用 `SchedulerService` 的 helper 方法保证行为一致。
- **CLI `serve` 子命令 (`papersys/cli.py`)**：串联配置加载、调度器初始化与 FastAPI 服务启动，`--dry-run` 下只校验作业不启动服务。
- **配置与示例**：
  - `papersys/config/scheduler.py` 现支持 `enabled`、`timezone`、`cron` 字段（兼容旧别名），并在模型层固定默认值。
  - `config/example.toml` 更新为示例化时区及推荐/摘要作业的 cron 表达式。
- **测试补齐**：
  - `tests/scheduler/test_service.py` 新增对 `trigger_job()` 的覆盖，验证手动触发会追加一次性作业。
  - `tests/web/test_app.py` 与 `tests/cli/test_cli_serve.py` 调整断言，匹配新的响应与日志。

### 验收结果
- `uv run pytest`（默认忽略 reference）通过 28 项测试，覆盖 config/scheduler/web/cli 模块。
- `uv run python -m papersys.cli --config config/example.toml serve --dry-run`：输出调度时区、作业注册信息，并在 dry-run 模式下安全退出。
- FastAPI TestClient 覆盖 `/jobs` 与手动触发 API，响应体含最新字段。

### 遇到的问题 & 处理
- **cron 解析误差**：分词解析导致分钟/小时错位 → 改用 `CronTrigger.from_crontab`，并显式记录时区。
- **手动触发无效果**：`job.modify(next_run_time=None)` 对未运行调度器无效 → 新增 `trigger_job()`，通过一次性任务实现立即执行。
- **配置字段漂移**：示例与模型字段不一致 → 统一改为 `cron` + `timezone`，并在测试中断言。
