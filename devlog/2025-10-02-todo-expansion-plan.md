# TODO Expansion Plan (2025-10-02)
Status: Planned
Last-updated: 2025-10-02

## Current Situation
- `devdoc/todo/` 目录中的条目已覆盖备份、配置巡检、调度可观测性等近期交付，但尚缺后续迭代的细化排期与风险拆解。
- `devdoc/architecture.md` 对未来阶段仅有高层描述，缺少与 TODO 列表联动的任务分解与优先级。
- 用户希望结合《devdoc/rool.md》的规范，对后续 TODO 进行系统性规划并扩写具体内容。

## Scope & Files
- `devdoc/todo/*.md`: 追加新的 TODO 条目或扩写现有计划。
- `devdoc/architecture.md`: 如有必要，补充与新 TODO 对应的架构背景说明。
- `devlog/`：记录本次规划调整（当前文档）。

## Risks
- **方向偏差**：新 TODO 可能与既有路线冲突，需引用架构文档保持一致。
- **范围失控**：条目过多或缺乏优先级，导致执行节奏难以管理。
- **信息重复**：与既有文档重复描述，增加维护成本。

## Mitigations
- 以“阶段目标 + 交付标准”格式撰写每个 TODO，明确验收和依赖。
- 结合当前系统瓶颈（调度、数据、发布、监控）设定优先级，避免一次性扩张。
- 引入里程碑或批次编号（如 T11/T12）保持延续性。

## Plan
1. 梳理现有 TODO 与架构文档，确定仍缺失的关键阶段（数据治理、前端控制台、观察性深化、LLM 成本控制等）。
2. 为每个新 TODO 撰写：Summary、Deliverables、Constraints、Completion Criteria、风险与回滚方案。
3. 在 `devdoc/todo/` 下新增或补充 Markdown（命名遵循 `TODO-<topic>.md`）。
4. 若引入架构层面调整，在 `devdoc/architecture.md` 标注对应章节，维持文档同步。
5. 变更后运行文档 lint（无自动测试需求，但需 `git status` 确认无遗漏）。

## Outcomes (2025-10-02)
- 清理 `devdoc/todo/` 下已完成或不再跟踪的条目，后续规划改在 devlog 中维护。
- 保留本计划文档作为后续需求驻地，避免 TODO 文档重复扩散。
- `devdoc/architecture.md` 已去除多余里程碑段落，以便未来根据实际执行再补充。

## Validation
- 人工检查 TODO 文档结构与内容完整性。
- `uv run --no-progress pytest` 可选执行，确认无误触代码（如本次仅改文档，可省略）。

## Rollback Strategy
- 如规划与需求不符，可通过 `git restore devdoc/todo/` 与 `devdoc/architecture.md` 恢复变更。
- 保留本计划文档，便于回顾修改背景。
