# Infinity Backend 兼容性测试报告

## 测试日期
2025-10-21

## 测试目标
尝试在 numpy 2.x 环境下强制安装并使用 `infinity-emb`/`embed` 库，测试 conan_v1 模型是否能正常运行。

## 测试环境
- Python: 3.12.11
- NumPy: 2.2.6
- 项目依赖: vllm 需要 numpy>=2.2
- 测试模型: TencentBAC/Conan-embedding-v1 (dimension=1792)

## 测试步骤

### 1. 强制安装 embed 库
```bash
uv pip install --no-deps embed
uv pip install --no-deps infinity-emb
```

**结果**: 安装成功，但导入失败
- `embed==0.3.0` 需要 `infinity-emb==0.0.58`
- 版本不匹配导致 `ImportError: cannot import name 'AutoPadding'`

### 2. 安装匹配版本
```bash
uv pip install --no-deps infinity-emb==0.0.58
```

**结果**: 导入失败
- 错误: `ModuleNotFoundError: No module named 'optimum.bettertransformer'`
- `optimum==2.0` 已移除 `bettertransformer` 模块

### 3. 降级 optimum
```bash
uv pip install --no-deps 'optimum==1.23.3'
```

**结果**: 可以导入，但运行时错误
- 加载模型成功
- BetterTransformer 优化失败：
  ```
  BertLayerBetterTransformer.forward() got an unexpected keyword argument 'encoder_attention_mask'
  ```

## 失败原因分析

### 1. 依赖冲突链
```
项目要求: numpy>=2.2 (vllm 依赖)
    ↓
embed 要求: numpy<2
    ↓
infinity-emb 要求: numpy<2, optimum<2.0
    ↓
optimum<2.0 的 BetterTransformer 与某些新模型不兼容
```

### 2. 技术问题
1. **NumPy 版本硬约束**: `infinity-emb<=0.0.77` 所有版本都明确要求 `numpy>=1.20.0,<2`
2. **Optimum 架构变更**: `optimum>=2.0` 移除了 `bettertransformer` 模块
3. **BetterTransformer 兼容性**: 即使使用 `optimum==1.23.3`，对某些 BERT 模型仍有参数不匹配问题

### 3. 根本原因
`infinity-emb` 在设计时针对 numpy 1.x 生态，与 numpy 2.x 不兼容：
- API 变更
- 内存布局差异  
- 类型系统变化

## 结论

**❌ 在 numpy 2.x 环境下强行使用 infinity-emb 不可行**

即使忽略依赖警告并强制安装：
1. 需要降级多个核心库（optimum, transformers 等）
2. 运行时仍有兼容性问题
3. 破坏了与 vllm 的兼容性

## 建议方案

### 方案 A：保持现状（推荐）
- 移除 Infinity backend 或标记为实验性功能
- 文档中明确说明需要独立环境
- 用户若需使用，创建专用的 numpy<2 环境

### 方案 B：条件支持
```python
try:
    from embed import BatchedInference
    INFINITY_AVAILABLE = True
except ImportError:
    INFINITY_AVAILABLE = False
    
if not INFINITY_AVAILABLE:
    # 提供清晰的错误提示
    raise RuntimeError(
        "Infinity backend requires a separate environment with numpy<2.\n"
        "Create with: python -m venv infinity_env && "
        "pip install embed numpy<2"
    )
```

### 方案 C：等待上游修复
关注 https://github.com/michaelfeil/infinity 的 numpy 2.x 支持进展。

## 测试结果总结

| 测试项 | 结果 | 备注 |
|--------|------|------|
| 安装 embed | ✅ | 需 --no-deps |
| 导入 embed | ❌ | 需匹配 infinity-emb 版本 |
| 版本匹配后导入 | ❌ | 需 optimum<2.0 |
| 降级 optimum 后导入 | ✅ | 有警告 |
| 运行推理 | ❌ | BetterTransformer 参数错误 |
| 与 numpy 2.x 兼容 | ❌ | 多重不兼容 |

## 清理命令
```bash
# 移除测试安装的包
uv pip uninstall embed infinity-emb optimum
```

## 参考链接
- infinity-emb 文档: https://michaelfeil.eu/infinity/0.0.77/
- numpy 2.0 迁移指南: https://numpy.org/devdocs/numpy_2_0_migration_guide.html
- GitHub Issues: https://github.com/michaelfeil/infinity/issues
