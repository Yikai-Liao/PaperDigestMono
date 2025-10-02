# TODO: Automated Data Backup Pipeline

## Summary
- Implement a scheduled backup flow that compresses critical artifacts (config, preferences, summaries) and syncs them to remote storage.
- Ensure restore scripts exist to rebuild the local environment from a backup bundle.

## Deliverables
1. ✅ Scheduler job definition leveraging existing infrastructure to package selected directories/files into timestamped archives.
2. ✅ Pluggable uploader abstraction supporting at least local filesystem + one remote target (Hugging Face dataset, S3, or similar) without heavyweight dependencies.
3. ✅ Restore script/documented procedure verifying the archive can rehydrate essential state.
4. ✅ Tests covering archive manifest generation and dry-run uploader behavior.
5. ✅ Documentation describing retention policy, credentials management, and manual restore checklist.

## Completion Notes
- `BackupService` + 上传器封装在 `papersys/backup/`, 支持本地与 Hugging Face Dataset 两种持久化方式。
- 调度器通过 `scheduler.backup_job` 挂载备份作业，dry-run 只生成包/日志，正式运行后自动清理 staging 并执行本地保留策略。
- 新增 `tests/backup/` 用例覆盖打包、失败清理与 dry-run 行为，示例配置补充备份段落。
- 参见 `devdoc/architecture.md` 中“备份与同步策略（已落地）”段落获取操作指南与恢复要点。

## Constraints & Notes
- Avoid adding large external libraries; lean on `tarfile`, `zipfile`, or `shutil`.
- Keep credentials out of the repo; use existing config patterns for secrets.
- Provide hooks to skip large media files when not needed.

## Suggested Branch Name
`feat/backup-automation`

## Prompt
```
请根据 #file:rules.md 指南完成以下工作：
1. 利用现有 Scheduler 基础添加定期备份任务，可配置备份范围与目的地。
2. 抽象上传接口，默认实现本地与 Hugging Face Dataset（使用现有依赖）。
3. 编写单测覆盖备份包生成、dry-run 上传及失败回退。
4. 文档中补充备份策略与恢复步骤。
```
