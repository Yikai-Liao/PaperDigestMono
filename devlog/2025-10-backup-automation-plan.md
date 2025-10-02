# 数据备份自动化开发计划（2025-10-??）

## 1. 背景与现状
- 当前仓库已有 APScheduler 驱动的 `SchedulerService`，但仅注册推荐与摘要两个占位任务，尚无数据备份能力。
- 配置层缺少对备份范围、目的地、保留策略的描述，示例配置也未体现备份需求。
- 缺少统一的备份打包与上传服务；`papersys` 中也没有针对本地或 Hugging Face Dataset 的同步工具。
- 文档未说明备份策略及灾备恢复步骤，用户无法按照统一流程完成恢复。

## 2. 目标与范围
1. 在保持现有调度架构的前提下，新增可配置的备份调度任务，可灵活启用/关闭，并可设置 cron 表达式。
2. 设计 `BackupConfig` 及上传抽象，默认支持本地目录与 Hugging Face Dataset 两种上传器，并提供 dry-run 模式。
3. 实现备份打包服务：可根据配置生成时间戳压缩包，记录清单并在上传失败时回滚临时文件。
4. 编写单元测试覆盖：
   - 备份包生成结果（包含清单元数据与排除规则）。
   - Dry-run 上传逻辑（不触发真实写入但记录操作）。
   - 上传失败后的清理回退。
5. 在 `devdoc/architecture.md` 中补充备份策略、上传配置、恢复流程及注意事项。

## 3. 涉及文件/模块
- `papersys/config/app.py`, `papersys/config/scheduler.py`：扩展备份相关配置。
- 新增 `papersys/config/backup.py` 用于备份源、目标、策略定义。
- 新增 `papersys/backup/` 包：
  - `service.py` 负责打包、调度入口。
  - `uploader.py` 定义上传抽象与两种实现（本地/HF Dataset）。
  - `__init__.py` 导出公共接口。
- `papersys/scheduler/service.py`：注册备份任务并触发打包上传。
- `config/example.toml`：加入备份配置示例。
- 新增 `tests/backup/`：
  - `test_service.py`（打包、失败回退）。
  - `test_uploader.py`（dry-run 行为）。
- `tests/scheduler/test_service.py`：覆盖备份任务注册。
- 文档：`devdoc/architecture.md`（策略与恢复步骤）；如需补充新指南，可增补 `devdoc/todo/TODO-backup-automation.md` 状态说明。

## 4. 影响与风险分析
| 风险 | 描述 | 缓解措施 |
| --- | --- | --- |
| 配置不兼容 | 新增字段可能破坏现有配置加载 | 保持默认禁用、提供严格测试；示例配置同步，确保 Pydantic 默认值安全。
| 备份范围误配置导致体积过大 | 用户可能错误包含大目录 | 支持排除模式与 dry-run 输出清单；文档强调范围控制。
| Hugging Face 上传失败 | 网络或凭证问题导致失败且残留临时文件 | 上传失败时捕获异常并清理临时包；提供 dry-run 和日志。
| 调度与备份耦合过紧 | 后续扩展其他上传器困难 | 抽象上传接口，使用工厂按配置创建实例。
| 测试依赖真实网络 | Hugging Face 上传测试需要外部服务 | 单测对 HF 上传仅验证 dry-run/模拟对象，避免真实调用。

## 5. 实施步骤
1. **配置建模**：编写 `BackupConfig`、`BackupDestinationConfig` 等模型，更新 `AppConfig`、`SchedulerConfig`、示例配置与相应测试。
2. **上传抽象**：创建 `Uploader` 协议及两个默认实现；实现 dry-run 支持、上下文日志与异常处理。
3. **备份服务**：实现打包逻辑（生成 tar.gz 与 manifest），整合上传器，确保失败清理与返回元数据。
4. **调度整合**：在 `SchedulerService` 中注册 `backup_job`，结合 `BackupService` 执行任务并支持 dry-run。
5. **测试**：编写备份服务与上传器测试，更新 scheduler 测试确保新 job 注册；运行全量相关测试。
6. **文档更新**：在架构文档补充策略、恢复流程、凭证管理注意事项；如有需要更新 TODO 状态。

## 6. 回滚策略
- 所有改动均通过新分支提交；若测试或集成失败，可直接使用 `git reset --hard` 回滚至开发前的基线。
- 关键配置和代码模块分步骤提交，便于定位问题。
- 在 dry-run 中验证配置后再上线，避免影响生产环境。

## 7. 预期验收
- `uv run --no-progress pytest tests/backup -v`、`uv run --no-progress pytest tests/scheduler/test_service.py -v` 全部通过。
- 文档中新增的策略与恢复步骤经审阅无缺漏。
- 通过 CLI 或日志验证 Scheduler 可注册备份任务（dry-run 输出）。

