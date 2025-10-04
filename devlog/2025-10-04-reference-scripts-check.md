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