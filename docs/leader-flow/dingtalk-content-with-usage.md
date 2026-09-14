# 推荐内容生成流程

这个项目把话题或固定 Tags 组合转成选题，生成研究 Prompt，调用 Eureka 产出报告／网页，最后将选题、标签和结果链接整理成产品可读取的内容数据。

## 项目怎么跑

输入 → generate_topic → generate_research_prompt → call_curl_task → 保存记录、导出产品 JSON。

1. **输入话题或 Tags。** 话题模式输入 idea、语言、生成条数和输出格式；例如“芯片互连，中文，1 条，report”。固定标签模式先指定角色、行业、工作需求和七维标签，再批量生成问题。
2. **生成选题：generate_topic。** LLM 输出标题、完整描述、受众、标签、实体和关键词。程序用统一枚举目录检查字段与组合，校验失败时最多修复一次；仍失败就停止。每条选题分配 brief_id。 按当前固定标签批量入口，6 类角色各关联 6 项工作需求，再覆盖 11 类行业，共 396 个基础受众组合；默认每组选择一套固定 Tags、生成 10 个问题，可得到 3,960 条选题。若将七维 Tags 按全部兼容规则展开，2.2.0 版目录共有 290,758 套可配置的“受众＋Tags”组合（包含泛行业及细分行业，不计实体、关键词和问题文本）；这是规则允许的配置空间，当前默认批次不会全量生成。
3. **生成研究 Prompt：generate_research_prompt。** 读取上一步已校验的选题，生成 content_category 和 research_instructions。程序将标题、受众、标签、关键词与研究要求拼成 generated_prompt，通过 brief_id 关联。这个阶段生成研究指令，标签沿用第一阶段。
4. **执行内容生成：call_curl_task。** 根据 format 选择 report 或 HTML，将 Prompt 提交给 Eureka，保存 session_id，再创建分享链接并查询完成状态。主流程会等待完成；批量节点 3 默认先提交，之后再集中查询。已有会话的任务可恢复，不重复提交。
5. **保存并导出。** JSON 保存完整运行结果，CSV 用于检查与汇总，并按 brief_id 更新状态。records-to-plg 将 CSV 转成 plg-rd-case-default-us.json，提取 session_id、share_id，保留受众、关键词、格式和完成状态，供产品接入。

三个处理节点可以分阶段运行，中间结果保存为 JSON，检查或修改后继续。当前项目主要交付结构化文件和内容链接，线上数据库接入需由产品侧完成。

## 一个例子：芯片互连

输入 idea = 芯片互连。第一阶段将它展开成一个明确的选题：

**标题：芯片互连方案的功耗、带宽与成本取舍。**

**描述：从产品设计视角比较芯片互连方案在功耗、带宽与制造成本上的取舍，形成支持方案选择的对比矩阵。**

下面是这条内容对应的字段。数量取自当前 2.2.0 版目录；前三项是受众，后面是内容标签。候选值是目录举例，实际选择会按描述和上层字段逐步收窄：先确定研究对象和主要任务，再匹配行业、任务、视角与成果，最后检查组合。

| 字段与规模 | 其它候选值举例 | 本例选择与依据 |
| --- | --- | --- |
| audience.role（6 类） | researcher（科研）；innovation_product_strategy（创新与产品战略） | rd_engineer：本例研究产品技术方案，选择研发类目标受众。 |
| audience.industry（11 类） | medical_devices（医疗器械）；energy（能源）；automotive（汽车） | electronics_manufacturing：研究对象属于芯片设计与制造领域。 |
| audience.jtbd（26 类） | existing_technologies（了解现有技术）；technical_feasibility（评估可行性）；product_ideas（生成产品创意） | technical_solutions：问题要求寻找和比较方案，主要任务不是验证可行性或提出创意。 |
| tags.role_perspective（18 类） | process_engineering（工艺工程）；reliability_engineering（可靠性工程）；system_integration（系统集成） | product_design：比较功能、性能和成本取舍；若改成排查失效，则考虑可靠性工程。 |
| tags.industry_segment（42 类） | electronic_components_interconnects（电子元件与互连）；computing_network_hardware（计算与网络硬件） | semiconductors：本例限定芯片内部及封装互连，归入半导体；独立连接器或整机应重新判断。 |
| tags.jtbd_task（36 类） | solution_search（寻找方案）；failure_resolution（失效处理）；process_optimization（工艺优化） | solution_comparison：描述明确要求比较不同技术路线。 |
| tags.desired_output（21 类） | candidate_shortlist（候选清单）；improvement_plan（改进方案）；validation_plan（验证计划） | comparison_matrix：按统一维度比较；程序规定 solution_comparison 只能搭配此成果。 |
| tags.topic_theme（16 类） | performance_improvement（性能提升）；technical_challenges（技术挑战）；safety_reliability（安全可靠性） | solution_comparison：固定标签模式下，主题聚焦路线比较，而不是单独讨论提升或风险。 |
| tags.question_intent（12 类） | evaluate_feasibility（评估可行性）；support_decision（支持决策）；assess_risks（评估风险） | compare_approaches：当前问法是“如何比较”；同主题可选前两种其它意图，但不允许 assess_risks。 |
| tags.scope_level（2 类） | industry（泛行业）；另一个值为 industry_segment（细分行业） | industry_segment：已选 semiconductors；只有未选细分行业时才用 industry。 |


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


## 后续：从不同产品的使用记录，看用户需要什么

以下全部为模拟数据，用来说明实现方式，不代表真实用户或行业结论。三个用户都主动选择“研发”，分别关注芯片互连、体外诊断仪器和储能电池组。保持角色相同，观察具体问题和任务偏好的差异。

统一看最近 30 天、观察窗口已完整的记录。每个问题设为 20 次有效曝光，方便比较。“使用 1 次”指用户进入阅读会话后，至少一次应用到工作区或基于内容启动研究任务；同会话重复操作只记一次，并关联到该次曝光。复制、下载也按阅读会话去重，单独统计，可能与使用重叠，不能相加当作总使用次数。

实现上，事件先通过 content_id 关联到内容的标签快照，再按 user_id、标签字段和值汇总。不能只统计全站哪个行业最热门，再把这个结果当作某个用户的画像。

**用户甲：电子制造／芯片互连**

这三条内容的行业标签为 electronics_manufacturing，细分行业标签为 semiconductors。表中列出变化的任务与成果标签；记录仍保留完整七维标签。

| 问题 | 任务 → 成果标签 | 曝光／点击／使用 | 复制／下载 |
| --- | --- | --- | --- |
| 芯片互连方案在带宽、功耗和成本上如何取舍？ | solution_comparison → comparison_matrix | 20／16／12 | 8／3 |
| 芯片封装散热方案在性能与集成成本上有哪些差异？ | solution_comparison → comparison_matrix | 20／14／8 | 5／4 |
| 芯片互连出现连接失效时有哪些排查与改进路径？ | failure_resolution → improvement_plan | 20／6／2 | 1／1 |

同为半导体内容，前两个方案比较问题共使用 20 次，失效改进问题使用 2 次；用户在当前观察窗口更常用方案比较内容。

**用户乙：医疗器械／体外诊断仪器**

这三条内容的行业标签为 medical_devices，细分行业标签为 in_vitro_diagnostics。表中列出变化的任务与成果标签；记录仍保留完整七维标签。

| 问题 | 任务 → 成果标签 | 曝光／点击／使用 | 复制／下载 |
| --- | --- | --- | --- |
| 体外诊断仪器的重复性应如何设计验证计划？ | validation_planning → validation_plan | 20／15／11 | 3／9 |
| 微流控检测芯片的验证测试应覆盖哪些条件？ | validation_planning → validation_plan | 20／14／9 | 2／7 |
| 体外诊断检测平台有哪些技术路线差异？ | solution_comparison → comparison_matrix | 20／7／3 | 1／2 |

两条验证计划共使用 20 次，方案比较使用 3 次；验证类内容下载 16 次，进一步支持用户希望保留验证材料的判断。

**用户丙：能源／储能电池组**

这三条内容的行业标签为 energy，细分行业标签为 batteries_stationary_storage。表中列出变化的任务与成果标签；记录仍保留完整七维标签。

| 问题 | 任务 → 成果标签 | 曝光／点击／使用 | 复制／下载 |
| --- | --- | --- | --- |
| 储能电池组的温升异常有哪些排查和改进路径？ | failure_resolution → improvement_plan | 20／14／10 | 4／3 |
| 储能系统连接失效应如何排查并形成改进方案？ | failure_resolution → improvement_plan | 20／12／8 | 3／2 |
| 储能系统技术路线如何比较寿命与成本？ | solution_comparison → comparison_matrix | 20／6／2 | 1／1 |

两条失效改进内容共使用 18 次，方案比较使用 2 次；用户在当前观察窗口更常用故障排查和改进内容。

**把问题记录汇总成标签使用次数**

每项同时列出“使用次数／有效曝光”，方便区分使用多与展示多。

| 用户 | 细分行业标签 | 任务标签 | 成果标签 |
| --- | --- | --- | --- |
| 甲 | semiconductors：22／60 | solution_comparison：20／40；failure_resolution：2／20 | comparison_matrix：20／40；improvement_plan：2／20 |
| 乙 | in_vitro_diagnostics：23／60 | validation_planning：20／40；solution_comparison：3／20 | validation_plan：20／40；comparison_matrix：3／20 |
| 丙 | batteries_stationary_storage：20／60 | failure_resolution：18／40；solution_comparison：2／20 | improvement_plan：18／40；comparison_matrix：2／20 |

例如用户甲的 solution_comparison 使用次数为两个比较问题的 12 次加 8 次，共 20 次。每次使用同时关联多个标签，但行业、任务、成果分别汇总；三个维度的次数不能相加，也不能证明是哪一个标签单独促成了使用。实际排序还要保留各标签的曝光分母，避免把展示更多误判成需求更强。

**最后形成可用于推荐的画像描述**

| 用户 | 根据记录得到的近期需求 | 推荐如何调整 |
| --- | --- | --- |
| 用户甲（电子制造／芯片互连） | 近期主要需要比较半导体技术路线，偏好能直接用于选型的对比矩阵。 | 优先推荐互连、封装等方案比较内容，保留少量可靠性内容。 |
| 用户乙（医疗器械／体外诊断仪器） | 近期更需要设计验证步骤、测试条件和评价指标，偏好验证计划。 | 优先推荐体外诊断仪器与微流控检测的验证计划，保留方案比较内容。 |
| 用户丙（能源／储能电池组） | 近期更需要排查异常和形成改进路径，偏好失效处理与改进方案。 | 优先推荐温升、连接和可靠性问题的排查改进内容，保留技术路线比较。 |

这些记录体现“领域＋任务＋成果形式”的差异：甲更常用方案比较，乙更常用验证计划，丙更常用失效改进。画像保存时区分用户主动填写的角色／行业与行为推断的近期需求，并记录时间窗、曝光量和样本量；不能从这三个模拟用户推断所有同行业用户都有相同需求。
