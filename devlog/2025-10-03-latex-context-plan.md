# 2025-10-03 latex context plan

## Current status
- 当前 `ArxivContentFetcher` 仅下载 LaTeX tarball 后粗暴清洗文本，直接作为 LLM 上下文，未充分利用 `latex2json`。
- 需求强调 LaTeX 源码的唯一用途应是通过 `latex2json` → JSON → Markdown 流程生成高保真文本。

## Risks
- `latex2json` 解析失败或耗时过长，可能拖慢摘要流水线。
- 新增 Markdown 缓存目录可能与现有输出目录冲突。
- 解析异常导致回退逻辑缺失，造成摘要上下文为空。

## Plan
1. 在 `papersys/summary/fetcher.py` 引入 `latex2json` 解析与 Markdown 转换辅助函数，消除旧的 `_sanitize_latex` 逻辑。
2. 为成功的 LaTeX 解析结果添加本地缓存，失败时回退到 marker PDF→Markdown；若两者皆失败则跳过该论文并记录日志。
3. 编写单元测试覆盖 LaTeX 成功、marker 回退、全部失败三类分支，确保 `ArxivContentFetcher` 行为符合预期。
4. 运行定向 pytest（summary 模块）验证变更，必要时追加全量测试。

## Rollback strategy
- 若解析或性能问题影响主流程，可回滚 `fetcher` 改动或临时禁用 `fetch_latex_source`。
- 删除新增的测试与缓存目录配置，恢复此前的简易上下文方案。
