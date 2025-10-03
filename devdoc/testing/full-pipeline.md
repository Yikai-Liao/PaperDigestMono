# 本地端到端推荐 + 摘要集成测试
Status: Reference
Last-updated: 2025-10-02

## 测试目标
- 从偏好数据与缓存嵌入构建推荐数据集，并训练/预测得到候选论文。
- 依次执行 PDF 占位生成、Markdown 渲染与 LLM 摘要生成，确认完整流水线无外部依赖。
- 整个过程限定在临时目录中，避免污染真实数据目录。

## 回归用例
- 对应自动化用例：`tests/integration/test_full_pipeline.py`
- 依赖组件：`RecommendationPipeline`、`SummaryPipeline`、Stub LLM (`base_url = "http://localhost"`)

## 数据准备（自动完成）
测试会在 `tmp_path` 下生成以下结构：

```
preference/events.csv         # 单条 like 偏好
cache/2025.parquet            # 三条带嵌入、分类与摘要的候选样本
summary-output/               # PDF 占位文件与 Markdown 输出
recommend-output/             # 推荐结果 JSONL（由配置预留，可选）
```

## 运行方式
```bash
uv run --no-progress pytest tests/integration/test_full_pipeline.py
```

运行成功后可在测试产生的临时目录中看到：
- `summary-output/*.pdf`：由占位写入逻辑生成的 PDF 文件，验证抓取阶段。
- `summary-output/markdown/*.md`：包含章节、要点和模型元信息的 Markdown 摘要。

## 验证要点
- 推荐阶段：`artifacts.dataset.preferred/background` 均非空，`recommended.height >= 1`。
- 摘要阶段：每个 `SummaryArtifact` 同时具有 PDF/Markdown 输出，Markdown 内容包含论文标题与 `Highlights` 部分。

## 注意事项
- 测试使用内置嵌入向量（随机指定的浮点数组），不依赖真实 HuggingFace 资源。
- LLM 请求走 Stub 分支，不会外发网络请求；如需真实模型可在配置中替换 base_url。
- 若需手动调试可将 `_write_candidate_cache` 中的样本列表扩展为更多论文，并调小/调大评分阈值以观察推荐结果变化。

## 手动真实数据演练
- **脚本位置**：`scripts/run_real_full_pipeline.py`
- **用途**：使用配置中的真实偏好数据、嵌入与 LLM 端点，在隔离的输出目录下跑通推荐→摘要全链路，便于人工检查真实产出质量。
- **运行示例**：
	```bash
	uv run --no-progress python scripts/run_real_full_pipeline.py \
			--config config/example.toml \
			--limit 3 \
			--output-dir .tmp-real-runs/$(date +%Y%m%d-%H%M%S)
	```
- **行为特性**：
	- 自动校验所选 LLM 的 API Key（例如 `GEMINI_API_KEY`）。
	- 从配置指向的 `preference/`、`cache/` 等目录读取数据，但所有中间产物（推荐结果、PDF、Markdown）都会写入 `--output-dir`，不会污染 `data/`。
	- 默认使用真实的 arXiv PDF 下载器；若 `fetch_latex_source = true`，会尝试抓取 e-print tarball 以提取正文提供给 LLM；`enable_latex = true` 仅影响模型输出是否允许包含 LaTeX。
	- 打印推荐样本概览与每篇论文的 Markdown 片段，便于快速人工复核。
