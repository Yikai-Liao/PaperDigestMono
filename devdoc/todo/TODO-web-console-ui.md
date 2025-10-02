# TODO: Web Console UX Upgrade

## Summary
- Deliver a lightweight web UI layered on the existing FastAPI app that surfaces scheduler status, job history, and manual trigger controls.
- Provide a responsive, modern interface without changing backend APIs.

## Deliverables
1. Static assets (Jinja2 templates or lightweight frontend bundle) served from FastAPI with real-time job listings pulled via existing endpoints.
2. Manual trigger UI that calls `/scheduler/run/{job_id}` and streams feedback to the user.
3. Basic authentication guard (token or simple password) configurable via TOML.
4. Frontend smoke tests (Playwright or pytest + httpx snapshots) ensuring key actions stay functional.
5. Documentation snippet covering deployment and customization steps.

## Constraints & Notes
- Reuse FastAPI templating or a minimal JS framework; avoid heavy SPA stacks.
- Align styling with existing project aesthetic; keep assets small and self-contained.
- Ensure accessibility (keyboard navigation, basic ARIA attributes).

## Suggested Branch Name
`feat/web-console-ui`

## Prompt
```
请基于 #file:rules.md 完成以下事项：
1. 在 FastAPI 应用中加入一个简洁的前端界面，展示 `/jobs` 数据并支持手动触发。
2. 实现可配置的简易鉴权机制（例如请求头 token），配置写入 TOML 并通过 Pydantic 管理。
3. 为主要交互编写端到端测试或 HTTP 层单测，确保触发流程可用。
4. 更新文档，说明启用方式与 UI 功能。
```
