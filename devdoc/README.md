# Dev Documentation Guide
Status: Index
Last-updated: 2025-10-03

下表汇总 `devdoc/` 目录下的常用文档，便于快速定位与更新：

| 文档 | 最近更新 | 目的 | 关键内容 |
| --- | --- | --- | --- |
| [architecture.md](architecture.md) | 2025-10-02 | 描述系统旧版流程与本地单例化目标架构 | 历史仓库拆解、模块职责、数据路径、未来规划 |
| [data-storage.md](data-storage.md) | 2025-10-02 | 规范化数据目录与字段定义 | `data/` 层次结构、CSV/Parquet 字段说明、迁移策略 |
| [env.md](env.md) | 2025-10-02 | 约束 Python 环境与关键依赖版本 | uv 管理规范、NumPy/Torch/vLLM 约束、故障排查记录 |
| [rool.md](rool.md) | 2025-10-02 | 团队研发流程守则 | 变更前置计划、测试/复盘要求、命令行约束 |
| [testing/full-pipeline.md](testing/full-pipeline.md) | 2025-10-02 | 端到端推荐+摘要测试指南 | 自动化用例说明、数据准备、真实数据演练脚本 |

维护约定：
- 更新任意文档后同步修正本表 `最近更新` 字段，并在相关 devlog 记录测试/验证情况。
- 大规模改动前需先在 `devlog/` 编写计划，完成后把关键结论回写到对应文档。
- 若新增文档，请在此表中注册描述并注明维护者。

更多阶段进度请参考 [devlog/index.md](../devlog/index.md)。
