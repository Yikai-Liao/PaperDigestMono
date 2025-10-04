# Migration CLI & Validation Follow-up
Status: Completed
Last-updated: 2025-10-11

## Current situation
- `papersys.migration.legacy` 已提供核心迁移实现与 Typer 子命令，但尚未纳入主 CLI，团队成员需要手动调用模块入口。
- Hugging Face 下载流程缺少重试与速率控制，遇到瞬时网络抖动会导致迁移中断且未出具补偿策略。
- 迁移输出（metadata/embeddings/preferences/summaries）仅依赖运行时直觉检查，缺乏自动化 schema 校验与报告断言，集成测试覆盖有限。
- 文档仍引用旧的手动脚本路径，未同步新的 CLI 与验证流程。

## Risks
- CLI 未集成导致实际使用门槛高，易于偏离统一入口的运维约定。
- 下载失败后未重试可能造成批量迁移不完整，而迁移日志又提示成功，影响数据可信度。
- 缺乏 schema 校验会让脏数据悄然写入生产 `data/`，后续流水线调试成本陡增。
- 文档与实现脱节会让后续接手者误用旧参数或路径，降低协作效率。

## Plan
1. 将迁移命令注册到 `papersys.cli`，支持 `migrate legacy` 子命令，复用现有 `MigrationConfig`，并输出与设定一致的 JSON 报告。
2. 在 `legacy._load_year_frame` / HF 下载链路中补充指数退避重试与最小间隔控制，允许 `--max-retries`、`--retry-wait` 配置，确保默认值兼顾可靠性与速度。
3. 实现轻量 schema 校验函数，验证 metadata/embeddings/preferences/summaries 的列集与非空约束，并将校验结果写入迁移报告；必要时在 CLI 中提供 `--strict` 选项决定失败策略。
4. 更新/新增测试：
   - 为 CLI 命令编写集成测试，覆盖 dry-run 及失败分支。
   - 扩展现有迁移测试，验证 schema 校验与报告字段。
5. 同步文档：更新 `devdoc/architecture.md` 与 `devdoc/env.md` 中的迁移部分，说明新 CLI 与重试策略；在完成后回填 devlog 执行记录。

## Rollback strategy
- 若 CLI 行为不兼容，可临时隐藏 `migrate` 子命令并退回到模块级入口，相关改动集中在单文件内易于逆转。
- 若重试逻辑导致 Hugging Face API 封锁，可切换到单次下载流程并在 devlog 记录经验，确保旧逻辑仍可用。
- 校验失败导致流程卡死时，可通过 `--strict=false` 暂时降级为 warning，并保留原始输出以便后续排查。

## Acceptance checklist
- `papersys.cli migrate legacy` 支持 dry-run / 非 dry-run，且输出报告与旧接口一致。
- 重试策略在模拟失败测试中生效，并在日志/报告中可见重试计数。
- 校验函数覆盖四类输出并在 pytest 中验证断言。
- 文档与 devlog 更新到位，测试全绿。

## Execution record
- 2025-10-11：集成 `papersys.cli migrate legacy` 命令，接入 LegacyMigrator 配置并提供 `--max-retries`、`--retry-wait`、`--strict/--no-strict` 等选项。
- 2025-10-11：在 LegacyMigrator 中加入下载重试统计、输出 schema 校验与验证日志写入。
- 2025-10-11：新增/更新测试 `tests/migration/test_legacy.py`、`tests/cli/test_cli_migrate.py`，运行 `uv run --no-progress pytest tests/migration/test_legacy.py` 与 `uv run --no-progress pytest tests/cli` 全部通过。
- 2025-10-11：更新 `devdoc/architecture.md` 与 `devdoc/env.md` 说明迁移 CLI、重试策略与 dry-run 流程。
