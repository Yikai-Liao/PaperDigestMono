# CLI 标准化测试与清洁化修正计划（2025-10-06）
Status: Completed
Last-updated: 2025-10-03

## 现状
- Typer 重构后的 CLI 尚无针对顶层 callback 和 `status`、`summarize` 等通用命令的系统化测试覆盖，`tests/cli` 仅验证 `serve --dry-run` 与配置子命令。
- `embed` 命令在 `if backlog:` 分支下直接堆叠了大段循环逻辑，违反既定 clean code 准则，降低可读性与可测试性。
- 缺乏对默认入口（无子命令、`--dry-run` 兼容路径）的回归保障，容易在未来改动中引入行为回退。

## 风险评估
- 触发 CLI 命令时会加载完整配置并初始化多个服务，若测试用例构造的配置不当，可能意外访问网络/文件系统导致测试不稳定。
- 抽取 backlog 处理函数时需保证所有日志与退出码语义保持不变，否则现有用户脚本可能受到影响。
- 增补测试需与现有 logger 捕获逻辑兼容，避免造成 CI 噪音或 flaky 输出。

## 实施方案
1. 设计最小化的 TOML 配置片段，仅启用所需模块，确保 CLI 命令在测试中可重复执行且不触发外部依赖。
2. 为 `status --dry-run` 与顶层 `--dry-run` 路径新增单元测试，覆盖日志输出与退出码；必要时抽取测试辅助函数，复用 log 捕获逻辑。
3. 将 `embed` 命令 backlog 处理的长分支提炼为私有辅助函数，保持现有日志文本与统计逻辑，主流程仅负责调度。
4. 运行并记录针对性与全量 pytest，确认新增测试通过且未破坏既有覆盖。

## 回滚策略
- 以单次 Git 提交为回滚单元；如测试新增导致失败，可首先回退测试文件，确认 CLI 行为保持稳定后再排查。
- 若 backlog 抽取后的逻辑出现回归，可将新辅助函数恢复为内联实现，同时保留新增测试帮助复现问题。

## 测试计划
- `uv run --no-progress pytest tests/cli/test_cli_status.py`
- `uv run --no-progress pytest tests/cli`
- `uv run --no-progress pytest`

## 后续跟踪
- 根据测试效果评估是否需要为其它 Typer 子命令（如 `ingest`、`embed` 标准路径）补充集成测试，纳入 TODO 列表。

## 执行记录（2025-10-03）
- 复用最小化配置生成器新增 `tests/cli/test_cli_status.py`，覆盖 `status --dry-run` 与顶层 `--dry-run` 两条关键路径。
- 抽取 `_process_embedding_backlog` 辅助函数，简化 `embed` 命令中 backlog 分支的控制流，实现与原逻辑等价的日志与计数行为。
- 使用 `uv run --no-progress pytest tests/cli/test_cli_status.py`、`uv run --no-progress pytest tests/cli` 与 `uv run --no-progress pytest` 验证所有测试全绿。
