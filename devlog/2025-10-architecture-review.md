# 架构文档更新开发计划（2025-10-01）

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
- 2025-10-01 提交记录：`a40968659d800cd226050e4a253975f10e75aa8d`（包含 T2-T4 变更）
