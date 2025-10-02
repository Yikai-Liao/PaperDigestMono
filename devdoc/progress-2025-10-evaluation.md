# 2025-10 仓库开发进度评估

## 1. 总体结论
- ✅ **核心骨架已完成**：配置体系、推荐/摘要流水线、调度与 Web 控制台均已以模块化形式落地，并通过 CLI 统一编排，满足“本地单例化”一期目标。
- ✅ **测试覆盖成型**：围绕配置解析、推荐与摘要流程、调度服务及 FastAPI 接口建立了系统级单元/集成测试，当前 `pytest` 覆盖 28 项用例（见 devlog 记录）。【F:devlog/2025-10-config-refactor-plan.md†L134-L171】
- ⚠️ **尚缺端到端联调与数据迁移工具**：数据迁移脚本与系统级流水线测试仍在待办列表，尚未交付（T9/T10）。【F:devlog/2025-10-config-refactor-plan.md†L16-L24】

## 2. 已完成能力盘点
### 2.1 配置与 CLI 基线
- `config/example.toml` 已覆盖调度、推荐、摘要、LLM 全量参数示例，支撑 Pydantic 校验与后续文档引用。【F:config/example.toml†L1-L82】
- CLI 提供 `status`、`summarize`、`serve` 子命令，并统一支持 `--dry-run` 校验，`status` 还会检查推荐数据源是否存在，便于部署前自查。【F:papersys/cli.py†L18-L191】
- 配置加载测试验证示例文件与错误分支，确保 TOML 变更即时触发失败回归。【F:tests/config/test_load_config.py†L15-L77】

### 2.2 推荐流水线
- 数据加载器完成偏好 CSV、候选 Parquet、历史摘要去重等逻辑，支持类别/年份过滤与嵌入有效性检查。【F:papersys/recommend/data.py†L15-L216】
- 集成测试覆写“加载→训练→预测→筛选”全过程，验证过滤条件、模型输出以及流水线容器返回结构。【F:tests/recommend/test_pipeline.py†L24-L182】

### 2.3 摘要流水线
- `SummaryPipeline` 将 PDF 拉取、LLM 摘要与 Markdown 渲染串联，dry-run 会提前创建目录并打印状态，确保环境可用。【F:papersys/summary/pipeline.py†L20-L121】
- 测试涵盖真实产物生成、dry-run 行为与未知 LLM 失败路径，保证模块在无外部依赖场景下可运行。【F:tests/summary/test_summary_pipeline.py†L46-L103】

### 2.4 调度与 Web 控制
- `SchedulerService` 已能按配置注册推荐/摘要作业、支持 dry-run、列出作业并允许手动触发一次性任务。【F:papersys/scheduler/service.py†L12-L142】
- FastAPI 应用暴露 `/health`、`/jobs`、`/scheduler/run/{job_id}` 接口，与 CLI `serve` 子命令整合，dry-run 模式仅验证配置。【F:papersys/web/app.py†L9-L38】【F:papersys/cli.py†L48-L125】
- CLI、调度与 Web 层均配有针对性测试，覆盖日志输出、API 返回和手动触发路径。【F:tests/cli/test_cli_serve.py†L9-L45】【F:tests/scheduler/test_service.py†L30-L85】【F:tests/web/test_app.py†L9-L70】

## 3. 质量与运维现状
- **测试策略**：以模块为单位构建 Pytest 覆盖，并通过 devlog 记录全量测试通过的频次；现阶段重点在单仓本地运行，不依赖外部服务即可完成大部分验证。【F:devlog/2025-10-config-refactor-plan.md†L48-L176】
- **配置验证**：`status --dry-run` 和 `serve --dry-run` 具备配置巡检功能，可及时发现缺失目录或禁用作业，有助于部署自诊断。【F:papersys/cli.py†L130-L185】
- **文档同步**：`devdoc/architecture.md`、`devlog/2025-10-architecture-review.md`、`devlog/2025-10-config-refactor-plan.md` 均更新了对应阶段的交付物与风险，利于知识传递（详见 devlog 引用）。【F:devlog/2025-10-config-refactor-plan.md†L48-L176】

## 4. 未完成与风险
| 领域 | 缺口 | 影响 | 参考 | 
| ---- | ---- | ---- | ---- |
| 数据运维 | 数据目录迁移脚本、端到端系统测试（T9/T10）未落地 | 无法验证真实数据流与多阶段串联 | 【F:devlog/2025-10-config-refactor-plan.md†L16-L24】 |
| 配置工具 | 缺少配置健康检查 CLI、文档自动化说明 | 难以及时发现废弃字段或提示新字段用途 | 【F:devdoc/todo/TODO-config-observability.md†L1-L24】 |
| 可视化 | FastAPI 仅提供 API，无前端界面与鉴权策略 | 手工运维体验受限，远程访问风险未控 | 【F:devdoc/todo/TODO-web-console-ui.md†L1-L28】 |
| 备份与自动化 | 备份自动化仍在 todo，未与当前单例流程整合 | 数据丢失/恢复策略不明确 | 【F:devdoc/todo/TODO-backup-automation.md†L1-L40】 |

## 5. 后续建议
1. **优先完成 T9/T10**：实现数据迁移脚本与系统级集成测试，验证推荐/摘要输出能与真实数据目录对接。【F:devlog/2025-10-config-refactor-plan.md†L16-L24】
2. **补齐配置观测工具链**：按 TODO 方案实现配置检查子命令，并将产出纳入 CI 或日常巡检流程。【F:devdoc/todo/TODO-config-observability.md†L1-L24】
3. **增强运维界面**：在既有 FastAPI 基础上引入轻量 UI 与鉴权，提升调度可视化与手动操作体验。【F:devdoc/todo/TODO-web-console-ui.md†L1-L28】
4. **规划数据安全与备份**：梳理备份自动化方案，使本地单例具备容灾能力。【F:devdoc/todo/TODO-backup-automation.md†L1-L40】

---
*撰写时间：2025-10-XX；评估基于仓库当前主分支文件状态与 devlog 记录。*
