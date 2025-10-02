# Summary pipeline real-data integration plan (2025-10-02)

## Current state
- 集成测试 `tests/integration/test_full_pipeline.py` 为了可重复性使用手工构造的候选 Parquet/CSV，并只覆盖推荐→占位 PDF → Stub LLM 的路径。
- `SummarySource` 仅携带摘要文本；`SummaryGenerator` 在大多数配置下仍然向 LLM 发送摘要而非正文。
- `PdfFetcher` 始终写入占位 PDF，未真正访问 arXiv；`enable_latex` 标记暂未生效。
- Markdown 渲染仅基于 LLM 回传的 JSON，缺乏 LaTeX→Markdown 的预处理链路。

## Target scope
- 使用真实的 arXiv ID 与本地嵌入缓存，跑通推荐→摘要。
- 从 arXiv 下载真实 PDF，并在 `enable_latex=true` 时额外抓取 e-print tarball 以提取 LaTeX 源。
- 将 LaTeX 转为 Markdown，作为上下文传入 LLM，最终保留 PDF、Markdown、结构化 JSON。
- 保持流水线在无网络/无 API Key 的测试环境下可覆盖（需要 stub/inject 机制）。

## Implementation steps
1. **数据接入与源描述**
   - 新增 `RecommendationDataLoader.describe_sources()` 的辅助函数，提供 `SummaryPipeline` 构建 `SummarySource` 所需的 pdf_url/latex_url。
   - 在 `tests/integration` 内保留现有轻量数据集，但允许通过环境开关切换为真实数据。真实跑通流程将在 CLI 演示命令中展示而非测试强制执行。

2. **HTTP Fetcher 重构**
   - 将 `PdfFetcher` 拆成接口 + 具体实现：`ArxivPdfFetcher`（真实下载）与 `PlaceholderPdfFetcher`（测试用）。
   - 实现 `ArxivFetcher`：
     - 以 `summary_pipeline.pdf` 的 `delay/max_retry` 控制重试；
     - 支持通过 `SummarySource.pdf_url` 或默认 `https://arxiv.org/pdf/<id>.pdf` 下载；
     - 下载完成后写入 `<pdf_dir>/<paper_id>.pdf`，同时返回路径。
   - 同步实现 `EPrintFetcher`（拉取 `https://export.arxiv.org/e-print/<id>` tarball），解包到临时目录并返回主 `.tex` 路径。

3. **LaTeX→Markdown 预处理**
   - 新增模块 `papersys.summary.extractor`：
     - 使用 `latex2json.TexReader` 解析 tex 源；
     - 生成结构化 JSON，再渲染为 Markdown（复用现有模板或新增简化模板）；
     - 若解析失败，回退到 pdf→纯文本（暂以摘要作为兜底）。
   - 在 `SummaryPipeline` 中将提取结果写入 `<pdf_dir>/markdown/raw/<paper_id>.md`，供 LLM 输入与缓存。

4. **LLM 调用上下文增强**
   - 扩展 `SummarySource` 增加 `markdown_path` 或 `content` 字段；`SummaryGenerator` 在构建 prompt 时附加正文（截断/摘要策略待定）。
   - 更新 `_LiteLLMClient.summarise`：
     - 如果存在正文，拼接 `Abstract` + `Body` + `Sections` 提示；
     - 继续沿用 JSON Schema 探测逻辑。

5. **CLI 与演示脚本**
   - 在 `papersys.cli` 新增 `summarize run`（或 `summaries real-run`）命令，接受 `--paper-id` 列表，运行真实抓取 + LLM 调用。
   - 文档更新：`devdoc/testing/full-pipeline.md` 补充真实跑通步骤、必须的环境变量。

6. **测试与验证**
   - 为 fetcher/extractor 编写单元测试，使用 `pytest` 的 monkeypatch/本地 HTTP server 注入假响应。
   - 更新现有集成测试以注入 `PlaceholderPdfFetcher`，确保不访问网络。
   - 新增 smoke test（标记为 `@pytest.mark.slow`）需显式启用才访问网络，可用于 CI 之外的人工验证。

## Risk assessment
- arXiv 网络访问可能被限流：需要超时 & 重试策略，必要时引入简单缓存。
- `latex2json` 对复杂宏的鲁棒性有限：需容错并提供 fallback。
- LLM 成本：真实命令默认走 dry-run/stub，需用户显式同意才触发远端调用。

## Rollback & mitigation
- 保留 `PlaceholderPdfFetcher` 并在配置层可选；若真实下载失败，允许 fallback 到占位 PDF + 摘要模式。
- 新增功能尽量封装在独立模块，出现问题可回滚对应文件而不影响推荐链路。