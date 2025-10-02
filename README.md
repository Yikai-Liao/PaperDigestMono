# PaperDigestMono

## Web 控制台快速上手

仓库内置的 FastAPI 应用现在包含一个轻量级的 Web 控制台，可查看 APScheduler 中注册的任务并手动触发。以下步骤可帮助你快速启用：

### 1. 配置访问令牌（可选但推荐）

在运行服务前，编辑你的配置文件（示例见 `config/example.toml`），新增或修改以下段落：

```toml
[web]
enabled = true
title = "PaperDigest Scheduler Console"

[web.auth]
enabled = true
header_name = "X-Console-Token"
token = "your-secret-token"
```

- 将 `token` 替换为你的共享密钥；若留空且 `enabled = true`，启动时会报错。
- 如需开放访问，可把 `[web.auth]` 删除或设置 `enabled = false`。

### 2. 启动 FastAPI 应用

```bash
uv run uvicorn papersys.web.app:create_app --factory --host 0.0.0.0 --port 8000
```

应用会加载 `config` 中的调度配置，控制台访问路径为 `http://localhost:8000/console`。根路径会自动重定向到控制台；未启用 UI 时将返回提示信息。

### 3. 使用 Web 控制台

- 页面会实时拉取 `/jobs` 接口返回的任务列表，并显示名称与 cron 表达式。
- 点击任意任务后的 “Run” 按钮即可调用 `/scheduler/run/{job_id}` 手动触发。
- 当启用了鉴权时，页面顶部会出现 Token 输入框。令牌仅保存在当前浏览器的 LocalStorage，不会上传服务器。
- API 直接访问同样需要在请求头中携带 `header_name` 对应的 Token 值，否则返回 401。

### 4. 健康检查与自动化

- `/health`：简单的存活探针，无需 Token。
- `/jobs`、`/scheduler/run/{job_id}`：在启用 Token 后将严格校验。
- 可在 CI 或脚本中通过 `X-Console-Token` 请求头调用接口，实现自动化触发。

如需更多配置字段或模块说明，请参阅 `devdoc/` 目录下的文档。
