# Topic Workflow LangGraph

日常入口为一个端到端图 `topic_workflow`，主图只有三个节点：

```text
输入 → generate_topic → generate_research_prompt → call_curl_task → 结果
```

- `generate_topic`：idea → 完整选题描述、目标受众和受控标签。
- `generate_research_prompt`：基于已校验的选题生成研究执行要求，输出完整的 Eureka prompt；继承原标签。
- `call_curl_task`：内部处理鉴权、提交、分享、完成状态查询与执行记录，返回每条内容的结果。

两个生成阶段都把校验和一次格式修复放在内部，主图不再展示错误分支。`generate_research_prompt` 产出的是供后续研究执行的提示词，不是文章摘要或最终答案。

详细规则见 [端到端流程说明](./docs/workflows/topic-workflow.md)；标签定义见 [第一阶段生成规则](./运营选题_第一阶段生成规则.md)。

## 安装与运行

```bash
uv sync --dev
uv run topic-workflow "芯片互连" --language en --format html --output json --pretty
```

也可以运行 `uv run python -m recommendation_contents.main`。模型及 Eureka 配置沿用项目 `.env`。输入只需要选题，不要求用户画像；默认中文、HTML、1 条内容。使用 `--count 2` 可一次生成两条描述，每条创建独立的 Eureka 任务。

```bash
uv run topic-workflow "芯片互连" --count 2 --language zh-CN --format report
```

`--context-json` 保留兼容入口，目前仅使用其中的 `language` 和 `format`；直接传入同名命令行参数时优先采用命令行值。

正常运行会保存：

```text
outputs/topic_workflow_runs/<generation_id>.json
outputs/topic_workflow_records.csv
outputs/topic_workflow_records.md
```

JSON 保存完整的选题、执行提示词、标签及接口返回结果。CSV 新增 `brief_id`、`generation_id`、`taxonomy_version`、`tags`、`classification`、`assumptions`、`status`，恢复任务时按 `brief_id` 更新同一行。

`--records-csv`、`--records-md` 可指定汇总文件；`--runs-dir` 指定可恢复执行记录目录。`--no-save` 禁用这些本地记录，也就不支持基于本地记录恢复。

## 等待与恢复

curl 节点默认持续查询完成状态，等待上限由 `EUREKA_COMPLETION_TIMEOUT_SECONDS` 控制，默认 600 秒，轮询间隔默认 5 秒。等待上限之外，在途 HTTP 请求还受单次请求超时约束。

超过等待上限会返回 `pending`，不会把报告标为完成。用返回的 `generation_result.generation_id` 继续查询原任务：

```bash
uv run topic-workflow --resume-run-id <generation_id> --output json --pretty
```

恢复会复用描述、提示词和已保存的 session ID；任务完成后不会重复提交。提交响应不明确时返回 `submission_unknown`，需核对远端任务后再决定下一步，程序不自动重发。

退出码：全部任务完成或按 `--stop-after` 正常停止为 0；生成失败、执行失败或等待未完成为 1；命令行参数错误为 2。

## 中间暂停检查

Studio 中点击 **Interrupt**，设置在 `generate_topic` 执行后暂停，检查 `generation_result.briefs`，再点 **Continue**。也可以在 `generate_research_prompt` 执行后暂停，检查 `task_specs[].generated_prompt`，再继续到 curl。

命令行支持把三个阶段分开运行，每一步读取上一步已生成的 JSON：

```bash
uv run topic-workflow "芯片互连" --stop-after generate_topic \
  --stage-output outputs/review/topic.json

uv run topic-workflow --from-stage-file outputs/review/topic.json \
  --stop-after generate_research_prompt --stage-output outputs/review/research-prompts.json

uv run topic-workflow --from-stage-file outputs/review/research-prompts.json --output json --pretty
```

每条命令之间可打开对应 JSON 检查。第一阶段文件中的描述和标签可修改；下一阶段会重新校验，复用已有生成结果。`--from-stage-file` 也接受下方独立第一阶段 CLI 的完整输出。详见 [暂停、编辑和继续](./docs/workflows/topic-workflow.md#7-在两个阶段之间检查)。

## 单独调试第一阶段

第一阶段的 CLI 仍可独立使用，共用主流程的实现。Studio 只注册端到端图，不再单独列出 `content_brief_workflow`。

```bash
uv run content-brief-workflow "芯片互连" --count 2 --language zh-CN \
  --output-file outputs/content_briefs/chip-interconnect.json
uv run content-brief-workflow --schema
uv run content-brief-workflow --validate-file \
  docs/recommendation-tags/v2/example-chip-interconnect-variants.json
```

### 按目标受众三元组批量生成节点 1

下面的命令按当前 role–JTBD 关联覆盖全部 11 个行业：396 个三元组。程序先为每个三元组确定一个固定标签组合，再从同一组合生成 10 个问题，共 3,960 行。所有问题都继承固定的工作视角、行业层级、具体任务、预期产出、主题、问题意图和范围；`keywords` 仍是自由检索词。它只运行 `generate_topic`，不生成研究提示词，也不执行 Eureka：

```bash
uv run profile-topic-node1 --cases-per-tag-set 10 --workers 4 \
  --output-json outputs/profile_topics/node1_topics.json \
  --output-csv outputs/profile_topics/node1_topics.csv
```

运行中断或部分三元组失败后，用相同参数加 `--resume`。程序会跳过已经成功的三元组，继续保存 JSON 和 CSV：

```bash
uv run profile-topic-node1 --cases-per-tag-set 10 --workers 4 --resume
```

运行时每完成一次模型调用都会打印整体进度、成功/失败数、已生成行数、耗时和预计剩余时间，同时立即更新 JSON 和 CSV 检查点：

```text
[42/396 |  10.6%] succeeded=41 failed=1 rows=410 elapsed=08:17 eta=1:09:50 rd_engineer__energy__technical_solutions: succeeded
```

先试一组三元组时，可传入三个筛选条件，并使用单独的预览文件：

```bash
uv run profile-topic-node1 \
  --role rd_engineer \
  --industry electronics_manufacturing \
  --jtbd technical_solutions \
  --role-perspective product_design \
  --jtbd-task solution_comparison \
  --desired-output comparison_matrix \
  --topic-theme ai_impact \
  --question-intent identify_applications \
  --scope-level industry \
  --cases-per-tag-set 10 \
  --output-json outputs/profile_topics/node1_preview.json \
  --output-csv outputs/profile_topics/node1_preview.csv
```

未指定二级枚举时，程序会产生一个可复现的泛行业默认组合；显式参数会覆盖其中对应字段。行业标签只保留 `industry → industry_segment` 两级：选择 `--industry-segment` 时范围会自动变成 `industry_segment`，仍可用 `--scope-level` 显式检查。具体技术、产品、材料和部件名称保存在自由文本 `entities` / `keywords` 中。

机器读取的完整枚举与组合映射在 `src/recommendation_contents/data/content_brief_catalog.json`；固定画像节点 1 的七维输出结构在 `src/recommendation_contents/data/profile_topic.schema.json`。重新导出 Schema：

```bash
uv run content-brief-workflow --profile-schema \
  --output-file src/recommendation_contents/data/profile_topic.schema.json
```

CSV 一行对应一个问题，并保存 `tag_set_id`。同一个 `tag_set_id` 下的问题具有完全相同的七维标签；节点 1 CSV 中的研究提示词、执行状态及链接占位列保持为空。JSON 保留每次模型调用的完整 generation result，供节点 2 批量读取。旧参数 `--cases-per-triple` 仍可作为兼容别名使用。

### 用节点 1 的结果批量生成节点 2

先检查节点 1 的 JSON/CSV；确认问题、描述和标签后，把**完整的节点 1 JSON**作为位置参数传给节点 2，CSV 不能作为恢复输入。完整批次包含 396 个 generation，每个 generation 包含同一标签组合下的 10 个 brief；节点 2 为每个成功的 brief 生成 `research_instructions`、`content_category` 和最终 `generated_prompt`：

```bash
uv run profile-topic-node2 outputs/profile_topics/node1_topics.json \
  --workers 4 \
  --format html \
  --output-json outputs/profile_topics/node2_research_prompts.json \
  --output-csv outputs/profile_topics/node2_research_prompts.csv
```

这个命令只运行 `generate_research_prompt`，**不会调用 Eureka，也不会执行 curl**。因此完成节点 2 后可以停下来，在 JSON 中按 generation 检查完整结构，或在 CSV 中逐行筛选和审阅问题、标签、研究要求与最终 prompt。需要人工维护时编辑 JSON，CSV 只是导出结果。

先确认规模和文件参数，不调用模型：

```bash
uv run profile-topic-node2 outputs/profile_topics/node1_topics.json \
  --workers 4 \
  --format html \
  --output-json outputs/profile_topics/node2_research_prompts.json \
  --output-csv outputs/profile_topics/node2_research_prompts.csv \
  --dry-run
```

运行时每完成一个 generation 都会输出一行进度，包括完成比例、成功/失败数、已生成行数、耗时、ETA、当前 `tag_set_id` 和状态；每次完成后立即原子更新 JSON 与 CSV 检查点：

```text
[42/396 |  10.6%] succeeded=41 failed=1 rows=410 elapsed=08:17 eta=1:09:50 <tag_set_id>: succeeded
```

需要中途停止时按一次 `Ctrl+C`。程序立即写入 `status=paused`，取消尚未开始的调用，然后等待最多 `--workers` 个已经开始的请求返回，并逐个保存结果；等待期间再按一次 `Ctrl+C` 会停止等待并完成最新检查点。Python 线程不能强制终止已经进入模型 provider 的 HTTP 请求，因此进程仍可能等待这些请求按 provider 的网络超时退出。中断命令最终以退出码 130 结束。之后使用**同一个节点 1 数据集和节点 2 输出文件**加 `--resume`，程序会跳过来源未变化的成功项，并继续失败、输入已变化或尚未处理的项：

```bash
uv run profile-topic-node2 outputs/profile_topics/node1_topics.json \
  --workers 4 \
  --format html \
  --output-json outputs/profile_topics/node2_research_prompts.json \
  --output-csv outputs/profile_topics/node2_research_prompts.csv \
  --resume
```

不带 `--resume` 时，如果输出文件已存在，命令会拒绝覆盖。确认要从节点 1 重新生成整个节点 2 批次时使用 `--overwrite`。`--resume` 与 `--overwrite` 不能同时使用。恢复时会检查工作流版本、阶段、taxonomy、来源数据集和格式；每个标签组合另有来源指纹，节点 1 中已修改的组合会自动重新生成。

想把一次运行限制为可审核的小批次，可以用 `--max-batches 20`；完成这 20 个后状态保持 `paused`，再用 `--resume` 继续。也可以用 `--role`、`--industry`、`--jtbd` 或可重复的 `--tag-set-id` 只处理选中的组合：

```bash
uv run profile-topic-node2 outputs/profile_topics/node1_topics.json \
  --tag-set-id <tag_set_id> \
  --max-batches 20 \
  --resume
```

Node 2 JSON 支持维护成功结果：编辑对应 `task_specs[]` 的 `content_category` 或 `research_instructions`，再执行 `--resume`。程序会校验这两个结构化字段，并重新组装 `generated_prompt`，不会再次调用模型。不要直接维护 `generated_prompt`，因为它会根据结构化字段重建。要让模型重新生成已成功的选中组合，首次使用筛选参数配合 `--resume --regenerate-selected`；如果同时用 `--max-batches` 分段，后续继续时只用 `--resume`，否则会再次把已重生成的选中项重置为待处理。

`--format html` 会在最终 prompt 中加入 HTML artifact 指令；`--format report` 会要求 Markdown 报告。新批次默认 `html`；恢复时不传 `--format` 会沿用检查点中的格式，两种格式不能在同一个恢复批次中混用。节点 2 JSON 为后续批量执行节点 3 保留机器结构；当前可以直接从 CSV 的 `generated_prompt` 列抽样并手动执行 curl。

## 推荐内容批量生成

当前推荐内容流程先假设已经有一个批次 `subject.json`。它保存每篇待生成内容的
`title`、`output`、`industry`、`sub_industry`、`content_category`、`categories`、
`keywords`、`role`、`jtbd` 等字段。后续可以扩展成由 agent 自动生成
`subject.json`，再进入同一套生成和验证命令。

批次目录按两层日期组织：

```text
outputs/
  0909/
    090916/
      report/
      html/
    090922/
      report/
  0910/
    091010/
      subject.csv
      subject.json
      subject_distribution_preview.csv
      report/
      html/
      plg-rd-case-default-us.json
  recommend-content-counts.csv
```

第一层是日期，例如 `0910`；第二层是批次时间，例如 `091010` 表示 9 月 10 日 10 点。
`subject.csv` 给人检查，`subject.json` 给脚本运行。最终产品文件
`plg-rd-case-default-us.json` 里的 list 字段必须是真 JSON 数组，不能是转义后的字符串。

### 运行 report

当前 `091010` 批次一共有 144 条 subject。跑完整 report：

```bash
uv run case-workflow outputs/0910/091010/subject.json \
  --mode report \
  --limit 144 \
  --wait-on-401 60 \
  --retry-on-auth-change \
  --retry-attempts 2 \
  --import-clipboard-on-401
```

`--mode report` 会使用 `subject.json` 中的基础 `output` 作为 prompt，并默认写入：

```text
outputs/0910/091010/report/recommend_content_091010_report_records.csv
/tmp/recommend_content_091010_report_results.json
```

### 运行 HTML

跑完整 HTML：

```bash
uv run case-workflow outputs/0910/091010/subject.json \
  --mode html \
  --limit 144 \
  --wait-on-401 60 \
  --retry-on-auth-change \
  --retry-attempts 2 \
  --import-clipboard-on-401
```

`--mode html` 会在 prompt 后追加：

```text
Use artifact-generator to generate the final result as HTML.
```

并默认写入：

```text
outputs/0910/091010/html/recommend_content_091010_html_records.csv
/tmp/recommend_content_091010_html_results.json
```

如果只想试跑前 3 条，把 `--limit 144` 改成 `--limit 3`。如果不传 `--limit`，默认只跑
3 条。

生成命令默认会在终端输出进度日志，例如：

```text
[1/144] start case-workflow case_index=0 mode=report title="..."
[1/144] done case-workflow case_index=0 mode=report title="..." status=ok session=yes share=yes
```

如果不想显示进度，可以加 `--no-progress`。如果使用 `--output json`，默认不会打印进度；
需要同时看进度时，可以额外加 `--progress`。

生成阶段有一个硬规则：当前条必须成功拿到 `session_url` 和 `share_url`，脚本才会写入
records CSV 并进入下一条。如果当前条没有生成 URL，脚本会停在当前条，不会继续跑后面的内容。

### 401 和 token 更新

如果运行过程中 token 过期，可以开启 401 等待重试。脚本遇到 401 后会等待指定秒数，
并重新读取 `.secrets/eureka_token.json`；只有发现 authorization、signature 或 cookie
发生变化时，才会重试当前 case。

加上 `--import-clipboard-on-401` 后，等待期间会轮询 macOS 剪贴板。你只需要在浏览器里对
`api/eureka/query/conversational` 请求执行 Copy as cURL，脚本会自动导入新的 header。

使用 `--retry-on-auth-change` 时，`case-workflow` 默认进入 access-only 模式，不会先调用
refresh token。需要继续使用 refresh token 分支时，再额外加：

```bash
uv run case-workflow outputs/0910/091010/subject.json \
  --mode report \
  --limit 144 \
  --wait-on-401 60 \
  --retry-on-auth-change \
  --retry-attempts 2 \
  --import-clipboard-on-401 \
  --use-refresh
```

### 完成状态验证

推荐把“生成 URL”和“验证内容是否完成”分开。生成阶段只负责拿到 `session_url` 和
`share_url`；过一段时间后，再单独调用 events 接口验证 session 是否完成。

验证 report：

```bash
uv run eureka-completion \
  --records-csv outputs/0910/091010/report/recommend_content_091010_report_records.csv
```

验证 HTML：

```bash
uv run eureka-completion \
  --records-csv outputs/0910/091010/html/recommend_content_091010_html_records.csv
```

同时验证两份：

```bash
uv run eureka-completion \
  --records-csv outputs/0910/091010/report/recommend_content_091010_report_records.csv \
  --records-csv outputs/0910/091010/html/recommend_content_091010_html_records.csv
```

默认会跳过已经 `isCompleted=true` 的行。如果想全部重新检查，加 `--all`：

```bash
uv run eureka-completion \
  --records-csv outputs/0910/091010/report/recommend_content_091010_report_records.csv \
  --all
```

如果单个 session 的 events 很长，可以用 `--max-pages` 调整最多翻页次数，默认是 20：

```bash
uv run eureka-completion \
  --records-csv outputs/0910/091010/report/recommend_content_091010_report_records.csv \
  --max-pages 50
```

验证命令也会默认输出进度日志，例如：

```text
[1/144] checking target=recommend_content_091010_report_records.csv case_index=0 session=sess_xxx title="..."
[1/144] done target=recommend_content_091010_report_records.csv case_index=0 session=sess_xxx title="..." status=completed isCompleted=true pages=2
```

同样可以用 `--no-progress` 关闭，或在 `--output json` 时额外加 `--progress` 打开。

completion endpoint 由 `.env` 控制。当前脚本默认按这个格式请求：

```env
EUREKA_COMPLETION_ENDPOINT=https://eureka-service.patsnap.com/api/eureka/share/sessions/{session_id}/events
EUREKA_COMPLETION_METHOD=POST
EUREKA_COMPLETION_BODY_JSON={"limit":500}
```

如果浏览器里真实 events 请求不是这个 URL 或不是 POST，需要把 `.env` 改成浏览器里那条请求的
真实 endpoint、method 和 body。否则会出现 HTTP 405 或一直判断不准。

验证逻辑是：

1. 从 records CSV 的 `session_url` 里提取 `sess_...`。
2. 第一次请求 events URL，body 只带 `limit=500`，不带 cursor。
3. 如果返回 `has_more=true`，读取这一页的 `stream_cursor`。
4. 用 `{"cursor":"<stream_cursor>","limit":500}` 再请求下一页 events。
5. 重复第 3-4 步，直到最后一页返回 `has_more=false`。
6. 如果中间 HTTP 失败、没有 `stream_cursor`、cursor 重复或超过 `--max-pages`，写入
   `completionStatus=http_error`，`isCompleted=false`。
7. 到达 `has_more=false` 的最后一页后，优先用最后一页顶层 `status` 或 `state` 判断。
8. 如果最后一页顶层没有状态，再扫描合并后的全部 `events`，取最后一个 `status` 或 `state`。
9. `completed`、`complete`、`done`、`success` 等会写成 `isCompleted=true`。
10. `failed`、`error` 等会写成 `isCompleted=false`，并从全部 events 中的 `type=error` 提取
   `message` 写入 `completionError`。
11. `running`、`pending`、`processing` 等会写成 `isCompleted=false`，保留
   `completionStatus`。

如果你在浏览器里看到的响应类似：

```json
{
  "events": [],
  "status": "completed",
  "terminal": true
}
```

脚本会先继续用 `stream_cursor` 翻到 `has_more=false` 的最后一页，再用最后一页的
`status=completed` 标记 `isCompleted=true`。如果实际没有标记成功，优先检查 `.env` 里的
`EUREKA_COMPLETION_ENDPOINT` 和 `EUREKA_COMPLETION_METHOD` 是否和浏览器里看到的 events
请求一致。

### 生成产品 JSON

产品侧默认推荐内容文件放在当前格式目录下：

```text
outputs/0910/091010/report/plg-rd-case-default-us.json
outputs/0910/091010/html/plg-rd-case-default-us.json
```

它通常从完成后的 records CSV 转换得到。转换时需要：

- `session_url` 改成 `session_id`，只保留 `sess_...`。
- `share_url` 改成 `share_id`，只保留 `id=` 到 `&from` 中间的值。
- `format` 标记内容格式，值为 `report` 或 `html`。
- `categories`、`keywords`、`jtbd`、`sub_industry` 这类 list 字段写成真实 JSON 数组。

从 records CSV 生成产品 JSON：

```bash
uv run records-to-plg outputs/0910/091017/html/recommend_content_091017_html_records.csv \
  --update-records-format
```

脚本会从路径自动识别 `html` 或 `report`。如果路径里没有格式信息，可以手动指定：

```bash
uv run records-to-plg path/to/records.csv --format report --update-records-format
```

### 旧 cases 输入

通用 `case-workflow` 仍然可以直接读取已有 cases JSON：

```bash
uv run case-workflow cases/500articles.json --limit 3
```

`industry-case-workflow` 也仍然可以按 `industry` 分组选择未使用内容：

```bash
uv run industry-case-workflow cases/500articles.json --dry-run
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

### Eureka token refresh

主图的 `call_curl_task` 内部负责 token 检查和必要时的刷新，不增加额外图节点。默认不执行真实 refresh：

```text
检查 token → 必要且可用时刷新一次 → 提交任务 → 分享与完成查询
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
uv run case-workflow outputs/0910/091010/subject.json \
  --mode report \
  --limit 144 \
  --wait-on-401 120 \
  --retry-on-auth-change \
  --retry-attempts 3 \
  --import-clipboard-on-401
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

新增 graph 后，如果运行中的服务仍只显示旧图，需要在启动该服务的终端重启
`uv run langgraph dev`，然后刷新
[本地 Studio](https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024)，
在 graph / assistant 选择器中选择 `topic_workflow`。

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

打开方式：

1. 浏览器打开 [https://smith.langchain.com](https://smith.langchain.com)。
2. 登录和 `LANGSMITH_API_KEY` 对应的 workspace。
3. 进入 `Tracing` / `Projects`。
4. 选择 `.env` 里配置的项目名，例如 `recommendation-contents`。
5. 打开 `topic_workflow` run，查看 `generate_topic`、`generate_research_prompt`、`call_curl_task`。
   单独调试第一阶段时，CLI run 名仍为 `content_brief_workflow`，内部只有 `generate_topic`。
   Studio 可在运行前查看结构，Tracing 需运行并上传记录后才可查看。

如果你想直接用 URL 打开项目，可以先进入 LangSmith 后在项目列表里点
`recommendation-contents`。项目 URL 和 workspace 有关，第一次以页面里显示的真实地址为准。

LangSmith UI 中的项目通常会在第一次成功上传 trace 后出现；如果运行环境无法访问
`https://api.smith.langchain.com`，本地执行仍会完成，但 UI 里不会看到新项目或链路。

## 目录

```text
src/recommendation_contents/
  config.py                 # .env 和环境变量配置读取
  graph.py                  # 三节点主图和状态定义
  brief_generation.py       # 第一阶段：idea → 选题
  brief_schema.py           # 第一阶段 schema 和枚举组合校验
  brief_prompts.py          # 第一阶段生成与修复提示词
  brief_graph.py            # 第一阶段独立调试入口
  brief_cli.py              # 第一阶段 CLI、schema 导出和离线校验
  profile_topic_cli.py      # 按画像与标签组合批量运行节点 1
  profile_research_prompt_cli.py  # 读取节点 1 检查点，批量运行节点 2
  research_prompt_generation.py  # 第二阶段：选题 → 研究执行提示词
  summary_generation.py     # 旧导入路径的兼容包装
  workflow_stages.py        # 暂停检查后的输入校验
  workflow_execution.py     # Eureka 执行、轮询和恢复
  llm.py                    # OpenAI chat model 构造
  main.py                   # CLI 入口
  cases_cli.py              # 读取 cases JSON 并批量生成 Eureka 链接
  auth_watcher.py           # 从已登录浏览器同步 Eureka auth header 到本地 cache
  nodes.py                  # 公共鉴权与批处理辅助操作
  records.py                # 每次运行的表格记录落盘
  services/eureka_curl.py    # Eureka curl 请求
  services/eureka_token.py   # Eureka token 检查和刷新
  state.py                  # 兼容批处理工具的状态定义
  data/content_brief_catalog.json  # 当前标签定义与映射
  data/profile_topic.schema.json   # 固定画像节点 1 的响应结构
```

根目录的 XLSX 和行业角色分析 MD 是规则来源；`cases/` 保存批处理输入和原始字段映射；`docs/` 保存当前规则契约与示例；`outputs/`、`visualization/` 保存业务产出和分析数据。

`.langgraph_api/` 是本机 Studio 的运行状态与检查点，保留本地文件但不纳入版本控制。`.venv/`、`__pycache__/`、测试和 lint 缓存同样不纳入版本控制。旧规则和已删除实现可从 Git 历史查看，工作区只保留当前版本。

调整生成行为时，分别修改 `brief_prompts.py` / `research_prompt_generation.py`；图的编排位于 `graph.py`。模型和 Eureka 接口仍通过 `.env` 中的 `OPENAI_*`、`EUREKA_*` 配置。
