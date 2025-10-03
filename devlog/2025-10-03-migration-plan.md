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