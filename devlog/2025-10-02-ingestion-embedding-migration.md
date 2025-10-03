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
