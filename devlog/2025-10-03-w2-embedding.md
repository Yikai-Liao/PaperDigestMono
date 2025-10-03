# 2025-10-03 W2 Embedding Backlog Implementation Plan

Status: Completed  
Last-updated: 2025-10-11

## 现状评估
- `EmbeddingService` 已支持后端选择与 CSV 路径解析，但仍按单次 CSV → Parquet 方式写入，未生成 `manifest.json` 与 `backlog.parquet`，与 `devdoc/data-storage.md` 的目标结构不符。
- CLI `papersys embed` 缺少按模型/年份的任务调度与 manifest/backlog 更新逻辑，无法对 `data/embeddings/<model_alias>/` 进行幂等补齐。
- 目前无 `scripts/run_embedding_sample.py`，难以快速演示最小批次嵌入流程。
- 测试用例覆盖生成 Parquet 与 backlog 检测，但未验证 manifest/backlog 文件、批处理分页或 CLI 交互路径。

## 目标与范围
1. 产出符合规范的嵌入目录结构：年度 Parquet + `manifest.json` + `backlog.parquet`，并保持幂等更新。
2. 支持 backlog 补齐：根据 metadata/embedding 状态生成待处理清单，按批次刷新 backlog 文件并允许 CLI 自动处理。
3. 提供运行脚本 `scripts/run_embedding_sample.py`，便于在小数据集上验证 embedding 流程。
4. 扩充测试覆盖：验证 manifest 更新、backlog 维护、CLI 参数路径解析与限量处理。
5. 更新文档（`devdoc/architecture.md` Embedding 章节）并记录实施过程（本 devlog）。

## 实施方案
1. **服务层增强**
   - 重构 `EmbeddingService.generate_embeddings_for_csv`：支持增量合并同年 Parquet、更新时间戳、来源标记，并返回任务指标。
   - 新增 `ManifestManager`/辅助函数，生成或更新 `manifest.json`（包含模型信息、文件清单、行数统计）。
   - 引入 backlog 管理：在检测缺失/失败任务时写入 `backlog.parquet`（字段包含 `paper_id`、`year`、`missing_reason`、`queued_at`、`model_alias`）。
2. **CLI/backlog 流程**
   - 扩展 `papersys embed`：默认执行 manifest/backlog 更新，`--backlog` 触发 backlog 批处理，支持 `--limit` 控制单次处理数。
   - 处理结果后刷新 backlog 文件（移除完成项，保留失败/剩余）。
3. **脚本与工具**
   - 新增 `scripts/run_embedding_sample.py`：加载配置、定位最新 metadata CSV、小批量跑一次嵌入并输出生成文件路径。
4. **测试**
   - 更新/新增 pytest：模拟 metadata CSV + 现有 Parquet，断言 manifest/backlog 内容、幂等性、CLI 推导路径。
   - 引入 fixture 构造 backlog 情景并验证 `--backlog` 执行。
5. **文档同步**
   - 在 `devdoc/architecture.md` Embedding 小节补充新目录结构与流程说明。
   - 在本日志记录实施与验证结果。

## 风险与缓解
- **大文件写入时间长**：测试和脚本使用裁剪后的 CSV/模型；生产环境可通过 `limit`、批量大小控制。
- **并发冲突**：暂不支持多进程写入，CLI 文档中强调串行运行；manifest/backlog 更改前先读取最新状态，保持幂等。
- **HF Hub 依赖**：计划阶段仅实现本地 backlog；外部依赖后续通过独立任务接入。

## 验证计划
- `uv run --no-progress pytest tests/embedding`
- `uv run --no-progress python scripts/run_embedding_sample.py --limit 5 --dry-run`
- 按需要运行 `uv run --no-progress python scripts/run_embedding_sample.py --limit 5`

## 回滚策略
- 若 manifest/backlog 逻辑导致数据损坏，可回滚 `EmbeddingService` 与 CLI 相关提交，同时恢复测试与脚本至旧版本。
- 在回滚前保留新生成的嵌入文件备份，防止数据丢失。

## 实施记录
- `EmbeddingService` 写入流程升级：年度 Parquet 添加 `generated_at`、`model_dim`、`source` 字段，幂等合并并更新 `manifest.json`；新引入 `refresh_backlog()` 输出 `backlog.parquet`（记录 `paper_id`、`missing_reason`、`origin` 等）。
- CLI `papersys embed` 支持基于 backlog 的批处理流程，常规模式在执行后刷新 backlog；新增 `scripts/run_embedding_sample.py` 便于小规模验证。
- `devdoc/architecture.md` Embedding 章节补充 manifest/backlog 机制；新测试覆盖 manifest 产出、backlog 计算与幂等性。

## 验证结果
- `uv run --no-progress pytest tests/embedding`
- `uv run --no-progress env PYTHONPATH=. python scripts/run_embedding_sample.py --limit 5 --dry-run`
- `uv run --no-progress env PYTHONPATH=. python scripts/run_embedding_sample.py --limit 5`

## 运行结论
- 回归测试全绿（8 项）；真实脚本写入 `data/embeddings/jasper_v1/2000.parquet`（5 条）并刷新 `manifest.json`、`backlog.parquet`，dry-run 可预览计划。嵌入服务现统一使用 `AppConfig.data_root` 解析输出目录，不再向仓库根目录落盘。
- backlog 刷新可区分“缺少年度文件”与“新增论文未嵌入”两种状态，`manifest.json` 会随 Parquet 更新实时同步计数。
