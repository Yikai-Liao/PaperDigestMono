# 2025-10-03 W1 Ingestion Migration Implementation Plan

Status: Completed  
Last-updated: 2025-10-11

## 现状评估
- `IngestionService` 仍写入 `metadata/raw/arxiv/<year>/arxiv_YYYY.csv`，未与 `data/metadata/metadata-YYYY.csv` 规范对齐，`latest.csv` 聚合视图缺失。
- CLI `papersys ingest` 暂不支持根据 `AppConfig.data_root` 解析产出目录，导致示例配置需要手动拼接路径。
- 缺少迁移计划要求的样例脚本 `scripts/run_ingestion_sample.py` 与针对流式增量/并发的测试覆盖。
- `devdoc/data-storage.md` 已描述目标目录结构，但未落地到实现。

## 目标与范围
1. 统一元数据落盘格式至 `data/metadata/metadata-YYYY.csv`，确保字段、编码符合 `devdoc/data-storage.md` 的定义，并保留 `latest.csv` 汇总视图。
2. 扩展 `IngestionService`：
   - 透过 `AppConfig.data_root` 派生输出目录；
  - 支持幂等追加、`Polars` 去重与年份分块；
  - 暴露批量/断点续传能力（`limit`、`from`/`until`）。
3. 增补 CLI 与样例脚本，提供最小化无外部依赖的演示运行路径。
4. 完善测试：覆盖字段标准化、追加去重、`latest.csv` 聚合、配置缺陷报错路径。
5. 文档同步（`devdoc/data-storage.md` 补充流程描述，并在本文件记录评估结果）。

## 实施方案
1. **目录解析与服务重构**
   - 在 `IngestionService` 内新增 `base_path` 解析逻辑（兼容独立传入与从 `config` 推导）；
   - 使用 `polars.DataFrame` 写入 CSV，字段顺序与类型按文档约束；
   - 新增 `flush_yearly_batches` 与 `update_latest_manifest` 等私有方法，封装写入/汇总。
2. **CLI/脚本联动**
   - 更新 `papersys.cli.ingest`，在创建服务时注入 `data_root`；
   - 编写 `scripts/run_ingestion_sample.py`，从 `config/example.toml` 加载配置并以限制模式跑一个小批次（默认 `limit=5`），输出日志到 stdout。
3. **测试体系**
   - 重写 `tests/ingestion/test_ingestion_service.py`：利用 `tmp_path` 模拟 `data_root`，校验年份文件与 `latest.csv` 行 dedupe；
   - 新增针对 `limit`、`from/until`、异常路径的测试；复用 `pytest` patch 拦截网络。
4. **文档与配置**
   - 在 `devdoc/data-storage.md` 中追加“写入流程示意”段落；
   - 如有需要，调整 `config/example.toml` 默认 `output_dir` = `metadata`（对齐数据目录）。

## 风险与缓解
- **字段兼容性风险**：旧 CSV 与新 schema 混用。→ 在写入前对列集合断言，如缺列直接报错并在日志中说明。
- **性能风险**：大批次写入导致内存峰值。→ 批次保持可配置（默认 500）；`polars` 流式写入。
- **并发写入风险**：调度器重复触发导致互斥冲突。→ 暂不支持并发，文档中标注需通过调度器串行。

## 验证计划
- 运行 `uv run --no-progress pytest tests/ingestion/test_ingestion_service.py`。
- 如时间允许执行 `uv run --no-progress pytest` 以确认回归。
- 手动运行 `uv run --no-progress python scripts/run_ingestion_sample.py --limit 3 --dry-run` 验证脚本行为（dry-run 模式仅打印目标路径与配置）。

## 回滚策略
- 若实施后影响其他 pipeline（embedding/recommend）读不到 CSV，回滚 `IngestionService` 与 CLI 相关改动，并保留新测试以捕捉问题。
- 数据侧回滚：保留旧目录 `metadata/raw/arxiv/`，必要时通过 git checkout 恢复。

## 实施记录
- 代码重构完成：统一产出 `metadata-YYYY.csv` + `latest.csv`，CLI 与嵌入流程更新适配，新增 `scripts/run_ingestion_sample.py`。
- 文档/配置：`config/example.toml`、`devdoc/data-storage.md` 更新，新增本 devlog。

## 验证结果
- `uv run --no-progress pytest tests/ingestion tests/embedding/test_embedding_service.py`
- `uv run --no-progress env PYTHONPATH=. python scripts/run_ingestion_sample.py --limit 10`

## 运行结论
- 实际抓取保存 10 条记录至 `data/metadata/metadata-2000.csv`，`data/metadata/latest.csv` 当前包含 758,369 条记录。
- 请求过程中 OAI-PMH 多次返回 resumption token，服务按照 `limit` 正常提前停止。
