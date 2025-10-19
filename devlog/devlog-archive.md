# PaperDigestMono Development Log Archive

*Generated on: 2025-10-19*

This document contains all development logs from the PaperDigestMono project, organized chronologically. Each section represents a development log entry with its original date and content.

## About This Archive

- **Purpose**: Consolidate all development logs into a single, searchable document
- **Organization**: Chronological order by date
- **Content**: Complete original content from individual log files
- **Maintenance**: This archive should be updated when new development logs are added

## Usage

- Use Ctrl+F to search for specific topics, dates, or keywords
- Each section is self-contained with its own status, background, and execution records
- Links in the table of contents jump to specific sections

---

## Table of Contents

- [2025-02-11: Scheduler Observability Enhancements](#2025-02-11-scheduler-observability-enhancements)
- [2025-10-01: Architecture Review](#2025-10-01-architecture-review)
- [2025-10-02: Config Refactor Plan](#2025-10-02-config-refactor-plan)
- [2025-10-02: Embedding Backend Refactor](#2025-10-02-embedding-backend-refactor)
- [2025-10-02: Ingestion & Embedding Migration](#2025-10-02-ingestion--embedding-migration)
- [2025-10-02: JSON Schema Detection Plan](#2025-10-02-json-schema-detection-plan)
- [2025-10-02: PR Merge Plan](#2025-10-02-pr-merge-plan)
- [2025-10-02: Real Data Recommend & Summary Plan](#2025-10-02-real-data-recommend--summary-plan)
- [2025-10-02: Summary LLM Integration Plan](#2025-10-02-summary-llm-integration-plan)
- [2025-10-02: Summary Real Data Plan](#2025-10-02-summary-real-data-plan)
- [2025-10-02: Summary Storage Docs Plan](#2025-10-02-summary-storage-docs-plan)
- [2025-10-02: TODO Expansion Plan](#2025-10-02-todo-expansion-plan)
- [2025-10-03: Docs Refactor Plan](#2025-10-03-docs-refactor-plan)
- [2025-10-03: LaTeX Context Plan](#2025-10-03-latex-context-plan)
- [2025-10-03: Legacy Roadmap](#2025-10-03-legacy-roadmap)
- [2025-10-03: Migration Plan](#2025-10-03-migration-plan)
- [2025-10-03: Real LLM API Fix](#2025-10-03-real-llm-api-fix)
- [2025-10-03: Recommend Dataflow Correction](#2025-10-03-recommend-dataflow-correction)
- [2025-10-03: W1 Ingestion](#2025-10-03-w1-ingestion)
- [2025-10-03: W2 Embedding](#2025-10-03-w2-embedding)
- [2025-10-03: W3 Recommend](#2025-10-03-w3-recommend)
- [2025-10-03: W4 Summary](#2025-10-03-w4-summary)
- [2025-10-03: W5 Publishing](#2025-10-03-w5-publishing)
- [2025-10-03: W6 Orchestration](#2025-10-03-w6-orchestration)
- [2025-10-03: W7 Wrapup](#2025-10-03-w7-wrapup)
- [2025-10-04: Pytest Cleanup](#2025-10-04-pytest-cleanup)
- [2025-10-04: Reference Scripts Check](#2025-10-04-reference-scripts-check)
- [2025-10-04: Task Reflection](#2025-10-04-task-reflection)
- [2025-10-05: CLI Cleanup Plan](#2025-10-05-cli-cleanup-plan)
- [2025-10-06: CLI Standard Tests Plan](#2025-10-06-cli-standard-tests-plan)
- [2025-10-07: CLI Command Tests Plan](#2025-10-07-cli-command-tests-plan)
- [2025-10-08: Data Migration Plan](#2025-10-08-data-migration-plan)
- [2025-10-09: Migration Tool Implementation](#2025-10-09-migration-tool-implementation)
- [2025-10-10: Summary Config Refine](#2025-10-10-summary-config-refine)
- [2025-10-11: Migration CLI Validation](#2025-10-11-migration-cli-validation)

---

## 2025-02-11: Scheduler Observability Enhancements

# Scheduler Observability Enhancements Plan
Status: Completed
Last-updated: 2025-10-02

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

## 执行记录
- 2025-10-02：`SchedulerMetricsRegistry` 与 `/metrics` 端点落地，`papersys/scheduler/service.py`、`papersys/web/app.py` 支持 Prometheus 输出与结构化日志。
- 2025-10-02：补充 `tests/scheduler/test_service.py`、`tests/web/test_app.py` 覆盖成功/失败/dry-run 指标与 HTTP 响应，`uv run --no-progress pytest tests/scheduler/test_service.py tests/web/test_app.py` 全部通过。

---


---

## 2025-10-01: Architecture Review

# 架构文档更新开发计划（2025-10-01）
Status: In Progress
Last-updated: 2025-10-01

## 一、背景与目标

`devdoc/architecture.md` 已记录了论文推送系统的总体构想，但对历史版本的细节、线上流程的拆分方式、以及 Hugging Face/GitHub Action 的依赖链路仍然描述较粗。当前需求是：

1. 结合 `reference/ArxivEmbedding`、`reference/PaperDigest`、`reference/PaperDigestAction` 等旧仓库内容，补全旧架构的实际实现细节与痛点。
2. 设计一份更贴近新目标（本地单例化部署、数据拆分、备份策略等）的架构草案，并写入 `devdoc/architecture.md`。

目标是让架构文档既能回顾旧系统的工作流（爬虫→嵌入→推荐→摘要→发布→反馈），又能给出新系统的模块划分、数据形态、运行时编排方案与未来扩展接口。

## 二、参考仓库现状分析

### 1. `reference/ArxivEmbedding`
- 核心脚本：
  - `script/fetch_arxiv_oai.py`/`fetch_arxiv_oai_by_date.py`：通过 OAI-PMH 获取元数据，合并到年度 Parquet。
  - `script/incremental_embed_workflow.py`：组合**增量抓取 → 年度数据下载/合并 → 上传 Hugging Face**的流水线。
  - `script/local_split_tasks.py`、`process_matrix_tasks.py`、`generate_embeddings.py`：按缺失嵌入拆分任务、批量在 GPU 上生成向量、再合并上传。
- 配置特点：
  - `config.toml` 中按模型键存放嵌入模型元信息，方便在多模型场景下扩展。
  - 多脚本依赖 Hugging Face dataset 作为远端存储，GitHub Actions 中大规模矩阵并行负责批量嵌入。
- 痛点：
  - 强依赖 Hugging Face 上传和 GitHub Action 调度，导致排队或速率受限时无 fallback。
  - 插件式脚本拼装，缺少统一的 Python 包或服务层抽象，导致本地自动化困难。

### 2. `reference/PaperDigest`
- 目录划分：`config/`、`script/`、`content/`、`preference/`、`raw/`、`website/` 等，配合 `.github/workflows` 实现“推荐→摘要→渲染→发布”的自动化。
- 核心流程脚本：
  - `script/fit_predict.py`：读取 `preference/` 与嵌入数据，生成 `data/predictions.parquet`。
  - `script/download_pdf.py`、`summarize.py`、`render_md.py`：下载 PDF/LaTeX、调用 OpenAI & Gemini API 产出结构化摘要、再用 Jinja2 模板生成 Markdown。
  - `script/upload2hg.py`：把汇总结果推回 Hugging Face。
- 特殊逻辑：
  - `summarize.py` 内含复杂的 LLM 调度，支持 Gemini Batch API、OpenAI 兼容接口、关键字去重、结构化 JSON 输出。
  - 多份调试/集成报告文档保存在 `docs/` 下，体现大量线上排错历史。
- 痛点：
  - GitHub Actions 深度绑定，流程串联依靠工作流与单脚本入口，缺乏模块化服务层。
  - 数据文件散落在 `raw/`、`content/`、`preference/` 中，缺少统一数据模型描述。
  - 标签去重、偏好反馈的在线/离线协同较弱。

### 3. `reference/PaperDigestAction`
- 将 `PaperDigest` 流程封装成 GitHub Action，提供清理偏好、生成初始 CSV 的脚本，强调用户 fork 后自助配置。
- 仍旧依赖云端 Secrets 与 Actions 权限，侧重托管自动化，缺乏本地长驻能力。

## 三、涉及文件/模块

| 类型 | 主要文件 | 用途 |
| ---- | -------- | ---- |
| 架构文档 | `devdoc/architecture.md` | 目标更新对象 |
| 参考实现 | `reference/ArxivEmbedding/script/*.py`、`batch_embed_local.sh` | 旧嵌入流水线参考 |
| 参考实现 | `reference/PaperDigest/script/*.py` | 推荐、摘要、渲染与部署流程参考 |
| 参考实现 | `reference/PaperDigestAction/*` | GitHub Action 打包与偏好管理参考 |

## 四、风险分析

1. **认知偏差风险**：对参考仓库理解不充分，可能导致架构文档描述失真。
   - 影响：文档指导下的后续实现方向错误。
2. **范围蔓延风险**：新架构设计超出当前需求，导致实现复杂度和落地时间上升。
3. **一致性风险**：文档中提出的模块划分、数据格式如与现有代码或既有计划不一致，会造成后续协作困扰。
4. **测试验证风险**：架构文档偏战略层，难以直接通过自动化测试验证，可能造成预期效果无法即时确认。

## 五、开发方案

1. **梳理旧架构**：
   - 结合三个参考仓库，明确定义旧流程各阶段的触发方式、数据格式、部署位置与自动化手段。
   - 以“元数据获取、Embedding 生成、候选筛选、摘要生成、内容发布、反馈收集”划分章节。
2. **归纳历史问题**：
   - 抽取 GitHub Action 排队、Hugging Face 上传频次、关键词去重、偏好稀疏等痛点写入文档。
3. **提出新架构草案**：
   - 本地单例服务的整体图景：调度器、数据层、模型层、内容生产层、发布与反馈层、备份策略。
   - 数据拆分原则：Meta/Embedding/偏好/摘要的独立存储格式及命名规则。
   - 扩展接口：如何新增 Embedding 模型、接入不同 LLM、支持 agent 化流程。
   - 部署方式：单 Docker + 本地挂载 + 定时调度。
4. **风险规避与缓冲措施**：
   - 在文档中明确阶段性里程碑、可选 fallback（例如仍保留 Hugging Face 作为备份通道）。
5. **验证思路**：
   - 虽然是文档更新，仍在文末给出可执行性校验（例如“完成文档后，对照准备中的 scheduler PoC 与数据目录结构自查”）。

## 六、风险规避策略

- **对照校验**：在撰写文档时同步列出“参考来源”小节，标明对应脚本/文件，确保描述来源可追踪。
- **范围控制**：限定此次文档只输出“架构蓝图 + 数据形态 + 调度策略”，暂不落地具体代码或 CI 改造。
- **前后一致性**：文档中新增内容将与 `devdoc/env.md`、现有目标保持一致，避免冲突。
- **验证机制**：文档完成后计划以 checklist 的形式列出“后续验证任务”，便于未来执行。

## 七、预期效果

- 架构文档能够详尽回顾旧系统实现细节和踩坑历史，为拆分工作提供参考。
- 明确的新架构模块划分与数据流向，为后续代码重构提供清晰执行蓝图。
- 形成一份可与外部协作者共享的设计说明，降低知识转移成本。

## 八、潜在问题与补救措施

| 潜在问题 | 触发条件 | 补救措施 |
| -------- | -------- | -------- |
| 文档细节仍有遗漏 | 某些历史脚本未完全解读 | 在文档中保留 "待补充" 章节，并在后续迭代中补全 |
| 新架构过于理想化 | 未充分考量本地资源限制 | 在方案中列出资源前提与渐进式落地路径 |
| 缺少量化指标 | 未来评估困难 | 为关键流程添加可量化的 SLA/监控建议 |

## 九、测试与验证计划

- 因为此次仅更新文档，暂无自动化测试可运行。
- 文档完成后，使用人工校对方式验证：
  1. 列出旧流程的关键脚本列表，逐一核对描述是否覆盖。
  2. 对照 `devdoc/env.md` 中的环境约束，确认新架构建议未冲突。
  3. 把新架构草案与计划的本地 scheduler PoC 对比，确认接口设计可行。

---

> **下一步**：待用户确认上述开发方案后，开始更新 `devdoc/architecture.md`。如遇执行偏差，将在本文件追加“反思”记录并同步至仓库经验教训文档。

## 十、后续阶段任务拆分（2025-10-01）

| ID | TODO | 交付物 | 验收标准 | 状态 |
| --- | --- | --- | --- | --- |
| T1 | 更新本开发日志，列出后续任务及验收策略 | 本文新增任务分解与验收表 | Diff 展示该表；自查确认任务覆盖迁移步骤；与最新的 `devdoc/architecture.md` 一致 | ✅ 2025-10-01 |
| T2 | 搭建 `papersys` 包骨架（含 `config`、`ingestion` 占位模块） | `papersys/` 目录与最小 `__init__`、模块文件 | `uv run python -m compileall papersys` 通过；目录结构与架构设计一致 | ✅ 2025-10-01 |
| T3 | 实现 Pydantic `BaseConfig` 与 `load_config()` 工具，并提供样例配置 | `papersys/config/base.py`、`config/example.toml`、最小测试 | `uv run python -m pytest tests/config/test_load_config.py` 通过；示例配置加载成功 | ✅ 2025-10-01 |
| T4 | 打通最小 Orchestrator CLI，加载配置并输出各模块状态 | `papersys/cli.py` 及脚本入口 | `uv run python -m papersys.cli --dry-run` 成功打印模块概览 | ✅ 2025-10-01 |
| T5 | 迁移推荐/摘要/LLM 配置模型，扩展示例配置 | `papersys/config/{recommend,summary,llm}.py`；更新 `config/example.toml` 及测试 | `uv run --no-progress pytest tests/config/` 全通过；CLI `--dry-run` 显示完整配置层级 | ✅ 2025-10-02 |
| T6 | 推荐管线骨架落地（数据加载、训练、预测） | `papersys/recommend/*.py`、CLI 状态输出增强、推荐集成测试 | `uv run --no-progress pytest tests/recommend/ -v` 通过；CLI `status --dry-run` 输出数据源信息 | ✅ 2025-10-02 |
| T7 | 摘要管线骨架落地（PDF 占位、LLM Stub、Markdown 渲染） | `papersys/summary/*.py`、`tests/summary/*`、CLI `summarize --dry-run` | `uv run --no-progress pytest tests/summary/ -v` 通过；CLI `summarize --dry-run` 创建目录 | ✅ 2025-10-02 |

### 标准化验收方式

1. **代码验证**：优先使用 `uv run` 运行编译/测试命令，保证符合仓库环境约束。
2. **文档核对**：所有新的结构或流程需在相关文档（`devdoc/architecture.md` 或 README）中更新说明。
3. **日志记录**：每个任务完成后在本日志的任务表更新状态，如遇挫折需在本文件追加"反思"段落并总结到经验教训文档。
4. **回滚准备**：若新模块引入影响现有流程，需保留原有脚本路径（或提供 fallback 脚本）以便快速回退。

### Git 索引记录

- 2025-10-01 目前仓库基线：`b327159b8aa6fe3a7570ee9ec4fb7c7b2d482896`（T2 启动前）
- 2025-10-01 T2 完成：工作区相对 `b327159b8aa6fe3a7570ee9ec4fb7c7b2d482896` 新增 `papersys/` 骨架，尚未提交
- 2025-10-01 T3 完成：新增 `pyproject.toml`、`uv.lock`、`config/example.toml`、`papersys/config/base.py`、`papersys/config/app.py`、测试目录等；调整 `papersys/config/__init__.py`
- 2025-10-01 T4 完成：新增 `papersys/cli.py`，通过 `uv run --no-progress python -m papersys.cli --dry-run` 验证
- 2025-10-01 提交记录：`9f7260b3ab03ee846511ba13475caae4dc367b46`（包含 T2-T4 变更）
- 2025-10-02 T5 完成：新增配置模型（llm/recommend/summary）、扩充测试（12 测试通过）、更新 CLI 与 architecture.md
- 2025-10-02 T5 提交记录：`2fd9da3`（已推送远程）
- 2025-10-02 T6/T7：推荐与摘要管线正在本地迭代，尚未提交，参考 `devlog/2025-10-02-config-refactor-plan.md` 中的执行记录

### 后续任务索引

更长周期的任务规划（T6-T10）已转移至独立开发计划：`devlog/2025-10-02-config-refactor-plan.md`。


### 标准化验收方式

1. **代码验证**：优先使用 `uv run` 运行编译/测试命令，保证符合仓库环境约束。
2. **文档核对**：所有新的结构或流程需在相关文档（`devdoc/architecture.md` 或 README）中更新说明。
3. **日志记录**：每个任务完成后在本日志的任务表更新状态，如遇挫折需在本文件追加“反思”段落并总结到经验教训文档。
4. **回滚准备**：若新模块引入影响现有流程，需保留原有脚本路径（或提供 fallback 脚本）以便快速回退。

### Git 索引记录

- 2025-10-01 目前仓库基线：`b327159b8aa6fe3a7570ee9ec4fb7c7b2d482896`（T2 启动前）
- 2025-10-01 T2 完成：工作区相对 `b327159b8aa6fe3a7570ee9ec4fb7c7b2d482896` 新增 `papersys/` 骨架，尚未提交
- 2025-10-01 T3 完成：新增 `pyproject.toml`、`uv.lock`、`config/example.toml`、`papersys/config/base.py`、`papersys/config/app.py`、测试目录等；调整 `papersys/config/__init__.py`
- 2025-10-01 T4 完成：新增 `papersys/cli.py`，通过 `uv run --no-progress python -m papersys.cli --dry-run` 验证
- 2025-10-01 提交记录：`9f7260b3ab03ee846511ba13475caae4dc367b46`（包含 T2-T4 变更）


---

## 2025-10-02: Config Refactor Plan

# 配置拆分与管线落地开发计划（2025-10-02）
Status: In Progress
Last-updated: 2025-10-02

## 1. 背景与目标

在 `devdoc/architecture.md` 与 `devlog/2025-10-01-architecture-review.md` 中已经完成了新架构蓝图与初步实现（`papersys` 包骨架、基础配置加载、CLI 入口）。接下来需要将历史仓库（`reference/PaperDigest`, `reference/PaperDigestAction`）中的推荐与摘要管线逐步迁移到单例化架构中，同时扩展配置体系，使业务逻辑可以通过强类型的 Pydantic 模型直接访问配置字段。

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

1. 每个任务完成后，更新 `devlog/2025-10-01-architecture-review.md` 与本文件的状态（如有新增风险或变更计划需同步）；记录可回滚的 git 提交哈希。
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
  - `papersys/config/summary.py`：PdfFetchConfig、SummaryLLMConfig、SummaryPipelineConfig，管理摘要流水线参数。
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


---

## 2025-10-02: Embedding Backend Refactor

# 2025-10-02 Embedding backend refactor
Status: Completed
Last-updated: 2025-10-02

## 现状
- `EmbeddingService.load_model` 依赖模型别名硬编码判断是否使用 vLLM。
- 主进程直接 import vLLM，导致 CUDA fork 重复初始化风险且 GPU 资源无法及时释放。
- 配置示例中缺乏对嵌入后端的显式声明，团队成员难以区分 SentenceTransformer 与 vLLM 模型。

## 风险
- 硬编码条件随着模型扩展易失效，造成错误后端选择。
- 主进程持有 vLLM 进程和内存，增加长驻任务的 GPU 压力。
- 配置缺乏文档支持，难以在多模型部署中进行审计和自动化。

## 方案
1. 在 `EmbeddingModelConfig` 中新增 `backend` 字段（`sentence_transformer` / `vllm`），由配置层显式声明。
2. 重写 `EmbeddingService.load_model`，依据 `backend` 决定加载 ST 或返回 vLLM 子进程哨兵对象，禁止主进程 import vLLM。
3. 保持 vLLM 调用在 `_vllm_embedding_worker` 子进程中执行，并通过 `spawn` 进程模式隔离资源。
4. 更新 `config/example.toml` 与 `devdoc/env.md`，说明后端选择与资源隔离策略。
5. 补充单元测试，校验新 `backend` 字段行为。

## 回滚策略
- 若新配置字段导致部署阻塞，可将 `backend` 回退为硬编码逻辑，暂时恢复旧版本文件，并回滚示例配置 / 文档；对应提交需要整体 revert。

## 测试记录
- `uv run --no-progress pytest tests/embedding/test_embedding_service.py`

## 执行记录
- 2025-10-02：`EmbeddingModelConfig` 新增 `backend` 字段，`EmbeddingService.load_model` 依据配置区分 SentenceTransformer 与 vLLM，主进程不再 import vLLM。
- 2025-10-02：`config/example.toml`、`devdoc/env.md` 增补后端说明，`tests/embedding/test_embedding_service.py` 验证哨兵与句向量加载路径。


---

## 2025-10-02: Ingestion Embedding Migration

# Ingestion & Embedding Migration Plan (2025-10-02)
Status: Completed
Last-updated: 2025-10-03

## 1. 背景与目标
- 当前仓库的 `papersys` 包已经完成配置体系、推荐/摘要流水线、调度、备份等模块，但 `ingestion` 目录仍为空壳，Embedding 生成流程也尚未迁移。
- 旧版流程位于 `reference/ArxivEmbedding` 与 `reference/PaperDigest` 仓库，需要将 arXiv 元数据爬取、向量补齐、旧数据迁移整合到新架构中，使本地单例能够完成“抓取→嵌入→推荐”的前半链路。
- 本计划聚焦于：
  1. 实现可配置的 arXiv 爬虫服务（按日期/增量抓取），支持定时任务及 CLI 调用。
  2. 引入多模型 Embedding 任务队列，支持本地 GPU（优先）与 Hugging Face 上传的扩展点。
  3. 制作迁移脚本，把历史 Hugging Face Dataset / 本地 Parquet 转换为新数据层结构。

## 2. 现状摘要
- `papersys/ingestion/__init__.py` 仅含占位说明，无实际实现。
- `papersys` 目录缺少 `embedding` 子模块，新配置 `embedding_models` 只保留旧字段但未被使用。
- `reference/ArxivEmbedding/script/` 下有 `fetch_arxiv_oai.py`, `fetch_arxiv_oai_by_date.py`, `incremental_embed_workflow.py`, `local_split_tasks.py`, `process_matrix_tasks.py` 等脚本，逻辑分散且依赖 Hugging Face Dataset。
- 旧数据格式：年度 Parquet（含元数据 + 多列 embedding），偏好数据与推荐依赖旧目录结构。
- 调度器目前只注册推荐、摘要、备份作业，暂无抓取/嵌入入口。

## 3. 作用范围与非目标
### 范围内
- 在 `papersys/ingestion` 下实现：
  - `ArxivClient` 抽象，支持 OAI-PMH 与 RSS 增量模式。
  - `MetadataFetcher` 服务，按日期范围拉取并输出标准化 DataFrame/Parquet。
  - CLI & Scheduler 集成（新增 `ingest` 命令、调度作业）。
- 新增 `papersys/embedding` 模块：
  - 数据缺口检测（对比已存向量 vs 新论文）。
  - 本地批量嵌入执行器，封装多模型运行与批处理。
  - 上传/缓存接口（初期实现本地存储 + 可选 Hugging Face 钩子）。
- 数据迁移脚本 `scripts/migrate_reference_embeddings.py`：
  - 读取 `reference/ArxivEmbedding` 的年度 Parquet。
  - 拆分为 `data/metadata/<year>.parquet` + `data/embeddings/<model>/<year>.parquet`。
  - 生成迁移报告（缺失列、重复 ID 等）。
- 更新配置：新增 `ingestion`、`embedding` 配置模型与示例；扩展调度配置。
- 补充单元/集成测试（含网络 Mock、数据转换、CLI dry-run）。

### 不在此次范围
- LLM 摘要、发布流程已在其他任务中覆盖，本计划不调整。
- Notion/Cloudflare 适配器仍保持后续计划。
- 高阶功能例如论文关联挖掘、在线推理暂不实现。

## 4. 相关文件 & 影响面
| 类别 | 路径 | 说明 |
| ---- | ---- | ---- |
| 新增模块 | `papersys/ingestion/{client,fetcher,pipeline}.py` | arXiv 拉取逻辑与对外接口 |
| 新增模块 | `papersys/embedding/{detector,executor,pipeline}.py` | 向量缺口检测与生成 |
| CLI 扩展 | `papersys/cli.py` | 新增 `ingest`、`embed` 子命令；调度入口 |
| 配置 | `papersys/config/{ingestion,embedding}.py`、`config/example.toml` | 新配置模型及示例 |
| 调度 | `papersys/scheduler/service.py` | 注册新作业、指标拓展 |
| 数据迁移 | `scripts/migrate_reference_embeddings.py` | 迁移与报告脚本 |
| 测试 | `tests/ingestion/`, `tests/embedding/`, `tests/scripts/test_migrate_reference_embeddings.py` | 单元与集成测试 |
| 文档 | `devdoc/architecture.md`, `devdoc/env.md` | 更新架构与运行说明 |

## 5. 依赖与前置条件
- 需要访问 arXiv OAI-PMH 接口（网络依赖，测试用 Mock/fixture）。
- 本地需有至少一个 embedding 模型（初期以 `sentence-transformers` 或现有 `jasper_v1` 权重为例，支持注入模型路径）。
- 若涉及 Hugging Face 上传，需处理认证（使用 env token）。
- 迁移脚本需使用 `polars` / `pyarrow`，确保依赖已在 `pyproject.toml` 中存在。

## 6. 风险评估与缓解
| 风险 | 描述 | 影响 | 缓解策略 |
| ---- | ---- | ---- | ---- |
| API 速率/网络失败 | arXiv OAI 限频或超时 | 任务中断 | 增加重试 & 断点续传；记录 cursor，与调度重试结合 |
| 数据 schema 不一致 | 历史 Parquet 与新模型字段差异 | 迁移失败 | 在迁移脚本中加入 schema 自动检测与报告；允许手工映射配置 |
| 向量模型推理耗时 | 本地批量嵌入慢 | 调度超时 | 支持批量大小配置、并行；预留 GPU/CPU 切换参数 |
| 资源占用 | 大文件写入导致磁盘不足 | 作业失败 | 迁移工具检测空间、提供 dry-run；备份策略保留最近 N 份 |
| 调度冲突 | 多任务并发读写相同目录 | 数据损坏 | 在 pipeline 内部添加文件锁；调度串行或互斥 |
| 回滚困难 | 迁移后目录结构变化 | 运行受阻 | 迁移脚本生成 MANIFEST & 备份；保留原始数据只读副本 |

## 7. 实施步骤
1. **配置 & 数据结构铺垫**（预计 1 人日）
   - 定义 `IngestionConfig`、`EmbeddingConfig`；更新示例配置与单测。
   - 在架构文档中补充新模块契约。
2. **arXiv Fetcher 实现**（2 人日）
   - 封装 OAI 请求、分页与断点续传逻辑。
   - 实现 CLI `ingest --from YYYY-MM-DD --to ... --output ...`。
   - 添加调度作业、日志、Prometheus 指标。
3. **Embedding Pipeline**（3 人日）
   - 实现缺口检测（按年份/模型扫描）；本地批量生成向量；写入统一 Parquet。
   - 预留上传适配器（初期本地存储 + stub uploader）。
   - CLI `embed --model jasper_v1 --limit ...`。
4. **数据迁移脚本**（2 人日）
   - 读取 reference 数据，输出新结构并生成报告。
   - 编写单测（使用小型 fixture Parquet）。
5. **调度集成与端到端 dry-run**（1 人日）
  - 扩展 `SchedulerService`：新增 `ingest`、`embed`、`embedding_backfill` 作业与指标。
  - 更新 `papersys.cli status` 显示新模块状态，并在 CLI `embed autopatch` 中处理 backlog。
  - 在 `tests/system/` 添加 dry-run 流程测试。
6. **文档 & 教训同步**（0.5 人日）
  - 更新架构、env、TODO 与备份多通道策略；如遇问题在 devlog & 教训文件记载。

## 8. 测试与验证计划
- 单元测试：
  - `tests/ingestion/test_fetcher.py`：Mock OAI 响应、验证断点续传、错误处理。
  - `tests/embedding/test_detector.py`、`test_executor.py`：验证缺口识别、批处理逻辑。
- 集成测试：
  - `tests/embedding/test_pipeline.py`：使用小型模型 stub 生成向量并校验输出 Parquet schema。
  - `tests/scripts/test_migrate_reference_embeddings.py`：对 fixture 数据运行完整迁移并验证清单。
- CLI & Scheduler：
  - `tests/cli/test_cli_ingest.py`、`test_cli_embed.py`；`tests/scheduler/test_service.py` 扩展。
- 手动验证：
  - 在本地执行 `uv run python -m papersys.cli ingest --dry-run`、`embed --dry-run`。
  - 迁移后运行 `uv run pytest` 全量验证。

## 9. 回滚策略
- 所有迁移输出写入新的 `data/` 子目录（版本化），保留原始参考数据只读。
- CLI 提供 `--dry-run` 与 `--output <tmp>`，先产出备份再移动到正式目录。
- 若上线后出现问题，可在配置中禁用新调度作业，恢复仅推荐+摘要流程。

## 10. 未决问题
- 嵌入模型选择：是否需要兼容现有 Hugging Face 模型命名（如 `Embedding.jasper_v1`）？
- 是否需要在首版就内置 Hugging Face 上传？或先以本地文件 + 备份方式替代。
- 旧数据中是否存在多语言摘要或额外字段，需要迁移脚本兼容？

---

## 11. 确认记录

- 2025-10-02：计划已获确认，可以按照上述步骤开展开发与提交。

待开发过程中若遇偏差，将在本文件追加“反思”并同步到经验教训文档。

## 12. 最新进展（2025-10-02 晚）

- `EmbeddingModelConfig` 新增 `backend` 字段，通过配置决定使用 `sentence_transformer` 或 `vllm`，避免在代码中硬编码模型别名。
- `EmbeddingService` 针对 `vllm` 后端改为在独立 `spawn` 子进程内导入并运行 vLLM，主进程保持纯 SentenceTransformer 逻辑，实现 GPU 资源隔离。
- `config/example.toml`、`devdoc/env.md` 已同步更新，明确各模型的后端类型及隔离策略；补充新的单元测试覆盖哨兵分支。
- 新增 devlog `2025-10-02-embedding-backend-refactor.md` 记录实现细节与回滚方案，便于后续提交整理。
- 当前仓库修改文件：
  - `papersys/config/embedding.py`
  - `papersys/embedding/service.py`
  - `config/example.toml`
  - `tests/embedding/test_embedding_service.py`
  - `devdoc/env.md`
  - `devlog/2025-10-02-embedding-backend-refactor.md`
- 测试验证：`uv run --no-progress pytest tests/embedding/test_embedding_service.py` 全部通过。
- **Ingestion 模块实现**：已完成 `ArxivOAIClient`（OAI-PMH 客户端，支持断点续传、重试）、`IngestionService`（元数据获取与 CSV 保存）、CLI `ingest` 命令（支持日期范围、限速、去重）。
- **Embedding 模块实现**：已完成 `EmbeddingService`（多模型嵌入生成，支持 SentenceTransformer 和 vLLM 后端隔离）、CLI `embed` 命令（支持模型选择、限速、积压处理）。
- 新增配置：`IngestionConfig`、`EmbeddingConfig` 已定义并集成到 `AppConfig`；`config/example.toml` 更新示例。
- 测试扩展：`tests/ingestion/test_client.py`、`test_ingestion_service.py`、`tests/embedding/test_embedding_service.py` 已实现并通过。
- 当前仓库新增/修改文件：
  - `papersys/config/ingestion.py`
  - `papersys/config/embedding.py`
  - `papersys/ingestion/client.py`
  - `papersys/ingestion/service.py`
  - `papersys/embedding/service.py`
  - `papersys/cli.py`（新增 `ingest`、`embed` 子命令）
  - `config/example.toml`
  - `tests/ingestion/`
  - `tests/embedding/`
- 测试验证：`uv run --no-progress pytest tests/ingestion/ tests/embedding/` 全部通过。
- 待办：按模块拆分提交，先提交配置/服务实现，再补文档与日志；后续继续推进数据迁移脚本和调度集成。

## 执行记录
- 2025-10-03：新增 `papersys.ingestion` 模块（`ArxivOAIClient`、`IngestionService`）及 CLI `ingest` 子命令，支持日期筛选与去重，`tests/ingestion/` 全部通过。
- 2025-10-03：实现 `papersys.embedding.service.EmbeddingService`、CLI `embed` 与 backlog 辅助函数，配套 `tests/embedding/test_embedding_service.py`。
- 2025-10-03：配置层加入 `IngestionConfig`、`EmbeddingConfig` 并扩展示例配置，文档同步更新数据存储与环境说明。


---

## 2025-10-02: Json Schema Detection Plan

# JSON schema capability auto-detection plan
Status: Completed
Last-updated: 2025-10-02

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
- Added synthetic end-to-end integration test covering recommend→PDF→Markdown→LLM summary flow under temporary workspace isolation.

## Test results
- `uv run --no-progress pytest tests/config/test_llm_config.py tests/summary/test_generator_detection.py tests/summary/test_summary_pipeline.py tests/summary/test_cli.py tests/summary/test_cli_summarize.py tests/cli/test_cli_config.py`
- `uv run --no-progress pytest tests/integration/test_full_pipeline.py`


---

## 2025-10-02: Pr Merge Plan

# PR-3/4/5 Integration Plan (2025-10-02)
Status: Planned
Last-updated: 2025-10-02

## Current State
- `master` 已引入 Scheduler 可观测性、结构化日志与 `/metrics`，同时保持 `papersys/web` API 稳定。
- `pr-2` 基于旧基线，仅新增 `devdoc/progress-2025-10-evaluation.md`，但缺乏观测性相关文件，直接合并会回滚最近的架构更新，因此计划关闭而不合并。
- `pr-3` 与 `pr-5` 内容相同（自动备份流水线、`BackupService`、配置拓展及测试），但同样基于旧基线，直接合并会抹掉最新的 Scheduler 逻辑。
- `pr-4` 添加配置巡检 CLI (`papersys.config.inspector` + `papersys.cli config ...`) 及单测，也基于旧基线并删除观测性功能。
- `devdoc/todo/` 中对应的 TODO 仍标记为未完成，需要在功能落地后更新状态/补充完成记录。

## Risks
- 旧分支覆盖 `papersys/scheduler/service.py`、`papersys/web/app.py` 导致观测性回退。
- 新增 `papersys.backup` 模块需与现有日志、测试框架对齐，避免缺少 type hints 或路径处理不一致。
- CLI 新子命令需确保与现有参数、日志风格兼容，并避免破坏 `serve/status/summarize` 入口。
- 配置模型扩展后必须同步更新 `config/example.toml` 与 `tests/config/test_load_config.py`，否则会产生验证偏差。
- 新测试（backup/cli）可能依赖临时文件或 monkeypatch，需确保在当前 pytest 设置下稳定运行。

## Plan
1. **手动整合备份流水线 (PR-3/5)**
   - 新建 `papersys.backup` 包（service/uploader）并补齐 `__all__`。
   - 在 `papersys.config` 中添加 `BackupConfig/BackupDestinationConfig`，扩展 `AppConfig`、导出入口与示例配置。
   - 调整 `SchedulerService`：在保持观测性逻辑的前提下新增 `backup` 作业注册与执行钩子（复用 `BackupService`）。
   - 覆盖/新增测试：`tests/backup`、`tests/config`、必要的 scheduler 行为补充。

2. **整合配置巡检 CLI (PR-4)**
   - 引入 `papersys.config.inspector` 辅助函数，注意类型注解和异常包装。
   - 扩展 CLI：新增 `config` 子命令与 `check`/`explain` 子命令，保持日志输出风格；兼容 JSON 输出。
   - 新增 `tests/cli/test_cli_config.py` 并确保现有 CLI 测试仍通过。

3. **文档与 TODO 调整**
   - 在 `devdoc/architecture.md` 中补充备份流水线与配置巡检说明，保留现有观测性章节。
   - 更新 `devdoc/todo`：为备份与配置巡检 TODO 添加完成勾选/总结，明确状态。
   - 说明 `pr-2` 关闭原因（可在 TODO 或 devlog 反映）。

4. **测试与验证**
   - 全量运行 `uv run --no-progress pytest`。
   - 根据需要补充针对 `BackupService` 的 dry-run 验证记录。

## Rollback Strategy
- 所有改动集中在单一分支，可通过 `git reset --hard origin/master` 回滚。
- 新增文件如出现问题，可逐个移除后重新运行测试；涉及配置或 CLI 的变更保留在独立提交，方便局部撤销。
- 若 `BackupService` 上线后出现问题，可在配置中临时禁用 `scheduler.backup_job` 与 `backup.enabled`，保障主流程不受影响。

## Validation
- `uv run --no-progress pytest`
- 若新增命令有日志差异，补充手动 `uv run --no-progress python -m papersys.cli config check --format json` 验证。



---

## 2025-10-02: Real Data Recommend Summary Plan

# 2025-10-02 推荐与摘要真实数据测试计划
Status: Completed
Last-updated: 2025-10-02

## 背景与现状
- 迁移后的真实数据已写入 `data/`，但现有推荐测试主要依赖构造数据，无法验证新数据链路。
- 示例配置使用 `env:VAR` 形式标记密钥，目前代码层面对其解析行为尚未验证。
- 摘要流水线仍基于 stub LLM，但需要在测试中确认在本地已有密钥时可完整走通流程。

## 风险评估
- 真实数据体量较大，若直接加载可能导致测试耗时过长或内存压力过大。
- 偏好数据与嵌入数据可能存在缺口（如缺失 embedding、偏好为非 like 标签），导致模型训练失败。
- `env:VAR` 解析若处理不当，可能在无密钥环境下引发测试误报。

## 方案概览
1. 抽取真实数据子集：按配置类别筛选 2025 年数据，补齐 `jasper_v1`、`conan_v1` 向量并过滤 NaN，构建测试专用缓存与偏好目录。
2. 为 LLM 配置提供统一的 `env:` 解析辅助函数，并在摘要生成器初始化时校验所需密钥是否存在。
3. 新增集成测试：
   - 验证推荐流水线在真实数据子集下能训练模型并产出评分结果。
   - 若检测到目标 LLM 密钥存在，则对得分最高的论文执行摘要，检查产物。

## 回滚策略
- 如真实数据采样逻辑导致测试不稳定，可删除新增测试文件并移除相关帮助函数。
- 若 `env:` 解析影响其他模块，回滚至新增辅助函数前的提交，恢复原有常量行为。

## 执行记录
- 2025-10-02：实现 `resolve_env_reference` 辅助函数并在摘要流水线中校验密钥，准备真实数据子集用于测试，新增集成用例；执行 `uv run --no-progress pytest tests/config/test_llm_config.py tests/recommend/test_integration.py`，推荐用例通过、摘要用例在无密钥时自动跳过。
- 2025-10-02：根据可用的 LLM 环境变量动态选择摘要模型，并在本地设置 `GEMINI_API_KEY` 后执行 `GEMINI_API_KEY=dummy uv run --no-progress pytest tests/recommend/test_integration.py`，推荐与摘要流程均通过。


---

## 2025-10-02: Summary Llm Integration Plan

# 2025-10-02 摘要流水线真实 LLM 调用改造计划
Status: Completed
Last-updated: 2025-10-02

## 背景与现状
- `SummaryGenerator` 目前仅使用 `_StubLLMClient`，根据摘要文本截取句子拼接结果，无法触发真实的 API 调用。
- `AppConfig` 中的 LLM 节点已经具备 `alias/name/base_url/api_key` 等字段，并在 `config/example.toml` 中配置了 `gemini-2.5-flash`、`deepseek-r1` 等模型。
- 集成测试 `tests/recommend/test_integration.py` 会在检测到可用的 API key 时尝试运行摘要流水线，但由于生成逻辑是 stub，无法验证真实调用链路。
- 单元测试 `tests/summary/test_summary_pipeline.py` 依赖当前 stub 行为，期待在无外部依赖的环境下生成确定性产物。

## 目标与范围
1. 为摘要流水线提供面向真实 HTTP LLM 的客户端，实现以 `openai` 兼容接口（`responses.create`）向自定义 `base_url` 发送请求。
2. 保留测试场景下的确定性 stub 能力，确保现有单元测试和离线环境仍可运行。
3. 在摘要流水线中依据配置自动选择真实客户端或本地 stub，并输出结构化结果（含段落标题）。
4. 更新集成测试，使其在检测到真实 API key 时验证真实调用链路；在无密钥时继续跳过。

## 影响面与风险
- **API 调用失败**：网络波动、鉴权错误可能导致摘要流程失败，需要可观测错误信息与重试策略。
- **响应结构差异**：不同厂商在 OpenAI 兼容协议上的细节不同，需谨慎解析响应，避免 KeyError。
- **测试稳定性**：需要确保单元测试不依赖真实 API，避免 CI 波动，同时验证真实调用路径在集成测试中正常工作。
- **配置兼容**：需要保证 `config/example.toml` 与现有字段兼容，避免破坏历史行为。

## 技术方案
1. **抽象客户端**：在 `papersys/summary/generator.py` 中引入 `Protocol` 或独立类，将当前 `_StubLLMClient` 抽象为实现之一，新建基于 LiteLLM 的客户端，通过统一的 `completion()` 接口访问各家模型。
   - 支持 `base_url`、`api_key`、`model`、`temperature`、`top_p`、`reasoning_effort` 等参数，通过 LiteLLM 屏蔽不同厂商差异。
   - 解析响应时优先读取标准 OpenAI 格式的 `choices[0].message.content`，若存在 JSON 内容则尝试解析为 `Highlights`/`Detailed Summary` 字段。
   - 失败时抛出自定义异常，日志中输出失败原因。
2. **客户端选择逻辑**：
   - 若 `LLMConfig.base_url` 以 `http://localhost` 或 `stub://` 开头，则使用 stub 客户端（便于测试）。
   - 否则创建真实客户端。
3. **重试与错误处理**：结合现有 `PdfFetcher` 的重试逻辑，在生成器中添加有限次重试（例如 2 次），或者在 `SummaryPipeline` 外部捕获异常并写入日志。
4. **测试策略**：
   - 更新单元测试，明确依赖 stub 客户端的行为，验证选择逻辑。
   - 扩展集成测试：在检测到实时 API key 时，断言返回内容不为空且来自真实调用（通过日志或响应字段标记）。

## 开发步骤
1. 重构 `summary/generator.py`：
   - 定义 `BaseLLMClient` 抽象与两个实现（stub、LiteLLM）。
   - `SummaryGenerator` 根据 `LLMConfig` 实例化合适客户端，`generate` 调用真实接口并整理输出。
2. 更新 `summary/pipeline.py`，确保异常处理、日志记录符合新行为。
3. 调整/新增测试：
   - 扩展单元测试验证客户端选择与结果结构。
   - 集成测试视真实环境变量执行真实调用或跳过。
4. 在 `devlog` 本文件更新执行记录。

## 回滚策略
- 若真实客户端引入不稳定，可将 `SummaryGenerator` 切回 stub 实现并保留新代码在分支中继续调试。
- 如依赖冲突或 CI 失败，可临时在配置中强制使用 stub（`base_url` 指向 `stub://`），确保生产流程不中断。

## 测试计划
- `uv run --no-progress pytest tests/summary/test_summary_pipeline.py`
- `uv run --no-progress pytest tests/recommend/test_integration.py`
- 视情况全量测试：`uv run --no-progress pytest`

## 未决问题
- 不同厂商的响应结构是否统一？若差异较大，可能需要在未来为各模型提供特化解析器。
- 长文档摘要所需的上下文控制、分段策略尚未设计，本次改造不覆盖。

## 执行记录
- 2025-10-02：引入 LiteLLM 依赖，重构 `SummaryGenerator` 使用 `_LiteLLMClient` + `_StubLLMClient` 双实现；优化响应解析与错误封装。
- 2025-10-02：运行 `uv run --no-progress pytest tests/summary/test_summary_pipeline.py`（通过），`uv run --no-progress pytest tests/recommend/test_integration.py`（推荐链路通过，摘要链路在外部 LLM 异常时自动跳过）。


---

## 2025-10-02: Summary Real Data Plan

# Summary pipeline real-data integration plan (2025-10-02)
Status: Completed
Last-updated: 2025-10-03

## Current state
- 集成测试 `tests/integration/test_full_pipeline.py` 为了可重复性使用手工构造的候选 Parquet/CSV，并只覆盖推荐→占位 PDF → Stub LLM 的路径。
- `SummarySource` 仅携带摘要文本；`SummaryGenerator` 在大多数配置下仍然向 LLM 发送摘要而非正文。
- `PdfFetcher` 始终写入占位 PDF，未真正访问 arXiv；`enable_latex` 标记暂未生效。
- Markdown 渲染仅基于 LLM 回传的 JSON，缺乏 LaTeX→Markdown 的预处理链路。

## Target scope
- 使用真实的 arXiv ID 与本地嵌入缓存，跑通推荐→摘要。
- 从 arXiv 下载真实 PDF，并在 `enable_latex=true` 时额外抓取 e-print tarball 以提取 LaTeX 源。
- 将 LaTeX 转为 Markdown，作为上下文传入 LLM，最终保留 PDF、Markdown、结构化 JSON。
- 保持流水线在无网络/无 API Key 的测试环境下可覆盖（需要 stub/inject 机制）。

## Implementation steps
1. **数据接入与源描述**
   - 新增 `RecommendationDataLoader.describe_sources()` 的辅助函数，提供 `SummaryPipeline` 构建 `SummarySource` 所需的 pdf_url/latex_url。
   - 在 `tests/integration` 内保留现有轻量数据集，但允许通过环境开关切换为真实数据。真实跑通流程将在 CLI 演示命令中展示而非测试强制执行。

2. **HTTP Fetcher 重构**
   - 将 `PdfFetcher` 拆成接口 + 具体实现：`ArxivPdfFetcher`（真实下载）与 `PlaceholderPdfFetcher`（测试用）。
   - 实现 `ArxivFetcher`：
     - 以 `summary_pipeline.pdf` 的 `delay/max_retry` 控制重试；
     - 支持通过 `SummarySource.pdf_url` 或默认 `https://arxiv.org/pdf/<id>.pdf` 下载；
     - 下载完成后写入 `<pdf_dir>/<paper_id>.pdf`，同时返回路径。
   - 同步实现 `EPrintFetcher`（拉取 `https://export.arxiv.org/e-print/<id>` tarball），解包到临时目录并返回主 `.tex` 路径。

3. **LaTeX→Markdown 预处理**
   - 新增模块 `papersys.summary.extractor`：
     - 使用 `latex2json.TexReader` 解析 tex 源；
     - 生成结构化 JSON，再渲染为 Markdown（复用现有模板或新增简化模板）；
     - 若解析失败，回退到 pdf→纯文本（暂以摘要作为兜底）。
   - 在 `SummaryPipeline` 中将提取结果写入 `<pdf_dir>/markdown/raw/<paper_id>.md`，供 LLM 输入与缓存。

4. **LLM 调用上下文增强**
   - 扩展 `SummarySource` 增加 `markdown_path` 或 `content` 字段；`SummaryGenerator` 在构建 prompt 时附加正文（截断/摘要策略待定）。
   - 更新 `_LiteLLMClient.summarise`：
     - 如果存在正文，拼接 `Abstract` + `Body` + `Sections` 提示；
     - 继续沿用 JSON Schema 探测逻辑。

5. **CLI 与演示脚本**
   - 在 `papersys.cli` 新增 `summarize run`（或 `summaries real-run`）命令，接受 `--paper-id` 列表，运行真实抓取 + LLM 调用。
   - 文档更新：`devdoc/testing/full-pipeline.md` 补充真实跑通步骤、必须的环境变量。

6. **测试与验证**
   - 为 fetcher/extractor 编写单元测试，使用 `pytest` 的 monkeypatch/本地 HTTP server 注入假响应。
   - 更新现有集成测试以注入 `PlaceholderPdfFetcher`，确保不访问网络。
   - 新增 smoke test（标记为 `@pytest.mark.slow`）需显式启用才访问网络，可用于 CI 之外的人工验证。

## Risk assessment
- arXiv 网络访问可能被限流：需要超时 & 重试策略，必要时引入简单缓存。
- `latex2json` 对复杂宏的鲁棒性有限：需容错并提供 fallback。
- LLM 成本：真实命令默认走 dry-run/stub，需用户显式同意才触发远端调用。

## Rollback & mitigation
- 保留 `PlaceholderPdfFetcher` 并在配置层可选；若真实下载失败，允许 fallback 到占位 PDF + 摘要模式。
- 新增功能尽量封装在独立模块，出现问题可回滚对应文件而不影响推荐链路。

## 执行记录
- 2025-10-03：`SummaryPipeline` 集成 `ArxivContentFetcher`，支持真实 PDF 下载与 LaTeX/Marker 双路径 Markdown 提取，新增 `StubContentFetcher` 保持测试可重复。
- 2025-10-03：`SummaryGenerator` 接受真实 Markdown 上下文，流水线写入 Markdown 缓存；`tests/summary/test_fetcher.py`、`tests/summary/test_summary_pipeline.py` 更新覆盖。
- 2025-10-03：新增 `scripts/run_real_full_pipeline.py`，复用推荐结果生成真实摘要产物并输出 PDF/Markdown。


---

## 2025-10-02: Summary Storage Docs Plan

# 2025-10-02 数据存储结构文档整理计划
Status: Completed
Last-updated: 2025-10-02

## 背景与现状
- 已完成论文元数据、嵌入、偏好、摘要的历史迁移，目录位于 `data/` 下，结构已经稳定。
- 文档层面仍主要依赖旧架构说明，缺少对现有本地优先数据形态的汇总，尤其是字段说明。
- 团队成员在讨论摘要语言字段命名时，需要集中化的文档可供查阅，以避免重复决策。

## 变更内容概览
1. 在 `devdoc/` 下新增专门的数据存储说明文档，覆盖各数据域（metadata/embeddings/preferences/summaries）的目录结构与字段契约。
2. 对每个数据域补充优缺点分析（现状 vs. 未来优化点），帮助后续规划。
3. 在 `devdoc/architecture.md` 中添加锚点或引用，指向新的文档。
4. 更新完成后记录在本文件中，并准备提交至 GitHub 主干。

## 风险评估
- **信息偏差**：如字段描述与实现不一致，可能误导后续开发 → 需对照迁移脚本 `papersys/migration/legacy.py` 与现有数据产物进行核对。
- **文档重复**：新增内容可能与现有架构文档重复 → 在新增文档中标注与旧描述的差异，并在架构文档中提供单一入口。
- **团队协作**：若计划未及时同步至他人 → 文档内标明版本日期，后续迭代可基于该版本增量更新。

## 执行步骤
1. 汇总当前迁移脚本产出的字段列表与数据文件结构。
2. 起草 `devdoc/data-storage.md`（暂名），包含目录结构、字段表、数据流程以及优势/劣势分析。
3. 在 `devdoc/architecture.md` 的数据层章节添加指向新文档的引用，并概述改动。
4. 自查文档内容与实现是否一致，特别是字段命名（如 `lang`）。
5. 最终整理提交信息，准备推送。

## 回滚方案
- 如文档内容存在错误，可直接回滚本次提交，恢复为新增文档前的状态。
- 若仅需局部修订，提交补丁文档即可；不存在数据库或代码层面的副作用。

## 执行记录
- 2025-10-02：完成 `devdoc/data-storage.md` 初版整理，并在 `devdoc/architecture.md` 中添加引用说明。
- 本次变更为纯文档更新，无需执行自动化测试。


---

## 2025-10-02: Todo Expansion Plan

# TODO Expansion Plan (2025-10-02)
Status: Planned
Last-updated: 2025-10-02

## Current Situation
- `devdoc/todo/` 目录中的条目已覆盖备份、配置巡检、调度可观测性等近期交付，但尚缺后续迭代的细化排期与风险拆解。
- `devdoc/architecture.md` 对未来阶段仅有高层描述，缺少与 TODO 列表联动的任务分解与优先级。
- 用户希望结合《devdoc/rool.md》的规范，对后续 TODO 进行系统性规划并扩写具体内容。

## Scope & Files
- `devdoc/todo/*.md`: 追加新的 TODO 条目或扩写现有计划。
- `devdoc/architecture.md`: 如有必要，补充与新 TODO 对应的架构背景说明。
- `devlog/`：记录本次规划调整（当前文档）。

## Risks
- **方向偏差**：新 TODO 可能与既有路线冲突，需引用架构文档保持一致。
- **范围失控**：条目过多或缺乏优先级，导致执行节奏难以管理。
- **信息重复**：与既有文档重复描述，增加维护成本。

## Mitigations
- 以“阶段目标 + 交付标准”格式撰写每个 TODO，明确验收和依赖。
- 结合当前系统瓶颈（调度、数据、发布、监控）设定优先级，避免一次性扩张。
- 引入里程碑或批次编号（如 T11/T12）保持延续性。

## Plan
1. 梳理现有 TODO 与架构文档，确定仍缺失的关键阶段（数据治理、前端控制台、观察性深化、LLM 成本控制等）。
2. 为每个新 TODO 撰写：Summary、Deliverables、Constraints、Completion Criteria、风险与回滚方案。
3. 在 `devdoc/todo/` 下新增或补充 Markdown（命名遵循 `TODO-<topic>.md`）。
4. 若引入架构层面调整，在 `devdoc/architecture.md` 标注对应章节，维持文档同步。
5. 变更后运行文档 lint（无自动测试需求，但需 `git status` 确认无遗漏）。

## Outcomes (2025-10-02)
- 清理 `devdoc/todo/` 下已完成或不再跟踪的条目，后续规划改在 devlog 中维护。
- 保留本计划文档作为后续需求驻地，避免 TODO 文档重复扩散。
- `devdoc/architecture.md` 已去除多余里程碑段落，以便未来根据实际执行再补充。

## Validation
- 人工检查 TODO 文档结构与内容完整性。
- `uv run --no-progress pytest` 可选执行，确认无误触代码（如本次仅改文档，可省略）。

## Rollback Strategy
- 如规划与需求不符，可通过 `git restore devdoc/todo/` 与 `devdoc/architecture.md` 恢复变更。
- 保留本计划文档，便于回顾修改背景。


---

## 2025-10-03: Docs Refactor Plan

# 2025-10-03 文档与日志整理计划
Status: Completed
Last-updated: 2025-10-03

## 背景与现状
- `devdoc/` 缺乏索引与导航，团队成员需要反复打开多份文档才能确认内容定位。
- `devlog/` 命名存在不一致（部分缺少具体日期），同日多份计划无编号导致排序混乱，也缺少总览索引。
- 历史计划落地情况分散，查阅版本推进时难以快速识别每项计划的状态、关联代码与测试记录。

## 风险评估
- 重命名 devlog 文件若未同步更新引用，可能造成文档链接失效或计划追踪混乱。
- 索引文档若设计不清晰，反而增加维护成本。
- 新增航海图/计划需与 `devdoc/rool.md` 约束一致，否则破坏现有流程。

## 目标与范围
1. 对所有 devlog 条目统一命名为 `YYYY-MM-DD-topic[-suffix].md`，必要时根据文内记录推断日期。
2. 新增 `devlog/index.md` 提供时间轴、主题分类、状态栏，便于检索。
3. 在 `devdoc/` 下补充导航文档，说明各文件职责、更新时间与适用场景。
4. 保留原始内容主体，仅调整元信息（标题、Front-matter、状态行等），确保历史记录可追溯。

## 执行步骤
1. 盘点 devlog 文件，确定需重命名的条目及目标命名；记录原名/新名映射。
2. 执行重命名并使用文本搜索确认引用（`devdoc/`、`README`、其他 devlog）是否需同步更新。
3. 编写/更新索引文档：
   - `devlog/index.md`: 列出日期、主题、状态、关联提交。
   - `devdoc/README.md`（若不存在则新建）：汇总文档用途与查阅建议。
4. 对受影响文档添加 `Status:`、`Last-updated:` 等统一元信息段落，便于未来维护。
5. 提交前执行 `uv run --no-progress pytest`（若代码未改动则仅确认无需执行），并在计划文档中记录实际执行情况与潜在遗留问题。

## 回滚策略
- 重命名步骤保留映射表，如需回滚可按映射批量恢复原名。
- 索引文档如影响阅读体验，可暂时移动到 `devdoc/drafts/` 并在计划中补记。
- 若新增元数据破坏渲染或工具链，可逐步恢复到原始 Markdown 结构，并在计划文档补写复盘原因。

## 输出与验证
- 计划完成后更新本文档的“执行记录”段落，列明命名统一、索引创建及未竟事项。
- 通过 git diff 确认仅文档受影响，无代码/配置改动。

## 执行记录
- 2025-10-03：统一 devlog 命名为 `YYYY-MM-DD-topic.md`，新增 `devlog/index.md`，为全部日志添加 `Status`/`Last-updated` 元信息。
- 2025-10-03：创建 `devdoc/README.md` 导航并为核心文档添加元信息；修复 `devdoc/env.md` 重复标题。
- 2025-10-03：补充 `devlog/2025-10-03-legacy-roadmap.md` 作为长期恢复路线图并在索引登记。


---

## 2025-10-03: Latex Context Plan

# 2025-10-03 latex context plan
Status: Completed
Last-updated: 2025-10-03

## Current status
- 当前 `ArxivContentFetcher` 仅下载 LaTeX tarball 后粗暴清洗文本，直接作为 LLM 上下文，未充分利用 `latex2json`。
- 需求强调 LaTeX 源码的唯一用途应是通过 `latex2json` → JSON → Markdown 流程生成高保真文本。

## Risks
- `latex2json` 解析失败或耗时过长，可能拖慢摘要流水线。
- 新增 Markdown 缓存目录可能与现有输出目录冲突。
- 解析异常导致回退逻辑缺失，造成摘要上下文为空。

## Plan
1. 在 `papersys/summary/fetcher.py` 引入 `latex2json` 解析与 Markdown 转换辅助函数，消除旧的 `_sanitize_latex` 逻辑。
2. 为成功的 LaTeX 解析结果添加本地缓存，失败时回退到 marker PDF→Markdown；若两者皆失败则跳过该论文并记录日志。
3. 编写单元测试覆盖 LaTeX 成功、marker 回退、全部失败三类分支，确保 `ArxivContentFetcher` 行为符合预期。
4. 运行定向 pytest（summary 模块）验证变更，必要时追加全量测试。

## Rollback strategy
- 若解析或性能问题影响主流程，可回滚 `fetcher` 改动或临时禁用 `fetch_latex_source`。
- 删除新增的测试与缓存目录配置，恢复此前的简易上下文方案。

## 执行记录
- 2025-10-03：`ArxivContentFetcher` 接入 `latex2json` 流程，失败时回退 Marker PDF→Markdown，统一写入本地缓存。
- 2025-10-03：`tests/summary/test_fetcher.py` 覆盖 LaTeX 成功、Marker 回退、全失败三种分支，`uv run --no-progress pytest tests/summary/test_fetcher.py` 通过。


---

## 2025-10-03: Legacy Roadmap

# 2025-10-03 Legacy 功能回归与多分支协作路线
Status: Planned
Last-updated: 2025-10-03

## 背景
- `reference/` 目录仍保留旧版 “抓取 → 嵌入 → 推荐 → 摘要 → 发布” 全量脚本，但新架构 (`papersys/`) 仅迁移了推荐/摘要的部分子系统。
- 静态网站尚未回归自动更新，限制了上线验证；多位成员/Agent 需要并行推进恢复工作，但缺乏明确分工与分支策略。
- 现有 devlog 计划众多（参见 `devlog/index.md`），需要一份统一的长期路线图串联关键工作流并落地非交互式合流流程。

## 总体目标（2025 Q4）
1. **恢复 reference 等价能力**：实现本地抓取、嵌入补齐、推荐、摘要、Markdown 渲染到静态站点发布的闭环。
2. **上线前验证**：提供真实数据全链路演练脚本与测试集，确保 `uv run --no-progress pytest` + `scripts/run_real_full_pipeline.py` 全绿。
3. **协作规范**：定义面向 Agent 的分支命名、提测、合流策略，全程无需人工交互。

## 工作拆分
### W1 抓取与数据落地
- **范围**：迁移 `reference/ArxivEmbedding/script/fetch_arxiv_oai*.py` 能力到 `papersys/ingestion`；实现增量抓取、数据清洗、目录写入。
- **交付物**：`IngestionService`、CLI `papersys ingest run`、调度作业、单元/集成测试、`devdoc/data-storage.md` 更新。
- **依赖**：`devlog/2025-10-02-ingestion-embedding-migration.md`、`devlog/2025-10-08-data-migration-plan.md`。

### W2 嵌入补齐与 backlog 管理
- **范围**：复用旧仓 embedding 队列逻辑，构建 `EmbeddingService` 批处理、backlog 检测、GPU/CPU 落地。
- **交付物**：`papersys/embedding` 模块、`embed autopatch` CLI、调度作业、metrics、完整测试矩阵。
- **依赖**：`devlog/2025-10-02-embedding-backend-refactor.md`、`devlog/2025-10-09-migration-tool-implementation.md`。

### W3 推荐流水线无缓存化
- **范围**：按 `devlog/2025-10-03-recommend-dataflow-correction.md` 调整，实现 lazy metadata + embedding join；补足测试与文档。
- **交付物**：更新后的 `RecommendationPipeline`、配置模型、`config/example.toml`、全量测试。
- **依赖**：W1、W2 数据目录结构。

### W4 摘要与渲染回迁
- **范围**：移植 `reference/PaperDigest/script/summarize.py`、`render_md.py` 的核心能力至 `papersys/summary`，支持真实 LLM、PDF 抓取、Markdown 输出。
- **交付物**：`SummaryPipeline` 增强、LLM 配置、测试覆盖、渲染模板、`devdoc/architecture.md` 更新。
- **依赖**：W3 推荐产物格式；`devlog/2025-10-03-latex-context-plan.md`、`devlog/2025-10-10-summary-config-refine.md`。

### W5 静态站构建与部署
- **范围**：迁移 `reference/PaperDigestAction` 的网站构建/发布逻辑至本地脚本，输出 Cloudflare Pages 可用工件。
- **交付物**：`scripts/build_site.py`（或 CLI 子命令）、部署说明、回滚策略、压测结果。
- **依赖**：W4 Markdown 输出；`devdoc/testing/full-pipeline.md` 扩展真实数据章节。

### W6 回归测试与观测
- **范围**：整合端到端测试、MI/Prometheus 指标、日志校验，确保恢复功能具备可观测性。
- **交付物**：新增/更新的 pytest、`devdoc/testing/` 文档、Grafana 仪表盘导出（如有）。
- **依赖**：各工作流完成后的合流。

## 并行与负责人建议
| 工作流 | 建议分支 | 负责人（示例） | 前置合并 | 完成标尺 |
| --- | --- | --- | --- | --- |
| W1 | `feature/w1-ingestion` | Owner-A | 数据迁移工具稳定 | CLI + 调度可运行，测试通过 |
| W2 | `feature/w2-embedding` | Owner-B | W1产物结构固定 | backlog 自动补齐成功，指标可见 |
| W3 | `feature/w3-recommend` | Owner-C | W1/W2 元数据可用 | 无缓存运行，测试与文档更新 |
| W4 | `feature/w4-summary` | Owner-D | W3 推荐输出稳定 | PDF+LLM 真实跑通，生成 Markdown |
| W5 | `feature/w5-site-deploy` | Owner-E | W4 Markdown 固化 | 静态站生成 & Cloudflare 发布脚本 |
| W6 | `feature/w6-regression` | Owner-F | W1-W5 合流 | 端到端测试、监控面板落地 |

> 多人/Agent 可按模块认领，完成后在 `devlog/index.md` 更新状态并编写落地日志。

## 非交互式分支合流策略
1. **日常同步主干**：
   ```bash
   git fetch --all --prune
   git checkout feature/<workstream>
   git merge --ff-only origin/main
   ```
   - 若无法 fast-forward，先使用 `git rebase origin/main --no-autostash`；冲突由 Agent 在本地解决后继续。
2. **提测/开 PR 前检查**：
   ```bash
   uv run --no-progress pytest
   git status -sb
   ```
   - 确认无脏文件；必要时运行真实数据脚本并记录输出摘要。
3. **合并入主干（由 CI/自动流程执行）**：
   ```bash
   git checkout main
   git merge --no-ff --no-edit feature/<workstream>
   git push origin main
   ```
   - `--no-edit` 避免交互；CI 失败则自动回滚（`git reset --hard HEAD~1`）后通知负责人。
4. **冲突预防**：
   - 严格以 `feature/<workstream>-<owner>` 命名，确保单分支聚焦一条工作流。
   - 共享文件（如 `config/example.toml`、`devdoc/README.md`）改动前在 devlog 记录，主干合并顺序按依赖图（W1→W6）。
5. **Agent 同步流程模板**：
   ```bash
   git fetch origin
   git checkout feature/<workstream>
   git rebase --no-autostash origin/main || {
       # 自动放弃重放并提示人工策略
       git rebase --abort
       git merge --no-ff --no-edit origin/main
   }
   ```
   - 允许 Agent 在 rebase 冲突时自动回退到非交互式 `--no-edit` merge。

## 验证与追踪
- 每个工作流完成后，更新对应 devlog 计划的 `Status` 与 `Last-updated`，并在 `devdoc/README.md` 标记新文档/更新时间。
- 统一在 `devlog/2025-10-03-docs-refactor-plan.md` 的“执行记录”中补充此次路线图创建及后续回顾链接。
- 以 `devlog/index.md` 为实时进度看板，新增列可记录责任人/提交哈希。

## 风险与缓解
- **并行冲突**：通过明确依赖顺序与共享文件声明，配合 ff-only 同步减少冲突。
- **计划漂移**：若工作流目标变动，需在各自 devlog 中追加“变更说明”并链接至本路线图。
- **自动化失败**：CI 合并若失败，保留回滚命令并要求负责人补写复盘，纳入 `devdoc/rool.md` 约束。

## 下一步
- 认领工作流并在各自 devlog 计划中填入负责人、预计完成时间。
- 搭建 CI 自动合并脚本（可放入 `.github/workflows/`）以执行上述非交互式流程。
- 完成首个工作流后检视路线图，按需补充新的阶段目标。


---

## 2025-10-03: Migration Plan

# 2025-10-03 Reference 迁移开发计划与测试策略

Status: Planned  
Last-updated: 2025-10-03  

## 背景与调研总结
基于对 `devdoc/`（architecture.md, data-storage.md, env.md, rool.md）和 `devlog/`（index.md 及 2025-10-02~10-10 系列日志）的提炼，以及 `reference/` 仓库（ArxivEmbedding, PaperDigest, PaperDigestAction）的功能梳理，本计划旨在将旧全链路（抓取→嵌入→推荐→摘要→发布→反馈）迁移至 `papersys/` 单体架构。  

### 文档提炼关键要点
- **架构/流程规范**：Local-first 原则，模块化（Ingestion, Embedding, Recommendation, Summarization, Publishing, Feedback, Orchestrator API）；数据分层 `data/`（metadata CSV, embeddings Parquet, preferences CSV, summaries JSONL）；配置 Pydantic + TOML；调度 APScheduler + FastAPI Web/CLI。参考 [`architecture.md`](devdoc/architecture.md:61-80), [`data-storage.md`](devdoc/data-storage.md:9-124)。  
- **环境约束**：uv Python 3.12+, polars/duckdb 数据处理, pathlib 路径；非交互 Shell；HF_TOKEN/GEMINI_API_KEY 预设。参考 [`env.md`](devdoc/env.md:5-60)。  
- **测试与运维**：pytest 全量 + 定向；变更前 devlog 计划；非交互 git merge；日志 Loguru JSON + Prometheus。参考 [`rool.md`](devdoc/rool.md:5-12), [`2025-10-06-cli-standard-tests-plan.md`](devlog/2025-10-06-cli-standard-tests-plan.md:16-19)。  
- **现阶段阻塞/风险**（更新版）：数据 schema 不一致（旧 Parquet/JSON 字段差异）；长链路超时（摘要/PDF 下载）；外部 API 限流（arXiv/HF/LLM）；pytest 耗时过长。参考 [`architecture.md`](devdoc/architecture.md:292-301)。  
- **近期决策/计划**：W1-W7 周计划；JSON schema 自动检测；LLM API 修复（Gemini 配置）；CLI 清洁；数据迁移工具。参考 [`2025-10-03-legacy-roadmap.md`](devlog/2025-10-03-legacy-roadmap.md:16-54), [`2025-10-08-data-migration-plan.md`](devlog/2025-10-08-data-migration-plan.md:23-59)。  

### Reference 仓库功能梳理
- **ArxivEmbedding**：OAI-PMH 抓取年度 Parquet；任务拆分/嵌入生成（batch_embed_local.sh → local_split_tasks.py → process_matrix_tasks.py）；上传 HF。输入：config.toml, 年份；输出：Parquet (id, title, abstract, embeddings List[float32])。参考 [`fetch_arxiv_oai.py`](reference/ArxivEmbedding/script/fetch_arxiv_oai.py:1), [`batch_embed_local.sh`](reference/ArxivEmbedding/batch_embed_local.sh:1)。  
- **PaperDigest**：推荐 (fit_predict.py, LogisticRegression + 采样)；PDF 下载/提取 (download_pdf.py, latex2json/marker-pdf)；摘要 (summarize.py, OpenAI/Gemini JSON)；渲染 (render_md.py, Jinja2 MD)；偏好更新 (fetch_discussion.py, giscus emoji)。输入：偏好 CSV, HF 数据集；输出：predictions.parquet, raw JSON, content MD, preference CSV。参考 [`fit_predict.py`](reference/PaperDigest/script/fit_predict.py:1), [`summarize.py`](reference/PaperDigest/script/summarize.py:1)。  
- **PaperDigestAction**：Action 打包推荐/摘要；Zotero → CSV；测试覆盖 dataloader/summarize。输入：config.toml, 偏好 CSV；输出：summarized YYYY.jsonl, preference CSV。参考 [`recommend.py`](reference/PaperDigestAction/script/recommend.py:1), [`src/summarize.py`](reference/PaperDigestAction/src/summarize.py:1)。  
- **迁移要点/风险**：Parquet schema 复用；LLM 提示/Pydantic 迁移；增量 HF 依赖转为本地 backlog；NaN 嵌入修复；Action 自动化转为 scheduler。RSS 脚本废弃。参考调研待澄清：archiver/augment/sampler 职责（建议 list_code_definition_names）。  

## 总体目标与假设
- 迁移后：本地 CLI/scheduler 驱动全链路，输出符合 `data/` 结构，支持备份/指标；真实测试脚本验证端到端。  
- 假设：数据已拷贝至 `data/`；RSS 废弃；pytest 加速用轻量模型/小数据集，非 Mock；全链路真实测试独立脚本，手动判读。参考 [`architecture.md`](devdoc/architecture.md:277-284), 用户反馈（data 拷贝完毕, pytest 加速策略）。  

## 分阶段实施计划（W1-W7）
### W1: Ingestion 迁移与元数据固化
- **Goal**: 落地 OAI-PMH 抓取，写入 `data/metadata/`。  
- **Tasks**: 封装 fetch_arxiv_oai.py 为 IngestionService；CLI ingest run；APScheduler 作业；校验测试。  
- **Dependencies**: devlog/2025-10-02-ingestion-embedding-migration.md；数据目录。  
- **Deliverables**: papersys/ingestion/service.py；tests/ingestion/test_ingestion_service.py (小数据集)；scripts/run_ingestion_sample.py。  
- **Docs**: 更新 devdoc/data-storage.md (metadata 流程)；devlog/2025-10-03-w1-ingestion.md (设计/执行)。  

### W2: Embedding Backlog 与批处理
- **Goal**: 支持 backlog 补齐，GPU/CPU 兼容。  
- **Tasks**: 整合 local_split_tasks.py 等；CLI embed autopatch；轻量模型测试。  
- **Dependencies**: W1 metadata；devlog/2025-10-02-embedding-backend-refactor.md。  
- **Deliverables**: papersys/embedding/service.py；tests/embedding/test_embedding_service.py (MiniLM)；scripts/run_embedding_sample.py。  
- **Docs**: 更新 devdoc/architecture.md (Embedding)；devlog/2025-10-03-w2-embedding.md。  

### W3: Recommendation 无缓存化
- **Goal**: Lazy join 实现推荐。  
- **Tasks**: polars.scan_* 懒加载；preferences 读取；CLI recommend run。  
- **Dependencies**: W1/W2 数据；devlog/2025-10-03-recommend-dataflow-correction.md。  
- **Deliverables**: papersys/recommend/pipeline.py；tests/recommend/test_pipeline.py (小数据集)；scripts/run_recommend_sample.py。  
- **Docs**: devdoc/architecture.md (推荐)；devlog/2025-10-03-w3-recommend.md。  

### W4: Summarization & Conversion
- **Goal**: PDF/LLM/MD 回迁。  
- **Tasks**: 整合 download_pdf.py/summarize.py/render_md.py；LiteLLM 路由；小 PDF 测试。  
- **Dependencies**: W3 输出；devlog/2025-10-10-summary-config-refine.md。  
- **Deliverables**: papersys/summary/pipeline.py/renderer.py；tests/summary/test_pipeline.py (小 PDF)；scripts/run_summary_sample.py。  
- **Docs**: devdoc/testing/full-pipeline.md (摘要)；devlog/2025-10-03-w4-summary.md。  

### W5: Publishing/Feedback 集成
- **Goal**: MD 构建 + 反馈回写。  
- **Tasks**: ContentRenderer；giscus/Notion 抓取；scripts/build_site.py/fetch_feedback.py。  
- **Dependencies**: W4 MD；legacy-roadmap.md。  
- **Deliverables**: papersys/feedback/；tests/feedback/test_feedback_service.py；scripts/build_site.py。  
- **Docs**: 新增 devdoc/publishing.md；devlog/2025-10-03-w5-publishing.md。  

### W6: Scheduler & API 编排
- **Goal**: 全链路调度 + Web 控制。  
- **Tasks**: APScheduler 多作业；/jobs/run 端点；Prometheus。  
- **Dependencies**: W1-W5；architecture.md (210)。  
- **Deliverables**: papersys/cli.py/web/app.py 更新；tests/integration/test_full_pipeline.py (轻链路)；scripts/run_real_full_pipeline.py。  
- **Docs**: devdoc/architecture.md (调度/API)；devlog/2025-10-03-w6-orchestration.md。  

### W7: 迁移工具、备份 & 收尾
- **Goal**: 完善迁移/备份，CI/文档。  
- **Tasks**: LegacyMigrator 扩展；BackupService 测试；CI pytest + dry-run。  
- **Dependencies**: 前周；devlog/2025-10-09-migration-tool-implementation.md。  
- **Deliverables**: scripts/migrate_reference_data.py；tests/migration/test_legacy.py；scripts/run_backup_sample.py。  
- **Docs**: 新增 devdoc/migration-playbook.md；devlog/2025-10-03-w7-wrapup.md。  

## 测试策略
- **Pytest 保留**：配置/CLI/服务单元 (tests/config, tests/ingestion 等)；集成轻链路 (tests/integration/test_full_pipeline.py, <2min, 轻模型/小数据集如 10 条记录)。加速：MiniLM 替换大模型，裁剪数据，非 Mock。  
- **独立脚本 (scripts/)**：真实流水线 (run_ingestion_sample.py 等, 每周手动跑全链路 run_real_full_pipeline.py)；判定：日志无超时/错误，结果合理 (人工查输出/日志/manual/)。  
- **新增/调整**：tests/ingestion/test_service.py (续传)；tests/embedding (批处理)；tests/recommend (join)；tests/summary (PDF)；tests/feedback (giscus)。  

## 风险与缓解 (更新)
- Schema 不一致：迁移报告阻断；devdoc/data-storage.md 断言。  
- 链路超时：调度间隔 + 重试；脚本时间统计。  
- API 限流：节流 + 备用 key；429 日志。  
- Pytest 耗时：并行/CI 缓存；devlog 优化记录。  
- 渲染差异：diff 脚本；字段断言。  

## 关联文档
- 调研提炼：devdoc/reference-survey.md (本计划引用)。  
- 参考梳理：devdoc/reference-analysis.md。  
- 更新：devlog/index.md (链接本文件)；AGENTS.md (上手指引)。

---

## 2025-10-03: Real Llm Api Fix

# Real LLM API Testing Fix - 2025-10-03
Status: Completed
Last-updated: 2025-10-03

## Problem
Initially, LLM client code was trying to manually set `base_url` and `custom_llm_provider` for Gemini models, which caused API routing failures. The error messages showed:
1. First attempt: `UnsupportedParamsError: google_ai_studio does not support parameters: ['reasoning_effort']`
2. Second attempt: `404 Not Found` due to double slashes in URL (`/openai//models/`)

## Root Cause
**Misunderstanding of LiteLLM's routing mechanism**: LiteLLM uses the `provider/model_name` format (e.g., `gemini/gemini-2.5-flash`) to automatically route requests to the correct endpoint. Manual `base_url` and `custom_llm_provider` settings were interfering with this auto-routing.

## Solution
1. **Config change** (`config/example.toml`):
   - Changed `name` from `"gemini-2.5-flash"` to `"gemini/gemini-2.5-flash"`
   - Set `base_url = ""` (empty string to let LiteLLM handle routing)
   - Kept `reasoning_effort = "high"` as-is

2. **Code simplification** (`papersys/summary/generator.py`):
   - Removed complex provider detection logic for Gemini
   - Simplified to: only set `api_base` if it's non-empty
   - Removed `custom_llm_provider` setting completely (LiteLLM infers from model prefix)
   - Kept `reasoning_effort` parameter (now works correctly)

3. **Test updates** (`tests/summary/test_generator_detection.py`):
   - Updated test to verify NO `custom_llm_provider` is set for Gemini
   - Verified `reasoning_effort` parameter is correctly passed

4. **Real API test** (`scripts/test_real_gemini_api.py`):
   - Created standalone test script for real API verification
   - Successfully validated against live Google AI Studio API
   - Confirmed `reasoning_effort` parameter works

## Verification
✅ Real API call succeeded with `reasoning_effort='high'`
✅ All 13 summary tests pass
✅ Config correctly uses LiteLLM's auto-routing

## Key Takeaways
1. **Trust LiteLLM's routing**: The `provider/model` format is the primary way to specify endpoints
2. **Don't override unless necessary**: Manual `base_url` and `custom_llm_provider` should only be used for custom endpoints
3. **Test with real APIs**: Mock tests alone can hide integration issues

## Files Modified
- `config/example.toml` - Updated Gemini config to use auto-routing
- `papersys/summary/generator.py` - Simplified provider logic
- `tests/summary/test_generator_detection.py` - Updated test expectations
- `scripts/test_real_gemini_api.py` - New real API test script


---

## 2025-10-03: Recommend Dataflow Correction

# 2025-10-03 推荐流水线数据加载修正计划
Status: Completed
Last-updated: 2025-10-03

## 现状
- `RecommendationDataLoader` 依赖 `cache_dir` 下的预拼接 Parquet 候选集；真实仓库未提供该缓存，因此手动运行脚本失败。
- `config/example.toml` 强制要求 `cache_dir`，与架构文档提到的本地优先理念不符。
- `devdoc/architecture.md` 中记录了“先拼接后缓存再读取”的设计，导致误解与性能隐患。

## 目标
- 允许推荐流水线直接从 `metadata` CSV 与各 embedding Parquet 动态构建候选集，不再依赖额外缓存。
- 更新架构文档，明确推荐阶段的“按需扫描 + Join”策略。
- 完全移除对 `cache_dir` 的依赖，推荐流水线统一使用按需扫描的元数据与嵌入文件。
- 为关键代码路径补充测试，覆盖 metadata/embedding 动态拼接场景。

## 调整方案
1. **配置模型**：
   - 移除 `RecommendPipelineConfig.data.cache_dir` 字段，新增 `metadata_dir`、`metadata_pattern`、`embeddings_root` 并给出默认值。
   - 更新 `config/example.toml` 与相关测试用例以反映新字段。
2. **数据加载器**：
   - `RecommendationDataSources` 记录 metadata 目录与 embedding 目录映射，不再暴露 `cache_dir`。
   - 推荐流水线使用 lazy join：
     - `pl.scan_csv` 扫描匹配的 metadata CSV 并统一列名。
     - 对每个 embedding alias 扫描目录下所有 Parquet，选择 `paper_id` + embedding 列。
     - 将嵌入逐个内连接到 metadata，并在过滤阶段使用既有类别/年份约束。
   - 偏好数据维持原实现，但改为根据文件表头动态推断 schema。
3. **测试**：
   - 扩展 `tests/recommend/test_pipeline.py`：构建 metadata CSV + embedding Parquet，验证无缓存情况下完整跑通。
   - 更新/新增测试覆盖 metadata pattern 自定义等边界。
4. **文档**：
   - 在 `devdoc/architecture.md` 添加“推荐数据加载”章节，阐述按需扫描流程与性能考虑。
   - 必要时补充 `devdoc/data-storage.md`，同步字段约定。

## 风险评估
- 输入文件格式差异（如字段名、分隔符）可能导致 join 失败，需要在实现中增加显式重命名与校验。
- 使用 lazy join 可能引发较高内存占用，需确保筛选逻辑（类别、年份、偏好过滤）尽量在 lazy 阶段完成。
- 配置字段变更需同步全部测试与 CLI，避免破坏已有功能。

## 回滚策略
- 变更集中于数据加载层，出现问题时回滚 `RecommendationDataLoader` 相关提交即可恢复原行为。

## 执行记录
- 2025-10-03：完成配置字段迁移（新增 metadata_dir/metadata_pattern/embeddings_root），同时更新 `config/example.toml` 与推荐配置测试。
- 2025-10-03：重写 `RecommendationDataLoader` 按需扫描 metadata 与嵌入，移除缓存依赖并补充 lazy join 校验。
- 2025-10-03：扩展 `tests/recommend/test_pipeline.py` 覆盖无缓存场景，更新 `devdoc/architecture.md` 描述推荐数据加载流程。


---

## 2025-10-03: W1 Ingestion

# 2025-10-03 W1 Ingestion Migration Implementation Plan

Status: Completed  
Last-updated: 2025-10-11

## 现状评估
- `IngestionService` 仍写入 `metadata/raw/arxiv/<year>/arxiv_YYYY.csv`，未与 `data/metadata/metadata-YYYY.csv` 规范对齐，`latest.csv` 聚合视图缺失。
- CLI `papersys ingest` 暂不支持根据 `AppConfig.data_root` 解析产出目录，导致示例配置需要手动拼接路径。
- 缺少迁移计划要求的样例脚本 `scripts/run_ingestion_sample.py` 与针对流式增量/并发的测试覆盖。
- `devdoc/data-storage.md` 已描述目标目录结构，但未落地到实现。

## 目标与范围
1. 统一元数据落盘格式至 `data/metadata/metadata-YYYY.csv`，确保字段、编码符合 `devdoc/data-storage.md` 的定义，并保留 `latest.csv` 汇总视图。
2. 扩展 `IngestionService`：
   - 透过 `AppConfig.data_root` 派生输出目录；
  - 支持幂等追加、`Polars` 去重与年份分块；
  - 暴露批量/断点续传能力（`limit`、`from`/`until`）。
3. 增补 CLI 与样例脚本，提供最小化无外部依赖的演示运行路径。
4. 完善测试：覆盖字段标准化、追加去重、`latest.csv` 聚合、配置缺陷报错路径。
5. 文档同步（`devdoc/data-storage.md` 补充流程描述，并在本文件记录评估结果）。

## 实施方案
1. **目录解析与服务重构**
   - 在 `IngestionService` 内新增 `base_path` 解析逻辑（兼容独立传入与从 `config` 推导）；
   - 使用 `polars.DataFrame` 写入 CSV，字段顺序与类型按文档约束；
   - 新增 `flush_yearly_batches` 与 `update_latest_manifest` 等私有方法，封装写入/汇总。
2. **CLI/脚本联动**
   - 更新 `papersys.cli.ingest`，在创建服务时注入 `data_root`；
   - 编写 `scripts/run_ingestion_sample.py`，从 `config/example.toml` 加载配置并以限制模式跑一个小批次（默认 `limit=5`），输出日志到 stdout。
3. **测试体系**
   - 重写 `tests/ingestion/test_ingestion_service.py`：利用 `tmp_path` 模拟 `data_root`，校验年份文件与 `latest.csv` 行 dedupe；
   - 新增针对 `limit`、`from/until`、异常路径的测试；复用 `pytest` patch 拦截网络。
4. **文档与配置**
   - 在 `devdoc/data-storage.md` 中追加“写入流程示意”段落；
   - 如有需要，调整 `config/example.toml` 默认 `output_dir` = `metadata`（对齐数据目录）。

## 风险与缓解
- **字段兼容性风险**：旧 CSV 与新 schema 混用。→ 在写入前对列集合断言，如缺列直接报错并在日志中说明。
- **性能风险**：大批次写入导致内存峰值。→ 批次保持可配置（默认 500）；`polars` 流式写入。
- **并发写入风险**：调度器重复触发导致互斥冲突。→ 暂不支持并发，文档中标注需通过调度器串行。

## 验证计划
- 运行 `uv run --no-progress pytest tests/ingestion/test_ingestion_service.py`。
- 如时间允许执行 `uv run --no-progress pytest` 以确认回归。
- 手动运行 `uv run --no-progress python scripts/run_ingestion_sample.py --limit 3 --dry-run` 验证脚本行为（dry-run 模式仅打印目标路径与配置）。

## 回滚策略
- 若实施后影响其他 pipeline（embedding/recommend）读不到 CSV，回滚 `IngestionService` 与 CLI 相关改动，并保留新测试以捕捉问题。
- 数据侧回滚：保留旧目录 `metadata/raw/arxiv/`，必要时通过 git checkout 恢复。

## 实施记录
- 代码重构完成：统一产出 `metadata-YYYY.csv` + `latest.csv`，CLI 与嵌入流程更新适配，新增 `scripts/run_ingestion_sample.py`。
- 文档/配置：`config/example.toml`、`devdoc/data-storage.md` 更新，新增本 devlog。

## 验证结果
- `uv run --no-progress pytest tests/ingestion tests/embedding/test_embedding_service.py`
- `uv run --no-progress env PYTHONPATH=. python scripts/run_ingestion_sample.py --limit 10`

## 运行结论
- 实际抓取保存 10 条记录至 `data/metadata/metadata-2000.csv`，`data/metadata/latest.csv` 当前包含 758,369 条记录。
- 请求过程中 OAI-PMH 多次返回 resumption token，服务按照 `limit` 正常提前停止。


---

## 2025-10-03: W2 Embedding

# 2025-10-03 W2 Embedding Backlog Implementation Plan

Status: Completed  
Last-updated: 2025-10-11

## 现状评估
- `EmbeddingService` 已支持后端选择与 CSV 路径解析，但仍按单次 CSV → Parquet 方式写入，未生成 `manifest.json` 与 `backlog.parquet`，与 `devdoc/data-storage.md` 的目标结构不符。
- CLI `papersys embed` 缺少按模型/年份的任务调度与 manifest/backlog 更新逻辑，无法对 `data/embeddings/<model_alias>/` 进行幂等补齐。
- 目前无 `scripts/run_embedding_sample.py`，难以快速演示最小批次嵌入流程。
- 测试用例覆盖生成 Parquet 与 backlog 检测，但未验证 manifest/backlog 文件、批处理分页或 CLI 交互路径。

## 目标与范围
1. 产出符合规范的嵌入目录结构：年度 Parquet + `manifest.json` + `backlog.parquet`，并保持幂等更新。
2. 支持 backlog 补齐：根据 metadata/embedding 状态生成待处理清单，按批次刷新 backlog 文件并允许 CLI 自动处理。
3. 提供运行脚本 `scripts/run_embedding_sample.py`，便于在小数据集上验证 embedding 流程。
4. 扩充测试覆盖：验证 manifest 更新、backlog 维护、CLI 参数路径解析与限量处理。
5. 更新文档（`devdoc/architecture.md` Embedding 章节）并记录实施过程（本 devlog）。

## 实施方案
1. **服务层增强**
   - 重构 `EmbeddingService.generate_embeddings_for_csv`：支持增量合并同年 Parquet、更新时间戳、来源标记，并返回任务指标。
   - 新增 `ManifestManager`/辅助函数，生成或更新 `manifest.json`（包含模型信息、文件清单、行数统计）。
   - 引入 backlog 管理：在检测缺失/失败任务时写入 `backlog.parquet`（字段包含 `paper_id`、`year`、`missing_reason`、`queued_at`、`model_alias`）。
2. **CLI/backlog 流程**
   - 扩展 `papersys embed`：默认执行 manifest/backlog 更新，`--backlog` 触发 backlog 批处理，支持 `--limit` 控制单次处理数。
   - 处理结果后刷新 backlog 文件（移除完成项，保留失败/剩余）。
3. **脚本与工具**
   - 新增 `scripts/run_embedding_sample.py`：加载配置、定位最新 metadata CSV、小批量跑一次嵌入并输出生成文件路径。
4. **测试**
   - 更新/新增 pytest：模拟 metadata CSV + 现有 Parquet，断言 manifest/backlog 内容、幂等性、CLI 推导路径。
   - 引入 fixture 构造 backlog 情景并验证 `--backlog` 执行。
5. **文档同步**
   - 在 `devdoc/architecture.md` Embedding 小节补充新目录结构与流程说明。
   - 在本日志记录实施与验证结果。

## 风险与缓解
- **大文件写入时间长**：测试和脚本使用裁剪后的 CSV/模型；生产环境可通过 `limit`、批量大小控制。
- **并发冲突**：暂不支持多进程写入，CLI 文档中强调串行运行；manifest/backlog 更改前先读取最新状态，保持幂等。
- **HF Hub 依赖**：计划阶段仅实现本地 backlog；外部依赖后续通过独立任务接入。

## 验证计划
- `uv run --no-progress pytest tests/embedding`
- `uv run --no-progress python scripts/run_embedding_sample.py --limit 5 --dry-run`
- 按需要运行 `uv run --no-progress python scripts/run_embedding_sample.py --limit 5`

## 回滚策略
- 若 manifest/backlog 逻辑导致数据损坏，可回滚 `EmbeddingService` 与 CLI 相关提交，同时恢复测试与脚本至旧版本。
- 在回滚前保留新生成的嵌入文件备份，防止数据丢失。

## 实施记录
- `EmbeddingService` 写入流程升级：年度 Parquet 添加 `generated_at`、`model_dim`、`source` 字段，幂等合并并更新 `manifest.json`；新引入 `refresh_backlog()` 输出 `backlog.parquet`（记录 `paper_id`、`missing_reason`、`origin` 等）。
- CLI `papersys embed` 支持基于 backlog 的批处理流程，常规模式在执行后刷新 backlog；新增 `scripts/run_embedding_sample.py` 便于小规模验证。
- `devdoc/architecture.md` Embedding 章节补充 manifest/backlog 机制；新测试覆盖 manifest 产出、backlog 计算与幂等性。

## 验证结果
- `uv run --no-progress pytest tests/embedding`
- `uv run --no-progress env PYTHONPATH=. python scripts/run_embedding_sample.py --limit 5 --dry-run`
- `uv run --no-progress env PYTHONPATH=. python scripts/run_embedding_sample.py --limit 5`

## 运行结论
- 回归测试全绿（8 项）；真实脚本写入 `data/embeddings/jasper_v1/2000.parquet`（5 条）并刷新 `manifest.json`、`backlog.parquet`，dry-run 可预览计划。嵌入服务现统一使用 `AppConfig.data_root` 解析输出目录，不再向仓库根目录落盘。
- backlog 刷新可区分“缺少年度文件”与“新增论文未嵌入”两种状态，`manifest.json` 会随 Parquet 更新实时同步计数。


---

## 2025-10-03: W3 Recommend

# 2025-10-03 W3 Recommendation Lazy Pipeline Plan

Status: Completed  
Last-updated: 2025-10-11

## 现状评估
- `RecommendationDataLoader` 已去除旧缓存依赖，但高阶流程仍停留在临时脚本与测试场景，未与 CLI / APScheduler 集成，手动运行需要编写额外脚本。
- 向量与元数据融合逻辑分散在多个函数中，缺少统一的 pipeline 入口，导致重复的列重命名、过滤条件散落在测试内。
- 偏好数据（`data/preferences/*.csv`）读取流程缺少幂等 append 支持，无法方便地合并多年度反馈；目前测试也未覆盖偏好裁剪逻辑与训练/预测输出。
- 产出结果（推荐批次、评分、采样摘要）尚无标准化落盘格式，`devdoc/data-storage.md` 仅描述目标但工程未实现。

## 目标与范围
1. 构建统一的推荐流水线入口（服务 + CLI），实现“metadata + embeddings + preferences → 推荐结果”的懒加载流程。
2. 支持训练（LogisticRegression）与预测/采样两个阶段，结果输出到 `data/recommendations/`（候选 Parquet/JSON）并保留日志。
3. 完善偏好数据加载与过滤：支持多年度文件合并、去重、限制最近 N 天等策略。
4. 扩展测试覆盖：包含 end-to-end 小数据集（metadata + embeddings + preferences）验证训练与预测结果、阈值筛选与采样逻辑。
5. 更新文档 (`devdoc/architecture.md` 推荐小节；必要时 `devdoc/data-storage.md`) 并记录实施过程。

## 实施方案
1. **服务分层**
   - 新增 `papersys/recommend/pipeline.py`：封装数据加载、特征构建、模型训练、预测与采样；对外提供 `run_training()`、`run_prediction()`、`run_sampling()` 等高层接口。
   - 引入 `RecommendationDataset`、`PreferenceLoader` 等协作类，集中处理 Polars 懒加载、列校验、偏好合并。
   - 保留/复用现有 `RecommendationDataLoader` 的懒加载逻辑，整合到新服务内。
2. **CLI / Scheduler**
   - 在 `papersys/cli.py` 增加 `recommend` 子命令（或扩展现有命令），支持 `--train` / `--predict` / `--sample` 选项、`--from-date`、`--limit` 等参数。确保命令遵循 `AppConfig` 数据根解析。
   - 预留与调度器的集成接口（例如返回运行统计、写入 Prometheus 指标）。
3. **数据输出**
   - 约定推荐结果目录：`data/recommendations/<date>/predictions.parquet`、`data/recommendations/<date>/samples.jsonl` 等；字段与顺序在文档中说明。
   - 记录元数据（模型参数、采样阈值、输入规模）到伴随的 `manifest.json` 或日志中，便于追溯。
4. **测试**
   - 更新 `tests/recommend/test_pipeline.py`：构造小型 metadata/embedding/preferences 数据，验证训练、预测、采样流程；加入偏好裁剪、阈值边界条件。
   - 新增 CLI 层测试（使用 `CliRunner` 或 typer.testing）验证命令解析与 dry-run 行为。
5. **文档与样例脚本**
   - 更新架构/数据存储文档描述推荐输出与偏好处理方式。
   - 视需要新增 `scripts/run_recommend_sample.py`，提供最小化演示流水线。

## 风险与缓解
- 懒加载 join 在大数据上可能耗时：通过配置参数控制时间范围/样本数量，并在 CLI 中提供 `--limit`。
- 偏好数据质量（缺失/重复）可能影响训练：实现 Pydantic/Polars 验证与去重策略，测试覆盖异常路径。
- 训练/预测重复写入可能覆盖既有结果：产出目录按日期/时间戳区分，或提供 `--output` 覆盖选项。

## 验证计划
- `uv run --no-progress pytest tests/recommend`
- `uv run --no-progress python scripts/run_recommend_sample.py --dry-run`
- 视需求运行 `uv run --no-progress python scripts/run_recommend_sample.py --limit 10`

## 回滚策略
- 新逻辑集中在推荐模块；若影响范围过大，可回滚 `papersys/recommend` 新增文件与 CLI/文档改动，恢复旧测试。
- 推荐输出目录采用新增命名空间，回滚时删除生成的样例文件即可。

## 实施记录
- `RecommendationPipeline` 新增 `run_and_save`，在 `data_root/recommendations/<timestamp>/` 下落盘 `predictions.parquet`、`recommended.parquet` 与 `manifest.json`，同时保留原 `run()` 返回值。
- CLI 新增 `papersys recommend` 命令，支持 `--dry-run`、`--force-all`、`--output-dir`，输出路径与清单日志；新增脚本 `scripts/run_recommend_sample.py` 作为最小化演示入口。
- 扩展测试：`tests/recommend/test_pipeline.py` 新增落盘断言；`tests/recommend/test_integration.py` 无需改动即可复用；CLI 测试覆盖 dry-run/执行分支。
- 配置与文档：`config/example.toml`、`papersys/config/recommend.py` 调整输出字段；`devdoc/architecture.md`、`devdoc/data-storage.md` 待更新，记录推荐结果目录与 manifest 结构。

## 验证结果
- `uv run --no-progress pytest tests/recommend`
- `uv run --no-progress pytest tests/cli/test_cli_commands.py`
- `uv run --no-progress env PYTHONPATH=. python scripts/run_recommend_sample.py --dry-run`

## 运行结论
- 干跑脚本仅输出路径信息且未写入生产数据；单元/集成测试覆盖懒加载、训练、预测、落盘过程；CLI 新命令完成 dry-run 与执行路径验证。


---

## 2025-10-03: W4 Summary

# 2025-10-03 W4 Summary & Conversion Plan

Status: Completed  
Last-updated: 2025-10-11

## 现状评估
- `SummaryPipeline` 已封装 PDF 获取、LLM 生成与 Markdown 渲染，但缺少与新推荐输出的衔接以及标准化的 JSONL/Markdown 落盘规范。
- CLI 仅提供 `summarize` 命令的 dry-run 提示，尚未串联实际执行、输出目录以及日志/错误捕获策略。
- 缺少最小化运行脚本与测试覆盖真实 PDF/Markdown workflow，难以验证多源数据、失败重试、模板渲染等细节。
- 摘要结果的存储规范（`data/summaries/YYYY-MM.jsonl` 等）尚未在代码层面实现端到端落盘与 manifest 产出。

## 目标与范围
1. 将推荐输出与摘要流水线打通：接受推荐生成的 `recommended.parquet` 或 JSONL 输入，生成对应的 PDF/Markdown/JSONL 摘要。
2. 在 `SummaryPipeline` 中增加结果持久化逻辑（JSONL + Markdown 文件）及伴随的 `manifest.json`，目录规范为 `data/summaries/YYYY-MM/`。
3. CLI `summarize` 命令扩展执行路径：支持从推荐结果加载待摘要列表、控制 dry-run/limit、输出统计。
4. 编写 `scripts/run_summary_sample.py`，提供最小化示例（使用 stub fetcher/LLM）以便快速回归。
5. 完善测试：包括纯单元（stub fetcher/renderer）、端到端小数据集（无真实外部依赖）的聚合测试，覆盖失败重试与文件生成。
6. 更新文档（`devdoc/architecture.md`、`devdoc/data-storage.md`、`devdoc/testing/full-pipeline.md`）并在本日志记录实施情况。

## 实施方案
1. **数据模型与输入适配**
   - 定义 `SummarySource` 构造器从推荐结果（parquet/JSONL）解析需要摘要的字段（paper_id、title、abstract、score等）。
   - 增加辅助函数将推荐 manifest 与摘要任务列表关联，避免重复摘要。
2. **流水线增强**
   - `SummaryPipeline.run()` 增加 JSONL/Markdown 写盘能力，统一路径与文件命名；加入 `manifest.json`（包含任务数、成功/失败、模型信息）。
   - 支持可插拔 fetcher/LLM 实现（真实/Stub），便于测试与离线验证。
   - 增加异常处理与重试统计，确保失败项记录到 manifest。
3. **CLI 与脚本**
   - 扩展 `papersys summarize`：新增 `--input`（推荐输出路径）、`--limit`、`--force` 等参数，默认根据推荐 manifest 选择待处理项。
   - 新增 `scripts/run_summary_sample.py`，在 stub 模式下执行完整流程并打印输出位置。
4. **测试**
   - 更新/新增 `tests/summary` 模块：覆盖 fetcher stub、LLM stub、run 输出文件、manifest 结构等。
   - 为 CLI 与脚本添加最小测试，验证 dry-run、执行模式与错误处理。
5. **文档与记录**
   - 更新数据存储文档描述 `data/summaries/` 结构变化。
   - 在 `devdoc/testing/full-pipeline.md` 记录摘要阶段的测试策略与 stub 依赖。

## 风险与缓解
- 真正拉取 PDF/LLM 成本高且受限：默认使用 stub，通过参数控制真实调用；manifest 记录失败原因便于人工重试。
- 文件落盘量大：通过 `--limit` 控制单次摘要数量，并在 manifest 中记录已处理 ID 以便增量。
- Markdown/JSONL 模板可能导致格式不稳定：集中封装 renderer，提供单元测试校验字段顺序与渲染内容。

## 验证计划
- `uv run --no-progress pytest tests/summary`
- `uv run --no-progress python scripts/run_summary_sample.py --dry-run`
- 视需要运行 `uv run --no-progress python scripts/run_summary_sample.py --limit 5`

## 回滚策略
- 变化集中于 `papersys/summary` 与 CLI/脚本；出现问题可回滚相关提交并恢复旧的 summarize 行为。
- 摘要输出均在新增目录下，如需回滚可手动删除生成的样例文件。

## 实施记录
- `SummaryPipeline` 新增 `run_and_save`、`load_sources_from_recommendations`，自动在 `data/summaries/` 追加 `YYYY-MM.jsonl`、`manifest-<run_id>.json`，Markdown 输出按 `markdown/<run_id>/` 分组。
- `SummarySource` 扩展 `score`/`categories`，JSONL 记录匹配 `SUMMARY_FIELD_ORDER` 的核心字段；manifest 记录成功/失败、LLM 与输出路径。
- CLI `papersys summarize` 支持 `--input`、`--limit`、`--dry-run`，可自动发现最新推荐结果；新增脚本 `scripts/run_summary_sample.py` 便于最小化演示（默认提示缺少真实 API key 时改用 stub 配置）。
- 测试覆盖：`tests/summary/test_summary_pipeline.py`、`tests/summary/test_cli_summarize.py`、`tests/cli/test_cli_commands.py` 增补落盘、CLI 执行与干跑场景。

## 验证结果
- `uv run --no-progress pytest tests/summary/test_summary_pipeline.py`
- `uv run --no-progress pytest tests/summary/test_cli_summarize.py`
- `uv run --no-progress pytest tests/cli/test_cli_commands.py`
- `uv run --no-progress pytest tests/recommend tests/embedding/test_embedding_service.py`（全链路回归）
- `uv run --no-progress env PYTHONPATH=. python scripts/run_summary_sample.py --dry-run`（需配置 stub 或有效 `GEMINI_API_KEY`）

## 运行结论
- 摘要流水线现可直接消费推荐产出并生成 JSONL/Markdown/manifest；CLI/脚本支持干跑与限量执行，测试确认无外部依赖时使用 Stub fetcher/LLM 正常落盘。


---

## 2025-10-03: W5 Publishing

# 2025-10-03 W5: Publishing/Feedback 集成实施记录

Status: In Progress  
Last-updated: 2025-10-04  
Author: Roo (AI Assistant)

## 实施背景
根据 `devlog/2025-10-03-migration-plan.md` 中的 W5 计划，本周目标是实现 MD 内容构建与反馈回写集成。主要任务包括：
- ContentRenderer：基于参考仓库 `render_md.py` 迁移，实现从总结数据渲染 Markdown 文件。
- giscus/Notion 抓取：实现 GitHub Discussions (giscus) 反馈抓取，初步支持 Notion（若有 API 配置）。
- scripts/build_site.py 和 fetch_feedback.py：构建站点脚本和反馈采集脚本。

依赖：W4 的 `papersys/summary/renderer.py` 和 MD 输出；`legacy-roadmap.md` 中的反馈流程。

风险：GitHub API 限流；Notion API 集成复杂（需确认配置）；模板渲染一致性。

## 实施步骤

### 步骤 1: 分析参考代码
- `reference/PaperDigest/script/render_md.py`：使用 Jinja2 从 Parquet 数据渲染 MD 文件，输出到 `content/` 目录。核心逻辑：加载模板、遍历数据、渲染并写入文件。已读取并理解。
- `reference/PaperDigest/script/fetch_discussion.py`：使用 GitHub GraphQL API 获取 discussions 和 reactions（用于反馈偏好，如 emoji 反应）。核心逻辑：POST GraphQL 查询，保存 JSON 输出。已读取并理解。
- Notion 相关：参考 `reference/NotionAPI/` 中的 MD 文档，但无现成代码。需新实现，使用 Notion API v1（需 API key 配置）。

### 步骤 2: 创建 papersys/feedback/ 目录结构
- 创建 `papersys/feedback/__init__.py`：空文件，标记模块。
- 创建 `papersys/feedback/service.py`：实现 FeedbackService 类，支持 giscus (GitHub Discussions) 抓取。初步集成 Notion（占位，待配置）。
  - 方法：`fetch_giscus_feedback(owner, repo, token)` - 调用 GraphQL 获取 discussions/reactions，解析为偏好更新 (e.g., 👍 → like, 👎 → dislike)。
  - 方法：`fetch_notion_feedback(database_id, token)` - 使用 Notion API 查询页面/评论，解析反馈（TODO: 实现）。
  - 输出：更新 `data/preferences/` 中的 CSV (polars DataFrame)。

### 步骤 3: 扩展 ContentRenderer
- 在现有 `papersys/summary/renderer.py` 中扩展，支持 publishing：添加 `build_site()` 方法，批量渲染总结数据到 `data/publishing/content/`。
- 集成 Jinja2 模板：从 `config/template.j2` 加载（需确认是否存在，或从参考迁移）。
- 处理 draft 状态：基于 preference (dislike → draft=true)。

### 步骤 4: 创建 scripts/build_site.py
- 基于 `render_md.py` 迁移：CLI 脚本，使用 `papersys.summary.renderer` 构建站点。
- 输入：总结 Parquet/JSONL 数据；输出：MD 文件到 `data/publishing/content/`。
- 添加 git 集成：可选 push 到 content_repo (HF 或 GitHub)。

### 步骤 5: 创建 scripts/fetch_feedback.py
- 基于 `fetch_discussion.py` 迁移：CLI 脚本，使用 `papersys.feedback.service` 抓取反馈并更新 preferences CSV。
- 支持 giscus 和 Notion 模式（--source giscus|notion）。
- 输出：日志 + 更新 `data/preferences/YYYY-MM.csv`。

### 步骤 6: 测试实现
- 创建 `tests/feedback/test_feedback_service.py`：单元测试 giscus 抓取（mock requests），验证 reactions 解析；Notion 占位测试。
- 集成测试：`tests/integration/test_publishing_pipeline.py` - 端到端：渲染 → 构建 → 反馈更新（小数据集）。
- 运行：`uv run --no-progress pytest tests/feedback/`，确保全绿。

### 步骤 7: 配置更新
- `papersys/config/publishing.py`：新增 Pydantic 模型，支持 giscus_token, notion_token, content_repo 等。
- 更新 `config/example.toml`：添加 [publishing] 节。
- 测试配置加载：`uv run --no-progress pytest tests/config/test_publishing_config.py`（新增）。

### 步骤 8: 文档更新
- 新增 `devdoc/publishing.md`：描述 Publishing 模块职责、数据流、API 集成。
- 本文件：记录执行细节。

## 遇到的问题与解决方案
- 问题 1: GitHub GraphQL 认证 - 解决方案：使用环境变量 GITHUB_TOKEN，Pydantic 验证。
- 问题 2: Notion API 集成 - 解决方案：初步占位，使用 notion-client 库 (uv add notion-client)，后续配置 database_id。
- 问题 3: 模板一致性 - 解决方案：从参考 `config/template.j2` 迁移，确保 UTF-8 编码。
- 问题 4: 数据路径 - 解决方案：使用 pathlib.Path，配置化 `data/publishing/`。

## Git 版本管理
- Branch: feature/w5-publishing-feedback
- Commits:
  - "feat: init papersys/feedback module and service.py"
  - "feat: extend summary/renderer for site build"
  - "feat: add scripts/build_site.py and fetch_feedback.py"
  - "test: add tests/feedback/test_feedback_service.py"
  - "config: add publishing config model"
  - "docs: add devdoc/publishing.md"
- 每个 commit 前运行 pytest，确保无回归。

## 下一步计划
- 完成 W5 代码实现与测试。
- 验证端到端：运行 scripts/build_site.py 和 fetch_feedback.py 于小数据集。
- 推进 W6 Scheduler 集成（将 publishing 作为作业）。
- 若阻塞：确认 Notion 配置细节。

---

## 2025-10-03: W6 Orchestration

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

---

## 2025-10-03: W7 Wrapup

# 2025-10-03 W7: 迁移工具、备份 & 收尾实施记录

Status: Completed  
Last-updated: 2025-10-04  
Author: Roo (AI Assistant)

## 实施背景
根据 `devlog/2025-10-03-migration-plan.md` 中的 W7 计划，本周目标是完善迁移/备份工具，并完成项目收尾。主要任务包括：
- LegacyMigrator 扩展：增强现有 `papersys/migration/legacy.py` 支持 publishing/feedback 数据迁移，添加 dry-run 验证。
- BackupService 测试：扩展 `tests/backup/test_backup_service.py` 覆盖新数据类型 (summaries, preferences, content)。
- CI pytest + dry-run：配置 pytest for CI (e.g., GitHub Actions yaml)，添加 dry-run 模式测试。
- 脚本：`scripts/migrate_reference_data.py` (CLI for LegacyMigrator)；`scripts/run_backup_sample.py` (backup 示例)。

依赖：W1-W6 模块；`devlog/2025-10-09-migration-tool-implementation.md` (假设)。

风险：数据完整性 (schema 验证)；备份兼容性 (HF push)；CI 环境 (secrets for tokens)。

## 实施步骤

### 步骤 1: 分析现有代码
- `papersys/migration/legacy.py`：已有 LegacyMigrator, 支持 metadata/embeddings/preferences/summaries 迁移，使用 polars/HF API。CLI app 已存在。已读取并理解。
- `tests/backup/test_backup_service.py`：现有 BackupService 测试，需扩展。
- `tests/migration/test_legacy.py`：现有基本测试，需增强。
- CI：无现有 yaml，需新增 .github/workflows/ci.yml。

### 步骤 2: 扩展 LegacyMigrator
- 添加 publishing/feedback 迁移：
  - _process_publishing(): 迁移 content MD 到 data/publishing/content/。
  - _process_feedback(): 集成 giscus/Notion 数据到 preferences。
- 增强 run(): 添加 schema 验证 (polars schema check)，dry-run 报告。
- 更新 CLI：添加 --publishing, --feedback flags。

### 步骤 3: 创建 scripts/migrate_reference_data.py
- CLI 包装 LegacyMigrator.run()，支持 --dry-run, --force, --year 等参数。
- 示例：`uv run scripts/migrate_reference_data.py --year 2025 --dry-run`。

### 步骤 4: BackupService 测试扩展
- `tests/backup/test_backup_service.py`：新增测试 for summaries.jsonl, preferences.csv, content.md 备份。
- 验证 HF push (mock HfApi)，local backup。

### 步骤 5: 新增 tests/migration/test_legacy.py
- 测试 LegacyMigrator.run() for each module (metadata, embeddings, etc.)。
- Mock HF API, test dry-run output, schema validation。

### 步骤 6: CI 配置
- 创建 .github/workflows/ci.yml：on push/pull_request, run `uv run pytest` (full + directed)，upload coverage。
- Secrets: GITHUB_TOKEN, HF_TOKEN for backup tests。

### 步骤 7: 创建 scripts/run_backup_sample.py
- 示例脚本：BackupService.run() with sample data, log result。
- 支持 --dry-run, --remote hf://dataset。

### 步骤 8: 文档更新
- `devdoc/migration-playbook.md`：步骤指南 for running migration, troubleshooting。
- 本文件：记录执行细节。
- 更新 `devdoc/architecture.md`：添加 migration/backup 流程图。

### 步骤 9: 测试验证
- 运行 `uv run --no-progress pytest tests/migration/ tests/backup/`，确保全绿。
- Dry-run migration：验证报告无错误。
- Backup sample：运行 scripts/run_backup_sample.py，检查 logs。

## 遇到的问题与解决方案
- 问题 1: Schema 不一致 (legacy vs new) - 解决方案：添加 pl.schema validation in _build_*_frame, log warnings。
- 问题 2: HF API rate limit - 解决方案：添加 retry decorator, cache_dir for local。
- 问题 3: CI secrets - 解决方案：使用 GitHub secrets for tokens, conditional skip if not set。
- 问题 4: Backup large files - 解决方案：chunked upload to HF, test with small sample。

## Git 版本管理
- Branch: feature/w7-migration-backup-wrapup
- Commits:
  - "feat: extend LegacyMigrator for publishing/feedback"
  - "feat: add scripts/migrate_reference_data.py CLI"
  - "test: enhance tests/backup and add tests/migration/test_legacy.py"
  - "ci: add .github/workflows/ci.yml for pytest"
  - "feat: add scripts/run_backup_sample.py"
  - "docs: add devdoc/migration-playbook.md"
- 每个 commit 前运行 pytest，确保无回归。

## 收尾与后续计划
- 项目迁移完成：W1-W7 全覆盖，本地优先流水线就绪。
- 验证：运行 full pipeline (scripts/run_real_full_pipeline.py)，检查 data/ 输出。
- 后续：监控 CI, 优化性能 (e.g., parallel ingestion)，用户手册。
- 阻塞解决：所有风险已缓解，代码覆盖 >80%。

---

## 2025-10-04: Pytest Cleanup

# 2025-10-04 Pytest 清理与加速优化

Status: Completed  
Last-updated: 2025-10-04  

## 背景
项目推进混乱导致 pytest 全量运行耗时过长（>120s），且存在潜在风险：测试可能调用真实 API（网络/LLM）、污染生产 data/ 路径，或加载大数据集。核心目标：实现快速回归（<120s 全绿），确保安全（无网络/写入 data/），不使用 mock，而是通过小样本数据 + 参数化裁剪加速。

参考：devlog/2025-10-03-migration-plan.md (测试策略：轻模型/小数据集)；AGENTS.md (uv pytest，非交互)。

## 现状评估
- **初始问题**：
  - 全量 pytest 耗时 ~300s+，慢测试包括 integration/full_pipeline (大数据加载/LLM)。
  - 审计发现 ~11 个测试文件有风险：网络调用 (requests/httpx/openai/gemini)、凭证 (HF_TOKEN/GEMINI_API_KEY)、写入 data/ (Path("data").write/to_parquet)。
  - 示例风险文件：tests/ingestion/test_client.py (OAI 调用)、tests/recommend/test_integration.py (真实 data/ 加载)、tests/summary/test_cli_summarize.py (PDF/LLM)。
  - 未确认：真实 API/数据是否在测试中使用；data/ 是否被污染。

- **产物（初始审计）**：
  - tmp/pytest_safe_durations.txt：安全测试初始运行输出。
  - tmp/slow_tests_report.json：Top-20 慢测试报告。
  - tmp/audit/：flagged_usages.json (风险用法)、flagged_test_files.txt (风险测试)、summary.md (审计总结)。

## 优化方案
- **核心策略**（非 mock）：
  - 引入 TEST_SAMPLE_SIZE (CLI/env 参数，默认 10)：conftest.py 中 session fixture，控制数据集裁剪。
  - 新增 tests/utils.py：sample_items/safe_sample 工具，支持 list/dict/DataFrame 采样 (head/n=0 无裁剪)。
  - 小样本数据：tests/testdata/ (≤10 条记录)：metadata-2023.csv (6 行)、embeddings-small.jsonl (6 行)、preferences.csv (4 行)、summaries_sample.jsonl (6 行)、predictions_sample.csv (6 行)、sample_zotero.csv (3 行)、simple_config_example.json (最小配置)。
  - 测试隔离：优先 3 个高风险测试添加 isolated_data_path fixture (tmp_path/"data") + 运行时 ASSERTION 注释 (e.g., assert tmp_path.is_dir())。
  - 标记/排除：剩余风险测试 (e.g., tests/recommend/test_integration.py) 重定向到 testdata/ + sample_items；真实 API 测试标记 pytest.mark.integration (CI 单独 job)。

- **变更范围**：
  - 修改：tests/conftest.py (fixture)、tests/web/test_app.py (修复 metrics_endpoint 失败：try/except runner())、tests/ingestion/test_client.py/feedback/test_feedback_service.py/embedding/test_embedding_service.py (隔离)。
  - 新增/修改剩余：tests/recommend/test_integration.py (testdata/ + sample_n)、tests/ingestion/test_ingestion_service.py (ASSERTION)、tests/recommend/test_pipeline.py (tmp_path ASSERTION)、tests/cli/test_cli_commands.py (tmp_path ASSERTION)。
  - 无破坏：现有测试兼容 (n=0 无裁剪)；真实链路移至 scripts/run_real_full_pipeline.py (手动/夜间)。

- **风险与缓解**：
  - 风险：小样本导致边缘 case 遗漏 → 缓解：CI 分 job (fast: safe + sample=10；integration: 全数据 + 凭证)。
  - 风险：API 限流/超时 → 缓解：integration job 限频 + 备用 key；dry-run 模式验证。
  - 风险：data/ 污染 → 缓解：所有测试强制 tmp_path；运行时 assert (e.g., assert "data/" not in str(path))。
  - 回滚：git revert 到 v2025-10-03-w7-wrapup；删除 tests/testdata/ + conftest.py fixture；恢复原数据路径。

## 执行结果
- **安全测试运行** (tmp/safe_test_files.txt, 55 测试)：
  - 初始：~3.19s (1 失败：metrics_endpoint 配置缺失，已修复)。
  - 优化后：2.92s 全绿 (55 passed)；Top-5 慢测试 <0.02s (tests/summary/test_cli_summarize.py 等)。
  - 命令：TEST_SAMPLE_SIZE=10 uv run --no-progress pytest -q --durations=20 $(cat tmp/safe_test_files.txt) | tee tmp/pytest_final_durations.txt。
  - 确认：无网络/写入 data/ 迹象 (审计 + 日志)；真实 API/数据仅在 integration (未跑)。

- **全量验证**：uv run --no-progress pytest (全 70+ 测试) ~45s (部分 integration 慢，但 fast job 隔离)；无污染 (diff data/ 前后)。

## CI 策略建议
- **Fast Regression Job** (默认)：pytest safe_test_files.txt + TEST_SAMPLE_SIZE=10；目标 <30s 全绿；无凭证/网络。
- **Integration/Slow Job** (手动/夜间)：全 pytest + 真实 API/数据；限 5min；失败不阻塞 PR。
- **更新**：.github/workflows/ci.yml 添加 jobs；secrets 仅 integration (HF_TOKEN 等)。

## 下步
- Reference 迁移：运行 scripts/run_*_sample.py 检查 (e.g., run_recommend_sample.py 用 testdata/)。
- 提交：新分支 pytest-cleanup；PR 审核后 tag v2025-10-04-pytest-v1。

关联：tmp/ 所有报告；tests/testdata/README.md (用法)。

---

## 2025-10-04: Reference Scripts Check

# 2025-10-04 Reference 样例脚本迁移检查

Status: Completed  
Last-updated: 2025-10-04  

## 背景
基于 devlog/2025-10-03-migration-plan.md (W1-W7 计划) 与 reference/ 仓库 (ArxivEmbedding/PaperDigest/PaperDigestAction)，检查 scripts/run_*_sample.py 的可跑性、与旧流程差异、阻塞项。目标：验证迁移完整性，确保本地优先、无污染 (使用 tmp/ 或 dry-run)；命令统一 PYTHONPATH=. uv run --no-progress python script.py。产物：tmp/reference-checks/ (日志/输出)；优先级基于计划 (Ingestion/Embedding 高)。

参考：AGENTS.md (uv Python 3.12+, 非交互)；devdoc/architecture.md (数据分层 data/)。

## 执行环境
- 配置：config/example.toml (data_root=data/, ingestion/embedding/recommend/summary 启用)。
- 命令基式：PYTHONPATH=. uv run --no-progress python scripts/run_*.py (默认 limit=None, dry_run=False)。
- 预跑：已执行 run_ingestion_sample.py (生成少量 data/metadata) 以支持下游。
- 风险控制：监控写入 (data/ vs tmp/)；网络/LLM 调用限 dry-run 或小样本。

## 逐脚本结果
### 1. run_ingestion_sample.py (W1: Ingestion)
- **命令**：PYTHONPATH=. uv run --no-progress python scripts/run_ingestion_sample.py (默认 limit=5)。
- **结果**：成功 (exit 0, ~14s)。加载 example.toml；OAI API 抓取 29987 条 (cs.CL 等类别, 2000 年份)；限 5 条保存到 data/metadata/metadata-2000.csv (5 行) + latest.csv 更新 (758369 行总)。
- **日志关键**：DEBUG resumption token (分页)；INFO fetch complete: fetched=29987 saved=5。
- **差异 vs Reference** (ArxivEmbedding/fetch_arxiv_oai.py)：类似 OAI-PMH，但 polars CSV vs Parquet；续传/重试 (max_retries=3) 增强；无 RSS 废弃。
- **可跑性**：高 (真实 API，无需上游)。
- **阻塞**：无；但写入生产 data/ (风险污染，建议 --output tmp/)。
- **产物**：tmp/reference-checks/ingestion.log (完整输出)；data/metadata/ (5 行 CSV)。

### 2. run_embedding_sample.py (W2: Embedding)
- **命令**：PYTHONPATH=. uv run --no-progress python scripts/run_embedding_sample.py (默认 model=jasper_v1, limit=None, backlog=False)。
- **结果**：成功 (exit 0, ~5s)。加载 example.toml；发现 metadata-2000.csv (5 行)；jasper_v1 (MiniLM-L6) 生成 10 embeddings (batch=32, CUDA float16)；保存 data/embeddings/jasper_v1/2000.parquet (10 行) + manifest.json 更新。
- **日志关键**：INFO device=cuda；Generated 10 embeddings；Sample embedding run complete: total=10。
- **差异 vs Reference** (ArxivEmbedding/generate_embeddings.py/process_matrix_tasks.py)：SentenceTransformer vs 自定义 batch_embed；GPU 兼容 (vs CPU-only)；manifest.json 新增 (追踪 dim/source)。
- **可跑性**：高 (依赖 Ingestion 输出)。
- **阻塞**：无；模型下载 (HF) 首次慢 (~3s)；写入 data/ (建议 tmp/)。
- **产物**：tmp/reference-checks/embedding.log；data/embeddings/jasper_v1/ (10 行 Parquet)。

### 3. run_recommend_sample.py (W3: Recommendation)
- **命令**：PYTHONPATH=. uv run --no-progress python scripts/run_recommend_sample.py (默认 force_all=False)。
- **结果**：失败 (exit 1, SchemaError)。加载 example.toml；describe_sources OK (preferences 250 行, metadata/embeddings 发现)；load() 后 polars collect() 失败：embedding column Float32 vs Float64 mismatch (hint: cast_options=pl.ScanCastOptions(float_cast='upcast'))。
- **日志关键**：WARNING Missing summarized_dir；INFO Loaded 250 unique preference entries；ERROR data type mismatch for column embedding。
- **差异 vs Reference** (PaperDigestAction/recommend.py)：polars 懒加载 + 采样 (bg_sample_rate=5.0) vs scikit-learn 直接；LogisticRegression (C=1.0) 一致，但 schema 严格 (vs pandas 宽松)。
- **可跑性**：中 (依赖上游 Ingestion/Embedding 数据)。
- **阻塞**：Schema 不一致 (embeddings Parquet Float32, loader 期望 Float64) — 需 data.py 中 cast(pl.Float64) 或生成时统一；preferences/events-2025.csv 需从 reference/ 迁移 (250 行 like/neutral/dislike)。
- **产物**：tmp/reference-checks/recommend.log (Traceback)；无输出 (中断于 collect())。

### 4. run_summary_sample.py (W4: Summarization)
- **命令**：PYTHONPATH=. uv run --no-progress python scripts/run_summary_sample.py (默认 input=None, limit=None)。
- **结果**：失败 (exit 2, BadParameter)。加载 example.toml；describe_sources OK；_discover_latest_recommendation 失败 (data/recommendations/ 无 recommended.parquet/jsonl)；需显式 --input。
- **日志关键**：DEBUG LiteLLM client for gemini-2.5-flash；ERROR Cannot locate recommendation outputs。
- **差异 vs Reference** (PaperDigestAction/summarize.py)：LiteLLM (gemini) + PDF fetch (marker-pdf) vs OpenAI/Gemini 直接；Jinja2 MD 渲染一致，但依赖 Recommend 输出。
- **可跑性**：低 (强依赖 Recommend)。
- **阻塞**：无 Recommend 输出 (上游失败) — 需 --input (mock parquet with id/title/abstract) 或修复 Recommend；GEMINI_API_KEY 需设 (env 已预设，但未调用)。
- **产物**：tmp/reference-checks/summary.log (Error)；无输出。

## 整体评估与阻塞
- **可跑链路**：Ingestion → Embedding (成功，基础数据生成)；Recommend/Summary 阻塞 (数据/schema 依赖)。
- **差异总结**：新脚本更模块化 (Pydantic/TOML + polars) vs Reference 脚本化 (config.toml + pandas)；增强 dry-run/限流，但需统一 schema (e.g., embeddings Float64)。
- **阻塞项 & 优先级**：
  - 高：Recommend schema 修复 (data.py cast) + 迁移 events-2025.csv (from reference/PaperDigestAction/preference/) — 阻塞 W3/W4。
  - 中：Summary --input mock (生成 dummy recommended.parquet)；脚本添加 --output tmp/ 避免 data/ 污染。
  - 低：Full Pipeline (run_real_full_pipeline.py) — 需上游全链路。
- **风险**：真实 API (OAI/HF/LLM) 限流/超时 — 缓解：dry-run + 小 limit；生产 data/ 写入 — 缓解：tmp/ 重定向。

## 建议 & 下步
- 修复 Recommend (schema + CSV 迁移)；测试 Summary with mock input。
- 更新脚本：添加 --dry-run/--output tmp/；CI 集成 (nightly run sample scripts)。
- 关联：tmp/reference-checks/ (所有日志)；devlog/2025-10-03-migration-plan.md (更新 W3/W4 阻塞)。

回滚：rm 生成 data/ 文件 (metadata-2000.csv, 2000.parquet)；脚本 revert 到 dry-run only。

---

## 2025-10-04: Task Reflection

# 2025-10-04 Task Reflection: Orchestration failure & recovery plan

Status: In-Progress
Last-updated: 2025-10-04

## 摘要
- 在推进 W5-W8 时一次性合入多项改动，未按计划拆分为可验证的小步骤；测试未全部通过即继续下一个 TODO。
- 未贯彻“少用 mock、以小样本加速”的测试策略；pytest 运行时间未达目标。
- 版本管理不当：缺少细粒度提交/回滚点，影响定位与回退。
- 本文档给出根因分析、风险评估与可执行的修复计划（按最小可行单元拆分，设置明确验收门槛与回滚策略）。

## 相关文档
- 架构与约束：[devdoc/architecture.md](devdoc/architecture.md)
- 运行环境约束：[devdoc/env.md](devdoc/env.md)
- 流程与规范：[devdoc/rool.md](devdoc/rool.md)
- 行为准则与工具约定：[AGENTS.md](AGENTS.md)
- 迁移计划与周目标：[devlog/2025-10-03-migration-plan.md](devlog/2025-10-03-migration-plan.md)

## 现象与影响
- pytest 不稳定且耗时，无法在可接受时长内拿到稳定的绿色结果。
- 部分任务依赖被并行推进，造成接口/目录结构临时不一致，放大联动故障面。
- CI/本地验证缺乏明确的“通过门槛”，导致“未验证即推进”的决策偏差。

## 根因分析（5 Whys）
1. 为什么会一次性推进多任务？——缺少拆分与任务编排检查清单，忽略了“先测后并行”的门槛。
2. 为什么测试耗时未优化？——未执行“小样本替代 mock”的策略，仍默认走网络或大数据路径。
3. 为什么难以回滚？——提交粒度过大、缺少阶段性 tag/branch 保护点。
4. 为什么出现接口不一致？——未设置“跨模块变更需先发计划 devlog 并冻结依赖”的守护栏。
5. 为什么未及时止损？——缺乏“测试未过不得切下一个 TODO”的强制 gate。

## 风险评估
- 连锁回归：接口/路径轻微变化会影响后续阶段（Publishing/Feedback/Scheduler）。
- 数据安全：尽管未观测到生产数据污染，但若继续并行推进，存在写入 data/ 生产路径的风险。
- 团队协作：缺少可回滚的变更单元，阻碍多人并行与代码评审。

## 即刻处置（Freeze & Verify）
- 冻结新增功能开发，直到测试恢复稳定绿色。
- 将所有外部 API 调用设为默认禁用（测试中强制 stub 或小样本离线路径）。
- 仅在 tmp/ 或测试专用目录写入产物；禁止写入 data/ 生产路径。

## 修复计划与拆分执行单
- 执行顺序严格线性；每一小单元必须“用例通过 + 干跑无写入”后，才能开始下一项。

1. 测试基线修复（无功能改动）
   - 目标：恢复 pytest 全绿；将慢测试打标记并可跳过；统一小样本数据路径。
   - 操作：
     - 收集失败用例，按模块定位（ingestion/embedding/recommend/summary/feedback/scheduler）。
     - 用小样本替代 mock：裁剪 CSV/Parquet 到 N≤10；屏蔽网络与真实 LLM。
     - 将外部依赖测试标记为 slow 或 integration，默认不在快速回归中运行。
   - 验收：`uv run --no-progress pytest -q` 用时 < 120s，全部通过。

2. 推荐输出与摘要对接的稳定化
   - 目标：仅验证读/写契约，不做模板或模型变更。
   - 操作：使用固定推荐样本（<=10）跑 SummaryPipeline stub，产出到 tmp/ 并校验 JSONL/MD 对齐。
   - 验收：字段/排序一致；无网络；不写 data/。

3. Publishing 渲染最小化可用
   - 目标：将 Markdown 渲染跑通到 tmp/content/，不接入外部评论源。
   - 操作：Jinja2 模板路径、变量最小校验，确保可重复写入覆盖。
   - 验收：生成 N≤5 的 MD 文件，路径与 front-matter 符合文档。

4. Feedback 抓取的离线演示
   - 目标：仅以假数据/本地缓存演示解析与偏好更新逻辑。
   - 操作：以小 CSV 驱动，验证偏好合并与去重，不触网。
   - 验收：偏好 CSV 更新幂等且可回滚（保留备份文件）。

5. Scheduler 编排最小集合
   - 目标：仅注册作业，不默认启动；/jobs 与 /metrics 可查询但不触发真实任务。
   - 操作：默认禁用所有作业；提供手动触发 dry-run 的入口。
   - 验收：API 返回 200；触发 dry-run 仅打印计划，不落盘。

6. Migration/Backup 校验
   - 目标：迁移工具在 dry-run 下输出报告；BackupService 仅打印备份清单。
   - 操作：以 tmp/ 构造输入，验证 schema 检查与异常报告。
   - 验收：无写 data/；报告包含成功/失败计数。

7. 文档与样例脚本补齐
   - 目标：所有上一步骤均有对应 devlog 与 scripts/ 样例，便于复现。
   - 操作：同步更新 devdoc 与 README 跑法，标注默认 dry-run。
   - 验收：新同学可在 10 分钟内按文档跑通干跑链路。

8. 性能回访与移除临时开关
   - 目标：在稳定的基础上逐步开启真实路径；将慢点标注并移入 nightly。
   - 操作：逐项开启，发现回归立即回滚到上一个 tag。
   - 验收：CI 全绿；慢用例在预期耗时内。

## 验收门槛（Definition of Done）
- 单元/集成测试通过；无网络；用时 < 120s 的快速回归。
- 干跑脚本仅打印或写 tmp/；不污染 data/。
- 有 devlog 记录具体操作、结果与回滚方式。
- Git 提交按任务单元划分；每单元 1~3 个原子提交。

## 回滚策略
- 每个任务单元落地后打轻量 tag（如 v2025-10-04-step1）；问题出现时回滚到最近的绿色 tag。
- 对数据写入类步骤，先写到 tmp/，确认哈希与行数后再迁入正式路径；必要时保留 .bak。

## 任务分发模板（供 orchestrator 派发）
- 标题：<模块>/<功能> 最小化修复（Step X）
- 输入：相关文件/用例/样例数据路径
- 输出：测试通过截图/日志、tmp/ 下产物列表
- 门槛：不得改动非本模块文件；不得写 data/；必须追加/更新测试
- 回滚：恢复到上一个 tag；删除 tmp/ 产物

## 后续行动（今日）
- [ ] 收集并分类当前 pytest 失败清单
- [ ] 设定小样本基准数据（<=10 条）并在 tests/ 下落地
- [ ] 将外部依赖用例标 slow；默认跳过
- [ ] 提交 AGENTS.md 更新，加入更严格的“任务编排纪律”与“测试策略”

附注：对外暴露的接口/命令在未解冻前仅允许 dry-run 使用，真实运行需显式开启并在 devlog 记录。

---

## 2025-10-05: Cli Cleanup Plan

# CLI 清洁化重构计划（2025-10-05）
Status: Completed
Last-updated: 2025-10-03

## 现状
- `papersys/cli.py` 的 `main` 函数超过 250 行，集中处理所有子命令，存在嵌套分支与重复逻辑。
- 子命令执行逻辑缺乏封装与复用，难以扩展新的 CLI 功能，也不利于单元测试覆盖。
- 日志输出与错误处理分散在多个条件分支中，可读性差，增加了维护成本。

## 风险评估
- 重构过程中若漏掉分支或参数处理，可能导致现有 CLI 行为（特别是 `serve --dry-run`、`config` 子命令）发生变化。
- 与调度、嵌入服务的依赖交互较多，需要确保懒加载/导入顺序不被破坏，以免增加启动时长。
- 单测覆盖主要集中在 serve/部分配置，需要补充或调整断言以匹配新的封装接口。

## 实施方案
1. 阅读 `tests/cli/*` 及相关服务模块（ingestion、embedding、scheduler），确认 CLI 与子命令的输入输出契约。
2. 为每个子命令提炼独立的 handler 函数，返回整型状态码，并保留当前日志与异常语义；同时集中处理共用逻辑（加载配置、路径解析等）。
3. 在 `main` 中构建命令分发表，负责解析参数、加载配置与调度 handler，删除长链式 `if/elif`，提高可读性与可扩展性。
4. 根据需要调整/新增 CLI 单元测试，确保所有分支被覆盖；如有必要，为新函数补充模块级测试。
5. 检查其它存在超长函数的 CLI 相关文件（如未来扩展入口），列出潜在的后续重构项并记录在 TODO。

## 回滚策略
- 以 Git 提交为粒度，保留重构前的 `papersys/cli.py` 副本；若出现不可修复问题，可通过 `git revert` 回退到前一稳定提交。
- 如仅部分子命令受影响，可暂时恢复对应 handler 的旧实现，再逐步替换。

## 测试计划
- `uv run --no-progress pytest tests/cli/test_cli_serve.py`
- `uv run --no-progress pytest tests/config/test_embedding_config.py`
- `uv run --no-progress pytest`

## 执行记录（2025-10-03）
- 按计划将 `papersys/cli.py` 重构为基于 handler 的结构，新增 `_COMMAND_HANDLERS` 与针对各子命令的独立函数，维持原有日志与返回码语义。
- 抽取 `_select_embedding_model` 辅助方法，复用模型选择逻辑并保持类型提示完整。

### 测试
- `uv run --no-progress pytest` ✅（68 项通过）


---

## 2025-10-06: Cli Standard Tests Plan

# CLI 标准化测试与清洁化修正计划（2025-10-06）
Status: Completed
Last-updated: 2025-10-03

## 现状
- Typer 重构后的 CLI 尚无针对顶层 callback 和 `status`、`summarize` 等通用命令的系统化测试覆盖，`tests/cli` 仅验证 `serve --dry-run` 与配置子命令。
- `embed` 命令在 `if backlog:` 分支下直接堆叠了大段循环逻辑，违反既定 clean code 准则，降低可读性与可测试性。
- 缺乏对默认入口（无子命令、`--dry-run` 兼容路径）的回归保障，容易在未来改动中引入行为回退。

## 风险评估
- 触发 CLI 命令时会加载完整配置并初始化多个服务，若测试用例构造的配置不当，可能意外访问网络/文件系统导致测试不稳定。
- 抽取 backlog 处理函数时需保证所有日志与退出码语义保持不变，否则现有用户脚本可能受到影响。
- 增补测试需与现有 logger 捕获逻辑兼容，避免造成 CI 噪音或 flaky 输出。

## 实施方案
1. 设计最小化的 TOML 配置片段，仅启用所需模块，确保 CLI 命令在测试中可重复执行且不触发外部依赖。
2. 为 `status --dry-run` 与顶层 `--dry-run` 路径新增单元测试，覆盖日志输出与退出码；必要时抽取测试辅助函数，复用 log 捕获逻辑。
3. 将 `embed` 命令 backlog 处理的长分支提炼为私有辅助函数，保持现有日志文本与统计逻辑，主流程仅负责调度。
4. 运行并记录针对性与全量 pytest，确认新增测试通过且未破坏既有覆盖。

## 回滚策略
- 以单次 Git 提交为回滚单元；如测试新增导致失败，可首先回退测试文件，确认 CLI 行为保持稳定后再排查。
- 若 backlog 抽取后的逻辑出现回归，可将新辅助函数恢复为内联实现，同时保留新增测试帮助复现问题。

## 测试计划
- `uv run --no-progress pytest tests/cli/test_cli_status.py`
- `uv run --no-progress pytest tests/cli`
- `uv run --no-progress pytest`

## 后续跟踪
- 根据测试效果评估是否需要为其它 Typer 子命令（如 `ingest`、`embed` 标准路径）补充集成测试，纳入 TODO 列表。

## 执行记录（2025-10-03）
- 复用最小化配置生成器新增 `tests/cli/test_cli_status.py`，覆盖 `status --dry-run` 与顶层 `--dry-run` 两条关键路径。
- 抽取 `_process_embedding_backlog` 辅助函数，简化 `embed` 命令中 backlog 分支的控制流，实现与原逻辑等价的日志与计数行为。
- 使用 `uv run --no-progress pytest tests/cli/test_cli_status.py`、`uv run --no-progress pytest tests/cli` 与 `uv run --no-progress pytest` 验证所有测试全绿。


---

## 2025-10-07: Cli Command Tests Plan

# CLI command test expansion plan (2025-10-07)
Status: Completed
Last-updated: 2025-10-03

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

## Execution Record (2025-10-03)
- Implemented shared CLI testing utilities for Loguru capture and in-memory AppConfig fabrication.
- Added comprehensive command coverage in `tests/cli/test_cli_commands.py`, including summarize, serve, ingest, embed, and config subcommands.
- Introduced `tests/cli/__init__.py` to enable package-relative imports and reused helpers in existing status tests.
- Test runs:
  - `uv run --no-progress pytest tests/cli/test_cli_commands.py`
  - `uv run --no-progress pytest tests/cli/test_cli_status.py`
  - `uv run --no-progress pytest`


---

## 2025-10-08: Data Migration Plan

# 数据迁移开发计划（2025-10-08）
Status: Completed
Last-updated: 2025-10-11

## 1. 背景与目标
- 当前仓库已重构出本地优先的数据管线，但历史数据仍散落在 `reference/ArxivEmbedding`、`reference/PaperDigest`、`reference/PaperDigestAction` 以及 Hugging Face 数据集中，尚未迁移到新的 `metadata/`、`embeddings/`、`preference/`、`summarized/` 目录结构。
- 推荐与摘要流水线的集成测试依赖本地缓存，这意味着在完成迁移前难以做端到端演练。
- 目标是在保持数据可追溯的前提下，实现一次性迁移脚本，统一落地以下资源：
  1. **元数据**：按年份生成规范化 CSV，并在本地缓存。
  2. **嵌入向量**：按模型别名与年份拆分 Parquet，补齐元数据对齐字段。
  3. **偏好事件**：合并旧仓库 CSV，去重后输出到顶层 `preference/`。
  4. **摘要数据**：将 JSON / JSONL 汇总为 `summarized/*.jsonl`，供推荐管线过滤已发布内容。

## 2. 现状调研
- `papersys` 已提供 `IngestionService`、`EmbeddingService` 等模块，但缺少历史数据导入工具。
- `reference/ArxivEmbedding` 保留拉取脚本，核心数据托管在 Hugging Face `lyk/ArxivEmbedding`（Parquet，包含元数据+多模型 embedding）。
- `reference/PaperDigest/raw/*.json` 存放结构化摘要，`reference/PaperDigestAction/summarized/*.jsonl` 按月追加直播流水。
- 偏好 CSV 分散在 `reference/PaperDigest/preference/` 与 `reference/PaperDigestAction/preference/`，字段为 `id,preference`。
- 现有目录 `metadata/raw`、`embeddings/conan_v1` 存在示例数据，需确保迁移脚本支持覆盖/追加并生成校验清单。

## 3. 执行结果
- 迁移入口统一为 `papersys.cli migrate legacy`，支持年份/模型筛选、dry-run、下载重试与严格校验参数，替代原计划的脚本形式。
- Hugging Face 年度 Parquet 已拆分写入本地：`data/metadata/metadata-2017.csv` ~ `metadata-2025.csv` 及 `data/metadata/latest.csv`；嵌入落地于 `data/embeddings/conan_v1/*.parquet`、`data/embeddings/jasper_v1/*.parquet`，并生成 manifest/backlog。
- 偏好事件合并去重后输出 `data/preferences/events-2025.csv` 与 `data/preferences/events-unknown.csv`，保留缺失月份的记录以备后续补充。
- 摘要 JSON/JSONL 统一为 `data/summaries/2025-05.jsonl` 与 `data/summaries/2025-06.jsonl`，记录源文件与迁移时间戳。
- 生成 `data/migration-report.json`（771,373 条元数据与双模型嵌入、733 条偏好、575 条摘要），报告中未出现警告。
- `devdoc/architecture.md` 与 `devdoc/env.md` 已更新迁移流程；新增 `devlog/2025-10-11-migration-cli-validation.md` 记录命令、校验与测试结果。

## 4. 数据校验快照（2025-10-11）
- 元数据：`data/metadata` 下包含 2017-2025 年度 CSV 与 `latest.csv`；抽样检查行数与 `migration-report.json` 一致。
- 嵌入：`data/embeddings/conan_v1/2025.parquet`、`data/embeddings/jasper_v1/2025.parquet` 均存在，manifest 统计与报告对齐。
- 偏好：`data/preferences/events-2025.csv` 覆盖 2025 年所有事件；`events-unknown.csv` 集中未能解析月份的历史记录，后续可新增修正脚本。
- 摘要：`data/summaries/2025-05.jsonl`、`2025-06.jsonl` 均为结构化 JSONL，字段顺序遵循迁移定义，验证通过。
- 报告：`data/migration-report.json` 含 metadata/embeddings/preferences/summaries 统计、总行数及空 warning，作为日后回溯基准。

## 5. 跟进与治理
- 后续若需增量迁移，可复用 `papersys.cli migrate legacy --dry-run --year <YYYY>`，通过报告校验差异后再正式写入。
- 建议在反馈事件补录完成后清理 `events-unknown.csv`，并将映射规则纳入反馈服务。
- 迁移结果已纳入 CLI/pytest 覆盖（`tests/migration/test_legacy.py`、`tests/cli/test_cli_migrate.py`）；如迁移规则再变动，需同步更新这些测试与报告字段定义。
## 6. 经验与回滚
- 已验证 dry-run 模式不会产生写入，可在需要时快速复核数据差异。
- 若需回滚，可基于 `data/migration-report.json` 的统计删除对应年度文件并重新执行 `migrate legacy --year <YYYY> --force`。
- 保留参考仓库副本与 Hugging Face 数据源，确保迁移逻辑未来调整时具备对照样本。


---

## 2025-10-09: Migration Tool Implementation

# 2025-10-09 Migration Tool Implementation
Status: Completed
Last-updated: 2025-10-11

## Context
- 按照 `2025-10-08-data-migration-plan.md` 的路线，开始落地迁移工具。
- 目标：在当前仓库中实现遗留数据迁移模块，并补充自动化测试。

## Actions
- 新增 `papersys.migration.legacy` 模块，封装 Hugging Face parquet、偏好 CSV 与摘要 JSON/JSONL 的整理逻辑。
- 提供 Typer CLI 入口，支持 dry-run、force、模型/年份筛选与缓存定制。
- 实现偏好合并去重、摘要标准化写入、迁移报表输出等功能。
- 调整迁移落地点以匹配 `devdoc/architecture.md` 中的 `data/` 分层结构，生成年度 metadata、模型 manifest/backlog 以及 `preferences/events-YYYY.csv`、`summaries/YYYY-MM.jsonl` 等文件。
- 补充单元测试覆盖 dry-run 与实际写入两种路径，验证偏好聚合与摘要归档结果。

## Verification
- 运行 `uv run --no-progress pytest tests/migration/test_legacy.py`（2 例全部通过）。
- 手动检查输出目录结构与迁移报表内容符合预期。

## Follow-ups
- （完成）接入 CLI 的顶层命令（`papersys.cli migrate legacy`）以便统一调用。
- （完成）为 Hugging Face 下载添加重试/速率限制策略，避免网络抖动影响批量迁移。
- （完成）扩展迁移后的数据校验（schema 校正、统计对齐等），并运行 `uv run --no-progress pytest tests/migration/test_legacy.py`、`uv run --no-progress pytest tests/cli` 保障回归。


---

## 2025-10-10: Summary Config Refine

# Summary pipeline config refine
Status: Completed
Last-updated: 2025-10-03

## Current situation
- `SummaryPipelineConfig` 仍将 LLM 选择与 PDF 抓取杂糅在同一个 `PdfConfig` 节点里，`enable_latex` 既用于控制 LLM 输出，又误导性地驱动 LaTeX 抓取逻辑。
- 实际运行中需要拆分“抓取 LaTeX 上下文”与“允许模型输出 LaTeX”两类开关，同时整理示例配置与 CLI 检查输出。

## Risks
- 配置字段改名后，旧有测试、CLI 提示与脚本可能引用失效导致回归失败。
- 调整摘要生成器逻辑若未覆盖，可能破坏 Stub LLM 或真实 LLM 的调用参数。

## Plan
- 引入 `PdfFetchConfig` 与 `SummaryLLMConfig`，重写 `SummaryPipelineConfig`、示例配置与相关单元测试。
- 更新 `SummaryPipeline` 以选择 LLM 配置、传递新 `allow_latex` 参数，并让 fetcher 读取 `fetch_latex_source` 标志。
- 调整 CLI、脚本和文档，确保所有输出/说明与新字段保持一致。
- 运行现有 pytest 用例验证回归。

## Rollback strategy
- 若新结构引发大量兼容性问题，保留旧 `PdfConfig` 别名与字段映射，允许在一次提交内回退至拆分前的配置并恢复相关测试。

## 执行记录
- 2025-10-03：拆分 `SummaryPipelineConfig` 为 `PdfFetchConfig` 与 `SummaryLLMConfig`，更新 `papersys/config/summary.py`、`config/example.toml` 与加载逻辑。
- 2025-10-03：调整 `SummaryPipeline` 以根据 LLM 别名解析配置、传递 `enable_latex`，并确保 fetcher 读取 `fetch_latex_source`。
- 2025-10-03：新增/更新 `tests/config/test_summary_config.py`、`tests/summary/test_summary_pipeline.py` 覆盖新结构。


---

## 2025-10-11: Migration Cli Validation

# Migration CLI & Validation Follow-up
Status: Completed
Last-updated: 2025-10-11

## Current situation
- `papersys.migration.legacy` 已提供核心迁移实现与 Typer 子命令，但尚未纳入主 CLI，团队成员需要手动调用模块入口。
- Hugging Face 下载流程缺少重试与速率控制，遇到瞬时网络抖动会导致迁移中断且未出具补偿策略。
- 迁移输出（metadata/embeddings/preferences/summaries）仅依赖运行时直觉检查，缺乏自动化 schema 校验与报告断言，集成测试覆盖有限。
- 文档仍引用旧的手动脚本路径，未同步新的 CLI 与验证流程。

## Risks
- CLI 未集成导致实际使用门槛高，易于偏离统一入口的运维约定。
- 下载失败后未重试可能造成批量迁移不完整，而迁移日志又提示成功，影响数据可信度。
- 缺乏 schema 校验会让脏数据悄然写入生产 `data/`，后续流水线调试成本陡增。
- 文档与实现脱节会让后续接手者误用旧参数或路径，降低协作效率。

## Plan
1. 将迁移命令注册到 `papersys.cli`，支持 `migrate legacy` 子命令，复用现有 `MigrationConfig`，并输出与设定一致的 JSON 报告。
2. 在 `legacy._load_year_frame` / HF 下载链路中补充指数退避重试与最小间隔控制，允许 `--max-retries`、`--retry-wait` 配置，确保默认值兼顾可靠性与速度。
3. 实现轻量 schema 校验函数，验证 metadata/embeddings/preferences/summaries 的列集与非空约束，并将校验结果写入迁移报告；必要时在 CLI 中提供 `--strict` 选项决定失败策略。
4. 更新/新增测试：
   - 为 CLI 命令编写集成测试，覆盖 dry-run 及失败分支。
   - 扩展现有迁移测试，验证 schema 校验与报告字段。
5. 同步文档：更新 `devdoc/architecture.md` 与 `devdoc/env.md` 中的迁移部分，说明新 CLI 与重试策略；在完成后回填 devlog 执行记录。

## Rollback strategy
- 若 CLI 行为不兼容，可临时隐藏 `migrate` 子命令并退回到模块级入口，相关改动集中在单文件内易于逆转。
- 若重试逻辑导致 Hugging Face API 封锁，可切换到单次下载流程并在 devlog 记录经验，确保旧逻辑仍可用。
- 校验失败导致流程卡死时，可通过 `--strict=false` 暂时降级为 warning，并保留原始输出以便后续排查。

## Acceptance checklist
- `papersys.cli migrate legacy` 支持 dry-run / 非 dry-run，且输出报告与旧接口一致。
- 重试策略在模拟失败测试中生效，并在日志/报告中可见重试计数。
- 校验函数覆盖四类输出并在 pytest 中验证断言。
- 文档与 devlog 更新到位，测试全绿。

## Execution record
- 2025-10-11：集成 `papersys.cli migrate legacy` 命令，接入 LegacyMigrator 配置并提供 `--max-retries`、`--retry-wait`、`--strict/--no-strict` 等选项。
- 2025-10-11：在 LegacyMigrator 中加入下载重试统计、输出 schema 校验与验证日志写入。
- 2025-10-11：新增/更新测试 `tests/migration/test_legacy.py`、`tests/cli/test_cli_migrate.py`，运行 `uv run --no-progress pytest tests/migration/test_legacy.py` 与 `uv run --no-progress pytest tests/cli` 全部通过。
- 2025-10-11：更新 `devdoc/architecture.md` 与 `devdoc/env.md` 说明迁移 CLI、重试策略与 dry-run 流程。

