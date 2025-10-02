# TODO: Configuration Tooling & Linting

## Summary
- Build developer tooling that validates and introspects `config.toml` files to prevent runtime misconfiguration.
- Offer a CLI subcommand that reports config health, deprecated fields, and diff against example templates.

## Deliverables
1. A new CLI command (e.g., `uv run python -m papersys.cli config check`) performing schema validation, default expansion, and friendly error messages.
2. Optional `--explain` flag generating per-field documentation sourced from Pydantic model descriptions.
3. Integration tests ensuring malformed configs raise actionable errors and valid configs succeed.
4. Documentation update describing the command and sample outputs.

## Constraints & Notes
- Reuse existing Pydantic models; do not introduce new config parsers.
- Ensure command execution is fast (<1s) and produces structured output suitable for CI.
- Include type hints everywhere and rely on `pathlib.Path` for file access.

## Suggested Branch Name
`feat/config-tooling`

## Prompt
```
遵循 #file:rules.md 的约束完成任务：
1. 新增 CLI 子命令用于检查与说明配置项，提供机器可读与人类可读两种输出模式。
2. 针对典型错误编写 pytest 单测，验证命令退出码与输出内容。
3. 更新示例配置与文档，确保新增字段或提示同步。
```
