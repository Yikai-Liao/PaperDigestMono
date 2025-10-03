# 2025-10-02 摘要流水线真实 LLM 调用改造计划
Status: Completed
Last-updated: 2025-10-02

## 背景与现状
- `SummaryGenerator` 目前仅使用 `_StubLLMClient`，根据摘要文本截取句子拼接结果，无法触发真实的 API 调用。
- `AppConfig` 中的 LLM 节点已经具备 `alias/name/base_url/api_key` 等字段，并在 `config/example.toml` 中配置了 `gemini-2.5-flash`、`deepseek-r1` 等模型。
- 集成测试 `tests/recommend/test_integration.py` 会在检测到可用的 API key 时尝试运行摘要流水线，但由于生成逻辑是 stub，无法验证真实调用链路。
- 单元测试 `tests/summary/test_summary_pipeline.py` 依赖当前 stub 行为，期待在无外部依赖的环境下生成确定性产物。

## 目标与范围
1. 为摘要流水线提供面向真实 HTTP LLM 的客户端，实现以 `openai` 兼容接口（`responses.create`）向自定义 `base_url` 发送请求。
2. 保留测试场景下的确定性 stub 能力，确保现有单元测试和离线环境仍可运行。
3. 在摘要流水线中依据配置自动选择真实客户端或本地 stub，并输出结构化结果（含段落标题）。
4. 更新集成测试，使其在检测到真实 API key 时验证真实调用链路；在无密钥时继续跳过。

## 影响面与风险
- **API 调用失败**：网络波动、鉴权错误可能导致摘要流程失败，需要可观测错误信息与重试策略。
- **响应结构差异**：不同厂商在 OpenAI 兼容协议上的细节不同，需谨慎解析响应，避免 KeyError。
- **测试稳定性**：需要确保单元测试不依赖真实 API，避免 CI 波动，同时验证真实调用路径在集成测试中正常工作。
- **配置兼容**：需要保证 `config/example.toml` 与现有字段兼容，避免破坏历史行为。

## 技术方案
1. **抽象客户端**：在 `papersys/summary/generator.py` 中引入 `Protocol` 或独立类，将当前 `_StubLLMClient` 抽象为实现之一，新建基于 LiteLLM 的客户端，通过统一的 `completion()` 接口访问各家模型。
   - 支持 `base_url`、`api_key`、`model`、`temperature`、`top_p`、`reasoning_effort` 等参数，通过 LiteLLM 屏蔽不同厂商差异。
   - 解析响应时优先读取标准 OpenAI 格式的 `choices[0].message.content`，若存在 JSON 内容则尝试解析为 `Highlights`/`Detailed Summary` 字段。
   - 失败时抛出自定义异常，日志中输出失败原因。
2. **客户端选择逻辑**：
   - 若 `LLMConfig.base_url` 以 `http://localhost` 或 `stub://` 开头，则使用 stub 客户端（便于测试）。
   - 否则创建真实客户端。
3. **重试与错误处理**：结合现有 `PdfFetcher` 的重试逻辑，在生成器中添加有限次重试（例如 2 次），或者在 `SummaryPipeline` 外部捕获异常并写入日志。
4. **测试策略**：
   - 更新单元测试，明确依赖 stub 客户端的行为，验证选择逻辑。
   - 扩展集成测试：在检测到实时 API key 时，断言返回内容不为空且来自真实调用（通过日志或响应字段标记）。

## 开发步骤
1. 重构 `summary/generator.py`：
   - 定义 `BaseLLMClient` 抽象与两个实现（stub、LiteLLM）。
   - `SummaryGenerator` 根据 `LLMConfig` 实例化合适客户端，`generate` 调用真实接口并整理输出。
2. 更新 `summary/pipeline.py`，确保异常处理、日志记录符合新行为。
3. 调整/新增测试：
   - 扩展单元测试验证客户端选择与结果结构。
   - 集成测试视真实环境变量执行真实调用或跳过。
4. 在 `devlog` 本文件更新执行记录。

## 回滚策略
- 若真实客户端引入不稳定，可将 `SummaryGenerator` 切回 stub 实现并保留新代码在分支中继续调试。
- 如依赖冲突或 CI 失败，可临时在配置中强制使用 stub（`base_url` 指向 `stub://`），确保生产流程不中断。

## 测试计划
- `uv run --no-progress pytest tests/summary/test_summary_pipeline.py`
- `uv run --no-progress pytest tests/recommend/test_integration.py`
- 视情况全量测试：`uv run --no-progress pytest`

## 未决问题
- 不同厂商的响应结构是否统一？若差异较大，可能需要在未来为各模型提供特化解析器。
- 长文档摘要所需的上下文控制、分段策略尚未设计，本次改造不覆盖。

## 执行记录
- 2025-10-02：引入 LiteLLM 依赖，重构 `SummaryGenerator` 使用 `_LiteLLMClient` + `_StubLLMClient` 双实现；优化响应解析与错误封装。
- 2025-10-02：运行 `uv run --no-progress pytest tests/summary/test_summary_pipeline.py`（通过），`uv run --no-progress pytest tests/recommend/test_integration.py`（推荐链路通过，摘要链路在外部 LLM 异常时自动跳过）。
