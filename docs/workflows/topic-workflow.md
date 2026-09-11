# 端到端推荐内容流程

更新日期：2026-09-11。执行记录版本：`2.0.0`。标签目录仍使用 `2.0.0`。

```text
输入 → generate_topic → generate_summary → call_curl_task → 结果
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
- 工作视角、细分行业、技术对象、具体任务和预期产出；
- 分类理由、范围假设、实体与关键词。

输出保存在 `generation_result.briefs`。一个生成请求可以返回多条选题，每条有独立 `brief_id`。

输入检查、枚举及组合校验、一次修复都在节点内部完成。无效输入不调用模型；生成不通过则抛出带阶段名称的错误，后续节点不执行。普通路径只调用一次模型。

## 3. generate_summary：生成执行提示词

输入是上一节点完整、已校验的选题，不再次从原始主题词重新选题。该节点名称为 `generate_summary`，语义是生成执行要求，不是生成最终文章的摘要。

第二次模型调用返回：

```json
{
  "summaries": [
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

代码与契约：[summary_generation.py](../../src/recommendation_contents/summary_generation.py)、[响应 schema](./summary-response.schema.json)。

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

CSV 按 `brief_id` 更新同一内容的状态，保留 `generation_id`、目录版本、受众、五维标签、分类依据和假设，避免恢复操作被计为新增内容。

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

如果还需要检查执行提示词，同时设置 `generate_summary` **After**（或 `call_curl_task` **Before**）断点。这样第二次继续之前不会提交 Eureka 任务。断点要在开始运行前设置，暂停不影响已经提交的外部任务。

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
  --stop-after generate_summary --stage-output outputs/review/summary.json
```

检查 `outputs/review/summary.json` 中的 `task_specs[].generated_prompt` 后执行：

```bash
uv run topic-workflow --from-stage-file outputs/review/summary.json --output json --pretty
```

三条命令分别调用第一阶段模型、第二阶段模型、Eureka；后续命令复用已有结果。也可以省略第二条命令的 `--stop-after` 和 `--stage-output`，直接从选题执行到最终结果。图仍为三个节点，导入已有结果时相应生成节点只校验并传递数据。

- `--stop-after` 是本次命令的正常停止，退出码为 0，输出 `status=paused`。不会执行下游节点或写入报告汇总表。
- 不指定 `--stage-output` 时保存到 `outputs/workflow_stages/<generation_id>.<node>.json`。即使指定 `--no-save`，显式要求的阶段快照仍会保存；`--no-save` 只关闭执行日志和结果汇总。
- `--from-stage-file` 也接受 `content-brief-workflow --output-file` 生成的完整第一阶段 JSON；只复制一句描述或单独 `briefs` 数组不够。它保留文件中的语言、条数和 ID。
- 默认沿用快照的 `format`；第一阶段文件可以用 `--format` 选择最终格式。导入已有 `task_specs` 时，格式必须与其一致。
- 修改选题内容后，应使用第一阶段文件重新生成第二阶段。如果从第二阶段文件改选题，先清空 `task_specs`，再用第二条命令重新生成提示词。不要单独修改顶层 `generated_prompt`：它不是实际提交源。执行前会核对 `task_specs` 中的描述、标签、语言和完整提示词是否一致。
- 第三阶段开始后，继续查询原任务应使用 `--resume-run-id`。相同 ID 对应已保存的执行内容，不能用修改后的提示词覆盖它；若要生成新内容，从新主题请求开始。

CLI 暂停时使用进程内 checkpointer，到下一次命令通过 JSON 导入继续；这不是跨进程保存的 LangGraph thread。Studio 的检查点由 LangGraph 服务管理。在 Python 同一进程中，可传入 `checkpointer`，用同一 `thread_id` 调用 `graph.invoke(..., interrupt_after=["generate_topic"])`，再用 `graph.invoke(None, config=同一配置)` 继续；静态断点不使用 `Command(resume=...)`。参见 [LangGraph 断点说明](https://docs.langchain.com/oss/python/langgraph/interrupts)。

如需通过 Studio/API 导入已有结果，新输入可设置 `{"stage_result": 完整阶段JSON}`；内容结构与 `--from-stage-file` 相同。默认未设置断点、也未指定 `--stop-after` 时，流程仍会自动执行到底。
