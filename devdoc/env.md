## Python

## Python

使用 uv 进行环境管理，禁止使用非uv 的python。所以运行需要uv run python。同时，禁止使用uv pip install，安装依赖使用uv add。

## 依赖管理

### 核心依赖版本约束

- **NumPy**: `>=2.2.0,<2.3`
  - 原因: vLLM 0.10.2 依赖 numba 0.61.2，而 numba 0.61.2 要求 `numpy<2.3`
  - 注意: 不能直接升级到 numpy 2.3+，除非 vLLM 更新到支持 numba 0.62.1+

- **Torch**: `>=2.8.0`
  - vLLM 0.10.2 已升级到 PyTorch 2.8.0，需保持一致

### vLLM 安装

vLLM 用于大型 embedding 模型推理（如 Qwen3-Embedding-0.6B for jasper_v1）。

安装方式：
```bash
# 使用 optional dependency 安装
uv sync --extra vllm
```

配置说明：
- 使用 vLLM 官方 wheel 仓库: `https://wheels.vllm.ai/0.10.2/`
- 配置在 `pyproject.toml` 的 `[tool.uv.index]` 和 `[tool.uv.sources]` 中
- 版本: `>=0.10.2`（支持 PyTorch 2.8.0 和 aarch64）

版本冲突排查记录（2025-10-02）：
1. **问题**: vLLM 0.10.2 与 numpy 2.3+ 冲突
2. **原因**: vLLM → numba 0.61.2 → numpy<2.3
3. **解决**: 将 numpy 约束为 `>=2.2.0,<2.3`
4. **验证**: 所有 67 个测试通过

### Embedding Backend 选择

- 通过 `embedding.models[].backend` 显式选择实现：
  - `sentence_transformer`：直接加载 SentenceTransformer；保持原模型行为。
  - `vllm`：在独立子进程中初始化 vLLM，生成完嵌入后自动退出以释放 GPU/CPU 资源。
- vLLM 子进程使用 `spawn` 启动策略，避免 CUDA fork 错误；主进程不会 import vLLM，确保资源隔离。

### 可选依赖

项目定义了以下 optional dependencies：
- `vllm`: 大型 embedding 模型推理（Qwen3-Embedding 等）

安装特定组合：
```bash
# 基础环境（不含 vLLM）
uv sync

# 包含 vLLM
uv sync --extra vllm
```
