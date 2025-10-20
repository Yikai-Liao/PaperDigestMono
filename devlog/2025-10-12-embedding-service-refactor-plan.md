# Embedding/Service 精简改造计划（Step 1）

## 背景与现状
- `EmbeddingService` 直接读取 CSV、批量写入 Parquet，同时缓存模型实例，导致职责混杂。
- CLI 端目前按 CSV 调用服务，模型加载逻辑和文件 IO 交织，难以在批量模式下复用。
- 现有实现重复扫描文件、缺乏统一的 `list[str] -> ndarray` 接口，也无法显式控制进度展示。

## 风险评估
- 调整嵌入流程可能破坏现有 Backlog 与 Manifest 逻辑；需验证去重与元数据写入仍正确。
- vLLM 子进程调用必须保持隔离，避免误将权重常驻主进程。
- CLI 将一次性加载所有待处理 CSV，需关注内存占用与 `limit` 参数语义变化。

## 目标方案
1. 重写 `EmbeddingService` 暴露最小接口：加载模型 + 接受 `list[str]` 并返回 `np.ndarray`，内部按配置批量并以 `tqdm` 汇报进度；移除模型缓存与 CSV 专用方法。
2. 删除 backlog/manifest 等附加职责，仅保留最小化落盘示例（单一 Parquet 输出），其余由上层 orchestration 负责。
3. 调整 CLI `embed` 命令：整合元数据读取与过滤、构造文本列表、调用服务接口并写回结果；backlog 参数沿用但仅提示后走全量路径。
4. 更新/补充测试覆盖新的服务接口、CLI 行为以及存储副作用，确保 Manifest 与去重逻辑完好。

## 验收标准
- 新接口返回 `np.ndarray`（二维），进度条可见且批量大小可配置。
- CLI 批量嵌入单次加载模型即可完成任务，`limit` 等参数行为有测试保障。
- 所有相关 pytest 用例通过，本地未写入 `data/` 目录。

## 回滚策略
- 若改造引入不可接受的行为差异，可恢复至当前 `EmbeddingService` 与 CLI 实现，并清理新添文件。
- 同步删除本计划文档并在 devlog 标注回滚原因，保留原有测试与配置。
