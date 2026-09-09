# Topic Workflow LangGraph

这是一个轻量的 LangGraph 主题任务框架，当前流程是：

1. 读取 `.env` 中的 OpenAI 和 Eureka curl 任务配置。
2. 标准化输入主题。
3. `generate_prompt` 节点使用模型把主题扩展成更完整的提示词。
4. `check_user_token` 节点在调用 Eureka 前检查 token 是否存在、是否需要 refresh。
5. 如果需要 refresh 且已配置 refresh 能力，进入 `refresh_user_token` 节点；否则继续。
6. `call_curl_task` 节点调用 Eureka conversational 接口，`query` 使用 `generated_prompt`。
7. 从响应中解析 `session_id`，生成 Eureka session 会话链接。
8. `call_curl_task` 继续调用 secure-share/create，解析 `data.share_id`。
9. 输出 Markdown 表格：输入、生成后的 prompt、session 会话链接、最终分享链接和报告元数据。
10. 默认把本次结果追加到 `outputs/topic_workflow_records.csv`，并重新生成 `outputs/topic_workflow_records.md`。

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

如果模型第一次没有返回合法 JSON，`generate_prompt` 会自动做一次 JSON 修复重试。重试仍失败时，才会把原始回复当作 `generated_prompt` 兜底，并在 `errors` 中记录。

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

## 批量读取 cases

如果 `cases` 目录里已经放好了抽取后的 JSON，可以直接读取其中的 `output` 字段作为下游
Eureka curl 输入，不再经过 `generate_prompt`：

```bash
uv run case-workflow cases/500articles.json --limit 3
```

如果运行过程中可能需要你重新从浏览器导入 header，可以开启 401 等待重试。程序遇到 401
后会等待指定秒数，重新读取 `.secrets/eureka_token.json`；只有发现 authorization、
signature 或 cookie 发生变化时，才会重试当前 case：

```bash
uv run case-workflow cases/500articles.json \
  --limit 3 \
  --wait-on-401 10 \
  --retry-on-auth-change \
  --import-clipboard-on-401
```

加上 `--import-clipboard-on-401` 后，程序等待期间会轮询 macOS 剪贴板。你只需要在浏览器里
对 `api/eureka/query/conversational` 请求执行 Copy as cURL，程序会自动导入新的 header。

使用 `--retry-on-auth-change` 时，`case-workflow` 默认进入 access-only 模式，不会先调用
refresh token。需要继续使用 refresh token 分支时，再额外加：

```bash
uv run case-workflow cases/500articles.json \
  --limit 3 \
  --wait-on-401 10 \
  --retry-on-auth-change \
  --use-refresh
```

默认会写入：

```text
outputs/case_workflow_records.csv
outputs/case_workflow_results.json
```

其中 `case_workflow_results.json` 会在每条 case 处理完后立即更新；只有成功生成
session 链接和分享链接后，CSV 才会保存输入、`output` 生成的 prompt 和元数据字段。
如果当前 case 没有生成链接，脚本会停在这一条，不会继续跑下一条。

需要额外生成 Markdown 表时再显式传入：

```bash
uv run case-workflow cases/500articles.json \
  --limit 3 \
  --records-md outputs/case_workflow_records.md
```

### 按行业批量生成

按 `industry` 分组，每个行业最多选择 5 篇未使用内容：

```bash
uv run industry-case-workflow cases/500articles.json --dry-run
```

先把这一波内容取出来、不调用 Eureka：

```bash
uv run industry-case-workflow cases/500articles.json \
  --per-industry 5 \
  --select-only \
  --selection-json cases/industry_case_selection.json
```

正式运行：

```bash
uv run industry-case-workflow cases/500articles.json \
  --per-industry 5 \
  --wait-on-401 60 \
  --retry-on-auth-change \
  --retry-attempts 2 \
  --import-clipboard-on-401
```

推荐把生成和完成验证分开。生成阶段拿到 `session_id`、`session_url`、`share_url` 后就进入下一条；
过一段时间再单独调用 events 接口验证是否完成。`.env` 中的默认 events 接口是：

```env
EUREKA_COMPLETION_ENDPOINT=https://eureka-service.patsnap.com/api/eureka/share/sessions/{session_id}/events
EUREKA_COMPLETION_METHOD=GET
```

生成完成后，单独验证并回填 `isCompleted`、`completionStatus`、`completionError`。
下面这条会同时扫描英文原版和英文 HTML 两个 records CSV：

```bash
uv run eureka-completion \
  --records-csv outputs/industry_outlook_records_en.csv \
  --records-csv outputs/industry_outlook_records_html_en.csv
```

验证逻辑读取 `/events` 返回的最新 `status`：`completed` 会标记
`isCompleted=true`；`running` 会标记 `isCompleted=false` 并保留 running 状态；
`failed` 会去 events 中查找 `type=error` 的 `message`，写入 `completionError`。
如果也想同步 usage 文件，可以额外加上：

```bash
uv run eureka-completion \
  --records-csv outputs/industry_outlook_records_en.csv \
  --records-csv outputs/industry_outlook_records_html_en.csv \
  --usage-csv cases/industry_outlook_usage_en.csv \
  --usage-csv cases/industry_outlook_usage_html_en.csv
```

如果已经先导出了这一波内容，也可以直接用 selection JSON 作为输入：

```bash
uv run industry-case-workflow cases/industry_case_selection.json \
  --per-industry 5 \
  --wait-on-401 60 \
  --retry-on-auth-change \
  --retry-attempts 2 \
  --import-clipboard-on-401
```

脚本会优先读取每条记录里的 `case_index`，所以 usage 表仍然会更新原始 cases 的编号。

脚本会在 `cases` 目录维护 usage 表：

```text
cases/case_usage.csv
```

`status=used` 的 case 后续不会再被选中；失败会标记为 `failed` 并保留错误原因，下次仍可重试。
正式运行时必须先生成当前 case 的 session 链接和分享链接，脚本才会进入下一条。
默认仍只写两个结果文件：

```text
outputs/case_workflow_records.csv
outputs/case_workflow_results.json
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
EUREKA_TOKEN_CHECK_MODE=presence
EUREKA_TOKEN_CACHE=.secrets/eureka_token.json
EUREKA_TOKEN_EXPIRY_SKEW_SECONDS=60
EUREKA_TOKEN_REFRESH_ENABLED=false
EUREKA_TOKEN_REFRESH_CMD=
EUREKA_TOKEN_REFRESH_URL=https://passport.patsnap.com/token/refresh
EUREKA_TOKEN_REFRESH_METHOD=POST
EUREKA_TOKEN_REFRESH_HEADERS_JSON={}
EUREKA_TOKEN_REFRESH_BODY_JSON={"from":"eureka","client_id":"<client_id>","response_type":"TOKEN"}
EUREKA_TOKEN_REFRESH_AUTHORIZATION_PATH=authorization
EUREKA_TOKEN_REFRESH_ACCESS_TOKEN_PATH=access_token
EUREKA_TOKEN_REFRESH_REFRESH_TOKEN_PATH=refresh_token
EUREKA_TOKEN_REFRESH_EXPIRES_AT_PATH=expires_at
EUREKA_TOKEN_REFRESH_EXPIRES_IN_PATH=expires_in
```

`EUREKA_AUTHORIZATION` 可以填完整的 `Bearer ...`；或者只填 `EUREKA_BEARER_TOKEN`，代码会自动补成 `Bearer <token>`。如果没有 Eureka 专用配置，`EUREKA_SIGNATURE_ID` 和 `EUREKA_SITE_LANG` 会分别 fallback 到 `PROFILE_GATE_SIGNATURE_ID`、`PROFILE_GATE_SITE_LANG`。

### Eureka token refresh 骨架

当前 refresh 链路已经接入 LangGraph，但默认不执行真实 refresh：

```text
START
  -> normalize_topic
  -> generate_prompt
  -> check_user_token
  -> refresh_user_token?      # token 缺失/过期且 refresh 已启用时
  -> check_user_token         # refresh 后重新判断
  -> call_curl_task
  -> finalize_result
  -> END
```

使用 passport refresh 接口时，`.env` 里只保留接口和非短期 token 配置：

```bash
EUREKA_AUTHORIZATION=
EUREKA_BEARER_TOKEN=
EUREKA_TOKEN_CACHE=.secrets/eureka_token.json
EUREKA_TOKEN_REFRESH_ENABLED=true
EUREKA_TOKEN_REFRESH_URL=https://passport.patsnap.com/token/refresh
EUREKA_TOKEN_REFRESH_BODY_JSON={"from":"eureka","client_id":"<client_id>","response_type":"TOKEN"}
```

refresh token 和可选 cookie 存在本地 cache 文件，不需要写进 `.env`。推荐用交互式输入，
避免 token 出现在 shell history：

```bash
uv run eureka-token save-refresh --client-id "<client_id>" --prompt-cookie
```

命令会提示输入 refresh token；如果 refresh 接口需要 cookie，再按提示粘贴 cookie。cache
文件默认放在 `.secrets/eureka_token.json`，`.secrets/` 已加入 `.gitignore`。

如果 refresh token 已经保存，只需要后补或更新 cookie：

```bash
uv run eureka-token save-cookie --prompt-cookie
```

如果不走 refresh token，也可以从浏览器复制当前请求的 curl，把短期 access token 和
signature 导入本地 cache。推荐复制 `api/eureka/query/conversational` 这条请求：

```bash
uv run eureka-token import-curl --clipboard
```

也可以通过文件或 stdin 导入：

```bash
uv run eureka-token import-curl --from-file /path/to/query.curl
pbpaste | uv run eureka-token import-curl
```

导入会提取并保存这些字段：

```text
authorization
x-signature-id
x-site-lang
cookie
```

输出只展示脱敏状态，不会打印 token 或 cookie 明文。

查看本地 token 状态：

```bash
uv run eureka-token status
```

手动触发一次 refresh：

```bash
uv run eureka-token refresh
```

新 access token 会写入 `EUREKA_TOKEN_CACHE`，并在当前运行中注入 curl client，不需要再把短期
access token 写进 `.env`。refresh 响应字段会自动兼容 `authorization`、`access_token`、
`accessToken`、`token`、`refresh_token`、`refreshToken`、`expires_in` 等常见命名。

### 浏览器登录态 watcher

如果 refresh token 有效期太短，可以让 watcher 复用一个已登录的浏览器 profile，持续监听
Eureka 页面正常发出的 `api/eureka/query/conversational` 请求，并把最新
`authorization`、`x-signature-id`、`x-site-lang` 和 cookie 同步到
`.secrets/eureka_token.json`：

```bash
uv run eureka-auth-watcher --profile .browser/eureka --interval 60
```

第一次运行会打开一个独立浏览器窗口。先在这个窗口里登录 Eureka，然后手动发一次搜索；
watcher 捕获到请求后会打印脱敏的 `eureka_auth_updated` 事件。后续批处理可以继续用：

```bash
uv run industry-case-workflow cases/industry_case_selection.json \
  --wait-on-401 120 \
  --retry-on-auth-change \
  --retry-attempts 3
```

如果要过夜跑，防止 Mac 睡眠：

```bash
caffeinate -dimsu uv run eureka-auth-watcher \
  --profile .browser/eureka \
  --interval 60 \
  --reload-interval 600
```

watcher 只使用你自己的浏览器登录态；如果 SSO、MFA 或验证码要求重新登录，需要在打开的浏览器里
手动完成。默认使用本机 Google Chrome channel；如果机器没有 Chrome，可以先安装 Playwright
Chromium，再启动时指定空 channel：

```bash
uv run playwright install chromium
uv run eureka-auth-watcher --browser-channel ''
```

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
    "topic_workflow": "recommendation_contents.graph:build_graph"
  },
  "env": ".env"
}
```

安装 LangGraph CLI 后，可以在项目根目录继续接 `uv run langgraph dev`、LangGraph Studio 或部署流程。

## LangSmith

如果要在 LangSmith 里看链路，在 `.env` 中配置：

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=recommendation-contents
```

直接跑 CLI 时，程序会先把 `.env` 注入当前进程环境，因此 LangSmith 可以读取到
`LANGSMITH_*` 配置。为了兼容不同版本的 LangChain，程序也会自动补齐
`LANGCHAIN_TRACING_V2`、`LANGCHAIN_API_KEY`、`LANGCHAIN_PROJECT` 等旧变量名。

LangSmith UI 中的项目通常会在第一次成功上传 trace 后出现；如果运行环境无法访问
`https://api.smith.langchain.com`，本地执行仍会完成，但 UI 里不会看到新项目或链路。

## 目录

```text
src/recommendation_contents/
  config.py                 # .env 和环境变量配置读取
  graph.py                  # LangGraph 编排入口
  llm.py                    # OpenAI chat model 构造
  main.py                   # CLI 入口
  cases_cli.py              # 读取 cases JSON 并批量生成 Eureka 链接
  auth_watcher.py           # 从已登录浏览器同步 Eureka auth header 到本地 cache
  nodes.py                  # 图节点逻辑
  prompts.py                # 完整提示词生成模板
  records.py                # 每次运行的表格记录落盘
  services/eureka_curl.py   # Eureka 两步 curl 调用
  services/eureka_token.py   # Eureka token 检查和 refresh 骨架
  state.py                  # 图状态定义
```

## 扩展方式

- 新增业务节点：在 `nodes.py` 里加函数，并在 `graph.py` 中注册。
- 更换模型：修改 `.env` 里的 `OPENAI_MODEL`、`OPENAI_BASE_URL`。
- 更换 Eureka 目标：修改 `.env` 里的 `EUREKA_QUERY_ENDPOINT`、`EUREKA_SHARE_ENDPOINT` 和 `EUREKA_EXTRA_HEADERS_JSON`。
# recommendations
