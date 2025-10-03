# 2025-10-03 W3 Recommendation Lazy Pipeline Plan

Status: Completed  
Last-updated: 2025-10-11

## 现状评估
- `RecommendationDataLoader` 已去除旧缓存依赖，但高阶流程仍停留在临时脚本与测试场景，未与 CLI / APScheduler 集成，手动运行需要编写额外脚本。
- 向量与元数据融合逻辑分散在多个函数中，缺少统一的 pipeline 入口，导致重复的列重命名、过滤条件散落在测试内。
- 偏好数据（`data/preferences/*.csv`）读取流程缺少幂等 append 支持，无法方便地合并多年度反馈；目前测试也未覆盖偏好裁剪逻辑与训练/预测输出。
- 产出结果（推荐批次、评分、采样摘要）尚无标准化落盘格式，`devdoc/data-storage.md` 仅描述目标但工程未实现。

## 目标与范围
1. 构建统一的推荐流水线入口（服务 + CLI），实现“metadata + embeddings + preferences → 推荐结果”的懒加载流程。
2. 支持训练（LogisticRegression）与预测/采样两个阶段，结果输出到 `data/recommendations/`（候选 Parquet/JSON）并保留日志。
3. 完善偏好数据加载与过滤：支持多年度文件合并、去重、限制最近 N 天等策略。
4. 扩展测试覆盖：包含 end-to-end 小数据集（metadata + embeddings + preferences）验证训练与预测结果、阈值筛选与采样逻辑。
5. 更新文档 (`devdoc/architecture.md` 推荐小节；必要时 `devdoc/data-storage.md`) 并记录实施过程。

## 实施方案
1. **服务分层**
   - 新增 `papersys/recommend/pipeline.py`：封装数据加载、特征构建、模型训练、预测与采样；对外提供 `run_training()`、`run_prediction()`、`run_sampling()` 等高层接口。
   - 引入 `RecommendationDataset`、`PreferenceLoader` 等协作类，集中处理 Polars 懒加载、列校验、偏好合并。
   - 保留/复用现有 `RecommendationDataLoader` 的懒加载逻辑，整合到新服务内。
2. **CLI / Scheduler**
   - 在 `papersys/cli.py` 增加 `recommend` 子命令（或扩展现有命令），支持 `--train` / `--predict` / `--sample` 选项、`--from-date`、`--limit` 等参数。确保命令遵循 `AppConfig` 数据根解析。
   - 预留与调度器的集成接口（例如返回运行统计、写入 Prometheus 指标）。
3. **数据输出**
   - 约定推荐结果目录：`data/recommendations/<date>/predictions.parquet`、`data/recommendations/<date>/samples.jsonl` 等；字段与顺序在文档中说明。
   - 记录元数据（模型参数、采样阈值、输入规模）到伴随的 `manifest.json` 或日志中，便于追溯。
4. **测试**
   - 更新 `tests/recommend/test_pipeline.py`：构造小型 metadata/embedding/preferences 数据，验证训练、预测、采样流程；加入偏好裁剪、阈值边界条件。
   - 新增 CLI 层测试（使用 `CliRunner` 或 typer.testing）验证命令解析与 dry-run 行为。
5. **文档与样例脚本**
   - 更新架构/数据存储文档描述推荐输出与偏好处理方式。
   - 视需要新增 `scripts/run_recommend_sample.py`，提供最小化演示流水线。

## 风险与缓解
- 懒加载 join 在大数据上可能耗时：通过配置参数控制时间范围/样本数量，并在 CLI 中提供 `--limit`。
- 偏好数据质量（缺失/重复）可能影响训练：实现 Pydantic/Polars 验证与去重策略，测试覆盖异常路径。
- 训练/预测重复写入可能覆盖既有结果：产出目录按日期/时间戳区分，或提供 `--output` 覆盖选项。

## 验证计划
- `uv run --no-progress pytest tests/recommend`
- `uv run --no-progress python scripts/run_recommend_sample.py --dry-run`
- 视需求运行 `uv run --no-progress python scripts/run_recommend_sample.py --limit 10`

## 回滚策略
- 新逻辑集中在推荐模块；若影响范围过大，可回滚 `papersys/recommend` 新增文件与 CLI/文档改动，恢复旧测试。
- 推荐输出目录采用新增命名空间，回滚时删除生成的样例文件即可。

## 实施记录
- `RecommendationPipeline` 新增 `run_and_save`，在 `data_root/recommendations/<timestamp>/` 下落盘 `predictions.parquet`、`recommended.parquet` 与 `manifest.json`，同时保留原 `run()` 返回值。
- CLI 新增 `papersys recommend` 命令，支持 `--dry-run`、`--force-all`、`--output-dir`，输出路径与清单日志；新增脚本 `scripts/run_recommend_sample.py` 作为最小化演示入口。
- 扩展测试：`tests/recommend/test_pipeline.py` 新增落盘断言；`tests/recommend/test_integration.py` 无需改动即可复用；CLI 测试覆盖 dry-run/执行分支。
- 配置与文档：`config/example.toml`、`papersys/config/recommend.py` 调整输出字段；`devdoc/architecture.md`、`devdoc/data-storage.md` 待更新，记录推荐结果目录与 manifest 结构。

## 验证结果
- `uv run --no-progress pytest tests/recommend`
- `uv run --no-progress pytest tests/cli/test_cli_commands.py`
- `uv run --no-progress env PYTHONPATH=. python scripts/run_recommend_sample.py --dry-run`

## 运行结论
- 干跑脚本仅输出路径信息且未写入生产数据；单元/集成测试覆盖懒加载、训练、预测、落盘过程；CLI 新命令完成 dry-run 与执行路径验证。
