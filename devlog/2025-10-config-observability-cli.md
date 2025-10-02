# 配置可观测性工具开发日志（2025-10-04）

## 1. 背景与目标
- 需求来源：`devdoc/todo/TODO-config-observability.md` 提出的 CLI 配置检查工具。
- 现状痛点：当前 `papersys.cli` 仅支持 `status/summarize/serve`，无法在部署前快速验证 `config.toml`。
- 目标：新增 `config` 子命令，提供机器可读输出与字段说明，配套测试与文档更新，降低配置出错成本。

## 2. 相关文件与模块
- `papersys/cli.py`：CLI 入口，需要扩展解析与命令执行逻辑。
- `papersys/config/*`：Pydantic 模型，需提取字段描述、检测弃用字段。
- `tests/cli/`：补充 pytest 覆盖典型错误场景。
- `config/example.toml`：示例配置需同步新增提示或字段。
- `devdoc/architecture.md`：文档同步新增 CLI 能力。

## 3. 风险分析
| 风险 | 描述 | 应对策略 |
| ---- | ---- | ---- |
| JSON 输出被日志污染 | Loguru 默认输出到 stderr，若误写入 stdout 会破坏机器可读性 | 严格区分 stdout/stderr，JSON 仅使用 `print()` 输出 |
| Pydantic 类型字符串化复杂 | 嵌套 Optional/List 等类型难以转换 | 编写独立的类型格式化工具，fallback 到 `repr`，并在测试中覆盖 |
| 校验失败信息晦涩 | 直接抛出 ValidationError 难排查 | 捕获异常并整理为统一错误结构，文本模式提供重点提示 |
| CLI 参数解析混乱 | 嵌套子命令易遗漏必选参数 | 使用 `set_defaults`/`required=True` 确保 `config` 子命令必须指定动作 |

## 4. 开发方案
1. **结构化校验工具**：在 `papersys/config/inspector.py` 新增 `check_config()`、`explain_config()` 函数，封装加载、错误整理、字段文档生成。
2. **CLI 集成**：`papersys/cli.py` 新增 `config` 子命令，支持 `check` 与 `explain`，提供 `--format`（`text`/`json`），`--explain` 由子命令区分。
3. **输出策略**：
   - `text`：使用 `logger` 输出摘要、警告与错误。
   - `json`：返回结构化字典（status, warnings, errors, fields）。
4. **测试覆盖**：
   - 成功校验 + JSON 输出。
   - 缺失文件。
   - 校验失败（非法字段）。
   - `explain` 命令输出包含嵌套字段。
5. **文档与示例**：
   - 在 `config/example.toml` 顶部增加调用提示。
   - `devdoc/architecture.md` 增补“配置可观测性”段落说明。

## 5. 预期效果
- CLI 能快速校验配置并提示弃用字段，JSON 输出可用于 CI。
- 文档指导用户使用新命令，示例配置提示自检方式。

## 6. 潜在问题与补救
- 若字段说明递归时遇到循环引用，使用集合记录已访问模型以避免无限递归。
- 若未来新增字段缺少描述，`explain` 输出会空描述，需在评审时提醒补充。

## 7. 测试计划
- `uv run --no-progress pytest tests/cli/test_cli_config.py -v`
- `uv run --no-progress pytest tests/cli -v`
- 按需回归 `uv run --no-progress pytest tests/config -v` 以确保无回归。

## 8. 实施结果（2025-10-04）
- 完成 `papersys/config/inspector.py` 新增校验与说明逻辑，支持递归输出嵌套字段，并对 `UnionType` 做了兼容处理。
- `papersys/cli.py` 引入 `config` 子命令及 `--format` 切换，文本模式通过 Loguru 输出可读信息，JSON 模式适用于 CI。
- 新增 `tests/cli/test_cli_config.py` 覆盖成功校验、缺失文件、校验失败与解释输出等核心场景。
- `config/example.toml` 与 `devdoc/architecture.md` 补充了使用指引，确保文档同步。
- 测试执行：
  - `uv run --no-progress pytest tests/cli/test_cli_config.py -v`
  - `uv run --no-progress pytest tests/cli -v`

