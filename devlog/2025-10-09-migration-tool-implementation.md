# 2025-10-09 Migration Tool Implementation
Status: In Progress
Last-updated: 2025-10-03

## Context
- 按照 `2025-10-08-data-migration-plan.md` 的路线，开始落地迁移工具。
- 目标：在当前仓库中实现遗留数据迁移模块，并补充自动化测试。

## Actions
- 新增 `papersys.migration.legacy` 模块，封装 Hugging Face parquet、偏好 CSV 与摘要 JSON/JSONL 的整理逻辑。
- 提供 Typer CLI 入口，支持 dry-run、force、模型/年份筛选与缓存定制。
- 实现偏好合并去重、摘要标准化写入、迁移报表输出等功能。
- 调整迁移落地点以匹配 `devdoc/architecture.md` 中的 `data/` 分层结构，生成年度 metadata、模型 manifest/backlog 以及 `preferences/events-YYYY.csv`、`summaries/YYYY-MM.jsonl` 等文件。
- 补充单元测试覆盖 dry-run 与实际写入两种路径，验证偏好聚合与摘要归档结果。

## Verification
- 运行 `uv run --no-progress pytest tests/migration/test_legacy.py`（2 例全部通过）。
- 手动检查输出目录结构与迁移报表内容符合预期。

## Follow-ups
- 接入 CLI 的顶层命令（`papersys.cli`）以便统一调用。
- 为 Hugging Face 下载添加重试/速率限制策略，避免网络抖动影响批量迁移。
- 扩展迁移后的数据校验（schema 校正、统计对齐等），并与现有 pipeline 做一次端到端验证。
