# CLI 清洁化重构计划（2025-10-05）
Status: Completed
Last-updated: 2025-10-03

## 现状
- `papersys/cli.py` 的 `main` 函数超过 250 行，集中处理所有子命令，存在嵌套分支与重复逻辑。
- 子命令执行逻辑缺乏封装与复用，难以扩展新的 CLI 功能，也不利于单元测试覆盖。
- 日志输出与错误处理分散在多个条件分支中，可读性差，增加了维护成本。

## 风险评估
- 重构过程中若漏掉分支或参数处理，可能导致现有 CLI 行为（特别是 `serve --dry-run`、`config` 子命令）发生变化。
- 与调度、嵌入服务的依赖交互较多，需要确保懒加载/导入顺序不被破坏，以免增加启动时长。
- 单测覆盖主要集中在 serve/部分配置，需要补充或调整断言以匹配新的封装接口。

## 实施方案
1. 阅读 `tests/cli/*` 及相关服务模块（ingestion、embedding、scheduler），确认 CLI 与子命令的输入输出契约。
2. 为每个子命令提炼独立的 handler 函数，返回整型状态码，并保留当前日志与异常语义；同时集中处理共用逻辑（加载配置、路径解析等）。
3. 在 `main` 中构建命令分发表，负责解析参数、加载配置与调度 handler，删除长链式 `if/elif`，提高可读性与可扩展性。
4. 根据需要调整/新增 CLI 单元测试，确保所有分支被覆盖；如有必要，为新函数补充模块级测试。
5. 检查其它存在超长函数的 CLI 相关文件（如未来扩展入口），列出潜在的后续重构项并记录在 TODO。

## 回滚策略
- 以 Git 提交为粒度，保留重构前的 `papersys/cli.py` 副本；若出现不可修复问题，可通过 `git revert` 回退到前一稳定提交。
- 如仅部分子命令受影响，可暂时恢复对应 handler 的旧实现，再逐步替换。

## 测试计划
- `uv run --no-progress pytest tests/cli/test_cli_serve.py`
- `uv run --no-progress pytest tests/config/test_embedding_config.py`
- `uv run --no-progress pytest`

## 执行记录（2025-10-03）
- 按计划将 `papersys/cli.py` 重构为基于 handler 的结构，新增 `_COMMAND_HANDLERS` 与针对各子命令的独立函数，维持原有日志与返回码语义。
- 抽取 `_select_embedding_model` 辅助方法，复用模型选择逻辑并保持类型提示完整。

### 测试
- `uv run --no-progress pytest` ✅（68 项通过）
