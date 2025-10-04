# 静态审计报告：写入与外部依赖

## 执行状态
执行成功。所有 codebase_search 查询均正常完成，无需 fallback 到 regex 搜索。共覆盖 18 个关键字/模式，识别出潜在风险位置。

## 统计
- 被标记的测试文件总数：3
- 被标记的代码文件总数：19

## Top-10 被标记文件（按风险等级排序：network > uses_key > writes_data > heavy_io）
1. **papersys/summary/fetcher.py** (code) - risk_tags: ["network"]  
   Snippet: `with urllib.request.urlopen(request, timeout=timeout) as response:` (line 27)  
   高风险：直接 HTTP 请求，可能导致网络延迟。

2. **papersys/ingestion/client.py** (code) - risk_tags: ["network"]  
   Snippet: `self.session = requests.Session()` (line 52)  
   高风险：持久 Session 用于 arXiv API 调用。

3. **reference/PaperDigest/script/summarize.py** (code) - risk_tags: ["uses_key", "network"]  
   Snippet: `client = OpenAI(api_key=api_key, base_url=base_url,)` (line 96)  
   高风险：LLM API 调用，使用 API key。

4. **scripts/test_real_gemini_api.py** (code) - risk_tags: ["uses_key"]  
   Snippet: `logger.info("GEMINI_API_KEY found: {}...", api_key[:10])` (line 24)  
   中风险：真实 API key 测试脚本。

5. **papersys/summary/conversion.py** (code) - risk_tags: ["heavy_io", "writes_data"]  
   Snippet: `result = subprocess.run(command,` (line 496)  
   中风险：外部工具调用，可能写入临时文件。

6. **papersys/embedding/service.py** (code) - risk_tags: ["network", "heavy_io"]  
   Snippet: `from sentence_transformers import SentenceTransformer` (line 17)  
   中风险：模型下载和 socket 通信。

7. **scripts/fetch_feedback.py** (code) - risk_tags: ["writes_data"]  
   Snippet: `out_path = Path("data/feedback") / f"{args.year}_discussions.csv"` (line 29)  
   低风险：直接写入 data/ 目录。

8. **papersys/feedback/service.py** (code) - risk_tags: ["writes_data", "network"]  
   Snippet: `df = service.fetch_giscus_feedback(Path("data/feedback/discussions.csv"))` (line 173)  
   低风险：反馈数据写入。

9. **papersys/summary/renderer.py** (code) - risk_tags: ["writes_data"]  
   Snippet: `with open(output_path, "w", encoding="utf-8") as f:` (line 81)  
   低风险：Markdown 输出写入。

10. **papersys/summary/pipeline.py** (code) - risk_tags: ["writes_data"]  
    Snippet: `with jsonl_path.open("a", encoding="utf-8") as fp:` (line 289)  
    低风险：JSONL 追加写入。

## 优先级建议
- **立即修复（高风险，network/uses_key）**：  
  - 推荐动作：引入 mock 库（如 responses, pytest-mock）模拟 API 响应；密钥使用 env: 格式并在 CI 中 masked；添加 retry_with_backoff 装饰器。  
  - 模板：`@responses.activate` 或 `@patch('papersys.summary.fetcher._http_get')`。

- **次要修复（中风险，heavy_io/writes_data）**：  
  - 推荐动作：所有写入使用 `tmp/` 目录（pytest tmp_path fixture）；引入 `TEST_SAMPLE_SIZE=10` env 变量限制数据量；subprocess 调用添加 timeout 和 dry-run 模式。  
  - 模板：`if os.getenv('DRY_RUN'): return`；`sample_size = int(os.getenv('TEST_SAMPLE_SIZE', 100))`。

- **手动回归（低风险）**：  
  - 推荐动作：配置路径参数化（Pydantic Field with default=Path('tmp/')）；日志记录所有写入操作。  
  - 模板：`output_dir: Path = Field(default_factory=lambda: Path('tmp/outputs'))`。

## CI 建议
- 将 slow/integration 测试分出单独 job（使用 pytest.mark.slow），仅在 nightly 或 manual trigger 时运行。  
- 在 CI 中设置 HF_TOKEN/GEMINI_API_KEY 为 masked secrets，仅 integration job 暴露；使用 mock 覆盖 unit tests。  
- 添加 pre-commit hook 检查 data/ 写入：`git diff --name-only | grep '^data/' && exit 1`。  
- 运行 `uv run pytest -m "not slow" -q` 确保快速回归 <120s 全绿。