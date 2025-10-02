# 数据迁移开发计划（2025-10-08）

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

## 3. 方案范围
### 范围内
- 新增脚本 `scripts/migrate_reference_data.py`：
  - 基于 `typer` 暴露 CLI，支持 `--years`、`--models`、`--dry-run`、`--source-root`、`--hf-dataset` 等参数。
  - 通过 `huggingface_hub` 下载指定年度的 Parquet，并使用 `polars` 拆分：
    - 输出 `metadata/curated/metadata-YYYY.csv`（列：`paper_id`、`title`、`abstract`、`categories`、`primary_category`、`authors`、`published_at`、`updated_at`、`doi`、`comment`、`journal_ref`）。
    - 输出 `embeddings/<model_alias>/YYYY.parquet`，字段含 `paper_id`、`embedding`、`model_dim`、`generated_at`、`source`。
  - 偏好数据：扫描参考仓库 CSV，合并去重（近期覆盖优先），输出 `preference/YYYY-MM.csv`。
  - 摘要数据：
    - 读取旧 JSON / JSONL，统一转换为一行一个对象的 JSONL，字段包括 `id`、`title`、`categories`、`score`、`abstract`、`problem_background`、`one_sentence_summary` 等原始信息，并补写 `source`、`migrated_at`。
    - 结果写入 `summarized/YYYY-MM.jsonl`，保持月份粒度。
  - 生成 `migration-report.json`（统计文件数、去重数量、跳过原因）。
- 辅助校验：实现最小 polars 校验函数，确保每个输出文件非空且 schema 匹配预期。
- 更新 `devdoc/architecture.md` / `devdoc/env.md` 中关于数据目录的落地状态。

### 非目标
- 不在本次实现 scheduler 自动触发，只提供 CLI 手动迁移。
- 不修改 Hugging Face 上的远端数据，仅做读取。
- 不重构推荐/摘要代码逻辑，除非为适配新输出格式所必须。

## 4. 关键步骤
1. **接口设计**：定义脚本 CLI、输出目录与报告格式；准备数据 schema 常量。
2. **元数据/嵌入迁移**：
   - 使用 `huggingface_hub` 下载年度 Parquet（支持缓存）。
   - 解析列拆分 metadata / embeddings，多模型列以列表形式写入。
   - 对嵌入缺失值生成 backlog 报告（写入 `embeddings/<model>/backlog-YYYY.parquet`）。
3. **偏好数据合并**：
   - 读取参考 CSV→统一 schema→按 `id` 去重（最新文件覆盖旧值）。
   - 输出至 `preference/YYYY-MM.csv` 并保留 `source` 列。
4. **摘要数据整理**：
   - 遍历 `raw/*.json`、`summarized/*.jsonl`，归一化字段。
   - 以 `summary_time` 或文件名推断年月，写入 JSONL。
5. **报告与校验**：
   - 汇总迁移条目数、跳过原因、耗时等。
   - 在 dry-run 模式下仅打印预期操作。
6. **文档更新与测试**：
   - 补充运行指南、环境要求。
   - 编写单测 / 集成测试（对小型 fixture 数据运行脚本核心函数）。

## 5. 风险与缓解
| 风险 | 影响 | 缓解策略 |
| ---- | ---- | ---- |
| Hugging Face 数据量大 / 速率限制 | 下载耗时或失败 | 支持 `--years`、`--cache-dir`、断点续传；提前校验 HF_TOKEN |
| Schema 演化导致字段缺失 | 迁移中断或数据错位 | 为关键列提供默认值和警告；报告中标记缺失字段 |
| JSON 异常或编码问题 | 摘要转换失败 | 加入 try/catch，记录错误文件，不中断主流程 |
| 偏好 CSV 字段冲突 | 最终输出错误 | 统一 schema 后再合并；保留 `source_file` 便于追溯 |
| 本地已有数据被覆盖 | 数据丢失 | 默认写入前备份（`.bak`）或要求 `--force` 标志 |

## 6. 验证计划
- 单元测试：针对元数据拆分、摘要合并、偏好去重等功能编写独立测试。
- 集成测试：在 `tests/scripts/test_migrate_reference_data.py` 中使用 fixture 模拟小规模 Parquet/JSON，运行脚本核心函数（dry-run + 实际执行）。
- 手动验证：
  - `uv run --no-progress python scripts/migrate_reference_data.py --dry-run --years 2024`
  - `uv run --no-progress python scripts/migrate_reference_data.py --years 2024 --models jasper_v1 --source-root reference/PaperDigest`
  - 检查输出目录结构与 `migration-report.json`。

## 7. 回滚策略
- 脚本在执行前对目标文件生成 `.bak` 或跳过已有文件；若输出异常可删除新目录并恢复备份。
- 迁移过程中保留原始参考数据（只读），失败时重新运行。

## 8. 待确认事项
- 嵌入 backlog 的结构（最小字段集合）是否需要立即对接调度器，或先生成报告即可。
- 摘要 JSONL 字段命名是否需要兼容未来 Web 展示（待与前端确认）。
- 是否需要将迁移脚本注册到 CLI（例如 `papersys.cli migrate-data`）。
