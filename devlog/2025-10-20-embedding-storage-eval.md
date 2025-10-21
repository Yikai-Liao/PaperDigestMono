# Embedding/Storage Zarr 可行性调研（Step 1）

## 背景与现状
- 目前嵌入向量以 `model/YYYY.parquet` 方式分年落盘，按 `manifest.json` 汇总维度与行数。
- 日常追加写入需要重新物化 Parquet 文件尾部，存在写放大与分区碎片问题。
- 读取时基于 `polars`/`pyarrow` 对整份 Parquet 进行批量扫描，随机抽取批次需额外过滤。

## 风险评估
- 替换存储格式若处理不当，可能破坏现有 `EmbeddingService` 与推荐流水线读取逻辑。
- Zarr + SQLiteStore 仍处于 Python 用户社区主导，生产经验相较 Parquet 少，需要验证稳定性。
- 压缩滤波（如 bitshuffle）与 chunk 设计不当会导致读放大或内存峰值异常。

## 评估方案
1. 选取 `data/embeddings` 下真实模型样本，复制到 `tmp/embedding_storage_eval/`，避免污染生产数据。
2. 编写一次性脚本，使用 Zarr SQLiteStore + Blosc 压缩（含 bitshuffle/不同压缩级别），对比：
   - 顺序追加写吞吐与写放大；
   - 压缩率与文件尺寸；
   - 随机批量读（多种批量大小）时的延迟与吞吐。
3. 与现有 Parquet 基线使用同一数据与批量以确保可比性，记录统计指标。
4. 汇总测试结果并评估是否可直接集成到 `EmbeddingService` 写入流程以及推荐模块读取逻辑。

## 验收标准
- 脚本可重复运行，默认仅访问 `tmp/embedding_storage_eval/` 等临时目录。
- 输出包含压缩率、追加写耗时、随机读耗时等核心指标，能与 Parquet 基线对照。
- 提出是否集成的建议与潜在改动点（配置、依赖、迁移步骤）。

## 回滚策略
- 若评估过程中发现阻塞风险，可直接删除临时目录与脚本，恢复 Parquet 流程。
- 在 devlog 追加备注说明中止原因，后续继续沿用现有存储方案。

## 实测结果（2025-10-21）
- 样本：`data/embeddings/jasper_v1/2024.parquet`（146,636 行，主维度 1024，舍弃 100 行 384 维数据）。
- 基线 Parquet 已改为使用 PyArrow 直写 float16，体积 282 MB，DuckDB 随机批量查询（256 ids × 12 批）平均 1.08 s/批。
- Zarr + SQLiteStore（float16 + Blosc[zstd, clevel=7, bitshuffle]，chunk=2048）体积 280 MB，chunk 写入 72 批，总耗时 4.2~4.6 s，平均每批 0.06~0.07 s。
- NPZ（`np.savez_compressed` + float16）体积 278 MB，写入 21~23 s，加载 7~9 ms，内存内随机批读取 0.00009 s/批。
- zfpy（lossless）体积 596 MB，写入 4.5 s，解压 6.1 s，随机批读取需整体解压后再切片（0.0001 s/批）；固定精度（tolerance=1e-3）体积 195 MB，写入 2.5 s，解压 2.7 s。
- Zarr 相对 float16 Parquet 压缩比 1.01×（几乎无差异），与 NPZ 持平；zfpy 在高精度模式下可达到更高压缩比，但需一次性解压，缺乏追加写与随机索引能力。
- 若将 Zarr compressor 切换为 zfpy（tolerance=1e-4），SQLiteStore 体积降至 273 MB，逼近独立 zfpy 的 270 MB，但随机批读取退化到 3.28 s/批（每次 chunk 解压占主导）；需评估是否接受该 CPU 开销与误差。
- 脚本输出：`tmp/embedding_storage_eval/jasper_v1_2024/report.json`，同时生成评测产物（Parquet 与 SQLite 文件）位于同目录，可重复运行验证。
- 待确认事项：推荐流水线目前依赖 `pl.scan_parquet` 懒加载，迁移到 Zarr 需新增索引映射与批量读取适配；Manifest/CLI 需调整以记录 chunk/SQLite 文件元信息。
