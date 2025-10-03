# Summary pipeline config refine
Status: Completed
Last-updated: 2025-10-03

## Current situation
- `SummaryPipelineConfig` 仍将 LLM 选择与 PDF 抓取杂糅在同一个 `PdfConfig` 节点里，`enable_latex` 既用于控制 LLM 输出，又误导性地驱动 LaTeX 抓取逻辑。
- 实际运行中需要拆分“抓取 LaTeX 上下文”与“允许模型输出 LaTeX”两类开关，同时整理示例配置与 CLI 检查输出。

## Risks
- 配置字段改名后，旧有测试、CLI 提示与脚本可能引用失效导致回归失败。
- 调整摘要生成器逻辑若未覆盖，可能破坏 Stub LLM 或真实 LLM 的调用参数。

## Plan
- 引入 `PdfFetchConfig` 与 `SummaryLLMConfig`，重写 `SummaryPipelineConfig`、示例配置与相关单元测试。
- 更新 `SummaryPipeline` 以选择 LLM 配置、传递新 `allow_latex` 参数，并让 fetcher 读取 `fetch_latex_source` 标志。
- 调整 CLI、脚本和文档，确保所有输出/说明与新字段保持一致。
- 运行现有 pytest 用例验证回归。

## Rollback strategy
- 若新结构引发大量兼容性问题，保留旧 `PdfConfig` 别名与字段映射，允许在一次提交内回退至拆分前的配置并恢复相关测试。

## 执行记录
- 2025-10-03：拆分 `SummaryPipelineConfig` 为 `PdfFetchConfig` 与 `SummaryLLMConfig`，更新 `papersys/config/summary.py`、`config/example.toml` 与加载逻辑。
- 2025-10-03：调整 `SummaryPipeline` 以根据 LLM 别名解析配置、传递 `enable_latex`，并确保 fetcher 读取 `fetch_latex_source`。
- 2025-10-03：新增/更新 `tests/config/test_summary_config.py`、`tests/summary/test_summary_pipeline.py` 覆盖新结构。
