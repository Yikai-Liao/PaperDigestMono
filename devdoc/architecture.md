# 论文推送系统单例化重构

## 功能概览

我的目标是搭建一个自动化的论文推送系统，包含了论文信息收集，筛选，归纳总结，可视化展示，反馈收集这么几个宏观的流程。

具体来讲，通过 xiv爬虫获取最新的论文meta data（包含摘要），然后自动更新一个总的论文 Embedding 池中。根据历史中已有的二分类数据，使用特定算法训练一个输入为Embedding的简单的二分类模型，根据这模型的打分结果，采样出一定数量的论文作为新增的需要展示的论文。然后获取这些论文具体的latex/pdf，转换为markdown形式，然后通过特定的prompt输入给llm api进行摘要，抽取我需要的特定信息（包含多个字段）保存到json中。这个json作为数据存储的媒介，可以快速格式化到各种形式。之后的流程是，格式化为markdown，添加到一个静态博客中，发布到cloudflare。这个静态博客接入了giscus系统，因此我可以通过定期检测github discussion中每个论文对应的评论区中来自用户自己添加的表情，来确定这个新论文的标签是possive 还是negtive，这个数据会被收集起来，用于下一轮的模型训练。

## 前身架构设计

之前版本的代码被拆分为 `ArxivEmbedding` 与 `PaperDigest` 两个仓库，并在当前仓库的 `reference/` 目录下以子模块形式保留，另有 `PaperDigestAction` 作为 GitHub Action 封装。整体流程依赖 Hugging Face Dataset 作为远端数据中枢，GitHub Actions 负责定时触发各阶段脚本。

### 总体流程（历史版本）

1. **元数据采集**：`reference/ArxivEmbedding/script/fetch_arxiv_oai.py` 与 `fetch_arxiv_oai_by_date.py` 通过 OAI-PMH 接口按年份/时间段抓取论文元数据，合并为年度 Parquet 并推送到 Hugging Face。
2. **嵌入补齐**：`incremental_embed_workflow.py` 下载对应年份 Parquet，找出嵌入为空的论文，调用 `local_split_tasks.py` + `process_matrix_tasks.py`（或本地 `batch_embed_local.sh`）批量补全多个模型的向量，再上传覆盖。
3. **推荐与摘要**：`reference/PaperDigest/script/fit_predict.py` 消耗偏好 CSV 与向量数据生成候选集合，`download_pdf.py`/`summarize.py` 获取 PDF 并调用 OpenAI/Gemini API 输出结构化 JSON，随后 `render_md.py` 渲染 Markdown。
4. **内容发布与反馈**：GitHub Actions 调用 `website/` 构建脚本，把 Markdown 发布到 Cloudflare Pages 并通过 giscus 讨论区收集反馈；`fetch_discussion.py` 定期读取讨论中的表情标记回写偏好数据。

### 关键代码仓库与职责

- **`ArxivEmbedding`**：以嵌入为核心的流水线。`config.toml` 使用模型键（如 `Embedding.jasper_v1`）管理多个嵌入模型的名称与维度。脚本依赖 `polars` 处理 Parquet，`huggingface_hub` 同步数据。
- **`PaperDigest`**：聚合推荐、摘要、渲染、部署流程。目录下的 `script/` 包含从模型训练、PDF 下载到 Markdown 渲染的完整链路；`docs/` 记录多个线上问题的修复过程。
- **`PaperDigestAction`**：把上述流程包装成可复用的 GitHub Action，附带偏好清理、Zotero 导入等工具脚本，强调 fork 后快速启用。

### 数据形态与传输路径

- **论文元数据**：年度 Parquet，列包含 `id/title/abstract/categories/created/updated` 及多个模型向量列。
- **向量数据**：与元数据合并存放，未完成时以全 0 或 `NaN` 占位。
- **推荐结果**：`PaperDigest/data/predictions.parquet` 储存候选论文与打分。
- **摘要输出**：`raw/` 下的 JSON + `content/` 下的 Markdown；部分示例 JSON 放在 `examples/`。
- **偏好反馈**：`preference/*.csv`，以 `arxiv_id` + `preference` 字段记录。

数据交换主要依赖 Hugging Face Dataset 作为中心仓库，经由 GitHub Actions 多次上传、下载，缺乏本地缓存与增量同步机制。

### 基础设施与运行方式

- **触发机制**：GitHub Actions 定时/手动触发多个 Workflow（嵌入、推荐、网页构建），Action 内使用 `uv run` 执行脚本。
- **计算资源**：嵌入阶段大量使用 GitHub Actions matrix 并行，CPU 推理为主；本地 GPU 脚本 `batch_embed_local.sh` 仅在手动场景使用。
- **机密信息**：API Key、PAT 借助 GitHub Secrets 注入。

### 历史痛点与经验

| 类别 | 表现 | 影响 |
| ---- | ---- | ---- |
| 计算资源 | GitHub Actions 排队、耗时长，缺乏本地兜底 | 嵌入与推荐延迟大，易被速率限制 |
| 数据同步 | 每个阶段频繁向 Hugging Face 上传完整文件 | 传输成本高，难以调试增量差异 |
| 标签治理 | `summarize.py` 中关键词合并依赖一次性 LLM 调用 | 语义重复积累，知识图谱难扩展 |
| 代码结构 | 脚本化调用，模块间缺少清晰边界与类型约束 | 扩展新功能需跨脚本修改，测试困难 |
| LLM 调度 | OpenAI 与 Gemini 混用，Fallback 逻辑分散 | 行为不可预期，错误处理复杂 |

### 尚未落地但规划过的功能

- **文章关联挖掘**：尝试以批处理 LLM 判断论文间关系，受限于 $O(N^2)$ 复杂度与算力尚未实施。
- **兴趣画像深化**：希望挖掘跨领域兴趣主题，但缺乏合适的反馈数据与算法验证。

## 新架构设计

### 目标原则

1. **Local-first**：核心流水线在本地单例运行，云端仅作为备份与远程触发入口。
2. **模块化**：以 Python 包形式重构，各模块有清晰输入输出契约，方便测试与复用。
3. **数据分层**：元数据、嵌入、偏好、摘要分离存储，采用统一键（arXiv ID）连接。
4. **可编排**：提供显式的调度与触发接口（本地 scheduler + 远程调用 API）。
5. **易扩展**：支持新增嵌入模型、摘要模型、下游展示渠道。

### 模块划分与职责

| 模块 | 职责 | 关键实现要点 |
| ---- | ---- | ---- |
| Ingestion Service | 调用 OAI-PMH/RSS，生成标准化元数据 CSV/Parquet | 重用 `fetch_arxiv_oai_by_date.py` 逻辑，封装为类 |
| Embedding Service | 补齐/刷新多模型向量 | 使用本地 GPU，任务队列+批处理；保留 Hugging Face 上传插件 |
| Recommendation Service | 训练/打分，输出候选列表 | 将 `fit_predict.py` 封装为对象，支持自定义采样批量 |
| Summarization Orchestrator | 下载 PDF、调用 LLM、产出 JSONL/Markdown | 保持单次结构化产物生成流程，聚焦日志与失败告警 |
| Publishing Adapter | Markdown→Astro/GitHub→Cloudflare，或 Notion API | 插件化输出端，支持多目标 |
| Feedback Collector | 聚合 giscus/Notion/手动偏好 | 标准化成偏好事件流 |
| Orchestrator API | 暴露 HTTP/CLI 接口统一触发流程 | 支持局域网访问与远程触发 |

### 数据层设计

#### 现有落地（参考仓库来源）

> 关于当前本地数据目录与字段契约的精确说明，请参见《[数据存储结构与字段说明](./data-storage.md)》。下文保留历史背景，后续规划以新文档为准。
- **ArxivEmbedding**（Hugging Face Dataset：`lyk/ArxivEmbedding`）
  - 年度 Parquet：`<year>.parquet`，字段包含 `id`（arXiv ID）、`title`、`abstract`、`categories`（list[str]）、`created`、`updated`、`doi` 以及多个嵌入列（如 `Embedding.jasper_v1`、`Embedding.m3e_large`，类型 list[float64]）。
  - GitHub Actions 负责上传至 Hugging Face，目录 `reference/ArxivEmbedding/script/` 中的 `incremental_embed_workflow.py` 使用本地缓存目录 `data/parquet/` 与 `data/cache/`。
- **PaperDigest**（Hugging Face Dataset：`lyk/PaperDigestContent`）
  - 推荐结果：`data/predictions.parquet`（列 `id`、`score`、`label`、`timestamp` 等）。
  - 摘要产物：`raw/*.json`（结构化字段 `metadata`, `sections`, `highlights`）、`content/*.md`。
  - 偏好事件：`preference/*.csv`，列含 `arxiv_id`、`preference`、`source`、`recorded_at`。

#### 新单例架构下的数据存储规划

所有持久化数据统一放在仓库根目录的 `data/`，按照模块和生命周期拆分，形成可挂载、易迁移的层次结构：

```
data/
  metadata/
      metadata-YYYY.csv                 # 去重、标准化后的年度主表（详见下表）
      latest.csv                        # 最近一次抓取的整合视图
  embeddings/
    <model_alias>/
      YYYY.parquet                      # 列：paper_id, embedding (list[float32]), generated_at, source
      manifest.json                     # 记录样本数、维度、上游模型信息
      backlog.parquet                   # 需补齐 embedding 的 paper 列表（详见下文）
  preferences/
    events-YYYY.csv                     # 追加式事件流（逗号分隔，字符串按 CSV 规范转义）
  summaries/
    YYYY-MM.jsonl                     # 每月聚合 JSONL，字段含 paper_id、sections、model_meta
  temp/
    markdown/                           # 临时 Markdown，供静态站点构建后清理
    pdf/                                # 下载的原始 PDF，缓存策略见运行规范
    cache/                              # 其他短期缓存（向量块、下载中间件等）
  backups/                              # TODO:需要重新设计以支持非压缩的多后端备份，甚至是否需要这个文件夹都需要商讨
```

元数据与嵌入表的字段契约：

| 数据集 | 必需字段 | 可选字段 | 说明 |
| --- | --- | --- | --- |
| `metadata/curated/metadata-YYYY.csv` | `paper_id`、`title`、`abstract`、`categories`（以 `;` 分隔的 ISO cats）、`published_at`、`updated_at`、`primary_category` | `doi`、`authors`（`;` 分隔）、`comment`、`journal_ref`、`versions`（JSON 字符串）、`ingested_at` | 字符串使用 UTF-8；含换行内容需经 CSV 规范转义 |
| `embeddings/<model_alias>/YYYY.parquet` | `paper_id`、`embedding` (list[float32])、`model_dim` (int)、`generated_at` (UTC ISO) | `hash`（向量哈希）、`version`（模型权重标记）、`source`（local/hf/manual） | `embedding` 推荐使用 `float32`；若需节省空间可在迁移脚本中转 `float16` |
| `embeddings/<model_alias>/backlog.parquet` | `paper_id`、`origin`（metadata/legacy/import）、`missing_reason`、`queued_at` | `priority`、`retry_count` | 记录待补齐的论文列表，调度器据此分配任务 |
| `preferences/events-YYYY.csv` | `paper_id`、`preference`（enum: like/dislike/neutral）、`recorded_at` | `source`、`confidence`、`note` | 引擎按 CSV 附加模式写入；字符串需转义 |

#### 路径与访问策略
- 所有读写通过 `AppConfig.data_root` 解析，允许相对/绝对路径；调度器、CLI 默认指向仓库根下 `data/`。
- 元数据抓取结果直接写入 CSV；若需保存原始 OAI 响应，可额外启用 Debug 选项输出至 `metadata/raw/arxiv/debug/`（默认关闭）。
- 迁移脚本 `scripts/migrate_reference_embeddings.py` 将历史 Parquet 拆分为 `metadata/curated/*.csv` 与 `embeddings/<model>/*.parquet`，同时生成 `backlog.parquet` 以标记缺失向量。
- `SummaryPipeline` 仅保留 JSONL 结构化文件；Markdown/PDF 等临时工件放入 `temp/`，完成发布或打包后由任务删除，避免占用空间。
- 备份服务打包 `data/`、`logs/`、`config/` 至 `backups/`（或远端），恢复时依据 MANIFEST 还原。

#### 自动化补齐策略
- 新增 `EmbeddingConfig` 支持 `auto_fill_backlog=true`；当配置中引入新模型时，迁移脚本会根据历史 `metadata` 生成 backlog，写入 `embeddings/<model>/backlog.parquet`。
- `EmbeddingService` 启动时检测 backlog：
  - 首先判断运行环境（CUDA、Metal、CPU）。服务会在初始化时探测 `torch.cuda.is_available()`、`torch.backends.mps.is_available()`，选择最优执行器（优先 CUDA > Apple Metal > CPU），并允许通过配置覆写。
  - 根据 backlog 分批拉取待处理论文，按模型配置（batch_size、precision、device）生成向量。
  - 成功写入后从 backlog 移除记录，并将结果追加至 `embeddings/<model>/YYYY.parquet`，更新 `manifest.json`。
- 对于旧数据的补齐：
  - 增加 CLI `embed autopatch --model <alias>`，读取 backlog 并执行批量补齐，可附带 `--from-year`、`--limit`。
  - 调度器新增 `embedding_backfill_job`，周期性检查 backlog，避免遗漏历史论文。

#### 目录忽略策略
- `data/`、`backups/`、`.tmp-backups/` 等运行目录已加入 `.gitignore`，临时目录（`temp/`）默认也忽略。
- 若需要提交目录结构，可放置 `.gitkeep` 并在文档说明用途。

### 配置管理策略

- 提供一个根配置文件 `config.toml`，由 `BaseConfig`（Pydantic `BaseModel`）解析。
- 按子模块继承，例如 `EmbeddingConfig`, `LLMConfig`, `SchedulerConfig`，均实现 `@classmethod from_toml(path: Path)`。
- 在运行时通过简单的 `load_config()` 辅助函数向各服务注入 Pydantic 对象；如未来出现多进程/多租户需求，可再引入 `ConfigRegistry` 或依赖注入容器，但当前阶段保持简洁。
- 配置变更通常低频，约定“修改后重启服务”，无需支持热加载，仅需启动时校验并输出有效配置快照。
- 在参考仓库落地：
	- `ArxivEmbedding` 中的模型列表由 `EmbeddingConfig` 管理，取代当前直接访问字典。
	- `PaperDigest` 中的 LLM 参数、模板路径、采样阈值通过 `LLMConfig` 和 `PipelineConfig` 提供，脚本重构为 `uv run python -m paper_digest.cli summarize --config ./config.toml` 类似接口。

#### 配置模块层级（已落地）

当前在 `papersys/config/` 下已实现以下配置模型（严格 Pydantic 验证，`extra="forbid"` + `frozen=True`）：

- **`base.py`**：`BaseConfig` 基类与 `load_config` 辅助函数，统一 TOML 读取逻辑。
- **`llm.py`**：`LLMConfig` 定义单个 LLM 端点（alias、name、base_url、api_key、temperature、top_p、num_workers、reasoning_effort）。
- **`recommend.py`**：
  - `LogisticRegressionConfig`：C、max_iter。
  - `TrainerConfig`：seed、bg_sample_rate、logistic_regression。
  - `DataConfig`：categories、embedding_columns、preference_dir、background_start_year、preference_start_year、embed_repo_id、content_repo_id、cache_dir。
  - `PredictConfig`：last_n_days、start_date、end_date、high_threshold、boundary_threshold、sample_rate、output_path。
  - `RecommendPipelineConfig`：聚合以上 data/trainer/predict 子节点。
- **`summary.py`**：
  - `PdfConfig`：output_dir、delay、max_retry、model（LLM alias）、language、enable_latex、acceptable_cache_model。
  - `SummaryPipelineConfig`：包含 pdf 节点。
- **`scheduler.py`**：
  - `SchedulerJobConfig`：`enabled`, `name`, `cron`（Cron 表达式）。
  - `SchedulerConfig`：`enabled`, `timezone`, `recommend_job`, `summary_job`。
- **`app.py`**：`AppConfig` 顶层配置（`data_root`、`scheduler_enabled`、`embedding_models`、`logging_level` 为历史兼容字段；`recommend_pipeline`、`summary_pipeline`、`llms`、`scheduler` 为新业务配置）。

示例配置 `config/example.toml` 包含完整字段，单元测试 `tests/config/test_*.py` 覆盖各层级读取与严格性校验，CLI `status --dry-run` 输出详细状态。

### 运行编排与调度

- **核心调度器**：使用 `APScheduler` 或 `Prefect` 在本地长驻进程中管理每日任务（爬虫→嵌入→推荐→摘要→发布）。
- **任务隔离**：各阶段以队列（如 `redis-queue` 或本地 `sqlite` 任务表）串联，避免长任务阻塞。
- **锁机制**：在嵌入/推荐阶段添加文件锁或数据库锁，防止远程触发与定时任务并发时重复写入。
- **观察性**：统一日志（`structlog`/`loguru`）+ Prometheus/Grafana（可选）监控耗时、成功率。

### 外部触发接口与远程控制

- **本地控制台（优先级最高）**：实现一个轻量网页/桌面界面，展示当前配置快照、实时日志、最近任务状态，并提供“手动触发推荐流水线”按钮，支持自定义时间范围与目标数量。
- **HTTP API 网关（中期）**：基于 FastAPI/Flask 暴露 `/run-pipeline`、`/run-embedding`、`/status` 等接口，供本地控制台或 CLI 调用，后续再拓展鉴权与参数校验。
- **远程访问（远期）**：
  - 局域网访问：可选接入 `tailscale`/`zerotier` 等虚拟局域网，让移动设备访问控制台。
  - 公网访问：如需通过 1c1g VPS 做入口，再评估 Cloudflare Tunnel/Tailscale Funnel 等方案，现阶段仅保留规划。
  - GitHub Action 触发：保留“Action 调用 HTTP API”思路，但排在远期，实现前需确认安全策略。
- **Notion 集成设想（远期）**：保留“Notion 页面触发流水线”的想法，等基础控制台稳定后再评估可行性。

#### 调度与 Web 控制台（已落地）

为了实现本地优先的自动化流程，系统引入了基于 `APScheduler` 的调度服务和基于 `FastAPI` 的轻量级 Web 控制台。

- **`SchedulerService` (`papersys/scheduler/service.py`)**:
  - **职责**: 管理所有周期性作业（如推荐、摘要），并收集运行时指标。
  - **功能**:
    - 根据 `config.toml` 中的 `scheduler` 配置动态注册和管理作业。
    - 支持 `dry-run` 模式，用于验证作业配置而不实际执行，同时记录模拟执行指标。
    - 提供优雅的启动和关闭接口，与 Web 服务生命周期集成。
    - 为每次执行输出结构化日志（含 `job_id/run_id/status/latency`），日志写入 `logs/scheduler.log` 的滚动文件。
    - 内建 Prometheus 友好的指标注册表，追踪成功/失败/干跑次数、最后一次耗时、下一次运行时间。
    - 当 `scheduler.backup_job` 存在时，自动调用 `BackupService` 打包上传备份；在 dry-run 模式下跳过上传但保留清单日志。

- **FastAPI Web 应用 (`papersys/web/app.py`)**:
  - **职责**: 提供一个用于监控和手动控制的 HTTP API 接口。
  - **启动**: 通过 CLI 命令 `uv run python -m papersys.cli serve` 启动。
  - **API 端点**:
    - `GET /health`: 健康检查接口，返回服务状态。
    - `GET /jobs`: 列出所有在调度器中注册的作业及其状态（包含下一次运行时间）。
    - `POST /scheduler/run/{job_id}`: 手动触发一个指定的作业立即执行。
    - `GET /metrics`: 返回 Prometheus 文本格式的调度器指标，可直接被 Prometheus/Grafana 抓取。

- **CLI `serve` 命令**:
  - **功能**: 作为调度器和 Web 服务的统一入口点。
  - **用法**: `uv run python -m papersys.cli serve [--host <host>] [--port <port>]`。
  - **`--dry-run` 支持**: `serve --dry-run` 会加载配置、验证并列出将要调度的作业，但不会启动 Web 服务器或实际运行任何作业，便于快速调试。

### 配置巡检工具（已落地）

- **CLI 子命令**：`uv run --no-progress python -m papersys.cli config check` 读取指定 TOML 并返回结构化结果，可通过 `--format json` 输出机器可读格式。
- **告警策略**：针对 `data_root`、`embedding_models`、缺失 `scheduler` 配置及空 `llms` 等历史遗留字段给出提示，帮助在迁移阶段发现配置缺口。
- **字段说明**：`config explain` 子命令遍历 Pydantic 模型，输出字段层级、是否必填、默认值与描述，便于同步文档或检查新字段发布情况。
- **脚本整合**：新工具复用 `load_config` 与现有模型，无需额外依赖，适合作为 CI 或 pre-commit 钩子。

### 内容生产与发布

- **Markdown 渲染**：继续使用 Jinja2 模板，但封装成 `ContentRenderer` 类，支持 Astro 网站与 Notion 两种输出模式。
- **LaTeX→Markdown 流程**：保留 `latex2json` 主路，`marker` 作为 fallback，确保日志清晰即可，短期内不额外实现复杂的回滚机制。
- **版本化存储**：Markdown/JSONL 结果写入 `output/`，以 Git 提交或 Notion API 同步方式对外发布；Cloudflare Pages 仍由 GitHub Action 部署。

### 反馈采集与偏好回写

- **giscus**：保留现有讨论区采集脚本，迁移为 `FeedbackCollector` 子模块，解析 emoji → 偏好事件。
- **Notion**：若切换到 Notion 展示，直接读取数据库中的“打分”列生成偏好事件。
- **手动导入**：保留 Zotero → CSV 转换脚本，接入统一偏好写入接口。

### 备份与同步策略（已落地）

- **核心理念**：将不同数据域拆分为可独立管理的“备份通道”。Embedding 大文件可落地 NAS 或 Hugging Face，纯文本内容可继续 Git 版本控制，配置与日志可保留本地 tar 包。`BackupService` 升级为 orchestrator，支持多目标并发执行。
- **配置模型调整**：`BackupConfig` 将 `destination` 扩展为列表，每个元素包含 `name`、`mode`（`local` / `huggingface` / `git` / `s3` 等）、`include`（路径或 glob）、`exclude`、`retention`、`options`（目标特定参数，如 `repo_id`、`branch`、`s3_bucket`）。
- **执行流程**：
  1. 加载各目标配置，针对 `include` 列表解析文件集。
  2. 对于 `local` 目的地，按照通道名称分别生成 tar.gz，保留 `MANIFEST.json`，并执行保留策略。
  3. 对于 `huggingface`，使用现有上传器将指定 Parquet 或 CSV 推送到 Dataset；如果选项开启 `delta_mode`，允许仅上传增量 diff。
  4. 对于 `git` 模式，仅执行变更检测和提醒，不自动提交；给出待同步目录列表，供人工 commit。
  5. 对于 `s3` 或未来扩展，使用相应 SDK 上传文件（`options` 指定 bucket、prefix 等）。
  6. 汇总通道执行结果（成功、跳过、失败）写入统一报告；失败不会短路其他通道，但会在 CLI/日志中标记并返回非零状态。
- **调度集成**：`scheduler.backup_job` 支持按通道选择执行。例如配置每日同步 Hugging Face Embedding、每周生成本地 tar 包、即时提醒 Git 同步状态。Dry-run 模式下输出将要触发的通道与预计文件大小。
- **典型场景**：
  - 本地 NAS：`mode=local`， `include=['data/embeddings']`，每日保留最近 3 份。
  - Hugging Face：`mode=huggingface`， `include=['data/embeddings/*.parquet']`，`options.repo_id='lyk/ArxivEmbedding'`。
  - Git 内容：`mode=git`， `include=['data/summaries/batched','config/']`，调度器只提示未提交内容，避免误把 Git 管理的文件打包上传。
  - S3 冷备：`mode=s3`， `include=['backups/*.tar.gz']`，`options.bucket='papersys-backups'`。
- **回滚与验证**：每个通道生成自身的 MANIFEST/校验和；本地 tar 包保持原策略。恢复时根据通道类型执行反向操作（下载 tar、从 HF Dataset 拉取最新 Parquet、复刻 Git 提交等）。

### 迁移步骤（建议）

1. 建立 Python 包骨架（`papersys/`），抽取 `ArxivEmbedding` 与 `PaperDigest` 中的可复用逻辑。
2. 实现 Pydantic 配置体系，并替换脚本中的直接字典访问。
3. 引入调度器与 HTTP API，完成本地单例 PoC。
4. 将生成的数据目录整理为新结构，编写迁移脚本从旧 Parquet/JSON 拆分。
5. 配置云端备份与 GitHub Action 触发入口。
6. 渐进式替换旧流水线，期间保留旧 Action 作为 fallback。

### Git 工作流与合并策略

- **不使用交互式合并提交**：在需要保留合并提交时，统一使用 `git merge --no-ff --no-edit <feature-branch>`。`--no-ff` 保留分支历史，`--no-edit` 避免进入编辑器，确保自动化脚本与无头环境可顺利执行。
- **首选快速前进模式**：若合并前目标分支未产生额外提交，可执行 `git merge --ff-only <feature-branch>` 保障无额外合并提交。
- **预先拉取最新远端**：在执行任何合并前先运行 `git fetch --all` 与 `git rebase`/`git pull --ff-only`，减少冲突并保持提交图线性化。
- **提交后立即验证**：合并完成后务必在目标分支执行 `uv run pytest` 等质量门禁命令，确认变更在主线上可复现通过。

### 风险与缓解

| 风险 | 描述 | 缓解策略 |
| ---- | ---- | ---- |
| 单点故障 | 本地单例服务宕机导致流程停摆 | 提供手动触发脚本 + 云端 Action 作为备用；关键数据实时备份 |
| 算力瓶颈 | 本地 GPU 资源不足以处理大批量嵌入 | 支持分批排程、夜间运行；必要时回退到云端 CPU 批处理 |
| 配置错误 | Pydantic 配置校验不当导致任务失败 | 编写单元测试/CI 校验配置 schema，提供默认值与示例 |
| 网络不稳定 | 本地→Hugging Face/Notion 同步中断 | 增量同步 + 重试队列，失败任务记录日志并可重放 |
| API 成本 | 多模型摘要导致费用不可控 | 在配置中加入预算阈值，超限自动切换到成本更低模型 |

### 后续验证指标

- 每日流水线从抓取到发布的总耗时 < 2 小时。
- 嵌入补齐延迟 < 30 分钟，并有失败重试记录。
- 每周自动生成的备份包可在独立环境恢复。
- 远程触发 API 接口含审计日志，能追溯触发者、参数、执行结果。
- 配置文件修改后重启并通过自检 < 5 分钟。
