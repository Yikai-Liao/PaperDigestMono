# 被标记测试的修复建议

## 示例1: tests/ingestion/test_client.py (network risk from requests.Session mock)
**问题位置**: Line 107 - `@patch("papersys.ingestion.client.requests.Session.get")`  
测试模拟 arXiv OAI API 调用，但未限制样本量，可能在 integration 模式下下载过多数据。

**改造建议代码片段 (patch 伪代码)**:  
```diff
+import os
 from unittest.mock import Mock, patch
-from papersys.ingestion.client import ArxivOAIClient
 
+def test_list_records_with_resumption(mock_get: Mock, oai_client: ArxivOAIClient) -> None:
+    sample_size = int(os.getenv('TEST_SAMPLE_SIZE', 5))  # 默认5条记录
+    mock_get.return_value.text = f'<ListRecords>{chr(10)*sample_size}</ListRecords>'  # 模拟小样本
     # 原有断言...
```
**添加 TEST_SAMPLE_SIZE 控制**: 在 CI 或 pytest.ini 中设置 `env: TEST_SAMPLE_SIZE=3`，确保测试仅处理少量数据，避免真实 API 滥用。

## 示例2: tests/feedback/test_feedback_service.py (network risk from requests.RequestException)
**问题位置**: Line 74 - `with pytest.raises(requests.RequestException): service.fetch_giscus_feedback()`  
测试异常处理，但真实调用可能泄露 key 或网络超时。

**改造建议代码片段 (patch 伪代码)**:  
```diff
+from unittest.mock import patch
 import pytest
-from papersys.feedback.service import FeedbackService
 
 def test_fetch_giscus_feedback_exception():
+    with patch('papersys.feedback.service.requests.get') as mock_get:
+        mock_get.side_effect = requests.RequestException("Mock error")
+        sample_size = int(os.getenv('TEST_SAMPLE_SIZE', 1))
+        # 限制反馈数据量
     with pytest.raises(requests.RequestException):
         service.fetch_giscus_feedback()
+        mock_get.assert_called_once()  # 验证仅调用一次
```
**添加 TEST_SAMPLE_SIZE 控制**: 使用 env 变量限制反馈查询数量，如 `TEST_SAMPLE_SIZE=2` 只 mock 2 条反馈记录。

## 示例3: tests/embedding/test_embedding_service.py (heavy_io from SentenceTransformer)
**问题位置**: Lines 85, 110 - `from sentence_transformers import SentenceTransformer`  
测试加载模型，可能触发 HuggingFace 下载，耗时且网络依赖。

**改造建议代码片段 (patch 伪代码)**:  
```diff
+import os
 from unittest.mock import patch, MagicMock
-from papersys.embedding.service import EmbeddingService
+from sentence_transformers import SentenceTransformer
 
 def test_embed_documents():
+    if int(os.getenv('TEST_SAMPLE_SIZE', 10)) < 1:
+        pytest.skip("Skip heavy embedding tests in quick mode")
+    with patch('sentence_transformers.SentenceTransformer') as mock_st:
+        mock_model = MagicMock()
+        mock_model.encode.return_value = [vec] * len(docs)  # Mock small vectors
+        mock_st.return_value = mock_model
     service = EmbeddingService(config)
-    result = service.embed_documents(docs)  # docs 限制为小样本
+    result = service.embed_documents(docs[:int(os.getenv('TEST_SAMPLE_SIZE', 5))])
     assert len(result) == len(docs)
```
**添加 TEST_SAMPLE_SIZE 控制**: 在 pytest 命令中添加 `--env TEST_SAMPLE_SIZE=3`，跳过或 mock 大模型加载，确保 unit test <1s。

## 示例4: tests/integration/test_full_pipeline.py (潜在 writes_data，未直接匹配但从搜索推断)
**问题位置**: 全管道测试可能写入 data/，需添加标记。  
**改造建议**: 添加 `@pytest.mark.integration` 和样本限制。  
**添加 TEST_SAMPLE_SIZE 控制**: `os.getenv('TEST_SAMPLE_SIZE', 1)` 只运行1篇论文管道。

## 通用建议
- 所有 flagged tests 标记为 `@pytest.mark.slow` 或 `.integration`，移出快速回归。  
- 使用 `tmp_path` fixture 替换硬编码 data/ 路径。  
- 在 conftest.py 添加 hook: `if os.getenv('QUICK_TESTS'): pytest.skip()` for heavy tests。