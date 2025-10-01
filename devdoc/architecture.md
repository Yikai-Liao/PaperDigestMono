# 论文推送系统单例化重构

## 功能概览

我的目标是搭建一个自动化的论文推送系统，包含了论文信息收集，筛选，归纳总结，可视化展示，反馈收集这么几个宏观的流程。

具体来讲，就是每天自动从Arxiv爬虫获取最新的论文meta data（包含摘要），然后自动更新一个总的论文 Embedding 池中。根据历史中已有的二分类数据，使用特定算法训练一个输入为Embedding的简单的二分类模型，根据这模型的打分结果，采样出一定数量的论文作为新增的需要展示的论文。然后获取这些论文具体的latex/pdf，转换为markdown形式，然后通过特定的prompt输入给llm api进行摘要，抽取我需要的特定信息（包含多个字段）保存到json中。这个json作为数据存储的媒介，可以快速格式化到各种形式。之后的流程是，格式化为markdown，添加到一个静态博客中，发布到cloudflare。这个静态博客接入了giscus系统，因此我可以通过定期检测github discussion中每个论文对应的评论区中来自用户自己添加的表情，来确定这个新论文的标签是possive 还是negtive，这个数据会被收集起来，用于下一轮的模型训练。

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

- **元数据（metadata）**：按年份拆分的 CSV（可选 Parquet 以保留 schema），字段包含论文基础信息与数据版本号。
- **嵌入（embeddings）**：每个模型 × 每个年份独立 Parquet，列格式 `[id, embedding: list[float32], stats]`（默认 `float16` 节省空间），允许并行新增模型。
- **偏好（preferences）**：追加式 CSV/JSONL，记录事件时间、来源（giscus/notion/manual）。
- **摘要（summaries）**：按 `year/month` 生成 JSONL，字段含 `paper_id、sections、model_meta`，方便 git diff。
- **缓存（artifacts）**：PDF、LaTeX 中间件放入挂载卷，统一清理策略。

所有数据以 `data/` 顶级目录分类，Docker 挂载本地硬盘；云端定期同步（见备份策略）。

### 配置管理策略

- 提供一个根配置文件 `config.toml`，由 `BaseConfig`（Pydantic `BaseModel`）解析。
- 按子模块继承，例如 `EmbeddingConfig`, `LLMConfig`, `SchedulerConfig`，均实现 `@classmethod from_toml(path: Path)`。
- 在运行时通过简单的 `load_config()` 辅助函数向各服务注入 Pydantic 对象；如未来出现多进程/多租户需求，可再引入 `ConfigRegistry` 或依赖注入容器，但当前阶段保持简洁。
- 配置变更通常低频，约定“修改后重启服务”，无需支持热加载，仅需启动时校验并输出有效配置快照。
- 在参考仓库落地：
	- `ArxivEmbedding` 中的模型列表由 `EmbeddingConfig` 管理，取代当前直接访问字典。
	- `PaperDigest` 中的 LLM 参数、模板路径、采样阈值通过 `LLMConfig` 和 `PipelineConfig` 提供，脚本重构为 `uv run python -m paper_digest.cli summarize --config ./config.toml` 类似接口。

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

### 内容生产与发布

- **Markdown 渲染**：继续使用 Jinja2 模板，但封装成 `ContentRenderer` 类，支持 Astro 网站与 Notion 两种输出模式。
- **LaTeX→Markdown 流程**：保留 `latex2json` 主路，`marker` 作为 fallback，确保日志清晰即可，短期内不额外实现复杂的回滚机制。
- **版本化存储**：Markdown/JSONL 结果写入 `output/`，以 Git 提交或 Notion API 同步方式对外发布；Cloudflare Pages 仍由 GitHub Action 部署。

### 反馈采集与偏好回写

- **giscus**：保留现有讨论区采集脚本，迁移为 `FeedbackCollector` 子模块，解析 emoji → 偏好事件。
- **Notion**：若切换到 Notion 展示，直接读取数据库中的“打分”列生成偏好事件。
- **手动导入**：保留 Zotero → CSV 转换脚本，接入统一偏好写入接口。

### 备份与同步策略

- **主存储**：本地 `data/` 目录（挂载卷）。
- **远程备份**：
	- 元数据与嵌入：按模型/年份将 Parquet 推送至 Hugging Face（继续使用，但降低频率，例如每日/每周一次）。
	- 摘要与偏好：压缩打包上传至私有对象存储或 GitHub Release。
	- 配置备份：`config.toml` 与偏好 CSV 自动同步到私有 git 分支。

### 迁移步骤（建议）

1. 建立 Python 包骨架（`papersys/`），抽取 `ArxivEmbedding` 与 `PaperDigest` 中的可复用逻辑。
2. 实现 Pydantic 配置体系，并替换脚本中的直接字典访问。
3. 引入调度器与 HTTP API，完成本地单例 PoC。
4. 将生成的数据目录整理为新结构，编写迁移脚本从旧 Parquet/JSON 拆分。
5. 配置云端备份与 GitHub Action 触发入口。
6. 渐进式替换旧流水线，期间保留旧 Action 作为 fallback。

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





