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
  - 安装/卸载依赖：`uv add <pkg>` / `uv remove <pkg>`；禁止直接改写 `pyproject.toml`。
- 倾向采用现代 CLI：`lsd`、`fd`、`tokei`、`duckdb`、`polars`、`numpy`、`fastapi`、`loguru` 等；避免 `find`、`conda`、`pandas`、`logging`。
- Python 代码务必使用 `pathlib.Path` 管理路径。

## Workflow guardrails
- 多文件或复杂改动前，必须在 `devlog/` 下新增变更计划 Markdown，覆盖现状、风险、方案与回滚策略，经确认后再动代码。
- 命令行禁用交互式或需要人工确认的操作（如默认的 `git merge` 编辑器、`rm -i` 等）。若需合并，使用非交互命令组合完成。
- 变更完成后按计划执行自动化测试并在 devlog 中记录结果与反思（若偏离预期）。

## Coding conventions
- 代码、注释、提交信息写英文；与用户交流使用中文。
- 强制完整 type hints；无需为非法输入写过度兼容逻辑，应让 Pydantic/异常直接拒绝。
- 偏好简洁、少嵌套、可复用、面向对象设计；必要时添加精炼注释。
- 坚持使用 Loguru（禁止 `logging` 模块），保留结构化输出。
- 配置变更走 TOML + Pydantic 模型流程，确保示例配置 (`config/example.toml`) 与测试同步。
- 控制依赖数量，若现有库可满足需求，避免额外引入。

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

## Documentation expectations
- 若新增功能或调整流程，更新：
  - `devdoc/architecture.md`（架构与模块职责）。
  - 关联 TODO 文档（在 `devdoc/todo/` 下标记进度）。
  - 需要时追加 `devlog/<date>-<topic>.md` 记录实施详情。
- 前端/控制台改动需说明部署与鉴权方式；调度/指标改动需记录采集方式与监控入口。

## Additional tips
- Scheduler 日志默认写入 `logs/scheduler.log`（Loguru JSON），指标通过 `/metrics` 暴露。
- 处理配置或鉴权时，优先复用现有 Pydantic 模型与 FastAPI 依赖注入。
- 若需参考外部规范或已有实现，可查看 `reference/` 子模块及 `devlog` 历史记录。
- 遇到大型或高风险改动，先起草计划并征求确认；必要时可在终端通过 `claude -p "总结一下这个项目"` 获取快速概览。
