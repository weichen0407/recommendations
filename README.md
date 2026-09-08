# Topic Workflow LangGraph

这是一个轻量的 LangGraph 主题任务框架，当前流程是：

1. 读取 `.env` 中的 OpenAI 和 Eureka curl 任务配置。
2. 标准化输入主题。
3. `generate_prompt` 节点使用模型把主题扩展成更完整的提示词。
4. `call_curl_task` 节点调用 Eureka conversational 接口，`query` 使用 `generated_prompt`。
5. 从响应中解析 `session_id`，生成 Eureka session 会话链接。
6. `call_curl_task` 继续调用 secure-share/create，解析 `data.share_id`。
7. 输出 Markdown 表格：输入、生成后的 prompt、session 会话链接、最终分享链接和报告元数据。
8. 默认把本次结果追加到 `outputs/topic_workflow_records.csv`，并重新生成 `outputs/topic_workflow_records.md`。

## 安装

```bash
uv sync --dev
```

项目会默认读取当前目录的 `.env`。真实密钥继续放在 `.env`，不要提交到版本库。

如果使用 Claude/Bedrock 这类 OpenAI-compatible endpoint，默认不会传 `temperature`。后端明确要求时再在 `.env` 中设置：

```env
OPENAI_TEMPERATURE=1
```

## 运行

```bash
uv run python -m recommendation_contents.main "新能源汽车电池回收趋势"
```

也可以传入额外上下文：

```bash
uv run python -m recommendation_contents.main \
  "新能源汽车电池回收趋势" \
  --context-json '{"audience":"企业战略分析师","language":"zh-CN"}'
```

安装后也可以直接用脚本入口：

```bash
uv run topic-workflow "新能源汽车电池回收趋势"
```

默认输出 Markdown 表格。需要完整 JSON 状态时：

```bash
uv run topic-workflow "新能源汽车电池回收趋势" --output json --pretty
```

每次运行都会保存一行记录：

```text
outputs/topic_workflow_records.csv
outputs/topic_workflow_records.md
```

记录表包含这些列：

```text
input
generated_prompt
session_url
share_url
title
categories
keywords
description
role
industry
jtbd
date
sub_industry
```

其中 `categories`、`keywords`、`jtbd`、`sub_industry` 在 CSV 中保存为 JSON array 字符串。

`generate_prompt` 节点会要求模型返回结构化 JSON：

```json
{
  "title": "string",
  "categories": ["scout_report"],
  "keywords": ["keyword"],
  "description": "string",
  "role": "innovation_product_strategy",
  "industry": "automotive",
  "jtbd": ["identify_innovation_opportunities"],
  "date": "2026-09-08",
  "sub_industry": ["ev_and_battery_systems"],
  "prompt": "给 Eureka 执行的完整提示词"
}
```

枚举值维护在 `enum_entities.json`。

临时运行、不想保存时：

```bash
uv run topic-workflow "新能源汽车电池回收趋势" --no-save
```

也可以指定保存路径：

```bash
uv run topic-workflow "新能源汽车电池回收趋势" \
  --records-csv outputs/custom_records.csv \
  --records-md outputs/custom_records.md
```

## Eureka curl 配置

`call_curl_task` 会先执行 conversational query：

```bash
curl -sS --url "$EUREKA_QUERY_ENDPOINT" \
  -H "Content-Type: application/json" \
  --data-raw '{"work_project":"","query":"<generated_prompt>","parallel":true,"image_ids":[],"file_ids":[],"skill_list":[],"timezone":"Asia/Shanghai"}'
```

拿到 `session_id` 后继续创建分享：

```bash
curl -sS --url "$EUREKA_SHARE_ENDPOINT" \
  -H "Content-Type: application/json" \
  --data-raw '{"data_id":"<session_id>","data_type":"AGENT_CONVERSATION"}'
```

可用环境变量：

```text
EUREKA_QUERY_ENDPOINT=https://eureka-service.patsnap.com/api/eureka/query/conversational
EUREKA_SHARE_ENDPOINT=https://eureka-service.patsnap.com/eureka/secure-share/create
EUREKA_AUTHORIZATION=
EUREKA_BEARER_TOKEN=
EUREKA_SIGNATURE_ID=
EUREKA_SITE_LANG=CN
EUREKA_EXTRA_HEADERS_JSON={}
EUREKA_TIMEOUT_SECONDS=60
EUREKA_TIMEZONE=Asia/Shanghai
```

`EUREKA_AUTHORIZATION` 可以填完整的 `Bearer ...`；或者只填 `EUREKA_BEARER_TOKEN`，代码会自动补成 `Bearer <token>`。如果没有 Eureka 专用配置，`EUREKA_SIGNATURE_ID` 和 `EUREKA_SITE_LANG` 会分别 fallback 到 `PROFILE_GATE_SIGNATURE_ID`、`PROFILE_GATE_SITE_LANG`。

## 开发检查

```bash
uv run ruff check .
uv run pytest
```

## LangGraph CLI

项目根目录已经包含 `langgraph.json`：

```json
{
  "dependencies": ["."],
  "graphs": {
    "topic_workflow": "./src/recommendation_contents/graph.py:build_graph"
  },
  "env": ".env"
}
```

安装 LangGraph CLI 后，可以在项目根目录继续接 `uv run langgraph dev`、LangGraph Studio 或部署流程。

## 目录

```text
src/recommendation_contents/
  config.py                 # .env 和环境变量配置读取
  graph.py                  # LangGraph 编排入口
  llm.py                    # OpenAI chat model 构造
  main.py                   # CLI 入口
  nodes.py                  # 图节点逻辑
  prompts.py                # 完整提示词生成模板
  records.py                # 每次运行的表格记录落盘
  services/eureka_curl.py   # Eureka 两步 curl 调用
  state.py                  # 图状态定义
```

## 扩展方式

- 新增业务节点：在 `nodes.py` 里加函数，并在 `graph.py` 中注册。
- 更换模型：修改 `.env` 里的 `OPENAI_MODEL`、`OPENAI_BASE_URL`。
- 更换 Eureka 目标：修改 `.env` 里的 `EUREKA_QUERY_ENDPOINT`、`EUREKA_SHARE_ENDPOINT` 和 `EUREKA_EXTRA_HEADERS_JSON`。
# recommendations
