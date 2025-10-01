# 配置拆分与管线落地开发计划（2025-10-02）

## 1. 背景与目标

在 `devdoc/architecture.md` 与 `devlog/2025-10-architecture-review.md` 中已经完成了新架构蓝图与初步实现（`papersys` 包骨架、基础配置加载、CLI 入口）。接下来需要将历史仓库（`reference/PaperDigest`, `reference/PaperDigestAction`）中的推荐与摘要管线逐步迁移到单例化架构中，同时扩展配置体系，使业务逻辑可以通过强类型的 Pydantic 模型直接访问配置字段。

本阶段目标：

1. **配置分层落地**：把推荐、摘要、LLM 等模块的配置拆分为独立的模型，保持类型安全与清晰的模块边界。
2. **核心服务封装**：将推荐与摘要管线重构为可复用模块，支持后续调度与控制台调用。
3. **调度与控制台基建**：建立本地调度器与轻量 Web/API 控制台，为远程触发与状态查看打基础。
4. **数据迁移 & 集成验证**：设计数据目录迁移脚本，并完成最小化的端到端集成测试流程。

## 2. 任务拆分与验收标准

| ID | TODO | 交付物 | 验收方式 |
| --- | --- | --- | --- |
| T5 | 迁移推荐/摘要/LLM 配置模型，扩展示例配置 | `papersys/config/recommend.py`、`summary.py`、`llm.py` 等；更新 `config/example.toml`；扩充测试 | `uv run --no-progress pytest tests/config/test_load_config.py` 通过；文档同步说明配置层级 |
| T6 | 封装推荐管线模块（数据加载、训练、预测） | `papersys/recommend/*.py`；最小数据 fixture & 单测 | `uv run --no-progress pytest tests/recommend/test_trainer.py` 等通过；CLI 能输出推荐模块状态 |
| T7 | 构建摘要流水线骨架（PDF 获取、LLM 调用、渲染接口） | `papersys/summary/*.py`；异步/重试策略；日志接口 | `uv run --no-progress pytest tests/summary/test_pipeline.py`；CLI `summarize --dry-run` 输出模块状态 |
| T8 | 实现调度服务与本地控制台（FastAPI + APScheduler） | `papersys/scheduler/service.py`、`papersys/web/app.py`；CLI 新增 `serve` 子命令 | `uv run --no-progress python -m papersys.cli serve --dry-run` 成功输出监听信息；新增 API 健康检查测试 |
| T9 | 数据目录整理与迁移脚本 | `scripts/migrate_data.py`；支持 `--dry-run`；更新文档 | 在临时目录执行脚本输出目标结构；脚本测试通过 |
| T10 | 集成测试：凑齐“抓取→嵌入→推荐→摘要→输出” 验证链路 | `tests/system/test_pipeline.py`；CLI `pipeline --dry-run` | `uv run --no-progress pytest tests/system/test_pipeline.py` 通过；命令正确串联模块 |

## 3. 风险与对策

| 风险 | 描述 | 缓解策略 |
| ---- | ---- | ---- |
| 配置迁移不一致 | TOML 示例与模型字段不匹配，导致运行失败 | 单元测试覆盖所有配置模型；为示例文件写额外断言 |
| 历史脚本依赖众多 | 引入过多第三方库、增加复杂度 | 优先复用现有依赖；必要时拆分为可选模块，控制依赖范围 |
| 调度与控制台耦合过紧 | 首版实现难以扩展远程触发 | 控制台先实现 `--dry-run`、健康检查；将后续功能列入 TODO，不一次性做完 |
| 集成测试耗时长 | 端到端流程涉及外部服务 | 构造最小离线样本或 mock；确保 CI 可快速执行 |

## 4. 校验流程

1. 每个任务完成后，更新 `devlog/2025-10-architecture-review.md` 与本文件的状态（如有新增风险或变更计划需同步）；记录可回滚的 git 提交哈希。
2. 统一使用 `uv run --no-progress` 执行所有命令，保证环境一致性。
3. 在 `devdoc/architecture.md` 中补充落地后的结构变化或新增的模块说明。
4. 每个阶段结束前执行 `git status`、`git add`、`git commit`、`git push`，并在日志中记录提交 ID。

## 5. 当前仓库基线

- 当前 HEAD：`9f7260b3ab03ee846511ba13475caae4dc367b46`（配置加载与 CLI 落地）
- 本计划生效时间：2025-10-02

---

> 后续将从 T5 开始执行，若在推进过程中发现新的风险或依赖调整，会同步更新此计划和架构文档。
