# 2025-10-03 推荐流水线数据加载修正计划

## 现状
- `RecommendationDataLoader` 依赖 `cache_dir` 下的预拼接 Parquet 候选集；真实仓库未提供该缓存，因此手动运行脚本失败。
- `config/example.toml` 强制要求 `cache_dir`，与架构文档提到的本地优先理念不符。
- `devdoc/architecture.md` 中记录了“先拼接后缓存再读取”的设计，导致误解与性能隐患。

## 目标
- 允许推荐流水线直接从 `metadata` CSV 与各 embedding Parquet 动态构建候选集，不再依赖额外缓存。
- 更新架构文档，明确推荐阶段的“按需扫描 + Join”策略。
- 完全移除对 `cache_dir` 的依赖，推荐流水线统一使用按需扫描的元数据与嵌入文件。
- 为关键代码路径补充测试，覆盖 metadata/embedding 动态拼接场景。

## 调整方案
1. **配置模型**：
   - 移除 `RecommendPipelineConfig.data.cache_dir` 字段，新增 `metadata_dir`、`metadata_pattern`、`embeddings_root` 并给出默认值。
   - 更新 `config/example.toml` 与相关测试用例以反映新字段。
2. **数据加载器**：
   - `RecommendationDataSources` 记录 metadata 目录与 embedding 目录映射，不再暴露 `cache_dir`。
   - 推荐流水线使用 lazy join：
     - `pl.scan_csv` 扫描匹配的 metadata CSV 并统一列名。
     - 对每个 embedding alias 扫描目录下所有 Parquet，选择 `paper_id` + embedding 列。
     - 将嵌入逐个内连接到 metadata，并在过滤阶段使用既有类别/年份约束。
   - 偏好数据维持原实现，但改为根据文件表头动态推断 schema。
3. **测试**：
   - 扩展 `tests/recommend/test_pipeline.py`：构建 metadata CSV + embedding Parquet，验证无缓存情况下完整跑通。
   - 更新/新增测试覆盖 metadata pattern 自定义等边界。
4. **文档**：
   - 在 `devdoc/architecture.md` 添加“推荐数据加载”章节，阐述按需扫描流程与性能考虑。
   - 必要时补充 `devdoc/data-storage.md`，同步字段约定。

## 风险评估
- 输入文件格式差异（如字段名、分隔符）可能导致 join 失败，需要在实现中增加显式重命名与校验。
- 使用 lazy join 可能引发较高内存占用，需确保筛选逻辑（类别、年份、偏好过滤）尽量在 lazy 阶段完成。
- 配置字段变更需同步全部测试与 CLI，避免破坏已有功能。

## 回滚策略
- 变更集中于数据加载层，出现问题时回滚 `RecommendationDataLoader` 相关提交即可恢复原行为。
