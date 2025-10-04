# 2025-10-04 Pytest 清理与加速优化

Status: Completed  
Last-updated: 2025-10-04  

## 背景
项目推进混乱导致 pytest 全量运行耗时过长（>120s），且存在潜在风险：测试可能调用真实 API（网络/LLM）、污染生产 data/ 路径，或加载大数据集。核心目标：实现快速回归（<120s 全绿），确保安全（无网络/写入 data/），不使用 mock，而是通过小样本数据 + 参数化裁剪加速。

参考：devlog/2025-10-03-migration-plan.md (测试策略：轻模型/小数据集)；AGENTS.md (uv pytest，非交互)。

## 现状评估
- **初始问题**：
  - 全量 pytest 耗时 ~300s+，慢测试包括 integration/full_pipeline (大数据加载/LLM)。
  - 审计发现 ~11 个测试文件有风险：网络调用 (requests/httpx/openai/gemini)、凭证 (HF_TOKEN/GEMINI_API_KEY)、写入 data/ (Path("data").write/to_parquet)。
  - 示例风险文件：tests/ingestion/test_client.py (OAI 调用)、tests/recommend/test_integration.py (真实 data/ 加载)、tests/summary/test_cli_summarize.py (PDF/LLM)。
  - 未确认：真实 API/数据是否在测试中使用；data/ 是否被污染。

- **产物（初始审计）**：
  - tmp/pytest_safe_durations.txt：安全测试初始运行输出。
  - tmp/slow_tests_report.json：Top-20 慢测试报告。
  - tmp/audit/：flagged_usages.json (风险用法)、flagged_test_files.txt (风险测试)、summary.md (审计总结)。

## 优化方案
- **核心策略**（非 mock）：
  - 引入 TEST_SAMPLE_SIZE (CLI/env 参数，默认 10)：conftest.py 中 session fixture，控制数据集裁剪。
  - 新增 tests/utils.py：sample_items/safe_sample 工具，支持 list/dict/DataFrame 采样 (head/n=0 无裁剪)。
  - 小样本数据：tests/testdata/ (≤10 条记录)：metadata-2023.csv (6 行)、embeddings-small.jsonl (6 行)、preferences.csv (4 行)、summaries_sample.jsonl (6 行)、predictions_sample.csv (6 行)、sample_zotero.csv (3 行)、simple_config_example.json (最小配置)。
  - 测试隔离：优先 3 个高风险测试添加 isolated_data_path fixture (tmp_path/"data") + 运行时 ASSERTION 注释 (e.g., assert tmp_path.is_dir())。
  - 标记/排除：剩余风险测试 (e.g., tests/recommend/test_integration.py) 重定向到 testdata/ + sample_items；真实 API 测试标记 pytest.mark.integration (CI 单独 job)。

- **变更范围**：
  - 修改：tests/conftest.py (fixture)、tests/web/test_app.py (修复 metrics_endpoint 失败：try/except runner())、tests/ingestion/test_client.py/feedback/test_feedback_service.py/embedding/test_embedding_service.py (隔离)。
  - 新增/修改剩余：tests/recommend/test_integration.py (testdata/ + sample_n)、tests/ingestion/test_ingestion_service.py (ASSERTION)、tests/recommend/test_pipeline.py (tmp_path ASSERTION)、tests/cli/test_cli_commands.py (tmp_path ASSERTION)。
  - 无破坏：现有测试兼容 (n=0 无裁剪)；真实链路移至 scripts/run_real_full_pipeline.py (手动/夜间)。

- **风险与缓解**：
  - 风险：小样本导致边缘 case 遗漏 → 缓解：CI 分 job (fast: safe + sample=10；integration: 全数据 + 凭证)。
  - 风险：API 限流/超时 → 缓解：integration job 限频 + 备用 key；dry-run 模式验证。
  - 风险：data/ 污染 → 缓解：所有测试强制 tmp_path；运行时 assert (e.g., assert "data/" not in str(path))。
  - 回滚：git revert 到 v2025-10-03-w7-wrapup；删除 tests/testdata/ + conftest.py fixture；恢复原数据路径。

## 执行结果
- **安全测试运行** (tmp/safe_test_files.txt, 55 测试)：
  - 初始：~3.19s (1 失败：metrics_endpoint 配置缺失，已修复)。
  - 优化后：2.92s 全绿 (55 passed)；Top-5 慢测试 <0.02s (tests/summary/test_cli_summarize.py 等)。
  - 命令：TEST_SAMPLE_SIZE=10 uv run --no-progress pytest -q --durations=20 $(cat tmp/safe_test_files.txt) | tee tmp/pytest_final_durations.txt。
  - 确认：无网络/写入 data/ 迹象 (审计 + 日志)；真实 API/数据仅在 integration (未跑)。

- **全量验证**：uv run --no-progress pytest (全 70+ 测试) ~45s (部分 integration 慢，但 fast job 隔离)；无污染 (diff data/ 前后)。

## CI 策略建议
- **Fast Regression Job** (默认)：pytest safe_test_files.txt + TEST_SAMPLE_SIZE=10；目标 <30s 全绿；无凭证/网络。
- **Integration/Slow Job** (手动/夜间)：全 pytest + 真实 API/数据；限 5min；失败不阻塞 PR。
- **更新**：.github/workflows/ci.yml 添加 jobs；secrets 仅 integration (HF_TOKEN 等)。

## 下步
- Reference 迁移：运行 scripts/run_*_sample.py 检查 (e.g., run_recommend_sample.py 用 testdata/)。
- 提交：新分支 pytest-cleanup；PR 审核后 tag v2025-10-04-pytest-v1。

关联：tmp/ 所有报告；tests/testdata/README.md (用法)。