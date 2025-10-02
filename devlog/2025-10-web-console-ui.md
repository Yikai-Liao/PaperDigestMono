# Web 控制台与鉴权改造计划（2025-10-03）

## 一、背景与目标

当前 FastAPI 服务仅提供 JSON API（`/health`、`/jobs`、`/scheduler/run/{job_id}`），缺少人性化的界面来查看任务状态与手动触发。同时，接口没有任何访问控制，生产部署时存在被误触发或恶意触发的风险。本次需求旨在：

1. 追加一个轻量级 Web 控制台，复用现有 API 展示任务列表并提供手动触发入口；
2. 引入配置化的请求头 Token 鉴权，保护关键接口；
3. 补充端到端/HTTP 层测试，确保受保护的触发流程仍可用；
4. 更新文档说明启用方式与 UI 功能，降低运维接入成本。

## 二、现状分析

- **后端结构**：`papersys/web/app.py` 当前只注册 JSON 路由，未包含模板或静态资源支持。`create_app()` 仅依赖 `SchedulerService`，与配置体系 (`papersys/config/app.py`) 没有直接联动。
- **调度服务**：`papersys/scheduler/service.py` 提供 `list_jobs()` 与 `trigger_job()`，能满足前端展示/手动触发的业务需求。
- **配置体系**：`config/example.toml` 已通过 `AppConfig` 管理，但无 Web/UI 或鉴权相关字段。
- **测试现状**：`tests/web/test_app.py` 覆盖现有 API，但未涉及鉴权或 UI。无端到端交互测试。

## 三、涉及模块与潜在影响

| 模块 | 文件 | 变更点 | 影响评估 |
| ---- | ---- | ------ | -------- |
| Web 应用 | `papersys/web/app.py` | 引入模板渲染、静态响应、请求头鉴权依赖 | 需确保现有 JSON API 向后兼容；`create_app` 签名调整后要同步更新调用处与测试 |
| 配置 | `papersys/config/app.py`、`papersys/config/__init__.py` | 新增 Web/Auth 配置模型 | TOML 结构变化需更新示例配置与潜在加载逻辑 |
| 配置样例 | `config/example.toml` | 添加 Web 控制台与鉴权字段 | 需要说明默认关闭或默认 Token 行为 |
| 前端资源 | `papersys/web/templates/*`, `papersys/web/static/*` | 新增模板与样式脚本 | 确保 FastAPI 可正确加载；注意包内资源路径 |
| 测试 | `tests/web/test_app.py` 或新增文件 | 扩展用例覆盖鉴权与 UI 基本加载 | 运行 `pytest` 保证通过 |
| 文档 | `README.md` 或 `devdoc/env.md` | 说明开启控制台与配置方法 | 便于部署者启用 |

## 四、风险分析与应对

1. **鉴权误伤合法请求**：若默认强制 Token，可能导致本地调试失败。→ 计划将 Token 配置设为可选，未配置时放行；配置后统一校验。
2. **模板加载失败**：打包路径错误或未在 FastAPI 中正确挂载可能导致 500。→ 使用 `pathlib` 获取 `templates` 目录，通过 `Jinja2Templates` 注册；配合测试验证 `/console` 正常响应。
3. **接口兼容性问题**：`create_app` 签名变动可能影响其他导入方。→ 提供默认参数（如 `auth_config=None`），并在测试中覆盖旧行为。
4. **前端交互不可用**：手动触发按钮调用失败或缺乏 Token 时无法工作。→ 设计前端逻辑：在页面中允许输入 Token 后再触发；编写 HTTP 层测试模拟有 Token 的请求。
5. **测试覆盖不足**：端到端交互需验证 401/200 场景。→ 新增 pytest 用例覆盖缺失 Token、Token 正确、错误 Token 三种情况，并确保 `/console` 返回 HTML。

## 五、开发方案

1. **配置扩展**：
   - 新增 `WebAuthConfig`（字段：`enabled`、`header_name`、`token`）与 `WebUIConfig`（字段：`enabled`、`title` 等）模型，挂载到 `AppConfig`。
   - 更新 `config/example.toml` 展示如何设置 Token（例如 `X-Console-Token`）。
2. **后端改造**：
   - 更新 `create_app`：接受 `AppConfig | None`，基于配置构建依赖。增加 `/console`（GET）渲染模板，静态加载简洁 CSS/JS。
   - 实现统一依赖函数 `verify_token`，对 `/jobs` 和 `/scheduler/run/{job_id}` 设置 `Depends`。未配置 Token 时直接放行；启用后校验请求头。
3. **前端实现**：
   - 在 `templates/console.html` 中使用 `<template>` + `<script>` 生成表格。JavaScript 负责调用 `/jobs`、渲染列表，并在按钮点击时发送 `POST` 请求。若启用 Token，则从浏览器 `localStorage` 或用户输入框读取后附加到请求头。
   - 简易样式保证响应式布局和可访问性（按钮具备 aria-label、键盘触发）。
4. **测试编写**：
   - 扩展 `tests/web/test_app.py`：覆盖 `/console` HTML 响应、鉴权缺失 401、错误 Token 401、正确 Token 200 + 触发成功。
   - 保留现有断言，确保未开启 Token 时原逻辑仍生效。
5. **文档更新**：
   - 在 `README.md` 新增“Web 控制台”章节，说明启动 FastAPI、配置 Token、界面功能。

## 六、风险规避与补救措施

- 在实现前端之前先编写依赖和 API 层测试，确保后端鉴权逻辑稳定。
- 如模板渲染出现路径问题，可通过 `TestClient` 的 `.get("/console")` 结果快速定位。
- 若 UI JS 请求因 CORS/路径错误导致失败，可先在测试中对 `/jobs` 直接调用验证接口可用，再调试前端脚本。
- 若最终 `pytest` 未通过，回滚到提交前状态，重新核对依赖注入逻辑。

## 七、预期效果

- Web 控制台可在桌面/移动端展示作业列表，并允许单击触发任务。
- Token 鉴权默认关闭；启用后，未携带正确 Token 的请求将收到 401。
- 新增测试覆盖关键流程，`uv run pytest` 全量通过。
- README 文档明确说明部署者如何启用与使用控制台。

## 八、测试计划

- 开发完成后执行 `uv run pytest tests/web/test_app.py -v`，确保 Web 层测试通过。
- 视情况补充运行 `uv run pytest` 全套，确认无回归。

> 待用户确认后开始编码，若执行中发现遗漏，将在本日志追加“反思”段落并更新经验教训记录。
