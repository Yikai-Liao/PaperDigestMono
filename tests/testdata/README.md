# tests/testdata 目录说明

## 目录用途

此目录用于存放轻量级样例数据，供快速 CI 回归测试和本地开发使用。所有文件均为小样本（≤10 条记录），旨在加速测试执行而不依赖真实大数据集。

这些文件是轻量替代品，用于快速回归测试。真正的全量或真实数据应放置在 scripts/ 或 data/ 目录下，仅用于手动回归或生产环境。

## 文件列表

- **metadata-2023.csv**  
  格式：CSV  
  字段：id, title, abstract, year  
  示例：6 行 arXiv 元数据记录。  
  测试引用：`Path("tests/testdata/metadata-2023.csv")`

- **embeddings-small.jsonl**  
  格式：JSONL  
  字段：{ "id": "<id>", "embedding": [floats] }  
  示例：6 行，对应 metadata ids 的 8 维嵌入向量。  
  测试引用：`Path("tests/testdata/embeddings-small.jsonl")`

- **preferences.csv**  
  格式：CSV  
  字段：user_id, paper_id, preference_score  
  示例：6 行用户偏好数据。  
  测试引用：`Path("tests/testdata/preferences.csv")`

- **summaries_sample.jsonl**  
  格式：JSONL  
  字段：{ "id": "<id>", "summary": "一句话摘要" }  
  示例：6 行论文摘要。  
  测试引用：`Path("tests/testdata/summaries_sample.jsonl")`

- **predictions_sample.csv**  
  格式：CSV  
  字段：id, score  
  示例：6 行预测分数。  
  测试引用：`Path("tests/testdata/predictions_sample.csv")`

- **sample_zotero.csv**  
  格式：CSV  
  字段：title, firstAuthor, year, abstract, publicationTitle  
  示例：3 行 Zotero 导出格式。  
  测试引用：`Path("tests/testdata/sample_zotero.csv")`

- **simple_config_example.json**  
  格式：JSON  
  内容：配置片段，指向上述样例文件。  
  示例：{"data_root": "tests/testdata", ...}  
  测试引用：`Path("tests/testdata/simple_config_example.json")`

## 后续步骤

在测试文件中指向这些样例数据，例如：

```python
from pathlib import Path

# 在 test 文件中
testdata_dir = Path(__file__).parent.parent / "testdata"
metadata_path = testdata_dir / "metadata-2023.csv"
```

使用这些路径加载数据进行测试验证。