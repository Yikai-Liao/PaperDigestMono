# 数据存储结构与字段说明
Status: Reference
Last-updated: 2025-10-02

> 更新时间：2025-10-02（基于 `papersys` 单仓本地优先架构）

## 目录总览

系统所有持久化数据集中于 `data/` 目录，按数据域拆分：

```
data/
  metadata/
    metadata-YYYY.csv
    latest.csv
  embeddings/
    <model_alias>/
      YYYY.parquet
      manifest.json
      backlog.parquet
  preferences/
    events-YYYY.csv
  summaries/
    YYYY-MM.jsonl
  logs/
    (运行日志，默认为 JSON 行)
  temp/
    (临时工件，例如 PDF、Markdown 草稿)
```

- **metadata/**：标准化后的论文元数据，按年份切分并提供汇总视图。
- **embeddings/**：每种模型独立存放向量、清单与补齐待办。
- **preferences/**：用户偏好事件流，按年份追加。
- **summaries/**：结构化摘要 JSONL，每月一文件。
- **logs/**、**temp/**：运行时日志与临时缓存，默认不纳入版本管理。

## 数据域详解

### 1. 元数据（`data/metadata/`）

| 字段名 | 类型 | 说明 | 来源 |
| --- | --- | --- | --- |
| `paper_id` | `str` | 唯一标识，等同 `arXiv` ID | Hugging Face 数据集年份 Parquet |
| `title` | `str` | 论文标题 | 同上 |
| `abstract` | `str` | 摘要全文 | 同上 |
| `categories` | `str` | 以 `;` 拼接的分类列表 | 同上（list → join）|
| `primary_category` | `str` | 分类第一个元素 | 同上 |
| `authors` | `str` | 作者列表，以 `;` 拼接 | 同上 |
| `published_at` | `str` (`ISO-8601`) | 创建时间 | 字段 `created` |
| `updated_at` | `str` (`ISO-8601`) | 最近更新时间 | 字段 `updated` |
| `doi` | `str` | DOI 编号（若存在） | 同上 |
| `comment` | `str` | arXiv Comment | 同上 |
| `journal_ref` | `str` | 期刊收录信息 | 同上 |
| `license` | `str` | 授权协议 | 同上 |
| `source` | `str`（恒为 `legacy_migration`） | 迁移来源 | 迁移脚本注入 |

**优点**
- 保持与迁移脚本 `LegacyMigrator` 输出一致，便于增量更新。
- CSV 结构易于查看、筛选及导入数据库。

**不足**
- 对长文本字段无压缩，单文件体积较大。
- `categories`、`authors` 串接后丢失结构化信息，后续若要分析需再拆分。

### 2. 向量（`data/embeddings/<model_alias>/`）

| 文件 | 作用 | 关键字段 |
| --- | --- | --- |
| `YYYY.parquet` | 存放指定年份的向量数据 | `paper_id`、`embedding` (`list[float32]`)、`model_dim` (`int`)、`generated_at` (`ISO-8601`)、`source` |
| `manifest.json` | 记录模型维度、样本总数、年度文件清单 | `model`、`dimension`、`total_rows`、`years`、`files`、`generated_at`、`source` |
| `backlog.parquet` | 待补齐或失败的样本列表 | `paper_id`、`missing_reason`、`origin`、`queued_at` |

**优点**
- 向量与元数据解耦，便于替换模型或混合多源向量。
- `manifest.json` 提供元数据，方便监控及同步。
- `backlog` 支持调度器增量补齐。

**不足**
- `embedding` 仍采用 `float32`，磁盘开销较高，后续可考虑改为 `float16` 或引入分块存储。
- 缺少向量内容校验（如摘要长度、校验和），需依赖上游流程保障。

### 3. 偏好事件（`data/preferences/`）

CSV 采用 UTF-8 编码，不带表头注释，字段如下：

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `paper_id` | `str` | 论文 ID |
| `preference` | `str`（`like`/`dislike`/`skip`/自定义标签） | 用户反馈枚举 |
| `recorded_at` | `str` (`ISO-8601`) | 推断或记录的时间戳 |

**优点**
- 简单、紧凑，兼容现有历史数据。
- 按年份拆分，便于按时间范围采样。

**不足**
- 未保留原 CSV 的来源信息，仅在迁移报告中计数；如需稽核需回溯源文件。
- 缺少事件来源、置信度等扩展字段，后续若需要需调整 schema。

### 4. 摘要（`data/summaries/`）

按月份生成 JSONL，每行一个论文摘要记录。核心字段顺序由 `SUMMARY_FIELD_ORDER` 固定，以确保输出稳定：

| 字段名 | 说明 | 备注 |
| --- | --- | --- |
| `id` | 论文 ID（兼容 JSON 中缺失 ID 的情况） | 必填 |
| `title` | 标题 | 可能为空 |
| `slug` | 渲染用别名 | 可选 |
| `one_sentence_summary` | 单句摘要 | 可选 |
| `problem_background`/`method`/`experiment`/`further_thoughts`/`reasoning_step` | 结构化摘要段 | 可选 |
| `summary` | 主体摘要文本 | 若旧数据无则留空 |
| `abstract`/`authors`/`institution`/`categories`/`keywords` | 原始元数据的冗余存储 | 视来源而定 |
| `preference`/`score` | 推荐阶段结果 | 可选 |
| `created`/`updated` | 原记录的时间戳 | 可选 |
| `summary_time` | 解析后的摘要生成时间 (`ISO-8601`) | 若缺失则空字符串 |
| `migrated_at` | 本次迁移的生成时间 (`ISO-8601`) | 由脚本注入 |
| `source` | 数据来源（`papersys.raw` 或 `papersys.action` 等） | 由脚本注入 |
| `source_file` | 原 JSON/JSONL 文件相对路径 | 便于追踪 |
| `lang` | 摘要语言标记（历史写入，约定沿用） | 外部预先标注 |
| `model`/`temperature`/`top_p` | LLM 推理参数 | 旧数据保留 |
| `year`/`date` | 部分旧记录的冗余字段 | 可选 |
| `license` | 授权协议 | 可选 |
| `show` | 布尔或字符串，用于下游展示控制 | 可选 |

额外内部字段 `__month__` 仅在写入阶段用于分组，不会落盘。

**优点**
- 以 JSONL 形式存储，方便批量处理与增量追加。
- 保留 `source_file` 便于追踪历史来源。
- 字段顺序固定，避免 diff 噪声和序列化不稳定问题。

**不足**
- 字段较多且来源不一，容易出现稀疏数据。
- `lang` 值由历史数据提供，缺少校验流程；如添加新语言需确定值域。
- 尚未拆分多语言或多版本摘要，后续如需更细粒度管理需拓展结构。

## 数据流动与交叉依赖

1. **迁移阶段**：`LegacyMigrator` 自引用仓库 `reference/` 读取旧数据，生成上述目录结构。
2. **在线阶段**：调度器依赖 `metadata/`、`embeddings/`、`preferences/` 生成推荐批次；摘要生成后写入 `summaries/`。
3. **反馈回流**：偏好事件更新 `preferences/`；如有新摘要语言需求，可在上游写入 `lang` 字段后重新迁移。

## 优缺点综述

| 数据域 | 优点 | 不足 | 潜在优化 |
| --- | --- | --- | --- |
| 元数据 | CSV 易读、字段契合现有需求、与向量解耦 | 大字段无压缩、结构化信息打平 | 评估 DuckDB/Parquet 作为主存格式；保留 authors/categories 原始结构 |
| 向量 | 分模型存储、自带 manifest/backlog | 空间成本高、无校验 | 引入压缩/分块；记录校验和；backlog 加权优先级 |
| 偏好 | 轻量、兼容旧 CSV、便于年份过滤 | 字段少、缺少来源追踪 | 增补 `source`/`confidence` 字段；引入事件版本号 |
| 摘要 | JSONL 易 diff、字段顺序固定、留有源路径 | 字段稀疏、`lang` 缺乏验证、多语言难支撑 | 设计 schema registry；增加语言枚举校验；考虑拆分多版本摘要 |

## 如何维护

- **新增字段**：
  1. 在产生该字段的服务或脚本中实现。
  2. 更新本文档及 `SUMMARY_FIELD_ORDER` / 数据写入逻辑。
  3. 补充测试或示例文件，确保迁移/生成流程稳定。

- **新增模型**：
  1. 在配置中注册新模型别名。
  2. 运行嵌入服务生成 `YYYY.parquet` 并同步 `manifest.json`。
  3. 如需回填历史数据，确保 `backlog.parquet` 更新。

- **数据校验**：
  - 元数据与偏好可使用 `polars`/`duckdb` 快速检查缺失值、重复 ID。
  - 摘要可编写 JSON schema 或 Pydantic 模型做批量验证。
  - 向量文件可通过 `model_dim` 与 `len(embedding)` 比对，防止维度错配。

## 关联文档
- `devdoc/architecture.md`：系统整体模块说明与历史背景。
- `devlog/2025-10-02-summary-storage-docs-plan.md`：本次文档整理的实施记录。
