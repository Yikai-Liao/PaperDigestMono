# 2025-10-03 W5: Publishing/Feedback 集成实施记录

Status: In Progress  
Last-updated: 2025-10-04  
Author: Roo (AI Assistant)

## 实施背景
根据 `devlog/2025-10-03-migration-plan.md` 中的 W5 计划，本周目标是实现 MD 内容构建与反馈回写集成。主要任务包括：
- ContentRenderer：基于参考仓库 `render_md.py` 迁移，实现从总结数据渲染 Markdown 文件。
- giscus/Notion 抓取：实现 GitHub Discussions (giscus) 反馈抓取，初步支持 Notion（若有 API 配置）。
- scripts/build_site.py 和 fetch_feedback.py：构建站点脚本和反馈采集脚本。

依赖：W4 的 `papersys/summary/renderer.py` 和 MD 输出；`legacy-roadmap.md` 中的反馈流程。

风险：GitHub API 限流；Notion API 集成复杂（需确认配置）；模板渲染一致性。

## 实施步骤

### 步骤 1: 分析参考代码
- `reference/PaperDigest/script/render_md.py`：使用 Jinja2 从 Parquet 数据渲染 MD 文件，输出到 `content/` 目录。核心逻辑：加载模板、遍历数据、渲染并写入文件。已读取并理解。
- `reference/PaperDigest/script/fetch_discussion.py`：使用 GitHub GraphQL API 获取 discussions 和 reactions（用于反馈偏好，如 emoji 反应）。核心逻辑：POST GraphQL 查询，保存 JSON 输出。已读取并理解。
- Notion 相关：参考 `reference/NotionAPI/` 中的 MD 文档，但无现成代码。需新实现，使用 Notion API v1（需 API key 配置）。

### 步骤 2: 创建 papersys/feedback/ 目录结构
- 创建 `papersys/feedback/__init__.py`：空文件，标记模块。
- 创建 `papersys/feedback/service.py`：实现 FeedbackService 类，支持 giscus (GitHub Discussions) 抓取。初步集成 Notion（占位，待配置）。
  - 方法：`fetch_giscus_feedback(owner, repo, token)` - 调用 GraphQL 获取 discussions/reactions，解析为偏好更新 (e.g., 👍 → like, 👎 → dislike)。
  - 方法：`fetch_notion_feedback(database_id, token)` - 使用 Notion API 查询页面/评论，解析反馈（TODO: 实现）。
  - 输出：更新 `data/preferences/` 中的 CSV (polars DataFrame)。

### 步骤 3: 扩展 ContentRenderer
- 在现有 `papersys/summary/renderer.py` 中扩展，支持 publishing：添加 `build_site()` 方法，批量渲染总结数据到 `data/publishing/content/`。
- 集成 Jinja2 模板：从 `config/template.j2` 加载（需确认是否存在，或从参考迁移）。
- 处理 draft 状态：基于 preference (dislike → draft=true)。

### 步骤 4: 创建 scripts/build_site.py
- 基于 `render_md.py` 迁移：CLI 脚本，使用 `papersys.summary.renderer` 构建站点。
- 输入：总结 Parquet/JSONL 数据；输出：MD 文件到 `data/publishing/content/`。
- 添加 git 集成：可选 push 到 content_repo (HF 或 GitHub)。

### 步骤 5: 创建 scripts/fetch_feedback.py
- 基于 `fetch_discussion.py` 迁移：CLI 脚本，使用 `papersys.feedback.service` 抓取反馈并更新 preferences CSV。
- 支持 giscus 和 Notion 模式（--source giscus|notion）。
- 输出：日志 + 更新 `data/preferences/YYYY-MM.csv`。

### 步骤 6: 测试实现
- 创建 `tests/feedback/test_feedback_service.py`：单元测试 giscus 抓取（mock requests），验证 reactions 解析；Notion 占位测试。
- 集成测试：`tests/integration/test_publishing_pipeline.py` - 端到端：渲染 → 构建 → 反馈更新（小数据集）。
- 运行：`uv run --no-progress pytest tests/feedback/`，确保全绿。

### 步骤 7: 配置更新
- `papersys/config/publishing.py`：新增 Pydantic 模型，支持 giscus_token, notion_token, content_repo 等。
- 更新 `config/example.toml`：添加 [publishing] 节。
- 测试配置加载：`uv run --no-progress pytest tests/config/test_publishing_config.py`（新增）。

### 步骤 8: 文档更新
- 新增 `devdoc/publishing.md`：描述 Publishing 模块职责、数据流、API 集成。
- 本文件：记录执行细节。

## 遇到的问题与解决方案
- 问题 1: GitHub GraphQL 认证 - 解决方案：使用环境变量 GITHUB_TOKEN，Pydantic 验证。
- 问题 2: Notion API 集成 - 解决方案：初步占位，使用 notion-client 库 (uv add notion-client)，后续配置 database_id。
- 问题 3: 模板一致性 - 解决方案：从参考 `config/template.j2` 迁移，确保 UTF-8 编码。
- 问题 4: 数据路径 - 解决方案：使用 pathlib.Path，配置化 `data/publishing/`。

## Git 版本管理
- Branch: feature/w5-publishing-feedback
- Commits:
  - "feat: init papersys/feedback module and service.py"
  - "feat: extend summary/renderer for site build"
  - "feat: add scripts/build_site.py and fetch_feedback.py"
  - "test: add tests/feedback/test_feedback_service.py"
  - "config: add publishing config model"
  - "docs: add devdoc/publishing.md"
- 每个 commit 前运行 pytest，确保无回归。

## 下一步计划
- 完成 W5 代码实现与测试。
- 验证端到端：运行 scripts/build_site.py 和 fetch_feedback.py 于小数据集。
- 推进 W6 Scheduler 集成（将 publishing 作为作业）。
- 若阻塞：确认 Notion 配置细节。