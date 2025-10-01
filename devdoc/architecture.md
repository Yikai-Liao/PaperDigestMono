# 论文推送系统单例化重构

## 功能概览

我的目标是搭建一个自动化的论文推送系统，包含了论文信息收集，筛选，归纳总结，可视化展示，反馈收集这么几个宏观的流程。

具体来讲，就是每天自动从Arxiv爬虫获取最新的论文meta data（包含摘要），然后自动更新一个总的论文 Embedding 池中。根据历史中已有的二分类数据，使用特定算法训练一个输入为Embedding的简单的二分类模型，根据这模型的打分结果，采样出一定数量的论文作为新增的需要展示的论文。然后获取这些论文具体的latex/pdf，转换为markdown形式，然后通过特定的prompt输入给llm api进行摘要，抽取我需要的特定信息（包含多个字段）保存到json中。这个json作为数据存储的媒介，可以快速格式化到各种形式。之后的流程是，格式化为markdown，添加到一个静态博客中，发布到cloudflare。这个静态博客接入了giscus系统，因此我可以通过定期检测github discussion中每个论文对应的评论区中来自用户自己添加的表情，来确定这个新论文的标签是possive 还是negtive，这个数据会被收集起来，用于下一轮的模型训练。

## 前身架构设计

之前版本的代码，被我拆分为了 `ArxivEmbedding` 和 `PaperDigest` 两个仓库，我将其作为submodule 添加到了 `reference` 路径下，以供参考。
也就是说以抽取Embedding为便捷，我将整体流程进行了切割。

另外，这一版方案中，我以huggingface dataset 和github action 为核心进行设计，使用按年份划分的parquet进行存储，将其作为远程的存储核心（因为有免费的无限量公共存储容量）

### ArxivEmbedding

在这个仓库中，分为爬虫和embedding两个主要环节：
* 每日爬虫：每天通过Arxiv API 获取最近两日的论文meta data，将embedding 字段设置为 全0或者nan的vector，合并到当前年份对应的parquet文件中。立即将该文件推动到Hugging Face
* Embedding: 下载当前年份的parquet，过滤出所有含nan或者全0的vector的行，然后使用多个制定的模型进行Embedding批量提取，填充回去之后立即上传。因为这一步是计算密集型，我利用了github aciton public仓库免费的特性，使用大量的matrix进行了任务拆分与并行，使用cpu进行embedding抽取。

### PaperDigest

这个仓库主要包含了静态网页的代码，与论文摘要的代码，使用了openai 的兼容api，并且非常不优雅的，在match到gemini时，单独使用了gemini的genai sdk，并且硬编码了模型的token价格。

tag的抽取不够优雅，目前采取了一种类似 BatchNorm 思想的解决方案，给出抽取tag的规范，然后在将一个批次的所有tag输入给LLM API，让其进行合并，详见一个变体，`reference/PaperDigestAction` 这个submodule。

### 目前发现的问题

#### 计算密集型问题

过度依赖了Github Action，将计算密集任务放在上面，目前已经出现了该仓库的特定任务一直被Queue的情况。因此，我计划将计算密集型任务转移到我本地准备7x24h开机的2060 6G 
笔记本中，使用cron，或者python的schedule进行本地运算。

由于Action的独立性，进行了多次上传，这在本地运行是不必要的，可以将Huggingface的仓库clone到本地使用，每隔几天push一次即可。

#### Tag 重复问题

目前提取的Tag仅仅在Batch内进行LLM去重，效果有限，时间积累下仍然出现了不少重复语义的Tag，需要优化解决方案。

#### 架构文件混乱

虽然我有意识做了文件管理，但是文件多分散到了大量的script中，没有形成体系，调用需要依靠命令行指令串联，无法将其直接作为python class或者类进行调用。

#### AI 调用混乱

目前LLM API使用了openai 库调用，gemini单独使用了google genai，然后使用了pydantic完成结构化输出，但是为了满足一些不支持结构化输出的模型还fallback到了一些更原始的json解析上。而且目前是一个prompt 直接出，完全没有考虑过多轮调用，agent化，应该如何处理，因为完全没有使用相关的agent框架，当然，目前功能还没有agent化的需求。

### 潜在的未实现功能

#### 文章联系发掘

目前仅仅一对一的对文章进行了信息提取，没有将有潜在联系的文章之间建立双链，比如方法有明显关联，甚至需要互相对比的两个文章。

或者一个文章的方法可能改进另一个文章方法的联系。但是这个功能是很难做到，仅仅依靠摘要Embedding的聚类是不够的，必须引入LLM API，但是这个调用很难处理，因为本身涉及到了 O(N^2) 的复杂度。

#### 用户兴趣画像分析

因为用户只有我自己，所有没有协同过滤等方法。我的兴趣很杂，我希望借助这套系统能够帮助我认识到我更深层次的兴趣点，不是说简单的对RL感兴趣，对医疗感兴趣，可能是更深层次一些的，比如对于量化加速感兴趣，对于于性能优化与加速感兴趣，等等吧，这些兴趣点可以是交叉的，各个方向的，我希望能发掘出来一些我自己意识不到的东西，帮我更好地认识我自己，但是这很困难，我暂时不知道怎么做。

## 新架构设计

我的目标是，摆脱大量的Github Action依赖，将其变为一个本地运行的单例（当然，giscus摆脱不了Action依赖）

我的本地部署目标是通过一个 docker （非docker compose）直接可以部署。

Embedding 应该以本地为主，云端用作备份同步，将meta data 与 Embedding 拆分，每个模型每隔年份而的Embedding数据单独保存在一个parquet数据中，以允许未来添加新的Embedding 模型，一定要充分的保留未来添加新模型的接口，例如如何在配置文件中定义这个模型Embedding 使用SentenceTransformer 还是vllm，embedding dim 等，不过或许每个模型单开一个python文件，通过继承特定class的形式是一个更灵活的拓展形式。对于meta data，我认为按规则切分开的csv或许是更好的选择。至于偏好数据，我觉得应该也要拆分出一个独立的数据，毕竟有偏好标注的论文很少，而我们完全可以使用arxiv id 作为主键，这很方便。

本地通过scheduler 来每日爬虫，获取metadata 后，自动依次触发Embedding。Embedding 结束之后，自动触发论文推荐pipeline。

论文推荐pipeline 仍然优先使用latex2json 再转markdown，保留marker 的fallback。

但是摘要后的数据我不打算继续保存为单独的json文件，我认为可以使用按规则，比如年份+月份，拆分的jsonl 来保存，顺序可以按ArxivID 排序，以利于git的增量更新。不过csv也是一种很好的形式。

当然，这种结构化数据的markdown格式化我认为还是可以使用jinja2，基于astro 和 github giscus 和 cloudflare page 的博客方案也可以保留，但是似乎notion + notion api 的非公开化方案也是一种选择，例如直接使用notion数据库，我甚至可以摆脱对giscus的依赖，所有摘要到的文章管理在一个Notion Database中。在notion中展示，推送，反馈，似乎比网页来的更加稳定。







