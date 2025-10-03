# 2025-10-02 Embedding backend refactor
Status: Completed
Last-updated: 2025-10-02

## 现状
- `EmbeddingService.load_model` 依赖模型别名硬编码判断是否使用 vLLM。
- 主进程直接 import vLLM，导致 CUDA fork 重复初始化风险且 GPU 资源无法及时释放。
- 配置示例中缺乏对嵌入后端的显式声明，团队成员难以区分 SentenceTransformer 与 vLLM 模型。

## 风险
- 硬编码条件随着模型扩展易失效，造成错误后端选择。
- 主进程持有 vLLM 进程和内存，增加长驻任务的 GPU 压力。
- 配置缺乏文档支持，难以在多模型部署中进行审计和自动化。

## 方案
1. 在 `EmbeddingModelConfig` 中新增 `backend` 字段（`sentence_transformer` / `vllm`），由配置层显式声明。
2. 重写 `EmbeddingService.load_model`，依据 `backend` 决定加载 ST 或返回 vLLM 子进程哨兵对象，禁止主进程 import vLLM。
3. 保持 vLLM 调用在 `_vllm_embedding_worker` 子进程中执行，并通过 `spawn` 进程模式隔离资源。
4. 更新 `config/example.toml` 与 `devdoc/env.md`，说明后端选择与资源隔离策略。
5. 补充单元测试，校验新 `backend` 字段行为。

## 回滚策略
- 若新配置字段导致部署阻塞，可将 `backend` 回退为硬编码逻辑，暂时恢复旧版本文件，并回滚示例配置 / 文档；对应提交需要整体 revert。

## 测试记录
- `uv run --no-progress pytest tests/embedding/test_embedding_service.py`

## 执行记录
- 2025-10-02：`EmbeddingModelConfig` 新增 `backend` 字段，`EmbeddingService.load_model` 依据配置区分 SentenceTransformer 与 vLLM，主进程不再 import vLLM。
- 2025-10-02：`config/example.toml`、`devdoc/env.md` 增补后端说明，`tests/embedding/test_embedding_service.py` 验证哨兵与句向量加载路径。
