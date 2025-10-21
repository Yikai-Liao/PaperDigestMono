# Infinity Backend 移除记录

## 日期
2025-10-21

## 移除原因
- `infinity-emb` 包与 numpy 2.x 不兼容，需要 numpy<2
- 与 vllm (需要 numpy>=2.2) 存在根本依赖冲突
- 包维护不佳，存在多重兼容性问题
- 即使强制安装也有运行时错误（BetterTransformer 问题）
- 用户反馈：包太恶心，不值得继续支持

## 移除内容

### 1. 配置文件 (`papersys/config/embedding.py`)
- ❌ 删除 `InfinityEngineLiteral` 类型定义
- ❌ 从 `BackendLiteral` 中移除 `"infinity"` 选项
- ❌ 删除 `EmbeddingModelConfig.infinity_engine` 字段

### 2. 服务代码 (`papersys/embedding/service.py`)
- ❌ 删除 `InfinityBackend` 类（约 90 行代码）
- ❌ 移除 `BackendRegistry.register("infinity", InfinityBackend)` 注册

### 3. 测试代码 (`tests/embedding/test_embedding_service.py`)
- ❌ 删除 `test_infinity_backend_import_error` 测试函数
- ✅ 更新 `test_backend_registry_has_all_backends` 不再检查 infinity

### 4. 临时文件
- ❌ 删除 `tmp/test_infinity_backend.py`
- ❌ 删除 `tmp/test_infinity_direct.py`

### 5. 配置示例 (`config/example.toml`)
- ❌ 删除 Infinity backend 的注释示例

## 保留内容

### 文档（作为历史记录）
- ✅ `devlog/2025-10-21-embedding-backend-refactor.md` - 重构文档
- ✅ `devlog/2025-10-21-infinity-numpy2-compatibility-test.md` - 兼容性测试
- ✅ `devlog/2025-10-21-infinity-test-summary.md` - 测试总结

这些文档保留作为：
1. 历史参考
2. 避免将来重复踩坑
3. 说明为什么不支持 Infinity

## 验证结果

```bash
$ uv run --no-progress pytest tests/embedding/test_embedding_service.py -v
================================================= 7 passed in 4.00s =================================================
```

✅ 所有测试通过（7/7）
✅ 代码中无残留 infinity 相关内容
✅ 配置文件已清理
✅ 仅保留两个后端：`sentence_transformer` 和 `vllm`

## 当前可用后端

### SentenceTransformer Backend
- ✅ 稳定、成熟
- ✅ 支持所有 sentence-transformers 模型
- ✅ CPU/GPU 都很好用
- ✅ 没有依赖冲突

### vLLM Backend
- ✅ 高性能
- ✅ 支持大型 embedding 模型
- ✅ GPU 加速
- ✅ 适合生产环境

## 影响评估

### ✅ 无负面影响
- 没有用户在使用 Infinity backend（从未正常工作过）
- 现有配置文件不需要修改
- 测试套件保持完整
- 代码更简洁、维护负担更小

### ✅ 正面影响
- 减少了约 120 行复杂代码
- 消除了一个潜在的混乱源
- 更清晰的文档和示例
- 降低了新手的困惑

## 代码变更统计

```
Files changed: 5
Additions: 4 lines
Deletions: 127 lines

papersys/config/embedding.py:        -5 lines
papersys/embedding/service.py:       -91 lines
tests/embedding/test_embedding_service.py: -20 lines
config/example.toml:                 -11 lines
tmp/ (deleted files):                -N/A lines
```

## 经验教训

1. **依赖兼容性至关重要**
   - 在添加新依赖前，务必检查与现有依赖的兼容性
   - numpy 版本冲突是难以解决的根本问题

2. **不要被名字迷惑**
   - "Infinity" 听起来很高大上，但实际维护很差
   - 成熟度和稳定性比新特性更重要

3. **及时止损**
   - 当发现一个依赖问题重重时，果断放弃
   - 不要为了一个功能牺牲整体架构

4. **保留文档记录**
   - 详细记录尝试过程和失败原因
   - 避免将来有人重复相同的错误

## 替代方案

如果未来有用户真的需要类似功能：

1. **等待上游修复**
   - 关注 infinity-emb 的 numpy 2.x 支持进展
   - 如果修复了，可以考虑重新添加

2. **使用 vLLM**
   - vLLM 已经足够快
   - 支持更多模型
   - 维护得很好

3. **直接用 sentence-transformers**
   - 简单可靠
   - 社区活跃
   - 文档完善

## 总结

Infinity backend 的移除是一个**正确的决定**：
- ✅ 清理了不工作的代码
- ✅ 简化了架构
- ✅ 避免了用户困惑
- ✅ 降低了维护成本

项目现在更加**简洁、稳定、可维护**。
