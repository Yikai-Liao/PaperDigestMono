# 2025-10-19 接手核查报告
Status: Draft
Last-updated: 2025-10-19

## 背景
- 目标：在正式接手 PaperDigestMono 之前，核对关键文档与实际实现是否一致，评估运行环境、数据现状与测试基线。
- 范围：围绕 2025-10-18 之前的文档更新与仓库最新 master 分支的代码/数据进行一次性梳理，不对生产数据做写操作。

## 核查范围与结论
- 文档与实现对齐性：存在多处偏差，已在下方逐项列出。
- 运行配置现状：CLI 与配置模型完备，但调度器对接实现缺口较大。
- 数据目录状态：结构基本符合文档，但存在命名差异与重复记录。
- 自动化测试：本轮未执行 pytest，全局测试结果仍未知。

> 结论：系统仍可手工按模块运行，但要实现文档所描述的“调度+备份一体化”仍需补课；建议在开展新的开发任务前，先补齐调度器调用与测试基线。

## 文档 vs. 实现差异
- `devdoc/data-storage.md` 声称 `data/temp/`、`data/logs/` 目录常驻；实际仓库当前只有 `data/metadata`, `data/embeddings`, `data/preferences`, `data/summaries`, `data/pdfs`，并未生成 `temp/` 或 `logs/` 子目录。日志默认写入仓库根部的 `logs/`（见 `papersys/scheduler/service.py::_setup_logging_sink`）。
- 同文档描述“推荐流水线默认写入 `data_root/recommendations/` 并移除 embedding 列”，但实际结果目录位于 `data/recommendations/<run_id>/`，`predictions.parquet` 依然包含 embedding 列；这与 `papersys/recommend/pipeline.py::run_and_save` 的行为一致。
- `devdoc/architecture.md` 记录 scheduler 已集成推荐、摘要、备份作业，且摘要流水线可通过调度器触发。实际代码中：
  - `SchedulerService._run_ingest_pipeline` 实例化 `IngestionService(self.config)`，但 `IngestionService` 需要 `IngestionConfig`，直接传入 `AppConfig` 会触发类型错误。
  - `_run_embed_pipeline`、`_run_embedding_backfill_pipeline` 调用 `EmbeddingService.run()` 与 `EmbeddingService.autopatch()`，两个方法均不存在（`papersys/embedding/service.py` 仅提供面向 CLI 的细粒度方法）。
  - `_run_summary_pipeline` 仅输出日志占位，未实际调用 `SummaryPipeline`。
- `devdoc/architecture.md` “备份与同步策略” 小节提及支持多通道（local/huggingface/git/s3），但实现仅允许单一目的地（`papersys/config/backup.py::BackupDestinationConfig` 与 `BackupConfig`）。
- `README.md` 仍为空，缺少对外部协作者的最小说明；文档索引包含 `devdoc/index.md`，但未更新以指向新的交接报告。

## 运行配置核查
- `config/example.toml` 覆盖 ingestion/embedding/recommend/summary/scheduler/backup 配置。备份配置只定义了本地通道，未包含文档中提到的 Hugging Face/多目的地示例。
- LLM 配置已列出 `deepseek-r1` 与 `gemini-2.5-flash`；摘要默认引用 `gemini-2.5-flash`，且 `SummaryPipeline` 会按 alias 查找匹配（`papersys/summary/pipeline.py::_resolve_llm_config`）。
- `papersys/cli.py` 中 `status`, `ingest`, `embed`, `summarize`, `serve`, `migrate legacy` 均可使用；`serve --dry-run` 能加载配置并列出计划的调度任务，但若真正执行调度，将因上述方法缺口而失败。

## 数据目录核查
- 当前 `data/` 结构：`metadata/`（含 2000-2025 年度 CSV 与 `latest.csv`）、`embeddings/`（多个模型 alias 子目录）、`preferences/`、`summaries/`、`migration-report.json`、`pdfs/`。未发现 `temp/` 或 `logs/`。
- `data/preferences/events-unknown.csv` 存在成对重复记录（同一 `paper_id` 与时间戳出现两次）；推荐加载器 `papersys/recommend/data.py` 在组装数据时不会自动去重，需要后续处理。
- `data/summaries/` 已有历史 JSONL；`SummaryPipeline` 写入时保持字段顺序，符合文档描述。

## 自动化测试状况
- 当前未执行 `uv run --no-progress pytest`。原因：本轮核查聚焦文档/代码对齐与数据状态，尚未进入功能改动阶段。
- 建议在接手后先跑一次全量 pytest，并把结果存档到 `devlog/` 新增条目。

## 待办与建议
1. 修复调度器调用链：为 `IngestionService`、`EmbeddingService`、`SummaryPipeline` 等补齐统一入口，或调整调度器调用方式，确保实际可运行。
2. 更新文档：同步 `devdoc/data-storage.md` 与 `devdoc/architecture.md`，明确当前数据目录与备份能力，并在 `README.md` 提供最小启动指南。
3. 清理数据：为偏好事件添加去重逻辑或脚本，避免训练数据偏移。
4. 测试基线：执行 pytest 并记录结果，确认关键模块可在本地环境通过。
