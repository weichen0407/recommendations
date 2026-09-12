# 端到端推荐内容流程

更新日期：2026-09-12。执行记录版本：`2.0.0`。标签目录使用 `2.2.0`。

```text
输入 → generate_topic → generate_research_prompt → call_curl_task → 结果
```

Studio 只注册 `topic_workflow`。图中没有额外的校验、修复、鉴权或完成包装节点。前两个节点各负责一个生成阶段，第三个节点执行 Eureka 任务。

## 1. 输入

```json
{"topic": "芯片互连", "language": "en", "count": 1, "format": "html"}
```

`topic` 是运营主题词；也支持 `idea` 作为别名，提供 `idea` 时优先采用。无需用户资料。默认 `language=zh-CN`、`count=1`、`format=html`；支持 `en`、1–10 条选题以及 `report` 格式。`request_context` 保留兼容入口，仅取其中的语言和格式。

## 2. generate_topic：生成选题

调用 [第一阶段公共实现](../../src/recommendation_contents/brief_generation.py)，依照 [运营选题规则](../../运营选题_第一阶段生成规则.md) 生成：

- 完整选题描述及标题；
- 目标受众 role、industry、JTBD；
- 工作视角、细分行业、具体任务和预期产出；
- 分类理由、范围假设，以及保存具体公司、产品、技术、材料和部件名称的自由文本实体与关键词。

输出保存在 `generation_result.briefs`。一个生成请求可以返回多条选题，每条有独立 `brief_id`。

输入检查、枚举及组合校验、一次修复都在节点内部完成。无效输入不调用模型；生成不通过则抛出带阶段名称的错误，后续节点不执行。普通路径只调用一次模型。

## 3. generate_research_prompt：生成研究执行提示词

输入是上一节点完整、已校验的选题，不再次从原始主题词重新选题。该节点生成供后续研究任务执行的提示词，不生成文章摘要、最终答案或报告正文。

第二次模型调用返回：

```json
{
  "research_prompts": [
    {
      "brief_id": "与输入一致的 ID",
      "content_category": "competitor_analysis",
      "research_instructions": "研究重点、分析步骤、报告结构与证据要求。"
    }
  ]
}
```

响应需覆盖全部输入 ID，每条恰好一次。不能加入 role、industry、JTBD 或 tags 覆盖字段。分类 `content_category` 沿用现有内容类别目录，与第一阶段的 `desired_output` 含义不同。

生成规则：

1. 按第一阶段的主要任务设计研究重点和成果结构，不扩展成无关的全景报告。
2. 继承实体、范围假设及目标受众。模型不自行重新分类，也不声称这些是实际用户已填写的资料。
3. 补充适当的证据要求、比较维度、限制和待核实事项；不输出研究结论，不编造项目材料、市场数据或专利结果。
4. 按指定语言生成研究指令。格式和固定分类信息由程序统一装配，不交给模型决定。
5. 响应字段、类别或 ID 校验失败时，最多修复一次；仍失败则停止，原始响应不会兜底成执行 prompt。

程序把模型生成的研究要求与原始描述、固定标签、关键词、假设、语言要求组合为 `task_specs[].generated_prompt`。HTML 模式固定添加：

```text
Use artifact-generator to generate the final result as HTML.
```

report 模式要求 Markdown 报告。这是执行指令，是否实际产出相应文件取决于 Eureka 的执行结果；本流程没有凭空新增其工具能力。

代码与契约：[research_prompt_generation.py](../../src/recommendation_contents/research_prompt_generation.py)、[响应 schema](./research-prompt-response.schema.json)。`summary_generation.py` 和 `summary-response.schema.json` 仅保留旧导入名与旧文件路径，不是新的规范入口；模型响应根字段已经统一迁移为 `research_prompts`，旧的 `summaries` 响应不再接受。

## 4. call_curl_task：执行并查询结果

对每条 task spec 分别执行以下内部步骤：

1. 检查 token，必要且可用时刷新一次。
2. 在本地执行记录中写入 `submitting`，再把 `generated_prompt` 原样作为 Eureka `query` 提交。
3. 获得 `session_id` 后立即保存，创建分享链接并保存返回 ID。
4. 查询会话完成状态；响应有分页时读取完整事件页。单个工具完成或 HTTP 成功标志不代表整个报告完成。
5. 完成后返回会话／分享链接、完成状态及 `completion_response`。该字段保存接口返回的结果数据；当前不单独下载 HTML 文件。

默认等待 600 秒，间隔 5 秒，由 `EUREKA_COMPLETION_TIMEOUT_SECONDS` 和 `EUREKA_COMPLETION_POLL_INTERVAL_SECONDS` 控制。每个在途 HTTP 请求另受单次超时约束。到达等待上限返回 `pending`，保留会话以便继续查询。

本节点不调用上游生成模型；Eureka 内部执行任务的模型调用由其自身控制。多条选题共用前两个阶段的两个正常生成调用，curl 则逐条提交和查询。

## 5. 结果与恢复

`results` 按每条 `brief_id` 返回独立状态：

| 状态 | 含义 |
| --- | --- |
| `completed` | 会话完成状态已经确认，结果数据保存在记录中。 |
| `pending` | 等待超时或查询暂时失败，可继续查询原会话。 |
| `submitted` | 已提交，但没有配置完成查询接口。 |
| `needs_auth` | 凭据缺失或被拒绝；修正鉴权后可恢复。 |
| `failed` | 明确提交失败或报告任务失败。 |
| `submission_unknown` | 提交响应不明确或提交中进程中断；需核对远端是否已有任务，程序不会自动重发。 |

分享创建不成功时保留 `share_status` 和会话链接；`completed` 判断的是会话是否完成，不保证分享链接创建成功。最终产物内容可通过会话、已成功创建的分享链接及接口返回数据检查。

批次 `status=succeeded` 表示所有会话均完成；部分或全部仍待查询时为 `pending`；存在明确失败、鉴权缺失或不确定提交时为 `failed`，具体情况查看每条结果。

执行记录保存在 `outputs/topic_workflow_runs/<generation_id>.json`，含完整选题、提示词和任务状态。写入使用原子替换；同一 run 加独占锁，防止同时恢复而重复提交。

恢复输入示例：

```json
{"resume_run_id": "之前返回的 generation_result.generation_id"}
```

恢复经过同样的三个节点，但前两个读取已保存且校验通过的结果，不重新调用模型。已有会话继续查询；已完成会话不重新提交。`submitting` 遗留状态视为提交结果不确定，不假定请求未到达服务端。

CSV 按 `brief_id` 更新同一内容的状态，保留 `generation_id`、目录版本、受众、四项基础标签、分类依据和假设，避免恢复操作被计为新增内容。

## 6. 调试与兼容

- 主流程入口为 `topic-workflow` / `recommendation_contents.main`；Studio 选择 `topic_workflow`。
- 第一阶段的 `content-brief-workflow` 命令保留，与主流程共享生成逻辑；不再在 Studio 注册第二张图。
- 现有 `case-workflow` 仍消费已经准备好的执行 prompt，原批处理工具不自动改为两阶段生成。
- LangSmith 中模型调用异常或生成校验失败会停在对应生成节点；curl 的业务状态同时保留在 `results`，需查看该状态，不能仅凭图运行返回就认定所有报告成功。
- 修改后需让运行中的 LangGraph 服务重新加载配置；如果仍看到旧图列表，应重启服务并刷新 Studio。

验证采用模型和 Eureka 接口替身，覆盖两个生成阶段、内部修复、字段继承、批量任务、完成状态、分页和恢复。未据此宣称真实模型输出质量或真实报告生成已验证。

## 7. 在两个阶段之间检查

第一阶段结果已经通过 graph state 自动成为第二阶段输入，不需要人工复制描述。`generation_result` 是完整的第一阶段结果，`generation_result.briefs` 保存描述、画像归类和标签；第二阶段读取这份结构化数据。`task_specs[].generated_prompt` 是第三阶段实际提交的完整提示词；顶层 `generated_prompt` 仅展示第一条。

### Studio 中暂停

在 Studio 的 Graph 模式选择 `topic_workflow`，点击 **Interrupt**，设置在 `generate_topic` **After** 暂停，再提交主题词。执行会停在第一阶段之后，展开 `generation_result.briefs` 检查内容，点击线程日志中的 **Continue** 才会继续。

如果还需要检查执行提示词，同时设置 `generate_research_prompt` **After**（或 `call_curl_task` **Before**）断点。这样第二次继续之前不会提交 Eureka 任务。断点要在开始运行前设置，暂停不影响已经提交的外部任务。

需要修改第一阶段时，在对应节点旁点 **Edit node state**，修改完整的 `generation_result` 后点击 **Fork**，从该检查点创建后续运行。第二阶段入口会重新校验枚举及标签组合；失败时不会调用模型。只检查时使用 Continue 即可。操作依据：[Studio 官方说明](https://docs.langchain.com/langsmith/use-studio)。

### 文件分阶段运行

第一步，只生成选题并保存可编辑的 JSON：

```bash
uv run topic-workflow "芯片互连" --stop-after generate_topic \
  --stage-output outputs/review/topic.json
```

检查或修改 `outputs/review/topic.json` 中的 `generation_result.briefs` 后，只生成第二阶段提示词：

```bash
uv run topic-workflow --from-stage-file outputs/review/topic.json \
  --stop-after generate_research_prompt \
  --stage-output outputs/review/research-prompts.json
```

检查 `outputs/review/research-prompts.json` 中的 `task_specs[].generated_prompt` 后执行：

```bash
uv run topic-workflow --from-stage-file outputs/review/research-prompts.json \
  --output json --pretty
```

三条命令分别调用第一阶段模型、第二阶段模型、Eureka；后续命令复用已有结果。也可以省略第二条命令的 `--stop-after` 和 `--stage-output`，直接从选题执行到最终结果。图仍为三个节点，导入已有结果时相应生成节点只校验并传递数据。

- `--stop-after` 是本次命令的正常停止，退出码为 0，输出 `status=paused`。不会执行下游节点或写入报告汇总表。
- 旧参数值 `--stop-after generate_summary` 暂时仍可使用，但程序会规范化为 `generate_research_prompt`；新脚本和文档应统一使用新名称。
- 不指定 `--stage-output` 时保存到 `outputs/workflow_stages/<generation_id>.<node>.json`。即使指定 `--no-save`，显式要求的阶段快照仍会保存；`--no-save` 只关闭执行日志和结果汇总。
- `--from-stage-file` 也接受 `content-brief-workflow --output-file` 生成的完整第一阶段 JSON；只复制一句描述或单独 `briefs` 数组不够。它保留文件中的语言、条数和 ID。
- 默认沿用快照的 `format`；第一阶段文件可以用 `--format` 选择最终格式。导入已有 `task_specs` 时，格式必须与其一致。
- 修改选题内容后，应使用第一阶段文件重新生成第二阶段。如果从第二阶段文件改选题，先清空 `task_specs`，再用第二条命令重新生成提示词。不要单独修改顶层 `generated_prompt`：它不是实际提交源。执行前会核对 `task_specs` 中的描述、标签、语言和完整提示词是否一致。
- 第三阶段开始后，继续查询原任务应使用 `--resume-run-id`。相同 ID 对应已保存的执行内容，不能用修改后的提示词覆盖它；若要生成新内容，从新主题请求开始。

CLI 暂停时使用进程内 checkpointer，到下一次命令通过 JSON 导入继续；这不是跨进程保存的 LangGraph thread。Studio 的检查点由 LangGraph 服务管理。在 Python 同一进程中，可传入 `checkpointer`，用同一 `thread_id` 调用 `graph.invoke(..., interrupt_after=["generate_topic"])`，再用 `graph.invoke(None, config=同一配置)` 继续；静态断点不使用 `Command(resume=...)`。参见 [LangGraph 断点说明](https://docs.langchain.com/oss/python/langgraph/interrupts)。

如需通过 Studio/API 导入已有结果，新输入可设置 `{"stage_result": 完整阶段JSON}`；内容结构与 `--from-stage-file` 相同。默认未设置断点、也未指定 `--stop-after` 时，流程仍会自动执行到底。

## 8. 画像标签批次的节点 2

`profile-topic-node1` 的输出是批次容器，顶层 `generations[]` 中每一项代表一个 role–industry–JTBD 与七维标签组合，一项通常包含 10 个 brief。它与单个 `topic-workflow --stop-after generate_topic` 快照的外层结构不同，因此使用专用的 `profile-topic-node2` 命令批量运行第二阶段：

```bash
uv run profile-topic-node2 outputs/profile_topics/node1_topics.json \
  --workers 4 \
  --format html \
  --output-json outputs/profile_topics/node2_research_prompts.json \
  --output-csv outputs/profile_topics/node2_research_prompts.csv
```

处理单位是 generation/tag set。一个正常 generation 触发一次第二阶段模型调用，同时为其中全部 brief 返回结果；如果响应校验失败，节点内部最多再调用一次进行格式修复。节点 1 中标记失败的 generation 不进入可执行范围；成功项如果缺少 briefs 或不符合当前 schema/标签规则，命令会在调用模型前报错。

每个成功 brief 的节点 2 产物包含：

| 字段 | 含义 |
| --- | --- |
| `brief_id` | 继承节点 1，用于稳定关联同一个问题。 |
| `research_instructions` | 模型生成的研究重点、分析步骤、结构与证据要求。 |
| `content_category` | 第二阶段受控内容类别。 |
| `generated_prompt` | 节点 3 可以原样提交的完整 prompt。 |
| `brief` | 节点 1 的问题、描述、受众、标签、实体、关键词和假设。 |
| `language` / `format` | 生成语言和最终交付格式。 |

批次 JSON 使用 `workflow_version=profile-topic-node2/1.0.0`、`stage=generate_research_prompt`，保留 generation 级状态、错误和完整 task specs，是恢复和维护的数据源。CSV 一行对应一个 brief，仅用于运营抽样和导出；恢复时不读取 CSV，下一次保存还会从 JSON 重新生成 CSV。节点 2 只生成 prompt，保持执行状态、session URL 和 share URL 为空，不初始化或调用 Eureka。

顶层 `status` 在写入过程中为 `running`；仍有待处理项或主动停止时为 `paused`；全部处理完成但存在失败项时为 `failed`；所有可执行项成功时为 `succeeded`。`progress` 保存 eligible、成功、失败、待处理 tag set 数及成功行数，`last_run` 保存本次筛选、调度和完成统计。

### 8.1 预检、进度和停止

在正式调用模型前可运行 `--dry-run`，检查输入批次、可执行与待调度 generation 数、格式和输出路径：

```bash
uv run profile-topic-node2 outputs/profile_topics/node1_topics.json \
  --workers 4 \
  --format html \
  --output-json outputs/profile_topics/node2_research_prompts.json \
  --output-csv outputs/profile_topics/node2_research_prompts.csv \
  --dry-run
```

正式运行时，每完成一个 generation 就输出一次 durable progress，并立即以原子替换方式更新 JSON 和 CSV：

```text
[42/396 |  10.6%] succeeded=41 failed=1 rows=410 elapsed=08:17 eta=1:09:50 <tag_set_id>: succeeded
```

终端按一次 `Ctrl+C` 可以安全停止批次。程序立即保存 `status=paused`，取消尚未开始的 future，然后等待最多 `--workers` 个已经开始的 provider 请求返回，并逐个写入检查点。等待期间再按一次 `Ctrl+C` 会停止等待并完成最新检查点；Python 线程不能强制终止已进入模型 provider 的 HTTP 请求，因此进程仍可能等待这些请求按 provider 的网络超时退出。中断命令最终以退出码 130 结束。以输出 JSON 为准，中断时仍未落盘的调用会在下次恢复时重新处理。节点 2 没有提交外部 Eureka 任务，因此重复处理这一项不会创建报告或会话。

正常完成、`--dry-run` 或达到 `--max-batches` 的主动检查点返回 0；本次有生成失败返回 1；命令行或输入校验错误返回 2。

如果希望每次主动停在固定数量的模型批次后检查，可用 `--max-batches`：

```bash
uv run profile-topic-node2 outputs/profile_topics/node1_topics.json \
  --max-batches 20

uv run profile-topic-node2 outputs/profile_topics/node1_topics.json \
  --max-batches 20 --resume
```

它在筛选及恢复检查后最多调度 20 个待处理 tag set，完成后保留 `status=paused`。第一条命令建立检查点，第二条命令继续处理后续 20 个。

### 8.2 跨进程继续

使用同一个节点 1 数据集和节点 2 JSON 输出路径，加 `--resume`。CSV 不能单独作为恢复数据源；如果只剩 CSV，命令会拒绝续跑：

```bash
uv run profile-topic-node2 outputs/profile_topics/node1_topics.json \
  --workers 4 \
  --format html \
  --output-json outputs/profile_topics/node2_research_prompts.json \
  --output-csv outputs/profile_topics/node2_research_prompts.csv \
  --resume
```

恢复会跳过来源内容未变化的成功 generation，并继续失败、尚未处理或来源指纹已变化的项。同一个节点 1 数据集后续增加成功 generation 或修正原 generation 时可以继续使用原检查点；数据集身份由节点 1 的工作流版本、`created_at` 和 taxonomy 确定，每个 generation 另有内容指纹。换成另一个数据集、taxonomy 或显式传入不同格式时，命令会拒绝续跑。恢复时省略 `--format` 会沿用已保存格式；并发数 `--workers` 只影响本次调度，可以按模型限流调整。

可以按画像或精确 tag set 缩小本次处理范围；`--tag-set-id` 可以重复：

```bash
uv run profile-topic-node2 outputs/profile_topics/node1_topics.json \
  --role rd_engineer \
  --industry energy \
  --jtbd technical_solutions \
  --resume
```

如果要精确指定组合，改用 `--tag-set-id <tag_set_id>`；重复参数即可选择多个 ID。画像筛选与 tag set 筛选同时提供时按交集处理。

不带 `--resume` 时，已有输出文件会触发错误，避免误覆盖。只有确认放弃现有节点 2 结果并从头生成时才使用 `--overwrite`；它不能与 `--resume` 同时使用：

```bash
uv run profile-topic-node2 outputs/profile_topics/node1_topics.json \
  --workers 4 \
  --format html \
  --output-json outputs/profile_topics/node2_research_prompts.json \
  --output-csv outputs/profile_topics/node2_research_prompts.csv \
  --overwrite
```

### 8.3 审阅和维护

节点 1 是问题和标签的来源。如果修改节点 1 的问题、描述、受众或标签，同一数据集内对应 generation 的来源指纹会变化；下一次 `--resume` 会只重新生成这些变化项。不要修改 Node 2 中复制的 `brief`，它不是输入来源。

人工维护必须编辑 Node 2 JSON 中对应的 `generations[].task_specs[]`，只修改 `content_category` 或 `research_instructions`。再次运行 `--resume` 时，程序会校验这些结构化字段，按当前 brief、语言和格式重新组装 `generated_prompt`，不会为仍然成功且来源未变化的项调用模型。不要直接编辑 `generated_prompt`，因为恢复时它会被结构化字段重建；不要编辑 CSV，下一次导出会覆盖它。

要让模型重新生成已经成功的组合，使用筛选条件配合 `--resume --regenerate-selected`：

```bash
uv run profile-topic-node2 outputs/profile_topics/node1_topics.json \
  --tag-set-id <tag_set_id> \
  --resume \
  --regenerate-selected
```

如果同时使用 `--max-batches` 分段重生成，第一次运行使用 `--regenerate-selected` 建立新的待处理集合，后续批次只使用 `--resume`。每次都重复传入 `--regenerate-selected` 会再次重置选中的成功项。

只需要重试失败或缺失项时，直接使用 `--resume`，不要加 `--regenerate-selected`。

批量节点 2 完成即是第二个人工检查点。此时没有 curl 请求；确认 `research_instructions`、`content_category` 和 `generated_prompt` 的质量后，才把节点 2 JSON 交给后续节点 3 执行器，或抽取 CSV 的 `generated_prompt` 手动执行。
