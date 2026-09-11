# 推荐内容 Tag 规则 v1

> 历史设计：本文件最初以用户画像作为生成输入。运营侧第一阶段现以 [运营选题_第一阶段生成规则.md](./运营选题_第一阶段生成规则.md) 为准：只需 idea，role / industry / JTBD 改为目标受众输出。v1 的枚举定义作为来源保留，用户上下文前置条件不用于新流程。

版本：`1.0.0`。日期：2026-09-11。状态：首版规则，供规则评审与后续 schema 实现使用。

本规则用于：接收用户明确选择的 role、industry、JTBD，在受控枚举和组合条件下生成问题及答案，再按标签观察推荐行为。

本轮交付规则和枚举目录；尚未修改现有生成流程、部署配置或运行 schema。内容标签描述问题与答案，不自动改写用户身份或确认兴趣。

配套的 [tag-catalog.json](./docs/recommendation-tags/v1/tag-catalog.json) 保存全部枚举、映射、条件和示例，作为后续 schema 的唯一枚举数据源。本文解释语义、使用顺序和行为分析口径。术语见 [CONTEXT.md](./CONTEXT.md)。

阅读路径：第 4 节看角色视角，第 5–6 节看行业与技术对象，第 7–8 节看任务与产出，第 9 节看组合规则，第 10 节看完整示例，第 11 节看点击分析。全部输入映射在第 3 节。

## 1. 依据与拆分原则

输入依据为 [Onboarding字段映射_三列版.xlsx](./Onboarding字段映射_三列版.xlsx) 的“正常映射”工作表 A1:C44。三个字段分别有 6、11、26 个值，均包含 `other`。输入值沿用原表，不重新命名。

业务依据为 [欧美行业与角色 JTBD Profiling 分析](./欧美行业与角色_JTBD_Profiling分析.md)：13 类具名细分角色（另有 Other）、42 个细分行业、546 个行业与角色组合。原文每个组合的触发情境、主任务、相关任务、交付物和成功判据用于提炼规则与示例，不把组合 ID 直接当作兴趣标签。具体 JTBD 为待验证的分析假设。

角色回答工作立场，行业回答领域，技术对象回答具体研究对象，任务回答要完成的动作，产出回答答案应交付的工作成果。同一任务可被不同角色采用，同一对象可在明确的多个行业中复用。

稳定枚举统一使用小写 `snake_case`。中文和英文名称只是展示文本。key 在字段内唯一；分析时使用 `维度:key`，例如 `role_perspective:product_design`。不把角色、行业和任务拼成一个不可拆分的长 tag。

以下新增枚举和匹配关系是规则设计，不表示原文已经逐项给出这些英文 key，也不表示已验证点击偏好。行业包含与排除范围沿用原文，技术对象为首版归纳目录，不宣称穷尽整个行业。

## 2. 字段契约

| 位置／字段 | 类型与数量 | 含义与约束 |
| --- | --- | --- |
| input_profile.job_role | 单个原表枚举 | 用户选择的角色入口；生成器只读。 |
| input_profile.industry_type | 单个原表枚举 | 用户选择的泛行业入口；生成器只读。 |
| input_profile.jtbd_primary | 单个原表枚举 | 当前主要任务入口；保留原值。多任务输入须在入口层拆成多个生成请求。 |
| tags.role_perspective | 必填，单个枚举 | 一道问题的主要工作视角；不能用来证明用户身份。 |
| tags.industry_segment | 必填，单个枚举或 null | 内容主要细分行业。未确定或未覆盖时为 null 并附原因。 |
| tags.technology_object | 必填，0–2 个不重复枚举 | 问题的主要技术对象；跨对象比较可用 2 个。泛主题或未覆盖时为空并附原因。 |
| tags.jtbd_task | 必填，单个枚举 | 一道问题只承载一个主要可执行任务。 |
| tags.desired_output | 必填，单个枚举 | 答案的主要工作成果，不等于文章类别或文件格式。 |
| taxonomy_version | 必填，版本字符串 | 本版为 1.0.0，与内容及曝光一起保存。 |
| selection | 必填，来源元数据 | 区分 role_preferred/task_override、明确上下文/探索和未确定原因；不是兴趣标签。 |
| answer_mode | 必填，模式枚举 | general_guidance、template、case_specific；仅三个输入时通常是前两者。 |
| design_source_refs | 可多值，原文 ID | 仅用于追溯规则来源，例如 E01-R01；不充当答案事实引用。 |

`industry_segment=null` 时，`technology_object=[]`。未细分原因按配套目录的 `metadata_enums` 取值；已有值时相应原因必须为 null。对象为空的原因可为 `broad_scope`、`not_in_catalog` 或 `industry_unresolved`。

`selection` 是生成记录：`within_input_exploration` 只表示这次选题选中了某个子领域。只有用户提供的上下文明确提及时才记录 `explicit_context`。跨行业选题需要明确业务关联，记录 `cross_industry_explicit_context` 及依据。不能以模型自身产出的文本当作用户上下文。

地区、具体工况、目标成本、时间窗口、文件材料属于可选上下文。其值只能来自显式输入或清楚标明的内容研究范围；模型不得假装这些已由用户选择。日期、地域与证据类型有助于答案质量，本版先作为上下文和元数据，不混入五个核心 tag。

## 3. 原始输入完整映射

### 3.1 角色：job_role

| 原表存储值 | 原表英文文案 |
| --- | --- |
| `rd_engineer` | R&D Engineer / Inventor |
| `researcher` | Researcher / Scientist |
| `innovation_product_strategy` | Innovation & Product Strategy |
| `in_house_ip_legal` | In-house IP & Legal |
| `patent_ip_services` | Patent & IP Services |
| `other` | Other |

### 3.2 行业：industry_type

| 原表存储值 | 原表英文文案 |
| --- | --- |
| `medical_devices` | Medical Devices |
| `materials` | Materials |
| `automotive` | Automotive |
| `electronics_manufacturing` | Electronics Manufacturing |
| `engineering` | Engineering |
| `biotech` | Biotechnology |
| `food_farming_production` | Food / Farming Production |
| `energy` | Energy |
| `chemical` | Chemical |
| `construction` | Construction |
| `other` | Other |

### 3.3 主要任务：jtbd_primary

| 原表存储值 | 原表英文文案 |
| --- | --- |
| `technical_solutions` | Find technical solutions |
| `existing_technologies` | Explore existing technologies |
| `product_ideas` | Generate product ideas |
| `technical_feasibility` | Assess technical feasibility |
| `patent_ip_risk` | Assess patent and IP risk |
| `new_research_fields` | Explore new research fields |
| `research_methods` | Find research methods |
| `research_trends` | Track research trends |
| `research_ideas` | Generate research ideas |
| `patents_literature` | Search patents and literature |
| `technology_competitors` | Track technologies and competitors |
| `innovation_opportunities` | Identify innovation opportunities |
| `rd_directions` | Evaluate R&D directions |
| `patent_landscapes` | Explore patent landscapes |
| `product_ip_risks` | Assess product IP risks |
| `prior_art` | Search prior art, assess novelty |
| `fto_design_risks` | Check FTO and design risks |
| `draft_review_patents` | Draft and review patents |
| `office_actions` | Respond to office actions |
| `fto_searches` | Conduct FTO searches |
| `draft_review_applications` | Draft and review applications |
| `draft_refine_claims` | Draft and refine claims |
| `technology_trends` | Track technology trends |
| `ideas_concepts` | Generate ideas and concepts |
| `search_draft_patents` | Search or draft patents |
| `other` | Other |

输入校验只接受原表值，或 `legacy_input_aliases` 明确登记的旧值；未知输入不静默转换为 `other`。`role`、`industry`、`jtbd` 可在入口层转换为标准字段名，但原字段与标准字段同时出现且值冲突时必须报错。空值和用户明确选择 Other 也必须区分。

原表没有 role 与 JTBD 的组合限制。项目现有 `enum_entities.json` 另有 `role_jtbd_map`，这是当前 UI／旧流程的默认任务关系。新规则保留它作为历史背景，明确任务优先于角色默认映射；该变化需在未来接入时实现，本轮没有改变运行行为。

## 4. 工作视角 role_perspective

### 4.1 原文角色与推荐视角的关系

| 原文 ID | 原文角色 | 对应内容视角 |
| --- | --- | --- |
| [R01](./欧美行业与角色_JTBD_Profiling分析.md#role-r01) | 研发工程师 | `product_design`、`process_engineering`、`system_integration`、`reliability_engineering`、`invention_development` |
| [R02](./欧美行业与角色_JTBD_Profiling分析.md#role-r02) | 独立发明人 | `invention_development` |
| [R03](./欧美行业与角色_JTBD_Profiling分析.md#role-r03) | 企业研究员／应用科学家 | `process_engineering`、`reliability_engineering`、`applied_research`、`research_methodology` |
| [R04](./欧美行业与角色_JTBD_Profiling分析.md#role-r04) | 高校／公共机构研究人员 | `scientific_contribution`、`research_methodology` |
| [R05](./欧美行业与角色_JTBD_Profiling分析.md#role-r05) | 创新与技术寻源负责人 | `technology_scouting`、`competitive_intelligence`、`ip_commercialization` |
| [R06](./欧美行业与角色_JTBD_Profiling分析.md#role-r06) | 产品战略负责人 | `product_strategy`、`competitive_intelligence` |
| [R07](./欧美行业与角色_JTBD_Profiling分析.md#role-r07) | 企业知识产权管理人员 | `competitive_intelligence`、`ip_portfolio_management`、`patent_evidence_analysis` |
| [R08](./欧美行业与角色_JTBD_Profiling分析.md#role-r08) | 企业专利法务 | `patent_risk_review`、`patent_prosecution` |
| [R09](./欧美行业与角色_JTBD_Profiling分析.md#role-r09) | 企业商务／一般法务 | `commercial_legal_review` |
| [R10](./欧美行业与角色_JTBD_Profiling分析.md#role-r10) | 外部专利律师 | `patent_risk_review`、`patent_evidence_analysis`、`patent_prosecution` |
| [R11](./欧美行业与角色_JTBD_Profiling分析.md#role-r11) | 专利检索与分析人员 | `patent_evidence_analysis` |
| [R12](./欧美行业与角色_JTBD_Profiling分析.md#role-r12) | IP 商业化与技术转移顾问 | `ip_commercialization` |
| [R13](./欧美行业与角色_JTBD_Profiling分析.md#role-r13) | 专利代理人 | `patent_prosecution` |
| [R00](./欧美行业与角色_JTBD_Profiling分析.md#role-r00) | 其他／尚未确定 | `task_exploration` |

### 4.2 每个 role 的默认视角候选

| job_role | 优先候选视角 |
| --- | --- |
| `rd_engineer` | `product_design`、`process_engineering`、`system_integration`、`reliability_engineering`、`invention_development` |
| `researcher` | `applied_research`、`scientific_contribution`、`research_methodology` |
| `innovation_product_strategy` | `technology_scouting`、`product_strategy`、`competitive_intelligence` |
| `in_house_ip_legal` | `ip_portfolio_management`、`patent_risk_review`、`patent_evidence_analysis`、`patent_prosecution`、`commercial_legal_review` |
| `patent_ip_services` | `patent_evidence_analysis`、`patent_prosecution`、`patent_risk_review`、`ip_commercialization` |
| `other` | `task_exploration` |

候选列表不是频率排序，也不是互斥身份。选择时先定具体任务，再在与任务相容的角色优先视角中选一个。若没有交集，用任务允许的其他视角并记录 `task_override`。`task_exploration` 只用于任务未明确时的导航。

R&D Engineer / Inventor 可展开为设计、工艺、系统集成、可靠性、发明构思五种视角。`invention_development` 表示讨论发明验证，不表示用户为独立发明人；`scientific_contribution` 也不推定高校任职。每道问题只选一个主视角；跨职责内容按主要产出所服务的责任选择，难以确定时拆题。

### 4.3 完整枚举与边界

| key | 中文／English | 定义 | 包含与排除 |
| --- | --- | --- | --- |
| `product_design` | 产品与部件设计 / Product and component design | 从产品功能、结构、材料和架构职责出发组织判断 | 包含设计规格和部件方案取舍；批次生产控制归 process_engineering |
| `process_engineering` | 工艺与制造 / Process engineering | 从制造流程、工艺窗口、良率及放大职责出发组织判断 | 包含量产一致性；仅讨论部件功能结构归 product_design |
| `system_integration` | 系统集成 / System integration | 从接口、部件协同及端到端系统运行出发组织判断 | 包含软硬件兼容、系统验证；单一部件寿命归 reliability_engineering |
| `reliability_engineering` | 可靠性工程 / Reliability engineering | 从故障、寿命、环境适应性及重复运行能力出发组织判断 | 包含故障恢复和寿命验证；纯科学机理贡献归 applied_research 或 scientific_contribution |
| `invention_development` | 发明构思与验证 / Invention development | 从发明概念的技术差异、原型及披露证据出发组织判断 | 可供受雇工程师采用；不表示独立个人身份，不等于专利可授权结论 |
| `applied_research` | 应用研究 / Applied research | 从机理、材料或方法能否解释并改善具体应用出发组织判断 | 关注可转化的研究证据；不推断雇主类型，生产操作优化归 process_engineering |
| `scientific_contribution` | 科学问题与研究贡献 / Scientific contribution | 从研究空白、可检验问题及相对既有工作的贡献出发组织判断 | 不推断高校身份；仅服务产品功能取舍归 product_design |
| `research_methodology` | 研究方法与可复现性 / Research methodology | 从实验设计、测量、基准及结果可复现性出发组织判断 | 包含研究方法比较；产品验收规划按产品或可靠性视角 |
| `technology_scouting` | 技术寻源与采用 / Technology scouting | 从外部技术供给、成熟度及引入条件出发组织判断 | 包含合作候选与试点门槛；客户定位归 product_strategy |
| `product_strategy` | 产品定位与路线图 / Product strategy | 从目标客户、使用场景、产品定位及功能优先级出发组织判断 | 包含进入路径；外部技术供应筛选归 technology_scouting |
| `competitive_intelligence` | 技术与竞争情报 / Competitive intelligence | 从竞争主体能力、技术变化及相对位置出发组织判断 | 可以使用技术或专利证据；核心是主体比较，非单一方案参数取舍 |
| `ip_portfolio_management` | 知识产权组合管理 / IP portfolio management | 从技术资产与业务路线的覆盖、布局和维护出发组织判断 | 具体组合分析需资产范围；不等于单产品侵权判断 |
| `patent_risk_review` | 专利风险审查 / Patent risk review | 从产品实施、权利要求、法律状态和适用范围出发组织风险问题 | 通用内容可做证据清单；不得把检索结果当确定法律结论 |
| `commercial_legal_review` | 合作合同与权属 / Commercial legal review | 从研发合作、数据使用、成果归属及交易责任出发组织判断 | 启用前需明确合作或合同场景；不把所有 Legal 用户都当专利律师 |
| `patent_evidence_analysis` | 专利检索与证据分析 / Patent evidence analysis | 从检索覆盖、家族日期、分类和特征证据映射出发组织判断 | 核心是可复核证据，不自动附带代理资格或法律意见 |
| `patent_prosecution` | 专利申请与审查 / Patent prosecution | 从披露支持、申请文件、权利要求及审查答复出发组织判断 | 缺具体披露或审查材料时仅生成模板，不虚构申请内容 |
| `ip_commercialization` | 技术许可与转移 / IP commercialization | 从技术资产与潜在采用方的匹配、开发差距和交易准备出发组织判断 | 启用前需明确许可、转移或引入场景；不凭职位推断正在交易 |
| `task_exploration` | 任务探索 / Task exploration | 在任务尚不明确时帮助比较可选工作及其交付物 | 仅用于 task_clarification；不作为其他已明确任务的万能标签 |

### 4.4 视角正例与反例

| 视角 | 适用例子 | 不应如此使用 |
| --- | --- | --- |
| `product_design` | 比较满足同一产品规格的部件方案 | 仅比较生产线批次控制策略 |
| `process_engineering` | 比较降低互连制造缺陷的工艺改进 | 只列产品功能清单 |
| `system_integration` | 比较传感器与控制器的接口方案 | 无系统关联的单一材料机理综述 |
| `reliability_engineering` | 针对热循环失效比较连接结构改进 | 仅评价论文的新颖程度 |
| `invention_development` | 为新采样结构规划最小验证 | 无依据断言用户是独立发明人 |
| `applied_research` | 研究噪声机制如何影响成像性能 | 仅制定生产排班计划 |
| `scientific_contribution` | 识别低数据量重建研究中的可检验空白 | 把用户认定为大学研究员 |
| `research_methodology` | 比较用于检验机制假设的实验方法 | 只列市场增长数字 |
| `technology_scouting` | 筛选可开展试点的封装技术路线 | 仅设计广告投放渠道 |
| `product_strategy` | 为新检测平台比较首发应用场景 | 仅核验专利法律状态 |
| `competitive_intelligence` | 跟踪不同企业的封装研发方向 | 仅对自己的样机做故障排查 |
| `ip_portfolio_management` | 将产品技术路线与专利主题覆盖关联 | 仅凭专利数量宣布不存在侵权风险 |
| `patent_risk_review` | 列出评估设计改动所需的权利要求证据 | 无产品与地域范围直接断言 FTO 安全 |
| `commercial_legal_review` | 整理合作研发成果归属的业务输入 | 把普通技术路线比较包装成合同审查 |
| `patent_evidence_analysis` | 设计能复现的微流控卡匣专利检索策略 | 将高相关度结果当作必然侵权结论 |
| `patent_prosecution` | 用披露支持表检查权利要求草稿 | 根据行业名称编造具体审查意见 |
| `ip_commercialization` | 识别许可候选与尚缺的验证证据 | 仅以引用次数推定可成交估值 |
| `task_exploration` | 说明方案比较和可行性评估分别解决什么 | 已明确检索任务仍标为未知任务 |

## 5. 细分行业 industry_segment

每个具名行业入口对应原文的若干子领域。它们是无补充上下文时的探索候选。用户的实际对象不在候选中时允许保留 null，避免只因目录存在就武断归类。

行业边界按问题主要交付物决定。电池材料与材料回收使用 `battery_materials_recycling`，储能电芯、系统及 BMS 使用 `batteries_stationary_storage`；车载应用不自动抹去材料或系统本体的区别。材料侧重性能体系，化学品侧重配方产品及应用制程；诊断试剂与研究用工具以用途区别。

本版使用一个主细分行业，不再追加第二个同等主行业。跨行业对象的复用关系见第 6 节；主要领域跨出用户输入时必须保留明确上下文依据。暂不提供跨行业的自动扩散规则。

航空航天沿用原文补充条目，但 `other` 没有默认子行业。只有明确给出航空航天相关工作时才选 `aerospace_space`。官方分类代码和 H1/H2 热门分组不进入本版行业枚举，也不覆盖任务相关性。

| key | 中文／English | 原始入口 | 包含范围 | 边界与排除 | 原文 |
| --- | --- | --- | --- | --- | --- |
| `medical_imaging` | 医学影像设备与诊断影像软件 / Medical Imaging Equipment & Diagnostic Imaging Software | `medical_devices` | CT、MRI、超声及直接承担影像重建或诊断辅助的软件 | 医院影像服务、一般健康应用不在此类；探测器上游另关联电子行业 | [H01](./欧美行业与角色_JTBD_Profiling分析.md#industry-h01) |
| `in_vitro_diagnostics` | 体外诊断与分子检测 / In Vitro Diagnostics & Molecular Testing | `medical_devices` | 临床检测试剂、仪器、分子诊断系统及居家检测产品 | 研究用试剂归H13生命科学工具；医院检验服务不是器械制造 | [H02](./欧美行业与角色_JTBD_Profiling分析.md#industry-h02) |
| `diabetes_monitoring_delivery` | 糖尿病监测与给药设备 / Diabetes Monitoring & Insulin Delivery Devices | `medical_devices` | 连续血糖监测、血糖仪、胰岛素泵及相关闭环设备 | 胰岛素药品归药物；非医疗运动手环与泛健康软件不在此类 | [H03](./欧美行业与角色_JTBD_Profiling分析.md#industry-h03) |
| `surgical_robotics` | 手术机器人与微创手术系统 / Surgical Robotics & Minimally Invasive Surgical Systems | `medical_devices` | 手术机器人、内镜介入平台、专用器械及术中导航 | 通用工业机器人归工业自动化；医院手术服务不在此类 | [H04](./欧美行业与角色_JTBD_Profiling分析.md#industry-h04) |
| `engineering_polymers_composites` | 工程聚合物与复合材料 / Engineering Polymers & Composites | `materials` | 树脂改性、工程塑料、纤维增强复材及半成品；按材料供应业务选择 | 涂料胶黏配方归M10；最终汽车/电子整机归其终端行业 | [M01](./欧美行业与角色_JTBD_Profiling分析.md#industry-m01) |
| `specialty_metals_alloys` | 特种金属与高性能合金 / Specialty Metals & Alloys | `materials` | 镍基高温合金、钛合金、特种钢及金属粉末供应研发 | 普通钢材贸易不作为热点；最终航空/医疗零件归终端行业 | [M02](./欧美行业与角色_JTBD_Profiling分析.md#industry-m02) |
| `technical_ceramics_glass` | 技术陶瓷与特种玻璃 / Technical Ceramics & Specialty Glass | `materials` | 电子绝缘散热陶瓷、陶瓷纤维、熔融石英及功能玻璃 | 建筑水泥归M14；陶瓷装饰和普通日用玻璃非本轮热点 | [M03](./欧美行业与角色_JTBD_Profiling分析.md#industry-m03) |
| `battery_materials_recycling` | 电池材料与材料回收 / Battery Materials & Recycling | `materials` | 正负极活性材料、电解质、隔膜材料与回收再生材料 | 电芯/电池包/储能系统归M05；采矿仅作上游标签 | [M04](./欧美行业与角色_JTBD_Profiling分析.md#industry-m04) |
| `automotive_electrified_powertrains` | 汽车电驱与动力总成 / Automotive Electrified Powertrains | `automotive` | BEV/HEV/PHEV 电机、逆变器、电驱桥及混合动力耦合系统 | 电芯材料及独立储能电池另归能源/材料；底盘与自动驾驶另列 | [E05](./欧美行业与角色_JTBD_Profiling分析.md#industry-e05) |
| `adas_automated_driving` | 驾驶辅助与自动驾驶系统 / ADAS & Automated Driving Systems | `automotive` | 感知融合、驾驶决策、控制、安全验证及车载计算集成 | 仅制造通用传感芯片归半导体；不将辅助驾驶等同无人驾驶 | [E06](./欧美行业与角色_JTBD_Profiling分析.md#industry-e06) |
| `automotive_chassis_body` | 汽车底盘与车身零部件 / Automotive Chassis & Body Components | `automotive` | 制动、转向、悬架、车身结构、座舱及车用热管理部件 | 电驱动力总成与 ADAS 算法单列；原材料归材料行业 | [E07](./欧美行业与角色_JTBD_Profiling分析.md#industry-e07) |
| `commercial_special_vehicles` | 商用及专用车辆 / Commercial & Special-Purpose Vehicles | `automotive` | 公路卡车、客车、厢式商用车及专用车整车/系统工程 | 乘用车、车队运营服务；非道路工程/农业机械归对应机械行业 | [E08](./欧美行业与角色_JTBD_Profiling分析.md#industry-e08) |
| `semiconductors` | 半导体 / Semiconductors | `electronics_manufacturing` | 芯片设计、晶圆制造、封装与测试；逻辑、存储、模拟及功率器件 | 整机、PCB及独立光学仪器；半导体设备按主营活动另标设备 | [E01](./欧美行业与角色_JTBD_Profiling分析.md#industry-e01) |
| `electronic_components_interconnects` | 电子元件与互连 / Electronic Components & Interconnects | `electronics_manufacturing` | PCB、连接器、无源器件和电子组装互连；覆盖刚柔板 | 半导体芯片、整机服务器、完整光学系统 | [E02](./欧美行业与角色_JTBD_Profiling分析.md#industry-e02) |
| `computing_network_hardware` | 计算与网络硬件 / Computing & Network Hardware | `electronics_manufacturing` | 服务器、存储系统、网络交换与通信设备的硬件和系统集成 | 纯软件 SaaS、芯片设计、数据中心电力设施本体 | [E03](./欧美行业与角色_JTBD_Profiling分析.md#industry-e03) |
| `photonics_optical_sensing` | 光子与光学传感系统 / Photonics & Optical Sensing Systems | `electronics_manufacturing` | 激光器、光学仪器、成像与光谱检测系统；光学传感模块 | 芯片级半导体器件归 E01；非光学传感按实际终端归类 | [E04](./欧美行业与角色_JTBD_Profiling分析.md#industry-e04) |
| `industrial_robotics_automation` | 工业机器人与自动化 / Industrial Robotics & Automation | `engineering` | 工业机器人、协作机器人、机器视觉集成和自动化工作单元 | 消费机器人；单台非机器人加工设备另列 | [E09](./欧美行业与角色_JTBD_Profiling分析.md#industry-e09) |
| `industrial_machinery` | 工业机械与生产设备 / Industrial Machinery & Production Equipment | `engineering` | 金属加工机床、成形与专用生产设备；机械子领域按客户对象补标签 | 机器人、增材设备单列；民用建筑施工服务不在此类 | [E10](./欧美行业与角色_JTBD_Profiling分析.md#industry-e10) |
| `additive_manufacturing_systems` | 增材制造设备与系统 / Additive Manufacturing Equipment & Systems | `engineering` | 工业 3D 打印机、过程监控、控制系统及设备集成 | 打印粉末与树脂归材料；纯打印服务按最终客户行业多标签 | [E12](./欧美行业与角色_JTBD_Profiling分析.md#industry-e12) |
| `engineering_design_services` | 工程设计与技术咨询服务 / Engineering Design & Technical Consulting Services | `engineering` | 面向设施、系统和产品的工程分析、设计、技术咨询与集成建议 | 设备制造、建筑施工承包、纯管理咨询和律师服务不在此类 | [E13](./欧美行业与角色_JTBD_Profiling分析.md#industry-e13) |
| `antibody_protein_medicines` | 抗体与治疗性蛋白药物 / Antibody & Therapeutic Protein Medicines | `biotech` | 单克隆抗体、双特异抗体、抗体偶联药物及其他治疗蛋白 | 小分子化药不是本子类；替客户生产归CDMO；细胞/基因产品另列 | [H05](./欧美行业与角色_JTBD_Profiling分析.md#industry-h05) |
| `cell_gene_therapies` | 细胞治疗与基因治疗 / Cell & Gene Therapies | `biotech` | CAR-T等细胞产品、体内/体外基因治疗及基因编辑治疗产品 | 非治疗用途基因编辑归对应农业/工业方向；一般试剂与纯CDMO另列 | [H06](./欧美行业与角色_JTBD_Profiling分析.md#industry-h06) |
| `biologics_process_manufacturing` | 生物药工艺开发与合同制造 / Biologics Process Development & Contract Manufacturing | `biotech` | 生物药CDMO、细胞株开发、培养纯化、分析及技术转移服务 | 自有药物发现归药物子类；通用设备销售可跨标工程行业 | [H07](./欧美行业与角色_JTBD_Profiling分析.md#industry-h07) |
| `industrial_enzymes_microorganisms` | 工业酶与工业微生物 / Industrial Enzymes & Microorganisms | `biotech` | 清洁、纺织、造纸和工业生物加工用酶、生产菌种及相关配方 | 食品配料归食品子类；可再生燃料成品归Chemical，能源作应用标签；聚合物成品归材料 | [H08](./欧美行业与角色_JTBD_Profiling分析.md#industry-h08) |
| `life_science_research_tools` | 生命科学研究工具与实验室仪器 / Life Science Research Tools & Laboratory Instruments | `biotech` | 研究用测序与单细胞/多组学仪器、样本制备、分析试剂和实验室自动化 | 用于临床诊断的成套IVD产品归H02；生物药CDMO归H07；研究用途不等同临床获批用途 | [H13](./欧美行业与角色_JTBD_Profiling分析.md#industry-h13) |
| `agricultural_machinery_precision_farming` | 农业机械与精准农业系统 / Agricultural Machinery & Precision Farming Systems | `food_farming_production` | 自动导航农机、精量播种、变量施用、感知与农业作业系统 | 以工程制造作主业可跨标Engineering；种植服务不是设备研发 | [H09](./欧美行业与角色_JTBD_Profiling分析.md#industry-h09) |
| `seeds_crop_breeding` | 种子与作物育种 / Seeds & Crop Breeding | `food_farming_production` | 商业种子、种苗与作物性状开发，含常规育种和生物技术育种 | 农业机械另归农业装备；农药和生物防治产品本版未单列，可用 Other 补充 | [H10](./欧美行业与角色_JTBD_Profiling分析.md#industry-h10) |
| `frozen_prepared_foods` | 冷冻及方便食品 / Frozen & Prepared Foods | `food_farming_production` | 冷冻果蔬、冷冻餐食及即食方便食品制造，聚焦加工保鲜工艺 | 纯食品机械制造可跨标Engineering；原粮、饮料和冷链运输服务不在此类 | [H11](./欧美行业与角色_JTBD_Profiling分析.md#industry-h11) |
| `food_ingredients_nutrition` | 食品配料与营养成分 / Food Ingredients & Nutritional Components | `food_farming_production` | 面向食品制造的蛋白、膳食纤维、酶、菌种和功能配料及应用配方 | 治疗性药物归生物药；工业用途酶归工业生物；不把替代蛋白视作全部行业 | [H12](./欧美行业与角色_JTBD_Profiling分析.md#industry-h12) |
| `batteries_stationary_storage` | 电池与固定式储能系统 / Batteries & Stationary Energy Storage | `energy` | 电芯制造、电池包、BMS、PCS与工商业/电网储能集成 | 活性材料归M04；整车动力系统归Automotive；非泛指所有发电 | [M05](./欧美行业与角色_JTBD_Profiling分析.md#industry-m05) |
| `grid_power_equipment` | 电网与电力设备 / Grid & Power Equipment | `energy` | 变压器、开关设备、电缆、保护控制与电网增强技术 | 发电设备归对应行业；仅售电交易不属于本类研发画像 | [M06](./欧美行业与角色_JTBD_Profiling分析.md#industry-m06) |
| `solar_photovoltaics` | 太阳能光伏设备 / Solar Photovoltaics | `energy` | 光伏电池片/组件、封装、支架跟踪及逆变器研发制造 | 晶圆级通用半导体归Electronics；上游树脂/玻璃归材料 | [M07](./欧美行业与角色_JTBD_Profiling分析.md#industry-m07) |
| `hydrogen_fuel_cell_equipment` | 制氢与燃料电池设备 / Hydrogen & Fuel Cell Equipment | `energy` | 电解槽、燃料电池电堆、氢压缩储运设备和辅助系统 | 工业氢气商品供应归M11；氢基燃料合成归M12 | [M08](./欧美行业与角色_JTBD_Profiling分析.md#industry-m08) |
| `electronic_chemicals` | 电子化学品 / Electronic Chemicals | `chemical` | 光刻胶、湿电子化学品、CMP浆料、电镀添加剂及沉积前驱体 | 工业气体商品归M11；晶圆器件/封装服务归Electronics | [M09](./欧美行业与角色_JTBD_Profiling分析.md#industry-m09) |
| `coatings_adhesives_sealants` | 涂料、胶黏剂与密封剂 / Coatings, Adhesives & Sealants | `chemical` | 工业/功能涂料、结构胶、电子胶及建筑密封配方研发制造 | 基础树脂供货归M01；实际喷涂/安装业务需另标服务角色 | [M10](./欧美行业与角色_JTBD_Profiling分析.md#industry-m10) |
| `industrial_specialty_gases` | 工业与电子特种气体 / Industrial & Specialty Gases | `chemical` | 高纯/特种气体、空分、纯化、气体配送和回收供应系统 | 氢能设备归M08；催化剂不与气体混为同一细分行业 | [M11](./欧美行业与角色_JTBD_Profiling分析.md#industry-m11) |
| `renewable_fuels` | 可再生燃料 / Renewable Fuels | `chemical` | SAF、可再生柴油、生物醇和合成燃料的化工转化生产 | 发酵平台研发归Biotechnology并加交叉标签；制氢设备归M08 | [M12](./欧美行业与角色_JTBD_Profiling分析.md#industry-m12) |
| `building_hvac_heat_pumps` | 建筑暖通与热泵设备 / Building HVAC & Heat Pumps | `construction` | 热泵、空调、通风、热水设备及建筑控制研发制造 | 施工安装另加承包/服务标签；不是把设备厂等同建筑承包商 | [M13](./欧美行业与角色_JTBD_Profiling分析.md#industry-m13) |
| `cement_concrete` | 水泥与混凝土 / Cement & Concrete | `construction` | 水泥、胶凝材料、预拌/预制混凝土，低碳技术作标签 | 主体是建材供应/产品研发；现场浇筑承包活动另标；不囊括所有材料 | [M14](./欧美行业与角色_JTBD_Profiling分析.md#industry-m14) |
| `prefabricated_modular_buildings` | 装配式与模块化建筑 / Prefabricated & Modular Buildings | `construction` | 工厂化模块/面板系统、结构连接及机电一体化交付 | 按工厂制造/设计/现场安装区分子活动；不等同房产开发或所有建筑 | [M15](./欧美行业与角色_JTBD_Profiling分析.md#industry-m15) |
| `water_wastewater_infrastructure` | 水与污水处理基础设施 / Water & Wastewater Infrastructure | `construction` | 给排水网络、处理工艺/设备、再生水与更新工程 | 水务运营/工程建设/设备研发分别打子活动标签；非所有环保行业 | [M16](./欧美行业与角色_JTBD_Profiling分析.md#industry-m16) |
| `aerospace_space` | 航空航天 / Aerospace & Space | `other` | 飞机、航空推进与航电、卫星及航天器部件/系统；建议从 Other 新增具名行业，Engineering 旧用户可按对象迁移 | 航空运营与旅游服务；陆海军工及纯网络安全不纳入 | [E11](./欧美行业与角色_JTBD_Profiling分析.md#industry-e11) |

## 6. 技术对象 technology_object

对象可以是部件、材料、系统、具体方法或工艺；例如“图像重建方法”是研究对象，“比较图像重建方法”中的“比较”才是任务。允许 0–2 个对象，使单对象问题和双对象比较都能表达。

每个对象的 `allowed_segments` 是本版精确允许关系，不能凭同名自行扩大。对象 key 跨行业复用时必须保持相同定义。本版例如 `microfluidic_cartridge` 同时用于诊断和生命科学研究工具，`metal_am_powder` 同时用于合金材料和增材系统。

目录中的若干对象是初始分组，例如“食品蛋白与纤维配料”；若行为证据表明分组过粗，下一版本拆分。未覆盖的主要对象可在问题正文保留原词，标签数组留空并记录 `not_in_catalog`，不能换成一个仅被顺带提及的近似对象。成本、良率提升、AI 热点、热门等目标或状态均不是技术对象。

下表列出完整对象目录。原文 ID 同时给出允许的细分行业，行业 key 对照第 5 节。通用边界：仅标记问题主要处理的定义内对象，排除顺带提及、优化目标和未登记的其他应用。

| key | 中文／English | 对象定义 | 允许细分行业／原文 |
| --- | --- | --- | --- |
| `imaging_detector` | 成像探测器 / Imaging detector | 成像链路中将入射信号转换为检测信号的器件 | [H01](./欧美行业与角色_JTBD_Profiling分析.md#industry-h01) |
| `image_reconstruction` | 图像重建方法 / Image reconstruction | 从采集数据恢复图像的算法和重建流程 | [H01](./欧美行业与角色_JTBD_Profiling分析.md#industry-h01) |
| `imaging_acquisition_chain` | 成像采集链路 / Imaging acquisition chain | 影像采集硬件及其信号链的系统组合 | [H01](./欧美行业与角色_JTBD_Profiling分析.md#industry-h01) |
| `microfluidic_cartridge` | 微流控卡匣 / Microfluidic cartridge | 集成样本输送、处理或反应的微流控载体 | [H02](./欧美行业与角色_JTBD_Profiling分析.md#industry-h02)、[H13](./欧美行业与角色_JTBD_Profiling分析.md#industry-h13) |
| `diagnostic_reagent_system` | 诊断试剂体系 / Diagnostic reagent system | 用于诊断检测的反应、探针及试剂组合 | [H02](./欧美行业与角色_JTBD_Profiling分析.md#industry-h02) |
| `sample_preparation` | 样本前处理 / Sample preparation | 进入检测或分析前的提取、分离及处理流程 | [H02](./欧美行业与角色_JTBD_Profiling分析.md#industry-h02)、[H13](./欧美行业与角色_JTBD_Profiling分析.md#industry-h13) |
| `glucose_sensor` | 葡萄糖传感器 / Glucose sensor | 用于葡萄糖监测的传感器及校准对象 | [H03](./欧美行业与角色_JTBD_Profiling分析.md#industry-h03) |
| `insulin_delivery_pump` | 胰岛素给药泵 / Insulin delivery pump | 控制微量给药的泵与给药机构 | [H03](./欧美行业与角色_JTBD_Profiling分析.md#industry-h03) |
| `wearable_skin_interface` | 穿戴皮肤界面 / Wearable skin interface | 设备与皮肤之间的黏附、封装及接触界面 | [H03](./欧美行业与角色_JTBD_Profiling分析.md#industry-h03) |
| `surgical_manipulator` | 手术操控机构 / Surgical manipulator | 手术机械臂、腕式器械和执行结构 | [H04](./欧美行业与角色_JTBD_Profiling分析.md#industry-h04) |
| `flexible_surgical_catheter` | 柔性手术导管 / Flexible surgical catheter | 用于腔内操作的柔性导管及传动结构 | [H04](./欧美行业与角色_JTBD_Profiling分析.md#industry-h04) |
| `surgical_navigation` | 手术导航系统 / Surgical navigation | 支持器械定位与操控的视觉导航链路 | [H04](./欧美行业与角色_JTBD_Profiling分析.md#industry-h04) |
| `engineering_polymer` | 工程聚合物 / Engineering polymer | 以结构或电热性能为目标的工程聚合物体系 | [M01](./欧美行业与角色_JTBD_Profiling分析.md#industry-m01) |
| `fiber_composite` | 纤维增强复合材料 / Fiber reinforced composite | 纤维与基体共同构成的工程复合材料 | [M01](./欧美行业与角色_JTBD_Profiling分析.md#industry-m01) |
| `polymer_molding` | 聚合物成型工艺 / Polymer molding | 聚合物或复材的成型、加工窗口及结构形成过程 | [M01](./欧美行业与角色_JTBD_Profiling分析.md#industry-m01) |
| `high_performance_alloy` | 高性能合金 / High performance alloy | 以耐温、疲劳等性能为目标的金属合金体系 | [M02](./欧美行业与角色_JTBD_Profiling分析.md#industry-m02) |
| `metal_am_powder` | 金属增材制造粉末 / Metal additive manufacturing powder | 用于金属增材制造的粉末原料及其适配特性 | [M02](./欧美行业与角色_JTBD_Profiling分析.md#industry-m02)、[E12](./欧美行业与角色_JTBD_Profiling分析.md#industry-e12) |
| `alloy_heat_treatment` | 合金热处理 / Alloy heat treatment | 调控合金组织与性能的热处理路线 | [M02](./欧美行业与角色_JTBD_Profiling分析.md#industry-m02) |
| `technical_ceramic` | 技术陶瓷 / Technical ceramic | 服务电、热或结构功能的陶瓷材料及基材 | [M03](./欧美行业与角色_JTBD_Profiling分析.md#industry-m03) |
| `specialty_glass` | 特种玻璃 / Specialty glass | 面向特定电热或结构性能的玻璃体系 | [M03](./欧美行业与角色_JTBD_Profiling分析.md#industry-m03) |
| `thermal_filler` | 导热填料 / Thermally conductive filler | 用于调节热传导和界面特性的填充材料 | [M03](./欧美行业与角色_JTBD_Profiling分析.md#industry-m03) |
| `battery_electrode_material` | 电池电极材料 / Battery electrode material | 电池正负极活性材料、包覆及颗粒体系 | [M04](./欧美行业与角色_JTBD_Profiling分析.md#industry-m04) |
| `battery_electrolyte` | 电池电解液 / Battery electrolyte | 电池电解液配方及与电极的相容体系 | [M04](./欧美行业与角色_JTBD_Profiling分析.md#industry-m04) |
| `battery_material_recovery` | 电池材料回收工艺 / Battery material recovery | 从退役材料回收、再生电池材料的工艺 | [M04](./欧美行业与角色_JTBD_Profiling分析.md#industry-m04) |
| `traction_motor` | 牵引电机 / Traction motor | 汽车电驱系统中产生牵引动力的电机 | [E05](./欧美行业与角色_JTBD_Profiling分析.md#industry-e05) |
| `traction_inverter` | 牵引逆变器 / Traction inverter | 汽车电驱系统的功率变换与控制部件 | [E05](./欧美行业与角色_JTBD_Profiling分析.md#industry-e05) |
| `electric_drive_assembly` | 电驱总成 / Electric drive assembly | 电机、传动及配套热管理的集成总成 | [E05](./欧美行业与角色_JTBD_Profiling分析.md#industry-e05) |
| `automotive_sensor_fusion` | 车载传感融合 / Automotive sensor fusion | 对摄像头、雷达等车载感知输入进行融合的方法 | [E06](./欧美行业与角色_JTBD_Profiling分析.md#industry-e06) |
| `automated_driving_control` | 自动驾驶决策控制 / Automated driving decision and control | 驾驶自动化中的决策与控制技术链 | [E06](./欧美行业与角色_JTBD_Profiling分析.md#industry-e06) |
| `driving_scenario_validation` | 驾驶场景验证体系 / Driving scenario validation | 面向运行场景、接管及降级的测试对象与方法体系 | [E06](./欧美行业与角色_JTBD_Profiling分析.md#industry-e06) |
| `vehicle_body_joint` | 车身连接结构 / Vehicle body joint | 汽车车身材料之间的连接及接头结构 | [E07](./欧美行业与角色_JTBD_Profiling分析.md#industry-e07) |
| `braking_suspension_component` | 制动与悬架部件 / Braking and suspension component | 汽车制动或悬架系统中的功能部件 | [E07](./欧美行业与角色_JTBD_Profiling分析.md#industry-e07) |
| `automotive_thermal_assembly` | 汽车热管理总成 / Automotive thermal assembly | 车身与底盘应用中的热管理部件组合 | [E07](./欧美行业与角色_JTBD_Profiling分析.md#industry-e07) |
| `commercial_vehicle_architecture` | 商用车辆架构 / Commercial vehicle architecture | 按载荷、动力及作业要求形成的整车系统架构 | [E08](./欧美行业与角色_JTBD_Profiling分析.md#industry-e08) |
| `vocational_body_interface` | 专用车辆上装接口 / Vocational body interface | 底盘与作业上装之间的机械、能源及控制接口 | [E08](./欧美行业与角色_JTBD_Profiling分析.md#industry-e08) |
| `vehicle_duty_cycle` | 车辆工作循环 / Vehicle duty cycle | 用于设计或验证商用车辆的载荷与运行工况序列 | [E08](./欧美行业与角色_JTBD_Profiling分析.md#industry-e08) |
| `chip_interconnect` | 芯片互连 / Chip interconnect | 芯片内部或芯片间用于信号与供电的互连结构 | [E01](./欧美行业与角色_JTBD_Profiling分析.md#industry-e01) |
| `semiconductor_packaging` | 半导体封装 / Semiconductor packaging | 芯片封装的结构、工艺及集成技术 | [E01](./欧美行业与角色_JTBD_Profiling分析.md#industry-e01) |
| `wafer_fabrication` | 晶圆制造工艺 / Wafer fabrication | 在晶圆上形成器件的制造流程及工艺窗口 | [E01](./欧美行业与角色_JTBD_Profiling分析.md#industry-e01) |
| `printed_circuit_board` | 印制电路板 / Printed circuit board | 板级布线、层叠、微孔及相关板材结构 | [E02](./欧美行业与角色_JTBD_Profiling分析.md#industry-e02) |
| `connector_contact` | 连接器接触结构 / Connector contact | 连接器中承担电连接的接触及配合结构 | [E02](./欧美行业与角色_JTBD_Profiling分析.md#industry-e02) |
| `solder_joint` | 焊点 / Solder joint | 电子装配中承担电与机械连接的焊接接头 | [E02](./欧美行业与角色_JTBD_Profiling分析.md#industry-e02) |
| `server_node` | 服务器节点 / Server node | 服务器硬件的计算节点及部件组织 | [E03](./欧美行业与角色_JTBD_Profiling分析.md#industry-e03) |
| `network_switch` | 网络交换机 / Network switch | 计算网络中的交换硬件及其互连结构 | [E03](./欧美行业与角色_JTBD_Profiling分析.md#industry-e03) |
| `rack_cooling` | 机柜散热系统 / Rack cooling | 面向服务器机柜的散热和冷却硬件系统 | [E03](./欧美行业与角色_JTBD_Profiling分析.md#industry-e03) |
| `laser_source` | 激光源 / Laser source | 光子或光学测量系统中的激光发射器件 | [E04](./欧美行业与角色_JTBD_Profiling分析.md#industry-e04) |
| `optical_sensing_chain` | 光学传感链路 / Optical sensing chain | 光路、探测器与信号处理共同形成的测量链 | [E04](./欧美行业与角色_JTBD_Profiling分析.md#industry-e04) |
| `optical_calibration` | 光学标定 / Optical calibration | 确定光学测量关系与误差修正的标定方法 | [E04](./欧美行业与角色_JTBD_Profiling分析.md#industry-e04) |
| `industrial_robot` | 工业机器人本体 / Industrial robot | 工业作业机器人的机械本体及运动能力 | [E09](./欧美行业与角色_JTBD_Profiling分析.md#industry-e09) |
| `end_effector` | 末端执行器 / End effector | 工业机器人接触工件或执行作业的末端机构 | [E09](./欧美行业与角色_JTBD_Profiling分析.md#industry-e09) |
| `automation_cell_control` | 自动化工作单元控制 / Automation cell control | 协调视觉、机器人与工序的单元控制系统 | [E09](./欧美行业与角色_JTBD_Profiling分析.md#industry-e09) |
| `machine_spindle` | 机床主轴 / Machine spindle | 加工设备中的主轴及相关旋转系统 | [E10](./欧美行业与角色_JTBD_Profiling分析.md#industry-e10) |
| `motion_axis` | 运动轴 / Motion axis | 工业设备中承担精密运动的轴系与驱动结构 | [E10](./欧美行业与角色_JTBD_Profiling分析.md#industry-e10) |
| `machining_process` | 机械加工工艺 / Machining process | 刀具、加工参数与过程控制组成的加工方案 | [E10](./欧美行业与角色_JTBD_Profiling分析.md#industry-e10) |
| `powder_energy_delivery` | 铺粉与能量输入系统 / Powder and energy delivery system | 增材设备中的铺粉及能量施加机构 | [E12](./欧美行业与角色_JTBD_Profiling分析.md#industry-e12) |
| `am_in_process_monitoring` | 增材过程监测 / Additive manufacturing process monitoring | 对增材成形过程和缺陷信号的在线监测 | [E12](./欧美行业与角色_JTBD_Profiling分析.md#industry-e12) |
| `engineering_system_design` | 工程系统方案 / Engineering system design | 工程服务中交付的设施或系统设计方案 | [E13](./欧美行业与角色_JTBD_Profiling分析.md#industry-e13) |
| `engineering_simulation_model` | 工程计算模型 / Engineering simulation model | 支持工程设计验证的计算或仿真模型 | [E13](./欧美行业与角色_JTBD_Profiling分析.md#industry-e13) |
| `multidisciplinary_interface` | 跨专业工程接口 / Multidisciplinary engineering interface | 不同工程专业之间需协调的设计接口与交付边界 | [E13](./欧美行业与角色_JTBD_Profiling分析.md#industry-e13) |
| `therapeutic_antibody` | 治疗性抗体 / Therapeutic antibody | 抗体序列、结构及相关治疗性蛋白对象 | [H05](./欧美行业与角色_JTBD_Profiling分析.md#industry-h05) |
| `adc_linker_payload` | 抗体偶联连接子与载荷 / Antibody conjugate linker and payload | 抗体偶联体系中的连接子、载荷及其组合 | [H05](./欧美行业与角色_JTBD_Profiling分析.md#industry-h05) |
| `protein_formulation` | 蛋白制剂 / Protein formulation | 治疗性蛋白的制剂配方与稳定体系 | [H05](./欧美行业与角色_JTBD_Profiling分析.md#industry-h05) |
| `therapeutic_cell` | 治疗性细胞 / Therapeutic cell | 作为治疗技术对象的细胞群体与表征 | [H06](./欧美行业与角色_JTBD_Profiling分析.md#industry-h06) |
| `gene_delivery_vector` | 基因递送载体 / Gene delivery vector | 用于基因递送的载体及递送系统 | [H06](./欧美行业与角色_JTBD_Profiling分析.md#industry-h06) |
| `gene_editing_system` | 基因编辑系统 / Gene editing system | 对遗传物质进行定向编辑的技术系统 | [H06](./欧美行业与角色_JTBD_Profiling分析.md#industry-h06) |
| `bioreactor_process` | 生物反应器工艺 / Bioreactor process | 培养、混合及传质等反应器运行工艺 | [H07](./欧美行业与角色_JTBD_Profiling分析.md#industry-h07) |
| `biologics_purification` | 生物药纯化工艺 / Biologics purification | 生物药下游分离、纯化及工艺转移对象 | [H07](./欧美行业与角色_JTBD_Profiling分析.md#industry-h07) |
| `production_cell_media` | 生产细胞与培养基体系 / Production cell and medium system | 生物药生产细胞株与配套培养基的组合体系 | [H07](./欧美行业与角色_JTBD_Profiling分析.md#industry-h07) |
| `industrial_enzyme` | 工业酶 / Industrial enzyme | 用于工业应用的酶及其制剂或固定化对象 | [H08](./欧美行业与角色_JTBD_Profiling分析.md#industry-h08) |
| `production_microorganism` | 生产微生物 / Production microorganism | 工业生产中承担合成或转化功能的菌株 | [H08](./欧美行业与角色_JTBD_Profiling分析.md#industry-h08) |
| `industrial_fermentation` | 工业发酵工艺 / Industrial fermentation | 工业微生物培养与产物生成的过程体系 | [H08](./欧美行业与角色_JTBD_Profiling分析.md#industry-h08) |
| `research_sequencing_imaging` | 研究用测序与成像平台 / Research sequencing and imaging platform | 用于生命科学研究的测序或成像仪器平台 | [H13](./欧美行业与角色_JTBD_Profiling分析.md#industry-h13) |
| `agricultural_vision` | 农业机器视觉 / Agricultural machine vision | 面向田间目标及作业对象的视觉识别系统 | [H09](./欧美行业与角色_JTBD_Profiling分析.md#industry-h09) |
| `precision_application_control` | 精准施用控制 / Precision application control | 控制喷嘴或施用执行器的定位与作业控制链 | [H09](./欧美行业与角色_JTBD_Profiling分析.md#industry-h09) |
| `agricultural_equipment_interface` | 农业装备接口 / Agricultural equipment interface | 农机、处方图和控制系统之间的数据或设备接口 | [H09](./欧美行业与角色_JTBD_Profiling分析.md#industry-h09) |
| `crop_germplasm` | 作物种质 / Crop germplasm | 作为育种输入与选择对象的种质材料 | [H10](./欧美行业与角色_JTBD_Profiling分析.md#industry-h10) |
| `molecular_breeding_marker` | 分子育种标记 / Molecular breeding marker | 用于育种选择和性状关联的分子标记 | [H10](./欧美行业与角色_JTBD_Profiling分析.md#industry-h10) |
| `field_phenotyping` | 田间表型方法 / Field phenotyping | 对作物性状在田间环境中进行测量和比较的方法 | [H10](./欧美行业与角色_JTBD_Profiling分析.md#industry-h10) |
| `food_matrix` | 食品基质 / Food matrix | 冷冻或方便食品的组成与结构体系 | [H11](./欧美行业与角色_JTBD_Profiling分析.md#industry-h11) |
| `food_thermal_processing` | 食品热加工 / Food thermal processing | 以热处理与热质传递为核心的食品加工过程 | [H11](./欧美行业与角色_JTBD_Profiling分析.md#industry-h11) |
| `food_freezing_drying` | 食品冷冻与干燥 / Food freezing and drying | 冷冻、干燥及相应品质保持工艺 | [H11](./欧美行业与角色_JTBD_Profiling分析.md#industry-h11) |
| `food_protein_fiber` | 食品蛋白与纤维配料 / Food protein and fiber ingredients | 用于营养与功能配方的蛋白和膳食纤维原料 | [H12](./欧美行业与角色_JTBD_Profiling分析.md#industry-h12) |
| `food_emulsion_gel` | 食品乳化与凝胶体系 / Food emulsion and gel system | 影响稳定性与口感的食品乳化或凝胶结构 | [H12](./欧美行业与角色_JTBD_Profiling分析.md#industry-h12) |
| `food_enzyme_fermentation` | 食品酶与发酵配料 / Food enzymes and fermentation ingredients | 用于食品配方和加工的酶、菌种及发酵配料 | [H12](./欧美行业与角色_JTBD_Profiling分析.md#industry-h12) |
| `battery_cell` | 电芯 / Battery cell | 储能系统的电化学储能单元，关注单元结构与运行特性 | [M05](./欧美行业与角色_JTBD_Profiling分析.md#industry-m05) |
| `storage_battery_cluster` | 储能电池簇 / Storage battery cluster | 多电芯或模组构成的储能电池组合 | [M05](./欧美行业与角色_JTBD_Profiling分析.md#industry-m05) |
| `battery_management_system` | 电池管理系统 / Battery management system | 承担电池状态管理、保护及控制的系统 | [M05](./欧美行业与角色_JTBD_Profiling分析.md#industry-m05) |
| `distribution_transformer` | 配电变压器 / Distribution transformer | 配电系统中的电压变换设备 | [M06](./欧美行业与角色_JTBD_Profiling分析.md#industry-m06) |
| `switchgear_protection` | 开关与保护设备 / Switchgear and protection equipment | 用于开断、故障隔离和保护的设备 | [M06](./欧美行业与角色_JTBD_Profiling分析.md#industry-m06) |
| `grid_condition_monitoring` | 电网状态监测 / Grid condition monitoring | 面向电网设备载荷、老化及运行状态的监测技术 | [M06](./欧美行业与角色_JTBD_Profiling分析.md#industry-m06) |
| `photovoltaic_cell` | 光伏电池片 / Photovoltaic cell | 承担光电转换的电池片结构和工艺对象 | [M07](./欧美行业与角色_JTBD_Profiling分析.md#industry-m07) |
| `photovoltaic_module` | 光伏组件 / Photovoltaic module | 电池片互联、封装及保护构成的光伏组件 | [M07](./欧美行业与角色_JTBD_Profiling分析.md#industry-m07) |
| `photovoltaic_inverter` | 光伏逆变器 / Photovoltaic inverter | 光伏发电应用中的功率变换设备 | [M07](./欧美行业与角色_JTBD_Profiling分析.md#industry-m07) |
| `electrolyzer` | 电解槽 / Electrolyzer | 用于制氢的电解反应设备与结构 | [M08](./欧美行业与角色_JTBD_Profiling分析.md#industry-m08) |
| `fuel_cell_membrane_electrode` | 燃料电池膜电极 / Fuel cell membrane electrode assembly | 燃料电池中的膜、电极及相应结构组合 | [M08](./欧美行业与角色_JTBD_Profiling分析.md#industry-m08) |
| `hydrogen_balance_of_plant` | 氢能辅助系统 / Hydrogen balance of plant | 制氢或燃料电池设备配套的水热及辅助运行系统 | [M08](./欧美行业与角色_JTBD_Profiling分析.md#industry-m08) |
| `photoresist` | 光刻胶 / Photoresist | 用于图形化制程的光刻胶材料体系 | [M09](./欧美行业与角色_JTBD_Profiling分析.md#industry-m09) |
| `cmp_slurry` | 化学机械抛光浆料 / Chemical mechanical polishing slurry | 用于 CMP 制程的抛光浆料与配方 | [M09](./欧美行业与角色_JTBD_Profiling分析.md#industry-m09) |
| `electronic_cleaning_plating` | 电子清洗与电镀化学品 / Electronic cleaning and plating chemicals | 电子级清洗液、电镀添加剂及相关应用配方 | [M09](./欧美行业与角色_JTBD_Profiling分析.md#industry-m09) |
| `coating_formulation` | 涂料配方 / Coating formulation | 形成涂层性能的树脂与配套配方体系 | [M10](./欧美行业与角色_JTBD_Profiling分析.md#industry-m10) |
| `adhesive_formulation` | 胶黏剂配方 / Adhesive formulation | 结构粘接或导热粘接使用的胶黏剂体系 | [M10](./欧美行业与角色_JTBD_Profiling分析.md#industry-m10) |
| `sealant_formulation` | 密封剂配方 / Sealant formulation | 用于密封及耐候功能的配方体系 | [M10](./欧美行业与角色_JTBD_Profiling分析.md#industry-m10) |
| `specialty_process_gas` | 工艺特种气体 / Specialty process gas | 工业或电子制造使用的高纯和特种气体 | [M11](./欧美行业与角色_JTBD_Profiling分析.md#industry-m11) |
| `gas_purification` | 气体纯化技术 / Gas purification | 去除工艺气体痕量杂质的设备或工艺 | [M11](./欧美行业与角色_JTBD_Profiling分析.md#industry-m11) |
| `gas_supply_system` | 供气系统 / Gas supply system | 管路、容器、阀件及冗余构成的供气系统 | [M11](./欧美行业与角色_JTBD_Profiling分析.md#industry-m11) |
| `renewable_fuel_feedstock` | 可再生燃料原料 / Renewable fuel feedstock | 用于可再生燃料生产的原料及预处理对象 | [M12](./欧美行业与角色_JTBD_Profiling分析.md#industry-m12) |
| `fuel_conversion_catalyst` | 燃料转化催化剂 / Fuel conversion catalyst | 支持可再生原料转化的催化剂体系 | [M12](./欧美行业与角色_JTBD_Profiling分析.md#industry-m12) |
| `renewable_fuel_process` | 可再生燃料工艺 / Renewable fuel process | 转化、分离和燃料产品形成的生产流程 | [M12](./欧美行业与角色_JTBD_Profiling分析.md#industry-m12) |
| `heat_pump_compressor` | 热泵压缩机 / Heat pump compressor | 热泵系统中的压缩部件 | [M13](./欧美行业与角色_JTBD_Profiling分析.md#industry-m13) |
| `hvac_heat_exchanger` | 暖通换热器 / HVAC heat exchanger | 暖通或热泵设备中的换热部件 | [M13](./欧美行业与角色_JTBD_Profiling分析.md#industry-m13) |
| `refrigerant_control_loop` | 制冷剂回路与控制 / Refrigerant loop and control | 制冷剂循环与相应楼宇或设备控制体系 | [M13](./欧美行业与角色_JTBD_Profiling分析.md#industry-m13) |
| `low_clinker_binder` | 低熟料胶凝体系 / Low clinker binder | 降低熟料比例的水泥胶凝材料组合 | [M14](./欧美行业与角色_JTBD_Profiling分析.md#industry-m14) |
| `supplementary_cementitious_material` | 辅助胶凝材料 / Supplementary cementitious material | 用于混凝土或水泥体系的补充胶凝原料 | [M14](./欧美行业与角色_JTBD_Profiling分析.md#industry-m14) |
| `concrete_mix` | 混凝土配合比 / Concrete mix | 混凝土原料比例与养护适配方案 | [M14](./欧美行业与角色_JTBD_Profiling分析.md#industry-m14) |
| `building_module` | 建筑模块 / Building module | 工厂预制并在现场组装的建筑单元 | [M15](./欧美行业与角色_JTBD_Profiling分析.md#industry-m15) |
| `modular_structural_connection` | 模块结构连接 / Modular structural connection | 模块化建筑单元之间的结构连接件与节点 | [M15](./欧美行业与角色_JTBD_Profiling分析.md#industry-m15) |
| `modular_mep_interface` | 模块机电接口 / Modular MEP interface | 模块化建筑机电系统的安装和连接接口 | [M15](./欧美行业与角色_JTBD_Profiling分析.md#industry-m15) |
| `water_treatment_membrane` | 水处理膜 / Water treatment membrane | 水与污水处理中承担分离功能的膜体系 | [M16](./欧美行业与角色_JTBD_Profiling分析.md#industry-m16) |
| `water_adsorption_media` | 水处理吸附介质 / Water adsorption media | 去除水中目标污染物的吸附材料 | [M16](./欧美行业与角色_JTBD_Profiling分析.md#industry-m16) |
| `aeration_system` | 曝气系统 / Aeration system | 水处理中供氧、气液传递及运行控制的设备系统 | [M16](./欧美行业与角色_JTBD_Profiling分析.md#industry-m16) |
| `aerospace_structure` | 航空航天结构 / Aerospace structure | 航空器或航天器的承载结构及其材料连接 | [E11](./欧美行业与角色_JTBD_Profiling分析.md#industry-e11) |
| `aerospace_propulsion_avionics` | 推进与航电系统 / Aerospace propulsion and avionics | 航空航天应用中的推进或航电技术系统 | [E11](./欧美行业与角色_JTBD_Profiling分析.md#industry-e11) |
| `satellite_system` | 卫星系统 / Satellite system | 卫星平台、载荷及其环境验证所涉及的系统 | [E11](./欧美行业与角色_JTBD_Profiling分析.md#industry-e11) |

## 7. 具体任务 jtbd_task

### 7.1 全部 26 个输入的候选任务

| jtbd_primary | 允许候选任务 |
| --- | --- |
| `technical_solutions` | `solution_search`、`solution_comparison`、`failure_resolution`、`process_optimization` |
| `existing_technologies` | `technology_landscape`、`solution_comparison`、`evidence_search` |
| `product_ideas` | `product_ideation`、`innovation_opportunity_identification` |
| `technical_feasibility` | `feasibility_assessment`、`validation_planning` |
| `patent_ip_risk` | `ip_risk_identification`、`prior_art_search`、`fto_evidence_search`、`design_risk_analysis` |
| `new_research_fields` | `research_field_exploration`、`research_gap_identification` |
| `research_methods` | `research_method_search`、`research_method_comparison`、`validation_planning` |
| `research_trends` | `research_trend_tracking`、`evidence_synthesis` |
| `research_ideas` | `research_ideation`、`research_gap_identification` |
| `patents_literature` | `evidence_search`、`evidence_synthesis` |
| `technology_competitors` | `technology_trend_tracking`、`competitor_tracking`、`technology_landscape` |
| `innovation_opportunities` | `innovation_opportunity_identification`、`licensing_opportunity_assessment` |
| `rd_directions` | `rd_direction_prioritization`、`feasibility_assessment`、`solution_comparison` |
| `patent_landscapes` | `patent_landscape_analysis`、`ip_portfolio_planning` |
| `product_ip_risks` | `ip_risk_identification`、`design_risk_analysis`、`fto_evidence_search`、`collaboration_terms_review` |
| `prior_art` | `prior_art_search`、`novelty_comparison` |
| `fto_design_risks` | `fto_evidence_search`、`design_risk_analysis` |
| `draft_review_patents` | `application_drafting`、`application_review`、`claims_drafting`、`claims_refinement` |
| `office_actions` | `office_action_analysis`、`office_action_response` |
| `fto_searches` | `fto_evidence_search` |
| `draft_review_applications` | `application_drafting`、`application_review` |
| `draft_refine_claims` | `claims_drafting`、`claims_refinement` |
| `technology_trends` | `technology_trend_tracking`、`technology_landscape` |
| `ideas_concepts` | `product_ideation`、`research_ideation`、`innovation_opportunity_identification` |
| `search_draft_patents` | `prior_art_search`、`evidence_search`、`application_drafting`、`claims_drafting` |
| `other` | `task_clarification` |

同一输入有多个候选任务时，一道问题只选一个。例如 `search_draft_patents` 允许检索或起草方向，不要求一题同时完成两种工作。多个输入可共享同一个具体任务，但仍保留原始输入以分析不同需求入口。

`patent_ip_risk` 与 `product_ip_risks` 不合并原始值。前者为较宽的技术／发明 IP 风险入口，后者强调产品使用风险；本版用候选任务和问题范围表达差异。`draft_review_patents` 与 `draft_review_applications` 共享部分工作，但保留不同来源。FTO、现有技术和新颖性差异不能当作完全等价的任务。

`licensing_opportunity_assessment` 和 `collaboration_terms_review` 需要显式场景。仅原始三个输入不足时，从同一输入的其他任务选题。`ip_portfolio_planning` 若缺资产范围，可以保留任务但只能生成规划模板，不能宣称拥有并评估了用户的真实组合。

`other` 在本版只映射 `task_clarification`。自填任务若需要进入具体任务枚举，应由入口层明确解析和保留原文后再建立独立版本的输入契约；本版不暗中推断替换。

### 7.2 完整任务定义与产出约束

| key | 中文／English | 定义 | 边界 | 允许产出 | 上下文要求 |
| --- | --- | --- | --- | --- | --- |
| `solution_search` | 寻找技术方案 / Find technical solutions | 在给定功能或问题下寻找可采用的技术方案 | 不以全领域盘点代替问题导向的寻找 | `candidate_shortlist`、`evidence_table` | `none` |
| `solution_comparison` | 比较技术方案 / Compare technical solutions | 在共同约束与评价条件下比较已识别的路线或方案 | 不等于寻找方案；纯研究方法比较用 research_method_comparison | `comparison_matrix` | `none` |
| `failure_resolution` | 解决技术失效 / Resolve technical failures | 从具体类型的故障或性能失效出发寻找修正措施及验证 | 核心是恢复功能；解释科学机理而无修正目标归 evidence_synthesis | `improvement_plan`、`validation_plan` | `none` |
| `process_optimization` | 优化工艺 / Optimize processes | 调整制造或运行参数、流程以改善良率、一致性或效率 | 排除只改变产品定位或研究命题 | `improvement_plan`、`comparison_matrix` | `none` |
| `technology_landscape` | 梳理现有技术 / Map existing technologies | 组织已有路线、技术类别和成熟度证据 | 静态结构为主；按时间监测用 technology_trend_tracking | `landscape_map`、`evidence_review` | `none` |
| `product_ideation` | 形成产品构思 / Generate product concepts | 从使用问题与技术能力形成可检验的产品或发明概念 | 科学贡献问题用 research_ideation | `concept_brief` | `none` |
| `feasibility_assessment` | 评估技术可行性 / Assess technical feasibility | 判断方案在指定条件下是否具备实施依据并识别证据缺口 | 缺条件时列条件性判断；执行验证计划用 validation_planning | `assessment_brief`、`comparison_matrix` | `none` |
| `validation_planning` | 规划验证 / Plan validation | 设计检验假设或方案的实验、样机或测试路径 | 排除声称实验已完成；研究方法搜寻用 research_method_search | `validation_plan` | `none` |
| `research_field_exploration` | 探索研究领域 / Explore research fields | 梳理新领域的核心问题、研究路线和进入知识基础 | 不以热点排行替代问题结构 | `landscape_map`、`evidence_review` | `none` |
| `research_gap_identification` | 识别研究空白 / Identify research gaps | 基于已有证据与限制指出尚未解决且可研究的问题 | 未检索到不等于不存在；具体提出课题用 research_ideation | `research_agenda`、`evidence_review` | `none` |
| `research_method_search` | 寻找研究方法 / Find research methods | 针对研究问题寻找测量、实验或分析方法 | 不把产品生产流程直接当研究方法 | `candidate_shortlist`、`evidence_table` | `none` |
| `research_method_comparison` | 比较研究方法 / Compare research methods | 比较研究方法的假设、样本要求、适用范围和局限 | 比较产品技术路线用 solution_comparison | `comparison_matrix` | `none` |
| `research_ideation` | 形成研究构思 / Generate research ideas | 将研究空白转成假设、课题和可检验路径 | 不只列宽泛研究方向；产品需求构思用 product_ideation | `research_agenda`、`concept_brief` | `none` |
| `evidence_search` | 检索专利与文献 / Search patents and literature | 围绕明确主题建立可复查的资料集及相关性说明 | 专门为现有技术或 FTO 检索时用专门任务；资料类型写检索范围 | `evidence_table` | `none` |
| `evidence_synthesis` | 综合研究证据 / Synthesize research evidence | 解释多项研究的共同发现、分歧和适用边界 | 不把专利公开当实验验证；纯检索列表用 evidence_search | `evidence_review` | `none` |
| `research_trend_tracking` | 跟踪研究趋势 / Track research trends | 按时间观察科学问题、研究方法或结果的变化 | 技术产品化与产业采用为主用 technology_trend_tracking | `trend_brief`、`landscape_map` | `none` |
| `technology_trend_tracking` | 跟踪技术趋势 / Track technology trends | 按时间跟踪技术路线、性能进展和采用证据 | 单纯静态盘点用 technology_landscape；单纯学术演变用 research_trend_tracking | `trend_brief` | `none` |
| `competitor_tracking` | 跟踪竞争主体 / Track competitors | 跟踪特定类型或指定主体的能力、研发及产品变化 | 未给主体时可以说明筛选方法，不虚构用户的竞争对手 | `trend_brief`、`comparison_matrix`、`landscape_map` | `none` |
| `innovation_opportunity_identification` | 识别创新机会 / Identify innovation opportunities | 从未满足需求、技术能力与应用缺口筛选机会 | 有具体许可交易目标时用 licensing_opportunity_assessment | `candidate_shortlist`、`assessment_brief` | `none` |
| `rd_direction_prioritization` | 排定研发方向 / Prioritize R&D directions | 对研发方向的价值、证据、成熟度和资源要求做取舍 | 未给资源预算时不编造企业真实评分 | `priority_matrix`、`comparison_matrix` | `none` |
| `patent_landscape_analysis` | 分析专利态势 / Analyze patent landscapes | 按主题、主体、时间和家族组织专利布局证据 | 专利态势不等于产品 FTO；自身资产决策用 ip_portfolio_planning | `landscape_map`、`evidence_table` | `none` |
| `prior_art_search` | 检索现有技术 / Search prior art | 针对技术特征和检索目的定位相关既有公开证据 | 需说明检索日期范围；不自动得出新颖性结论 | `evidence_table` | `none` |
| `novelty_comparison` | 比较新颖性差异 / Compare novelty-related features | 将给定技术特征与既有证据逐项比较并标明缺口 | 技术差异不等于可授权判断；缺披露可提供比较方法 | `comparison_matrix`、`evidence_table`、`document_template` | `none` |
| `fto_evidence_search` | 检索 FTO 相关证据 / Search FTO evidence | 围绕产品实施、目标范围和时间搜集权利要求及状态线索 | 与现有技术检索目的不同；缺范围时提供检索框架，不判定安全 | `evidence_table`、`document_template` | `none` |
| `design_risk_analysis` | 分析设计相关专利风险 / Analyze design-related patent risk | 比较设计实施或改动与相关权利要求证据，识别待审问题 | 设计绕开假设须验证；缺具体范围时限于方法与风险清单 | `risk_register`、`comparison_matrix`、`document_template` | `none` |
| `ip_risk_identification` | 识别知识产权风险事项 / Identify IP risk issues | 梳理技术使用、专利或权属相关的证据缺口与行动事项 | 不自动扩展到合同谈判或确定法律意见；具体合同用 collaboration_terms_review | `risk_register`、`document_template` | `none` |
| `application_drafting` | 起草申请文件 / Draft patent applications | 根据技术披露组织申请文件与支持关系 | 不虚构技术特征；只给三个输入时提供模板 | `application_draft`、`document_template` | `disclosure` |
| `application_review` | 审阅申请文件 / Review patent applications | 核对给定文件的技术支持、表述一致性与待修改事项 | 必须有被审阅文件；没有则提供审阅模板 | `review_notes`、`document_template` | `application` |
| `claims_drafting` | 起草权利要求 / Draft patent claims | 从技术披露中组织核心特征和权利要求层级 | 不从行业名称推造发明特征；无披露用模板 | `claims_draft`、`document_template` | `disclosure` |
| `claims_refinement` | 完善权利要求 / Refine patent claims | 对已有权利要求及支持材料提出范围、依赖和表述修改 | 没有原权利要求及支持材料时只提供模板 | `review_notes`、`comparison_matrix`、`document_template` | `claims_and_support` |
| `office_action_analysis` | 分析审查意见 / Analyze office actions | 将给定意见、引证与申请支持材料对应，定位待回应事项 | 不根据行业猜测审查意见或期限；缺材料用模板 | `evidence_table`、`review_notes`、`document_template` | `office_action_package` |
| `office_action_response` | 组织审查答复 / Prepare office action responses | 根据给定审查意见与申请材料组织回应及修改支持 | 缺具体材料只提供答复结构模板 | `response_outline`、`document_template` | `office_action_package` |
| `licensing_opportunity_assessment` | 评估许可与转移机会 / Assess licensing opportunities | 关联技术资产、应用证据和采用方需求，识别交易准备缺口 | 需许可、转移或引入场景；不虚构合作意向 | `transaction_brief`、`candidate_shortlist`、`document_template` | `licensing_context` |
| `collaboration_terms_review` | 梳理合作与权属问题 / Review collaboration and ownership issues | 将合作目标、成果与数据使用对应到待讨论的合同业务问题 | 需合作或合同场景；不因为 Legal 标签自动启用 | `risk_register`、`document_template` | `collaboration_context` |
| `ip_portfolio_planning` | 规划知识产权组合 / Plan IP portfolios | 对技术资产覆盖、业务重点和维护方向形成规划 | 具体方案需要资产范围；无范围仅提供方法模板 | `portfolio_plan`、`priority_matrix`、`document_template` | `portfolio_scope` |
| `task_clarification` | 澄清当前任务 / Clarify the current task | 帮助用户区分任务、所需材料与对应工作成果 | 已有明确任务时不用于替代该任务 | `task_menu` | `none` |

### 7.3 任务与视角允许关系

| 任务 | 允许工作视角 |
| --- | --- |
| `solution_search` | `product_design`、`process_engineering`、`system_integration`、`reliability_engineering`、`invention_development`、`applied_research`、`technology_scouting` |
| `solution_comparison` | `product_design`、`process_engineering`、`system_integration`、`reliability_engineering`、`invention_development`、`applied_research`、`technology_scouting`、`product_strategy` |
| `failure_resolution` | `product_design`、`process_engineering`、`system_integration`、`reliability_engineering`、`applied_research` |
| `process_optimization` | `process_engineering`、`system_integration`、`reliability_engineering`、`applied_research` |
| `technology_landscape` | `product_design`、`process_engineering`、`system_integration`、`invention_development`、`applied_research`、`technology_scouting`、`competitive_intelligence` |
| `product_ideation` | `product_design`、`invention_development`、`technology_scouting`、`product_strategy` |
| `feasibility_assessment` | `product_design`、`process_engineering`、`system_integration`、`reliability_engineering`、`invention_development`、`applied_research`、`technology_scouting`、`product_strategy` |
| `validation_planning` | `product_design`、`process_engineering`、`system_integration`、`reliability_engineering`、`invention_development`、`applied_research`、`scientific_contribution`、`research_methodology` |
| `research_field_exploration` | `applied_research`、`scientific_contribution`、`research_methodology`、`technology_scouting` |
| `research_gap_identification` | `applied_research`、`scientific_contribution`、`research_methodology` |
| `research_method_search` | `applied_research`、`scientific_contribution`、`research_methodology` |
| `research_method_comparison` | `applied_research`、`scientific_contribution`、`research_methodology` |
| `research_ideation` | `applied_research`、`scientific_contribution`、`research_methodology`、`invention_development` |
| `evidence_search` | `product_design`、`invention_development`、`applied_research`、`scientific_contribution`、`research_methodology`、`technology_scouting`、`patent_evidence_analysis` |
| `evidence_synthesis` | `applied_research`、`scientific_contribution`、`research_methodology`、`reliability_engineering`、`technology_scouting`、`patent_evidence_analysis` |
| `research_trend_tracking` | `applied_research`、`scientific_contribution`、`research_methodology`、`technology_scouting` |
| `technology_trend_tracking` | `product_design`、`process_engineering`、`system_integration`、`technology_scouting`、`product_strategy`、`competitive_intelligence` |
| `competitor_tracking` | `competitive_intelligence`、`technology_scouting`、`product_strategy`、`ip_portfolio_management` |
| `innovation_opportunity_identification` | `technology_scouting`、`product_strategy`、`competitive_intelligence`、`invention_development` |
| `rd_direction_prioritization` | `technology_scouting`、`product_strategy`、`applied_research`、`scientific_contribution` |
| `patent_landscape_analysis` | `patent_evidence_analysis`、`ip_portfolio_management`、`competitive_intelligence`、`technology_scouting`、`patent_risk_review` |
| `prior_art_search` | `invention_development`、`patent_evidence_analysis`、`patent_prosecution`、`patent_risk_review` |
| `novelty_comparison` | `invention_development`、`patent_evidence_analysis`、`patent_prosecution`、`patent_risk_review` |
| `fto_evidence_search` | `patent_evidence_analysis`、`patent_risk_review` |
| `design_risk_analysis` | `patent_risk_review`、`patent_evidence_analysis`、`product_design`、`system_integration` |
| `ip_risk_identification` | `patent_risk_review`、`ip_portfolio_management`、`patent_evidence_analysis`、`invention_development`、`product_strategy` |
| `application_drafting` | `patent_prosecution`、`invention_development` |
| `application_review` | `patent_prosecution`、`patent_risk_review` |
| `claims_drafting` | `patent_prosecution`、`invention_development` |
| `claims_refinement` | `patent_prosecution`、`patent_risk_review` |
| `office_action_analysis` | `patent_prosecution`、`patent_evidence_analysis`、`patent_risk_review` |
| `office_action_response` | `patent_prosecution`、`patent_risk_review` |
| `licensing_opportunity_assessment` | `ip_commercialization`、`technology_scouting` |
| `collaboration_terms_review` | `commercial_legal_review`、`ip_commercialization` |
| `ip_portfolio_planning` | `ip_portfolio_management`、`patent_evidence_analysis` |
| `task_clarification` | `task_exploration` |

### 7.4 上下文要求

| 要求 key | 具体含义 | 缺失时 |
| --- | --- | --- |
| `none` | 无需额外项目材料即可生成一般性问题；不允许捏造具体项目事实。 | 可做一般性方法或研究内容；不生成虚构项目事实 |
| `disclosure` | 具体输出需给定技术披露及支持材料。 | 使用 document_template，answer_mode=template |
| `application` | 具体输出需给定被审阅申请文件。 | 使用 document_template，answer_mode=template |
| `claims_and_support` | 具体输出需给定原权利要求及技术支持材料。 | 使用 document_template，answer_mode=template |
| `office_action_package` | 具体输出需给定审查意见、引证与相关申请材料；涉及日期和范围需明确。 | 使用 document_template，answer_mode=template |
| `licensing_context` | 明确给出许可、转移或技术引入场景；仅 industry 和 role 不满足条件。 | 排除该任务候选 |
| `collaboration_context` | 明确给出合作或合同场景；仅 Legal 或产品 IP 风险输入不满足条件。 | 排除该任务候选 |
| `portfolio_scope` | 具体布局方案需给定资产组合范围及业务技术重点。 | 使用 document_template，answer_mode=template |

## 8. 预期产出 desired_output

预期产出描述用户拿到的工作成果。`comparison_matrix` 可以出现在网页或报告中；这些文件格式不影响该标签。`scout_report` 等现有内容类别仍属于旧 categories 维度，与这里没有一对一替换关系。

实际回答可以附带辅助材料，但按主要交付物选择一个产出标签。若同一条目承诺多个独立主要成果，拆成问题条目；不依靠大量产出标签覆盖不清晰的选题。

| key | 中文／English | 定义 | 边界 |
| --- | --- | --- | --- |
| `candidate_shortlist` | 候选清单 / Candidate shortlist | 列明候选、筛选依据和适用条件 | 不仅罗列名称；有同口径横向比较时优先 comparison_matrix |
| `comparison_matrix` | 对比矩阵 / Comparison matrix | 在统一指标、条件和证据口径下比较多个选项 | 不把不同条件的数值直接排名；单方案可行性归 assessment_brief |
| `improvement_plan` | 改进方案 / Improvement plan | 给出问题、改进措施、依据和验证方式 | 不仅解释失效机理；纯验证步骤归 validation_plan |
| `landscape_map` | 领域图谱 / Landscape map | 按主题、技术路线或主体组织领域覆盖与关系 | 技术和专利图谱由任务区别；时间变化为主归 trend_brief |
| `concept_brief` | 构思说明 / Concept brief | 描述问题、构思差异、依据和最小验证 | 不声称已完成实验或已确认专利新颖性 |
| `assessment_brief` | 评估说明 / Assessment brief | 对明确问题整理条件、证据、缺口及继续判断的依据 | 不是无条件可行或安全的结论；多选项对照归 comparison_matrix |
| `validation_plan` | 验证计划 / Validation plan | 写明假设、样本或工况、方法、指标和判定规则 | 不把计划写成已完成的实验结果 |
| `research_agenda` | 研究问题清单 / Research agenda | 提出研究空白、具体问题、依据和可检验路径 | 产品构思归 concept_brief，不只罗列流行关键词 |
| `evidence_table` | 证据表 / Evidence table | 将来源、定位、技术特征或结论与支持证据对应 | 不编造文献或专利；综合解释为主归 evidence_review |
| `evidence_review` | 证据综述 / Evidence review | 对多项证据做综合解释、分歧分析和局限说明 | 不仅列检索结果；动态跟踪为主归 trend_brief |
| `trend_brief` | 趋势简报 / Trend brief | 在明确时间窗口内说明变化、证据及影响 | 不以静态图谱代替时间变化，不把预测当已发生事件 |
| `priority_matrix` | 优先级矩阵 / Priority matrix | 按目标、评价维度和证据安排候选优先级 | 说明权衡与不确定性，不凭任意分数制造确定排名 |
| `risk_register` | 风险事项清单 / Risk register | 记录风险问题、适用范围、证据缺口和待执行行动 | 不是无范围的法律结论；事实检索本身归 evidence_table |
| `application_draft` | 申请文件草稿 / Application draft | 基于给定技术披露组织说明书、实施例和相关申请段落 | 须有披露材料；没有材料用 document_template |
| `review_notes` | 审阅与修改意见 / Review notes | 对已有文件逐项指出问题、依据和修改建议 | 须有被审阅文本；没有文本用 document_template |
| `claims_draft` | 权利要求草稿 / Claims draft | 基于明确技术披露组织权利要求层级和支持依据 | 不虚构技术特征；没有披露材料用 document_template |
| `response_outline` | 审查答复提纲 / Office action response outline | 依据给定审查意见和申请材料整理答复结构与支持证据 | 没有具体意见及相关文件时用 document_template |
| `transaction_brief` | 许可与转移准备说明 / Transaction brief | 关联技术资产、采用方需求、开发缺口和交易准备 | 不编造交易意向或估值；单纯技术名单归 candidate_shortlist |
| `portfolio_plan` | 组合布局方案 / Portfolio plan | 将明确资产范围与业务技术重点对应，提出维护或补充方向 | 须有组合或资产范围；通用规划方法用 document_template |
| `task_menu` | 任务与产出导航 / Task menu | 帮助用户区分可选任务、前提和相应交付物 | 不是宣称已经明确的用户需求 |
| `document_template` | 工作文档模板 / Working document template | 提供字段、结构、填写说明和待补材料清单 | 模板中的假设或占位符不能写成真实用户材料或已完成结论 |

## 9. 组合与生成规则

| 编号 | 规则 | 执行要求 |
| --- | --- | --- |
| S01 | 保持输入 | input_profile 只保存经精确别名表转换后的三个原始选择；生成器不得改写。other 是用户选择，null 是内容尚未细分，二者不可混用。 |
| S02 | 先任务后视角 | jtbd_task 必须来自 jtbd_allowed_tasks[input_profile.jtbd_primary]。候选任务不是频率排序；只有一个主要任务，不把一项复合入口机械生成成复合问题。 |
| S03 | 角色是偏好而非禁止 | 优先取所选任务 allowed_perspectives 与 role_preferred_perspectives 的交集。交集为空时从任务允许视角中选择并记录 task_override，保留原始 role；不把跨角色任务拒绝或偷换为角色默认任务。 |
| S04 | 条件视角不代表身份 | 视角只描述内容工作立场，不推定独立发明人、高校身份、律师资格、客户委托或拥有专利组合。licensing_opportunity_assessment 与 collaboration_terms_review 必须满足明确场景门槛；不满足时删除该候选，改选同一原始 JTBD 下其他可用任务。 |
| S05 | 行业候选范围 | 无额外上下文时，具名行业只允许选择 entry_industry 相同的细分行业，记录 within_input_exploration，或保持 null 并说明 broad_scope。其他行业明确作为主工作对象出现在提供的上下文时才可跨行业，记录 cross_industry_explicit_context 和依据。 |
| S06 | Other 与覆盖缺口 | industry_type=other 且没有明确上下文时 industry_segment 必须为 null。aerospace_space 仅在明确航空航天工作场景时选择。具名输入下的未覆盖对象也不强塞给现有 42 项，记录 not_in_catalog；可使用问题正文中的原始对象词，但不创造枚举。 |
| S07 | 技术对象 | technology_object 为 0–2 个不重复对象，必须均允许出现在已选 industry_segment。industry_segment 为 null 时对象数组为空；问题主要研究对象不在目录时留空并记录 not_in_catalog，不用顺带提及的已知对象冒充。 |
| S08 | 明确与探索的来源 | 只有传入上下文明确给出相应细分领域或对象时才可记录 explicit_context；否则记为探索。界面语言、模型猜测和本批次生成结果都不是用户确认依据。 |
| S09 | 产出一致 | desired_output 必须属于任务的 allowed_outputs；模板模式只允许 document_template。task_clarification 必须搭配 task_exploration 和 task_menu。内容 categories 或文件格式不得直接替代 desired_output。 |
| S10 | 缺材料的回退 | disclosure、application、claims_and_support、office_action_package、portfolio_scope 缺少所需材料时 answer_mode=template 且 desired_output=document_template，问题写成方法或模板请求；条件门槛 licensing_context/collaboration_context 不能靠模板回退绕过。 |
| S11 | 三输入的默认边界 | 仅有三个输入时生成一般性问题或模板；不伪造具体竞争者、产品版本、客户预算、实验数据、国家或专利材料。具体项目答案另需提供上下文。原研究面向欧美不代表用户已选择美国。 |
| S12 | Other 任务 | jtbd_primary=other 在本版只生成 task_clarification，以已有角色或行业解释任务选项。即使补充文本表达了其他任务，也先在入口层明确选择或保留原始输入并另作解析升级，不能悄悄改变本版映射。 |
| S13 | 枚举不存在 | 未知枚举一律拒绝；不让模型即时增加 other、unknown 或同义 key。使用字段规定的 null/空数组及原因，或进入待新增标签清单。 |
| S14 | 问题和答案匹配 | 先选择合法组合再生成问题和答案。除结构检查外还要复核语义：主视角、任务、对象与实际内容一致；只有顺带出现的概念不能获得标签。检索无结果也要如实记录，不能为满足标签编造答案。 |
| S15 | 证据及范围 | 原文角色/行业 ID 是设计溯源，不是生成答案的事实引用。生成答案须另记录实际检索来源、时间及适用条件；趋势题需明确时间窗口，具体产品风险题需明确产品、地域和评估日期，否则保持通用证据框架。 |
| S16 | 冻结版本 | 每次展示保存 content_id、question_version、answer_version、taxonomy_version 和标签快照；已曝光内容不得原地重写标签。重新分类产生新版本，历史曝光保持原快照。 |

### 9.1 生成顺序

1. 将已登记的旧字段／旧值精确转换成三个标准输入，保存原始请求与标准结果。未知值、空值或冲突进入输入错误，不借助 other 隐藏错误。
2. 按原始 JTBD 取候选任务，去掉未满足明确场景门槛的候选，再选一个任务。候选映射不带市场频率或点击率权重。
3. 用任务允许视角与角色优先视角求交集；无交集时按任务覆盖，保留 task_override。任务为澄清时固定 task_exploration。
4. 依据泛行业选探索子领域，或按明确上下文选择领域；对象必须属于该子领域。无法细分时按契约保留 null／空数组及原因。
5. 按任务和现有材料选择产出与 answer_mode；需要具体文件却没有材料时，改成明确的模板题。
6. 用选定的视角、对象、任务和产出编写问题及答案要求。问题应能看出主要工作动作，不能只生成“某行业最新趋势”作为所有任务的通用标题。
7. 检索并生成答案，另行保存真正用于回答的来源与研究范围。原文 ID 只作为设计示例的来源。
8. 做结构校验、跨字段规则校验和语义复核。任一不通过则修订或暂缓展示，不能通过增加标签掩盖题文不一致。
9. 冻结条目版本与标签快照，再展示并关联曝光、点击和后续行为。

### 9.2 批量生成与多样性

在同一组输入下轮换合法视角、子领域、对象或任务，避免所有问题只来自一个热门子行业。不做所有维度的笛卡尔积，也不假定 546 个原文组合都适用于每个用户。

初始轮换仅是生成覆盖策略，不能标为真实偏好或设定无依据的点击提升预期。比较视角效果时尽量固定任务、对象、产出、位置及人群；第 10 节前三个例子用于展示多样性，同时改变了任务，不构成单变量实验。

去重以问题意图、对象和实际答案覆盖为依据。同一问题的同义改写不应因换了标签而重复入库；确需不同视角时，问题和主要产出应体现该差别。

### 9.3 可复用的生成约束文字

> 只使用本请求提供的枚举目录与允许组合。保留 input_profile，不推定用户的细分身份或兴趣。先选择一个 jtbd_task，再选择允许的 role_perspective、industry_segment、technology_object 和 desired_output。未知的主要行业或对象按契约留空并说明原因，不创造 key。只生成一道主要问题和相应答案要求。缺少具体文件时生成模板题，不编造披露、专利文件、实验数据或用户背景。返回选题来源、answer_mode 与设计引用。实际生成答案时另行检索事实来源，并复核答案与标签一致。

未来可由后端先确定候选组合，将字段以 const 或缩小后的 enum 传给模型，也可允许模型在请求限定的合法组合中选择。无论采用哪种方式，五个核心维度的 key 均来自配套目录。

## 10. 可核对的生成示例

以下均为规则演示，不代表真实用户或已经生成的答案。Q10 的补充工作场景也是假设输入。问题后的要求说明答案应怎样组织，不编造实际研究结论。

### Q01 · 哪些芯片互连方案可以在功耗、带宽与制造成本之间取得不同取舍？

输入：`rd_engineer`、`electronics_manufacturing`、`technical_solutions`。

| 标签 | 值 |
| --- | --- |
| role_perspective | `product_design` |
| industry_segment | `semiconductors` |
| technology_object | `chip_interconnect` |
| jtbd_task | `solution_comparison` |
| desired_output | `comparison_matrix` |

模式：`general_guidance`；视角来源：`role_preferred`；行业来源：`within_input_exploration`。

答案要求：按统一条件列出候选路线、比较维度与证据。 标明不可直接比较的数据及缺口，不编造统一实验结果。

设计来源：[E01-R01](./欧美行业与角色_JTBD_Profiling分析.md#job-e01-r01)。

### Q02 · 哪些工艺改进可以减少芯片互连制造缺陷、提高良率？

输入：`rd_engineer`、`electronics_manufacturing`、`technical_solutions`。

| 标签 | 值 |
| --- | --- |
| role_perspective | `process_engineering` |
| industry_segment | `semiconductors` |
| technology_object | `chip_interconnect` |
| jtbd_task | `process_optimization` |
| desired_output | `improvement_plan` |

模式：`general_guidance`；视角来源：`role_preferred`；行业来源：`within_input_exploration`。

答案要求：按缺陷类型整理工艺调整、证据及适用条件。 提出验证步骤，不假定知道用户的实际良率。

设计来源：[E01-R01](./欧美行业与角色_JTBD_Profiling分析.md#job-e01-r01)。

### Q03 · 芯片互连在热循环下发生失效时，有哪些结构或材料改进方案？

输入：`rd_engineer`、`electronics_manufacturing`、`technical_solutions`。

| 标签 | 值 |
| --- | --- |
| role_perspective | `reliability_engineering` |
| industry_segment | `semiconductors` |
| technology_object | `chip_interconnect` |
| jtbd_task | `failure_resolution` |
| desired_output | `improvement_plan` |

模式：`general_guidance`；视角来源：`role_preferred`；行业来源：`within_input_exploration`。

答案要求：关联失效现象、候选原因、改进措施和验证。 比较证据的工况，不把一般机理写成用户项目已确认根因。

设计来源：[E01-R01](./欧美行业与角色_JTBD_Profiling分析.md#job-e01-r01)、[E01-R03](./欧美行业与角色_JTBD_Profiling分析.md#job-e01-r03)。

### Q04 · 比较生物反应器放大前后传质差异，可以采用哪些实验与测量方法？

输入：`researcher`、`biotech`、`research_methods`。

| 标签 | 值 |
| --- | --- |
| role_perspective | `research_methodology` |
| industry_segment | `biologics_process_manufacturing` |
| technology_object | `bioreactor_process` |
| jtbd_task | `research_method_comparison` |
| desired_output | `comparison_matrix` |

模式：`general_guidance`；视角来源：`role_preferred`；行业来源：`within_input_exploration`。

答案要求：比较方法的测量对象、实验条件、局限与可复现性。

设计来源：[H07-R03](./欧美行业与角色_JTBD_Profiling分析.md#job-h07-r03)、[H07-R04](./欧美行业与角色_JTBD_Profiling分析.md#job-h07-r04)。

### Q05 · 固定式储能电池管理系统中，有哪些值得进一步验证的技术创新机会？

输入：`innovation_product_strategy`、`energy`、`innovation_opportunities`。

| 标签 | 值 |
| --- | --- |
| role_perspective | `technology_scouting` |
| industry_segment | `batteries_stationary_storage` |
| technology_object | `battery_management_system` |
| jtbd_task | `innovation_opportunity_identification` |
| desired_output | `candidate_shortlist` |

模式：`general_guidance`；视角来源：`role_preferred`；行业来源：`within_input_exploration`。

答案要求：机会须关联使用问题、技术证据和待验证条件。 不将研究信号直接写成已有商业需求。

设计来源：[M05-R05](./欧美行业与角色_JTBD_Profiling分析.md#job-m05-r05)。

### Q06 · 为诊断微流控卡匣准备 FTO 相关证据检索，应如何界定技术特征、范围并组织结果？

输入：`in_house_ip_legal`、`medical_devices`、`fto_design_risks`。

| 标签 | 值 |
| --- | --- |
| role_perspective | `patent_risk_review` |
| industry_segment | `in_vitro_diagnostics` |
| technology_object | `microfluidic_cartridge` |
| jtbd_task | `fto_evidence_search` |
| desired_output | `evidence_table` |

模式：`general_guidance`；视角来源：`role_preferred`；行业来源：`within_input_exploration`。

答案要求：先列待明确的实施方案、地域及评估日期。 给出检索与证据组织方法，不输出具体产品可自由实施的结论。

设计来源：[H02-R08](./欧美行业与角色_JTBD_Profiling分析.md#job-h02-r08)、[H02-R11](./欧美行业与角色_JTBD_Profiling分析.md#job-h02-r11)。

### Q07 · 针对半导体封装技术，如何建立关联审查意见、引证和原始披露的答复工作模板？

输入：`patent_ip_services`、`electronics_manufacturing`、`office_actions`。

| 标签 | 值 |
| --- | --- |
| role_perspective | `patent_prosecution` |
| industry_segment | `semiconductors` |
| technology_object | `semiconductor_packaging` |
| jtbd_task | `office_action_response` |
| desired_output | `document_template` |

模式：`template`；视角来源：`role_preferred`；行业来源：`within_input_exploration`。

答案要求：保留意见、引证、支持位置、答复路径等待填字段。 没有实际审查文件，所有占位内容均标明，不虚构期限。

设计来源：[E01-R13](./欧美行业与角色_JTBD_Profiling分析.md#job-e01-r13)。

### Q08 · 在选定的近十二个月观察窗口中，光刻胶技术有哪些值得跟踪的进展与验证难点？

输入：`other`、`chemical`、`technology_trends`。

| 标签 | 值 |
| --- | --- |
| role_perspective | `technology_scouting` |
| industry_segment | `electronic_chemicals` |
| technology_object | `photoresist` |
| jtbd_task | `technology_trend_tracking` |
| desired_output | `trend_brief` |

模式：`general_guidance`；视角来源：`task_override`；行业来源：`within_input_exploration`。

答案要求：执行时明确起止日期并核对实际来源。 将研发结果、产品公告与采用证据分别说明。

设计来源：[M09-R05](./欧美行业与角色_JTBD_Profiling分析.md#job-m09-r05)。

### Q09 · 寻找技术方案、评估可行性和检索专利分别适用于什么工作，需要准备什么材料？

输入：`other`、`other`、`other`。

| 标签 | 值 |
| --- | --- |
| role_perspective | `task_exploration` |
| industry_segment | `None` |
| technology_object | [] |
| jtbd_task | `task_clarification` |
| desired_output | `task_menu` |

模式：`general_guidance`；视角来源：`task_exploration`；行业来源：`unresolved`。

答案要求：解释各任务的目的、输入和产出，供用户选择。 不填补用户的角色或行业。

设计来源：[R00](./欧美行业与角色_JTBD_Profiling分析.md#role-r00)。

### Q10 · 卫星系统方案比较中，应如何组织质量、功耗、接口与环境验证的取舍？

输入：`rd_engineer`、`other`、`technical_solutions`。

示例补充上下文：{"work_domain": "卫星系统研发"}。

| 标签 | 值 |
| --- | --- |
| role_perspective | `system_integration` |
| industry_segment | `aerospace_space` |
| technology_object | `satellite_system` |
| jtbd_task | `solution_comparison` |
| desired_output | `comparison_matrix` |

模式：`general_guidance`；视角来源：`role_preferred`；行业来源：`explicit_context`。

答案要求：给出系统方案比较框架和需要补充的设计约束。

设计来源：[E11-R01](./欧美行业与角色_JTBD_Profiling分析.md#job-e11-r01)。

### Q11 · 评估当前材料方案的技术可行性，应准备哪些性能约束、加工条件与验证证据？

输入：`rd_engineer`、`materials`、`technical_feasibility`。

| 标签 | 值 |
| --- | --- |
| role_perspective | `product_design` |
| industry_segment | `None` |
| technology_object | [] |
| jtbd_task | `feasibility_assessment` |
| desired_output | `assessment_brief` |

模式：`general_guidance`；视角来源：`role_preferred`；行业来源：`unresolved`。

答案要求：在材料大类层面给出评估框架，不擅自选定材料体系。

设计来源：[R01](./欧美行业与角色_JTBD_Profiling分析.md#role-r01)。

### Q12 · 检索半导体封装构思的现有技术时，应如何拆分技术特征并组织证据？

输入：`rd_engineer`、`electronics_manufacturing`、`prior_art`。

| 标签 | 值 |
| --- | --- |
| role_perspective | `invention_development` |
| industry_segment | `semiconductors` |
| technology_object | `semiconductor_packaging` |
| jtbd_task | `prior_art_search` |
| desired_output | `evidence_table` |

模式：`general_guidance`；视角来源：`role_preferred`；行业来源：`within_input_exploration`。

答案要求：给出特征拆分、检索范围和记录方式。 角色与现有 UI 默认任务不同，仍保留明确选择的 prior_art。

设计来源：[E01-R02](./欧美行业与角色_JTBD_Profiling分析.md#job-e01-r02)、[E01-R11](./欧美行业与角色_JTBD_Profiling分析.md#job-e01-r11)。

### Q13 · 为固定式储能系统评估 BMS 集成方案时，应核对哪些接口、保护与验证条件？

输入：`rd_engineer`、`materials`、`technical_feasibility`。

示例补充上下文：{"work_domain": "本次明确要评估固定式储能 BMS 系统集成"}。

| 标签 | 值 |
| --- | --- |
| role_perspective | `system_integration` |
| industry_segment | `batteries_stationary_storage` |
| technology_object | `battery_management_system` |
| jtbd_task | `feasibility_assessment` |
| desired_output | `assessment_brief` |

模式：`general_guidance`；视角来源：`role_preferred`；行业来源：`cross_industry_explicit_context`。

答案要求：评估的主对象为已明确的系统集成，保留原始 materials 入口。 缺少具体规格时列出条件与证据要求，不给出项目已可行结论。

设计来源：[M05-R01](./欧美行业与角色_JTBD_Profiling分析.md#job-m05-r01)。

### Q14 · 比较半导体器件的电迁移模型时，应如何组织适用条件与验证数据？

输入：`researcher`、`electronics_manufacturing`、`research_methods`。

| 标签 | 值 |
| --- | --- |
| role_perspective | `research_methodology` |
| industry_segment | `semiconductors` |
| technology_object | [] |
| jtbd_task | `research_method_comparison` |
| desired_output | `comparison_matrix` |

模式：`general_guidance`；视角来源：`role_preferred`；行业来源：`within_input_exploration`。

答案要求：当前对象字典没有专门的电迁移模型，正文保留对象名称，标签不强行换成顺带提及的部件。 明确模型假设、可比数据与证据缺口。

设计来源：[E01-R03](./欧美行业与角色_JTBD_Profiling分析.md#job-e01-r03)。

### 10.1 一条完整记录的结构示意

这是记录示例，不是 JSON Schema。所有示例的完整记录，包括未细分原因，都保存在 tag-catalog.json 的 examples 中。

```json
{
  "example_id": "Q01",
  "taxonomy_version": "1.0.0",
  "input_profile": {
    "job_role": "rd_engineer",
    "industry_type": "electronics_manufacturing",
    "jtbd_primary": "technical_solutions"
  },
  "tags": {
    "role_perspective": "product_design",
    "industry_segment": "semiconductors",
    "technology_object": [
      "chip_interconnect"
    ],
    "jtbd_task": "solution_comparison",
    "desired_output": "comparison_matrix"
  },
  "selection": {
    "perspective": "role_preferred",
    "industry": "within_input_exploration",
    "objects": "within_segment_exploration",
    "industry_unresolved_reason": null,
    "object_unresolved_reason": null
  },
  "answer_mode": "general_guidance",
  "provided_context": {},
  "question": "哪些芯片互连方案可以在功耗、带宽与制造成本之间取得不同取舍？",
  "answer_requirements": [
    "按统一条件列出候选路线、比较维度与证据。",
    "标明不可直接比较的数据及缺口，不编造统一实验结果。"
  ],
  "design_source_refs": [
    "E01-R01"
  ]
}
```

### 10.2 反例与预期处理

| 编号 | 基于示例及改动 | 预期处理 | 原因 |
| --- | --- | --- | --- |
| N01 | Q01：{"tags.role_perspective": "rd_engineer"} | reject | 原始角色值不是工作视角枚举。 |
| N02 | Q01：{"tags.technology_object": ["battery_management_system"]} | reject | 对象未在半导体细分行业的允许范围内。 |
| N03 | Q01：{"tags.jtbd_task": "claims_drafting"} | reject | technical_solutions 的允许任务不包含权利要求起草。 |
| N04 | Q01：{"tags.desired_output": "scout_report"} | reject | 旧内容类别不是预期产出枚举。 |
| N05 | Q09：{"tags.industry_segment": "aerospace_space", "selection.industry": "within_input_exploration", "selection.industry_unresolved_reason": null, "selection.object_unresolved_reason": "broad_scope"} | reject | 没有明确航空航天上下文，other 不自动映射航空航天。 |
| N06 | Q07：{"tags.desired_output": "response_outline", "answer_mode": "case_specific"} | reject | 缺审查意见与申请材料，不得生成具体项目答复。 |
| N07 | Q05：{"tags.jtbd_task": "licensing_opportunity_assessment", "tags.desired_output": "transaction_brief"} | reject | 虽然入口允许候选任务，但未满足明确许可或转移场景门槛。 |
| N08 | Q01：{"tags.technology_object": ["chip_interconnect", "chip_interconnect"]} | reject | 对象数组不得重复。 |
| N09 | Q01：{"input_profile.job_role": "rd_engineer_inventor"} | normalize_then_validate | 这是受支持的旧输入别名，入口转换为 rd_engineer 后再校验，不能原样进入标准输入。 |
| N10 | Q01：{"question": "有哪些改善服务器机柜冷却的工艺？"} | semantic_review_reject | 枚举可以通过结构检查，但问题对象与半导体芯片互连标签不一致。 |

## 11. 曝光、点击与推荐优化

标签首先描述内容，推荐偏好由行为逐步估计。点击一次发明验证内容不能把用户认定为独立发明人；没有点击也不一定表示不感兴趣，尤其需要区分是否实际曝光。

有效曝光的可见性阈值由产品埋点统一定义并版本化，不由 LLM 生成。每条曝光有唯一 impression_id；多次真实展示可以分别产生曝光，重复采集的同一次展示要去重。点击必须关联实际曝光。

| 事件／信息 | 必需内容 |
| --- | --- |
| 曝光 | `impression_id`、`content_id`、`question_version`、`answer_version`、`taxonomy_version`、`input_profile_snapshot`、`tags_snapshot`、`selection_snapshot`、`answer_mode`、`timestamp`、`placement`、`position`、`recommendation_policy_version` |
| 点击 | `event_id`、`impression_id`、`content_id`、`timestamp` |
| 推荐补充结果 | `answer_view`、`evidence_saved`、`task_started`、`task_completed`、`useful_feedback` |

计算标签 CTR：**带该标签且有至少一次有效点击的曝光数 ÷ 带该标签的有效曝光数**。同一 impression_id 多次点击在这个指标中只算一次有点击；曝光为零时结果为不可估计。

统计可以从单维度开始，再看 `role_perspective × jtbd_task` 或 `industry_segment × technology_object`。带两个技术对象的同一次曝光可进入两个对象的统计，但总体曝光只计一次；不同标签的统计不能相加当总体结果。

至少按输入群体、展示位置、观察窗口和推荐策略版本检查差异，展示样本量与不确定性。多个标签共同出现时，观察到的是关联；不能把整条内容的点击完全归功于每个 tag。若要估计某个视角的贡献，需要在可比人群及曝光条件下控制其他因素或进行实验。

新标签和低曝光标签先使用上层角色、泛行业或任务信号，保留探索机会，不因少量未点击立即淘汰。探索内容与明确上下文匹配内容可通过 selection_snapshot 分开分析。批量生成数量不等于曝光数量。

有条件时进一步记录查看答案、保存证据、启动任务、完成任务与有用反馈。CTR 是早期兴趣信号，不能单独证明答案帮助用户完成工作。

## 12. 与现有项目的衔接

当前 `src/recommendation_contents/schemas.py` 通过 `enum_entities.json` 读取旧的 role、industry、jtbd、sub_industry、categories，并未使用本目录。本轮只新增规则资料。

输入兼容可复用 `cases/onboarding_field_mapping.json` 与 `src/recommendation_contents/onboarding_fields.py` 中的精确映射，例如：

- `rd_engineer_inventor` → `rd_engineer`。
- `researcher_scientist` → `researcher`。
- `biotechnology` → `biotech`。
- `food`、`farming_production` → `food_farming_production`，不能从合并后的值反向猜出原来的两个入口。
- `find_technical_solutions` → `technical_solutions`。其余 JTBD 旧值完整映射见配套目录 `legacy_input_aliases.jtbd`。

这些转换用于原始输入层。旧 jtbd 数组仍表示原来的主要任务集合，不能直接当作新的 jtbd_task；数组包含多个主要任务时先分请求。旧 sub_industry 与新 42 项粒度不同，必须依据原问题／答案重新分类，不能全部字符串替换。例如 `ev_and_battery_systems` 可能涉及汽车电驱、储能系统或材料，不能无证据强映射为一个新值。

后续接入应增加新标签对象与 taxonomy_version，保留历史元数据及旧值转换来源。categories、keywords、title、prompt 等已有字段可以继续发挥原用途；不把 categories 改写成 desired_output，也不把关键词直接当受控技术对象。

## 13. 版本、维护与后续 schema 验收

### 13.1 标签变更规则

key 的含义一经用于曝光便保持稳定。只改展示文案或澄清不改变含义的说明可以发布补丁版本；增加枚举、对象适用关系或候选组合发布次版本；删除、合并、拆分含义或不兼容契约发布主版本。即使增加枚举也必须保留内容所用版本。

每条枚举记录 status、introduced_in、replaced_by；本版均为 active，表示目录中可用，不表示已上线。废弃记录仍可解析历史内容，不立即从历史字典中删除。合并或拆分应记录旧新关系及影响范围，重新打标产生新内容版本。

新增 tag 的依据可以是反复出现的目录缺口、无法清晰区分的现有含义或足够的行为／访谈证据。LLM 可以提交候选词及理由，但不能在生成结果中直接使用未登记 key。热点更新改变研究素材与时效信息，不应频繁改写行业主分类。

### 13.2 schema 需要承担的检查

- 原始输入只能是精确的 6、11、26 个存储值；五个维度值来自 tag-catalog.json。
- 单值字段、对象数量与去重、null／空数组对应原因、必填元数据及版本正确。
- JTBD 输入与任务、任务与视角、任务与产出、行业与对象之间的交叉关系合法。
- 用户角色与任务不一致时允许按规则选择任务视角，不能照搬旧 UI 映射作为全局禁止条件。
- Other、目录外对象、明确跨行业上下文、缺文件模板回退和条件任务门槛均有确定处理方式。
- Q01–Q14 应满足结构与规则；N01–N08 应被拒绝，N09 应精确归一化，N10 应由语义复核发现。

标准 JSON Schema 能约束结构、枚举与部分条件关系；具体 LLM 服务支持的子集、跨字段引用校验和语义复核需要在实现阶段分别处理。配套目录是受控词表与关系数据，不宣称它本身已经执行这些校验。

### 13.3 本版验证范围

本版检查输入与原 XLSX 一致、42 个原文行业全部覆盖、字典 key 和引用完整、全部任务可由输入到达、所有技术对象具备允许行业、示例及反例符合预期。问题示例用于验证分类设计，尚未调用 LLM 批量生成答案，也未验证推荐效果。

### 13.4 目录规模

| 目录 | 数量 |
| --- | --- |
| 原始角色 | 6 |
| 原始行业 | 11 |
| 原始 JTBD | 26 |
| role_perspectives | 18 |
| industry_segments | 42 |
| technology_objects | 123 |
| jtbd_tasks | 36 |
| desired_outputs | 21 |
| 正例 | 14 |
| 反例 | 10 |
