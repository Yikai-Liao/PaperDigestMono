# PR-3/4/5 Integration Plan (2025-10-02)
Status: Planned
Last-updated: 2025-10-02

## Current State
- `master` 已引入 Scheduler 可观测性、结构化日志与 `/metrics`，同时保持 `papersys/web` API 稳定。
- `pr-2` 基于旧基线，仅新增 `devdoc/progress-2025-10-evaluation.md`，但缺乏观测性相关文件，直接合并会回滚最近的架构更新，因此计划关闭而不合并。
- `pr-3` 与 `pr-5` 内容相同（自动备份流水线、`BackupService`、配置拓展及测试），但同样基于旧基线，直接合并会抹掉最新的 Scheduler 逻辑。
- `pr-4` 添加配置巡检 CLI (`papersys.config.inspector` + `papersys.cli config ...`) 及单测，也基于旧基线并删除观测性功能。
- `devdoc/todo/` 中对应的 TODO 仍标记为未完成，需要在功能落地后更新状态/补充完成记录。

## Risks
- 旧分支覆盖 `papersys/scheduler/service.py`、`papersys/web/app.py` 导致观测性回退。
- 新增 `papersys.backup` 模块需与现有日志、测试框架对齐，避免缺少 type hints 或路径处理不一致。
- CLI 新子命令需确保与现有参数、日志风格兼容，并避免破坏 `serve/status/summarize` 入口。
- 配置模型扩展后必须同步更新 `config/example.toml` 与 `tests/config/test_load_config.py`，否则会产生验证偏差。
- 新测试（backup/cli）可能依赖临时文件或 monkeypatch，需确保在当前 pytest 设置下稳定运行。

## Plan
1. **手动整合备份流水线 (PR-3/5)**
   - 新建 `papersys.backup` 包（service/uploader）并补齐 `__all__`。
   - 在 `papersys.config` 中添加 `BackupConfig/BackupDestinationConfig`，扩展 `AppConfig`、导出入口与示例配置。
   - 调整 `SchedulerService`：在保持观测性逻辑的前提下新增 `backup` 作业注册与执行钩子（复用 `BackupService`）。
   - 覆盖/新增测试：`tests/backup`、`tests/config`、必要的 scheduler 行为补充。

2. **整合配置巡检 CLI (PR-4)**
   - 引入 `papersys.config.inspector` 辅助函数，注意类型注解和异常包装。
   - 扩展 CLI：新增 `config` 子命令与 `check`/`explain` 子命令，保持日志输出风格；兼容 JSON 输出。
   - 新增 `tests/cli/test_cli_config.py` 并确保现有 CLI 测试仍通过。

3. **文档与 TODO 调整**
   - 在 `devdoc/architecture.md` 中补充备份流水线与配置巡检说明，保留现有观测性章节。
   - 更新 `devdoc/todo`：为备份与配置巡检 TODO 添加完成勾选/总结，明确状态。
   - 说明 `pr-2` 关闭原因（可在 TODO 或 devlog 反映）。

4. **测试与验证**
   - 全量运行 `uv run --no-progress pytest`。
   - 根据需要补充针对 `BackupService` 的 dry-run 验证记录。

## Rollback Strategy
- 所有改动集中在单一分支，可通过 `git reset --hard origin/master` 回滚。
- 新增文件如出现问题，可逐个移除后重新运行测试；涉及配置或 CLI 的变更保留在独立提交，方便局部撤销。
- 若 `BackupService` 上线后出现问题，可在配置中临时禁用 `scheduler.backup_job` 与 `backup.enabled`，保障主流程不受影响。

## Validation
- `uv run --no-progress pytest`
- 若新增命令有日志差异，补充手动 `uv run --no-progress python -m papersys.cli config check --format json` 验证。

