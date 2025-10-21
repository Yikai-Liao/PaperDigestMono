# Embedding Backend Refactoring - 2025-10-21

## 目标
将 embedding 服务从硬编码的 if-else 分发模式重构为基于策略模式的后端注册机制，并添加 Infinity 后端支持。

## 动机
原有代码存在的问题：
1. **违反开闭原则**：每次添加新后端都需要修改 `EmbeddingService.embed_texts` 主逻辑
2. **代码臃肿**：大量 if-elif-else 分支使代码难以维护
3. **测试困难**：后端逻辑与服务逻辑耦合，难以独立测试
4. **职责不清**：`EmbeddingService` 需要了解每个后端的具体实现细节

## 实施方案

### 1. 架构设计

#### 核心组件
- **`EmbeddingBackend`** (ABC)：定义后端接口
  - `embed_batch()`: 批量生成 embeddings
  - `cleanup()`: 可选的资源清理方法

- **`BackendRegistry`**：后端注册表
  - `register(name, backend_class)`: 注册后端
  - `get(name)`: 获取已注册的后端类
  - `list_backends()`: 列出所有可用后端

- **具体后端实现**：
  - `SentenceTransformerBackend`: 使用 sentence-transformers 库
  - `VLLMBackend`: 使用 vLLM（子进程模式）
  - `InfinityBackend`: 使用 infinity_emb/embed 库

### 2. 代码变更

#### papersys/config/embedding.py
```python
# 添加新的后端类型和配置
BackendLiteral = Literal["sentence_transformer", "vllm", "infinity"]
InfinityEngineLiteral = Literal["torch", "optimum"]

class EmbeddingModelConfig(BaseConfig):
    ...
    infinity_engine: InfinityEngineLiteral = Field("torch", ...)
```

#### papersys/embedding/service.py
**重构前**：
```python
if model_config.backend == "sentence_transformer":
    # 直接在主函数中实现逻辑
    model = self._load_sentence_transformer(...)
    for batch in batches:
        vectors = self._encode_with_sentence_transformer(...)
elif model_config.backend == "vllm":
    # 直接在主函数中实现逻辑
    ...
```

**重构后**：
```python
# 获取后端实例（自动缓存）
backend = self._get_backend(model_config.backend)

# 统一接口调用
for batch in batches:
    vectors = backend.embed_batch(batch, model_config, device, precision)
```

### 3. 新增功能：Infinity Backend

#### 特性
- 基于 `infinity_emb` 库（通过 `embed` 封装）
- 支持异步批处理和自动队列管理
- 内置模型缓存和资源管理
- 支持 torch 和 optimum 引擎

#### 依赖冲突处理
**问题**：infinity-emb 所有版本都要求 `numpy<2`，与项目的 `numpy>=2.2` (vllm 依赖) 冲突。

**实验结果**（详见 `devlog/2025-10-21-infinity-numpy2-compatibility-test.md`）：
- ❌ 强制安装在 numpy 2.x 环境下不可行
- 即使忽略依赖并降级相关包（optimum<2.0），仍有运行时兼容性问题
- BetterTransformer 与某些模型存在参数不匹配

**最终方案**：
1. 将 Infinity 后端设为**可选且实验性功能**
2. 运行时动态检测 `embed` 库是否可用
3. 提供清晰的错误提示和解决方案

**错误提示**：
```python
RuntimeError(
    "embed library is required for infinity backend but not installed.\n"
    "Note: embed requires numpy<2, which conflicts with vllm's numpy>=2.2 requirement.\n"
    "Options: 1) Use sentence_transformer or vllm backend, or 2) Create separate environment for infinity"
)
```

**使用建议**：
- ✅ **推荐**: 使用 sentence_transformer 或 vllm 后端（完全兼容）
- ⚠️ **实验性**: 如需 Infinity backend，创建独立虚拟环境：
  ```bash
  python -m venv infinity_env
  source infinity_env/bin/activate
  pip install embed 'numpy<2' sentence-transformers
  ```

### 4. 测试更新

#### 更新现有测试
```python
# 旧方式：mock 内部方法
with patch.object(EmbeddingService, "_load_sentence_transformer", ...):
    ...

# 新方式：mock 后端实例
mock_backend = MagicMock()
mock_backend.embed_batch.return_value = fake_vectors
with patch.object(service, "_get_backend", return_value=mock_backend):
    ...
```

#### 新增测试
- `test_backend_registry_has_all_backends`: 验证所有后端已注册
- `test_backend_instances_are_cached`: 验证后端实例缓存机制
- `test_infinity_backend_import_error`: 验证 infinity 后端的错误处理

### 5. 测试结果
```bash
$ uv run --no-progress pytest tests/embedding/test_embedding_service.py -v
...
tests/embedding/test_embedding_service.py::test_embed_texts_returns_matrix PASSED [ 12%]
tests/embedding/test_embedding_service.py::test_embed_texts_honours_batch_size PASSED [ 25%]
tests/embedding/test_embedding_service.py::test_embed_texts_handles_empty_input PASSED [ 37%]
tests/embedding/test_embedding_service.py::test_embed_texts_vllm_backend PASSED [ 50%]
tests/embedding/test_embedding_service.py::test_batch_size_never_exceeds_total PASSED [ 62%]
tests/embedding/test_embedding_service.py::test_backend_registry_has_all_backends PASSED [ 75%]
tests/embedding/test_embedding_service.py::test_backend_instances_are_cached PASSED [ 87%]
tests/embedding/test_embedding_service.py::test_infinity_backend_import_error PASSED [100%]

8 passed in 6.42s
```

## 优势

### 1. 符合 SOLID 原则
- **单一职责**：每个后端类只负责自己的推理逻辑
- **开闭原则**：添加新后端无需修改现有代码
- **依赖倒置**：依赖抽象接口而非具体实现

### 2. 可扩展性
添加新后端只需：
```python
class NewBackend(EmbeddingBackend):
    def embed_batch(self, texts, model_config, device, precision):
        # 实现逻辑
        ...

BackendRegistry.register("new_backend", NewBackend)
```

### 3. 可测试性
- 后端可以独立测试
- 服务逻辑与后端实现解耦
- Mock 和测试更简单

### 4. 可维护性
- 代码结构清晰，职责明确
- 减少认知负担
- 便于代码审查

## 使用示例

### 配置文件
```toml
[[embedding.models]]
alias = "jasper_v1"
name = "michaelfeil/bge-small-en-v1.5"
dimension = 384
backend = "sentence_transformer"

[[embedding.models]]
alias = "qwen3_v1"
name = "Qwen/Qwen3-Embedding-0.6B"
dimension = 1024
backend = "vllm"

# Infinity 后端（需单独环境）
[[embedding.models]]
alias = "infinity_test"
name = "sentence-transformers/all-MiniLM-L6-v2"
dimension = 384
backend = "infinity"
infinity_engine = "torch"
```

### 代码调用
```python
from papersys.embedding import EmbeddingService
from papersys.config import load_app_config

config = load_app_config("config/app.toml")
service = EmbeddingService(config.embedding)

# 自动选择正确的后端
texts = ["Paper title", "Abstract content"]
embeddings = service.embed_texts(texts, config.embedding.models[0])
```

## 后续改进

1. **异步支持**：为 Infinity 后端添加原生异步接口
2. **批处理优化**：实现跨后端的智能批处理调度
3. **性能监控**：为每个后端添加 Prometheus 指标
4. **配置验证**：启动时检查后端依赖是否满足
5. **文档完善**：添加每个后端的详细使用文档和性能对比

## 回滚方案
如果发现重构引入问题：
1. 回退到最近的 git tag
2. 测试用例已全部更新，直接 `git revert` 本次提交
3. 无数据持久化格式变更，无需担心兼容性

## 验收标准
- [x] 所有现有测试通过
- [x] 新增测试覆盖后端注册和调度逻辑
- [x] Infinity 后端实现完成（运行时可选）
- [x] 配置格式向后兼容
- [x] 代码符合项目风格指南
- [x] 文档更新完成

## 总结
本次重构将 embedding 服务从过程式设计转变为面向对象设计，大幅提升了代码质量和可维护性。虽然 Infinity 后端因依赖冲突暂时只能作为可选功能，但架构设计为未来扩展预留了充分空间。
