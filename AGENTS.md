# AGENTS.md

## Project overview
- **Purpose**: PaperDigestMono 构建了一个本地优先的论文采集、推荐、摘要与发布流水线。
- **关键模块**：
  - `papersys/config` – 以 Pydantic 管理 TOML 配置（App、Scheduler、LLM、Pipeline 等）。
  - `papersys/scheduler` – 基于 APScheduler 的作业调度，现已具备结构化日志、Prometheus 指标与手动触发入口。
  - `papersys/web` – FastAPI 应用，暴露 `/health`、`/jobs`、`/scheduler/run/{job_id}`、`/metrics` 等接口。
  - `papersys/cli.py` – 统一入口（`serve` 等命令）串联配置、调度器、Web 控制台。
- **文档索引**：系统架构请先读 `devdoc/architecture.md`，环境约束见 `devdoc/env.md`，流程规范见 `devdoc/rool.md`。

## Environment & tools
- 仅使用 **uv** 管理 Python 3.12+ 环境：
  - 运行命令统一格式：`uv run --no-progress python …`、`uv run --no-progress pytest …`。
  - 安装/卸载依赖：`uv add <pkg>` / `uv remove <pkg>`；禁止直接改写 `pyproject.toml` 或使用 `pip install` 系列命令。
- 默认选用现代 CLI 与库：`duckdb`、`polars`、`numpy`、`fastapi`、`loguru`；避免 `find`、`conda`、`pandas`、`logging`。
- 数据处理优先 `polars`（惰性执行）与 `duckdb`（复杂查询），兼容 HuggingFace 数据源。
- Python 代码务必使用 `pathlib.Path` 管理路径。
- Shell 命令必须是非交互式的；提前确认输出量，避免进入分页或需要人工确认的流程。

## Workflow guardrails
- 多文件或复杂改动前，必须在 `devlog/` 下新增变更计划 Markdown，覆盖现状、风险、方案与回滚策略，经确认后再动代码。
- 命令行禁用交互式或需要人工确认的操作（如默认的 `git merge` 编辑器、`rm -i` 等）。若需合并，使用非交互命令组合完成。
- 变更完成后按计划执行自动化测试并在 devlog 中记录结果与反思（若偏离预期）。

## Collaboration mindset
- 保持耐心细致：完整阅读相关代码与文档，再动手实现，拒绝“跳步骤”或侥幸通过测试。
- 遇到不确定性时及时沟通，宁可多问也不要猜测需求或接口行为。
- 信息检索是首选手段：对于第三方库、奇怪报错或依赖问题，优先查阅官方文档、GitHub Issues、StackOverflow 等资源。

## Coding conventions
- 代码、注释、提交信息写英文；与用户交流使用中文。
- 强制完整 type hints；无需为非法输入写过度兼容逻辑，应让 Pydantic/异常直接拒绝。
- 偏好简洁、少嵌套、可复用、面向对象设计；必要时添加精炼注释。
- 坚持使用 Loguru（禁止 `logging` 模块），保留结构化输出。
- 配置变更走 TOML + Pydantic 模型流程，确保示例配置 (`config/example.toml`) 与测试同步。
- 控制依赖数量，若现有库可满足需求，避免额外引入。

### Clean code checklist
- 遵循标准命名：描述性、可搜索、可发音，消除魔法数，以常量取代。
- 小函数、单一职责、无副作用；避免布尔开关参数，优先拆分方法。
- 使用早返回、`break`/`continue`、专用对象来减少嵌套与逻辑耦合。
- 注释只用于表达意图或重要警告，勿冗余、勿保留注释掉的代码。
- 结构整洁：相关逻辑上下相邻，变量贴近使用位置，保持合理空行与缩进。
- 测试要快、独立、可重复，并针对变更补齐覆盖。

## Build & test commands
- 全量测试：
  ```bash
  uv run --no-progress pytest
  ```
- 定向测试示例：
  ```bash
  uv run --no-progress pytest tests/scheduler/test_service.py
  uv run --no-progress pytest tests/web/test_app.py
  ```
- 任何功能修改后都要更新/新增 pytest 用例，保持 `33`+ 项测试全绿。

## Git & merge guidelines
- 合并使用非交互命令：`git merge --no-ff --no-edit <branch>`；如目标分支可 fast-forward，首选 `git merge --ff-only`。
- 合并前执行 `git fetch --all` 并同步最新主干。
- 提交前确保工作树整洁 (`git status -sb`)，必要时 `git restore` / `git clean`。
- 推送前至少运行一次完整测试并确认通过。

## PR review discipline
- 默认将外部贡献者视作未经验证的同事，逐项核对需求是否被正确理解与完整实现。
- 全量检查是否存在破坏性变更（接口行为、持久化格式、配置示例、兼容性等），必要时回溯需求确认。
- 关注代码风格与架构一致性：命名、文件组织、依赖选择需与现有约定保持一致，禁止随意新增目录或脚手架。
- 审核测试策略：确认新增/修改的测试覆盖目标行为，避免跳过或弱化原有测试；必要时要求补充。
- 对不确定项写下评审意见并请求说明，不假设对方“应该懂”。在 merge 前宁缺毋滥。

## Documentation expectations
- 若新增功能或调整流程，更新：
  - `devdoc/architecture.md`（架构与模块职责）。
  - 关联 TODO 文档（在 `devdoc/todo/` 下标记进度）。
  - 需要时追加 `devlog/<date>-<topic>.md` 记录实施详情。
- 前端/控制台改动需说明部署与鉴权方式；调度/指标改动需记录采集方式与监控入口。

## Additional tips
- SQL 语句保持全大写关键字、4 空格缩进、禁止 `SELECT *`，并为复杂逻辑添加注释。
- Scheduler 日志默认写入 `logs/scheduler.log`（Loguru JSON），指标通过 `/metrics` 暴露。
- 处理配置或鉴权时，优先复用现有 Pydantic 模型与 FastAPI 依赖注入。
- 若需参考外部规范或已有实现，可查看 `reference/` 子模块及 `devlog` 历史记录。
- 遇到大型或高风险改动，先起草计划并征求确认；必要时可在终端通过 `claude -p "总结一下这个项目"` 获取快速概览。
