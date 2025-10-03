# Reference 仓库功能调研分析

Status: Reference  
Last-updated: 2025-10-03  

## ArxivEmbedding 模块
### 关键功能
- OAI-PMH 元数据抓取，按年份生成 Parquet。  
- 嵌入补齐：下载 HF Parquet，检测缺失向量，任务拆分/批处理生成嵌入，合并上传。  
- RSS 抓取（遗弃）。  

### 脚本依赖
- 入口：batch_embed_local.sh → local_split_tasks.py → process_matrix_tasks.py → merge.py。  
- 依赖：uv, polars, huggingface_hub, embed 库, loguru。  

### 输入输出
- 输入：config.toml (模型键/维度), 年份, HF_TOKEN。  
- 输出：YYYY.parquet (id, title, abstract, categories[list], embeddings[list[float32]]); 任务 JSON。  
- 路径：temp/local_matrix_tasks/, merged_data/。  

参考：[`fetch_arxiv_oai.py`](reference/ArxivEmbedding/script/fetch_arxiv_oai.py:1), [`batch_embed_local.sh`](reference/ArxivEmbedding/batch_embed_local.sh:1)。

## PaperDigest 模块
### 关键功能
- 推荐：LogisticRegression 训练/预测，自适应采样。  
- PDF 下载/提取：arXiv PDF/LaTeX → Markdown (latex2json/marker-pdf)。  
- 摘要：LLM (OpenAI/Gemini) 结构化 JSON 生成。  
- 渲染：Jinja2 MD 输出。  
- 偏好：giscus emoji → CSV 更新。  

### 脚本依赖
- 推荐：fit_predict.py (polars/sklearn) → download_pdf.py → pdf_extractor.py → summarize.py (OpenAI/Gemini) → render_md.py。  
- 偏好：fetch_discussion.py → update_preference.py。  
- 依赖：uv, polars, tiktoken, marker-pdf, latex2json。  

### 输入输出
- 输入：config.toml (类别/LLM/阈值), 偏好 CSV, HF 数据集。  
- 输出：predictions.parquet (id, score); raw JSON; content MD; preference YYYY.csv。  
- 路径：raw/, preference/, pdfs/, content/。  

参考：[`fit_predict.py`](reference/PaperDigest/script/fit_predict.py:1), [`summarize.py`](reference/PaperDigest/script/summarize.py:1)。

## PaperDigestAction 模块
### 关键功能
- Action 打包推荐/摘要；Zotero → CSV 偏好生成；数据清理。  

### 脚本依赖
- 入口：recommend.py (dataloader/trainer/sampler); summarize.py (summarize/json2md); generate_preference.py。  
- src/：dataloader (加载), trainer (模型), summarize (LLM), archiver (归档?), augment (增强?), sampler (采样)。  
- 测试：test_dataloader/summarize/archiver。  
- 依赖：uv, polars/sklearn, HF Hub, LLM (OpenAI/Gemini/DeepSeek), marker-pdf。  

### 输入输出
- 输入：config.toml, 偏好 CSV, HF 数据集, Zotero CSV。  
- 输出：recommendations.parquet; summarized YYYY.jsonl; preference YYYY.csv。  
- 路径：preference/, summarized/, cache/, test/data/。  

参考：[`recommend.py`](reference/PaperDigestAction/script/recommend.py:1), [`src/summarize.py`](reference/PaperDigestAction/src/summarize.py:1)。

## 迁移要点/兼容风险
- 接口：Parquet schema 复用 (id/title/abstract/embeddings); LLM 提示/Pydantic (PaperSummary) 迁移。  
- 数据：偏好 CSV/HF preference 标准化；JSONL 适配 summaries/ (institution/one_sentence_summary 等)。  
- 流程：HF 增量 → 本地 backlog；Action 自动化 → scheduler；NaN 嵌入修复 (~30%)。  
- 风险：并行 num_workers 与 FastAPI 冲突；uv/3.12+ 兼容 (tiktoken/marker-pdf)；性能 (单机 GPU)。  

## 待澄清
- src/archiver/augment/sampler 确切职责 (建议 list_code_definition_names src/)。  
- example_usage.py 额外 LLM 细节 (建议运行测试)。  
- 偏好更新是否保留 Telegram Bot (查 devlog/2025-10-03-legacy-roadmap.md)。  

后续：search_files reference/ "TODO/FIXME"；pytest tests/ 验证旧流水线。