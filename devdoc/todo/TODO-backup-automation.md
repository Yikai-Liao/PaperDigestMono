# TODO: Automated Data Backup Pipeline

## Summary
- Implement a scheduled backup flow that compresses critical artifacts (config, preferences, summaries) and syncs them to remote storage.
- Ensure restore scripts exist to rebuild the local environment from a backup bundle.

## Deliverables
1. Scheduler job definition leveraging existing infrastructure to package selected directories/files into timestamped archives.
2. Pluggable uploader abstraction supporting at least local filesystem + one remote target (Hugging Face dataset, S3, or similar) without heavyweight dependencies.
3. Restore script/documented procedure verifying the archive can rehydrate essential state.
4. Tests covering archive manifest generation and dry-run uploader behavior.
5. Documentation describing retention policy, credentials management, and manual restore checklist.

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
