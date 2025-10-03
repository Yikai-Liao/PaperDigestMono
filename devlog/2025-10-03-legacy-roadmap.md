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
