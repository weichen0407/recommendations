输入 → generate_topic → generate_research_prompt → call_curl_task → 保存记录、导出产品 JSON。

1. **输入话题或 Tags。** 话题模式输入 idea、语言、生成条数和输出格式；例如“芯片互连，中文，1 条，report”。固定标签模式先指定角色、行业、工作需求和七维标签，再批量生成问题。
2. **生成选题：generate_topic。** LLM 输出标题、完整描述、受众、标签、实体和关键词。程序用统一枚举目录检查字段与组合，校验失败时最多修复一次；仍失败就停止。每条选题分配 brief_id。
3. **生成研究 Prompt：generate_research_prompt。** 读取上一步已校验的选题，生成 content_category 和 research_instructions。程序将标题、受众、标签、关键词与研究要求拼成 generated_prompt，通过 brief_id 关联。这个阶段生成研究指令，标签沿用第一阶段。
4. **执行内容生成：call_curl_task。** 根据 format 选择 report 或 HTML，将 Prompt 提交给 Eureka，保存 session_id，再创建分享链接并查询完成状态。主流程会等待完成；批量节点 3 默认先提交，之后再集中查询。已有会话的任务可恢复，不重复提交。
5. **保存并导出。** JSON 保存完整运行结果，CSV 用于检查与汇总，并按 brief_id 更新状态。records-to-plg 将 CSV 转成 plg-rd-case-default-us.json，提取 session_id、share_id，保留受众、关键词、格式和完成状态，供产品接入。

三个处理节点可以分阶段运行，中间结果保存为 JSON，检查或修改后继续。当前项目主要交付结构化文件和内容链接，线上数据库接入需由产品侧完成。

## 一个例子：芯片互连

输入 idea = 芯片互连。第一阶段将它展开成一个明确的选题：

**标题：芯片互连方案的功耗、带宽与成本取舍。**

**描述：从产品设计视角比较芯片互连方案在功耗、带宽与制造成本上的取舍，形成支持方案选择的对比矩阵。**

下面是这条内容对应的字段。数量取自当前 2.2.0 版目录；前三项是受众，后面是内容标签。

| 字段 | 目录规模 | 示例值与含义 |
| --- | --- | --- |
| audience.role | 6 类角色 | rd_engineer：研发工程师／发明者 |
| audience.industry | 11 类行业 | electronics_manufacturing：电子制造 |
| audience.jtbd | 26 类工作需求 | technical_solutions：寻找技术方案 |
| tags.role_perspective | 18 类工作视角 | product_design：产品设计 |
| tags.industry_segment | 42 类细分行业 | semiconductors：半导体 |
| tags.jtbd_task | 36 类具体任务 | solution_comparison：方案比较 |
| tags.desired_output | 21 类预期成果 | comparison_matrix：对比矩阵 |
| tags.topic_theme | 16 类内容主题 | solution_comparison：方案比较主题（固定标签模式） |
| tags.question_intent | 12 类问题意图 | compare_approaches：比较路线（固定标签模式） |
| tags.scope_level | 2 类范围层级 | industry_segment：细分行业（固定标签模式） |

普通话题模式输出前七行，即三个受众字段加四项基础标签。切换到固定标签批量模式时，再配置最后三项，构成七维内容标签。同组问题共享一个 tag_set_id，不能逐题改变标签。

具体研究对象单独保存：entities = [芯片互连]；keywords = [芯片互连、功耗、带宽、制造成本]。“芯片互连”是自由文本，不新增成行业标签。选型切口和比较维度由运营扩展的部分，写入 assumptions。

第二阶段为这条选题生成研究要求，例如：

> 从产品设计视角比较芯片互连方案，使用可靠公开资料并标明证据限制。围绕带宽、功耗和制造成本整理共同的比较维度，形成方案对比矩阵。

程序把这段要求和标题、受众、标签、关键词拼成完整 Prompt。第三阶段选择 report，交给 Eureka 生成报告；如果选择 HTML，则请求生成网页。同一份研究 Prompt 可用于两种格式，两种执行各自保存结果。

最终，这条记录包含：标题、描述、受众、tags、keywords、brief_id、generation_id、taxonomy_version，以及执行后得到的 session_id、分享链接、format 和状态。后续查询同一任务时更新原记录。

这里的选题和标签来自仓库中的规则示例，研究要求是说明性示例；会话 ID 和结果链接在真实执行后产生。

## 标签规则与下一步

标签来自 content_brief_catalog.json，Schema 检查结构，程序再检查字段间的组合关系。几个直接影响生成结果的规则：

- **行业必须匹配。** electronics_manufacturing 可以对应 semiconductors，不能对应 automotive_chassis_body；行业只保留“泛行业 → 细分行业”两级。
- **任务限定成果。** technical_solutions 可拆成 solution_search、solution_comparison、failure_resolution、process_optimization。选择 solution_comparison 时，成果必须是 comparison_matrix，不能改成 trend_brief。
- **固定标签必须保持一致。** 例如 product_design 不能在同组某一题里改成 reliability_engineering。需要改做失效分析时，应新建标签组合，使用 failure_resolution 与 improvement_plan。
- **主题、问题意图和范围也有约束。** solution_comparison 主题允许 compare_approaches；不允许 assess_risks。选择 semiconductors 后，scope_level 必须是 industry_segment。
- **实体与关键词可以变化。** 固定标签组合下，可以生成不同研究对象和比较维度的问题，但不能只换同义词。固定标签输入当前不单独锁定“芯片互连”这个实体，具体对象需要通过话题入口或选题审核控制。

接下来主要补三件事：把完整 tags、标签版本和 brief_id／content_id 映射传到产品；将曝光、点击、复制、下载、使用事件关联回内容；按标签统计曝光及后续使用表现，用于调整推荐排序和下一批选题。当前产品 JSON 的导出字段还没有包含完整 tags 和上述追溯字段，需要补齐。
