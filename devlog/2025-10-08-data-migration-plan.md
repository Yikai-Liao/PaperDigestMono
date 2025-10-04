# 数据迁移开发计划（2025-10-08）
Status: Completed
Last-updated: 2025-10-11

## 1. 背景与目标
- 当前仓库已重构出本地优先的数据管线，但历史数据仍散落在 `reference/ArxivEmbedding`、`reference/PaperDigest`、`reference/PaperDigestAction` 以及 Hugging Face 数据集中，尚未迁移到新的 `metadata/`、`embeddings/`、`preference/`、`summarized/` 目录结构。
- 推荐与摘要流水线的集成测试依赖本地缓存，这意味着在完成迁移前难以做端到端演练。
- 目标是在保持数据可追溯的前提下，实现一次性迁移脚本，统一落地以下资源：
  1. **元数据**：按年份生成规范化 CSV，并在本地缓存。
  2. **嵌入向量**：按模型别名与年份拆分 Parquet，补齐元数据对齐字段。
  3. **偏好事件**：合并旧仓库 CSV，去重后输出到顶层 `preference/`。
  4. **摘要数据**：将 JSON / JSONL 汇总为 `summarized/*.jsonl`，供推荐管线过滤已发布内容。

## 2. 现状调研
- `papersys` 已提供 `IngestionService`、`EmbeddingService` 等模块，但缺少历史数据导入工具。
- `reference/ArxivEmbedding` 保留拉取脚本，核心数据托管在 Hugging Face `lyk/ArxivEmbedding`（Parquet，包含元数据+多模型 embedding）。
- `reference/PaperDigest/raw/*.json` 存放结构化摘要，`reference/PaperDigestAction/summarized/*.jsonl` 按月追加直播流水。
- 偏好 CSV 分散在 `reference/PaperDigest/preference/` 与 `reference/PaperDigestAction/preference/`，字段为 `id,preference`。
- 现有目录 `metadata/raw`、`embeddings/conan_v1` 存在示例数据，需确保迁移脚本支持覆盖/追加并生成校验清单。

## 3. 执行结果
- 迁移入口统一为 `papersys.cli migrate legacy`，支持年份/模型筛选、dry-run、下载重试与严格校验参数，替代原计划的脚本形式。
- Hugging Face 年度 Parquet 已拆分写入本地：`data/metadata/metadata-2017.csv` ~ `metadata-2025.csv` 及 `data/metadata/latest.csv`；嵌入落地于 `data/embeddings/conan_v1/*.parquet`、`data/embeddings/jasper_v1/*.parquet`，并生成 manifest/backlog。
- 偏好事件合并去重后输出 `data/preferences/events-2025.csv` 与 `data/preferences/events-unknown.csv`，保留缺失月份的记录以备后续补充。
- 摘要 JSON/JSONL 统一为 `data/summaries/2025-05.jsonl` 与 `data/summaries/2025-06.jsonl`，记录源文件与迁移时间戳。
- 生成 `data/migration-report.json`（771,373 条元数据与双模型嵌入、733 条偏好、575 条摘要），报告中未出现警告。
- `devdoc/architecture.md` 与 `devdoc/env.md` 已更新迁移流程；新增 `devlog/2025-10-11-migration-cli-validation.md` 记录命令、校验与测试结果。

## 4. 数据校验快照（2025-10-11）
- 元数据：`data/metadata` 下包含 2017-2025 年度 CSV 与 `latest.csv`；抽样检查行数与 `migration-report.json` 一致。
- 嵌入：`data/embeddings/conan_v1/2025.parquet`、`data/embeddings/jasper_v1/2025.parquet` 均存在，manifest 统计与报告对齐。
- 偏好：`data/preferences/events-2025.csv` 覆盖 2025 年所有事件；`events-unknown.csv` 集中未能解析月份的历史记录，后续可新增修正脚本。
- 摘要：`data/summaries/2025-05.jsonl`、`2025-06.jsonl` 均为结构化 JSONL，字段顺序遵循迁移定义，验证通过。
- 报告：`data/migration-report.json` 含 metadata/embeddings/preferences/summaries 统计、总行数及空 warning，作为日后回溯基准。

## 5. 跟进与治理
- 后续若需增量迁移，可复用 `papersys.cli migrate legacy --dry-run --year <YYYY>`，通过报告校验差异后再正式写入。
- 建议在反馈事件补录完成后清理 `events-unknown.csv`，并将映射规则纳入反馈服务。
- 迁移结果已纳入 CLI/pytest 覆盖（`tests/migration/test_legacy.py`、`tests/cli/test_cli_migrate.py`）；如迁移规则再变动，需同步更新这些测试与报告字段定义。
## 6. 经验与回滚
- 已验证 dry-run 模式不会产生写入，可在需要时快速复核数据差异。
- 若需回滚，可基于 `data/migration-report.json` 的统计删除对应年度文件并重新执行 `migrate legacy --year <YYYY> --force`。
- 保留参考仓库副本与 Hugging Face 数据源，确保迁移逻辑未来调整时具备对照样本。
