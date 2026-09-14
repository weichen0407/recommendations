| 规则 | 正确示例 | 会被拒绝或需要纠正的示例 |
| --- | --- | --- |
| 一条选题只承担一个主要任务。 | 比较芯片互连方案，输出对比矩阵。 | 同时要求完整市场报告、失效改进和专利申请稿；需要运营拆题。 |
| 行业只保留两级：industry → industry_segment。 | electronics_manufacturing → semiconductors。 | electronics_manufacturing → automotive_chassis_body；父子不匹配会被程序拒绝。 |
| 具体技术、产品、材料、公司等放入 entities／keywords。 | entities = 芯片互连。 | 新建 industry_segment = chip_interconnect；不在目录中会被拒绝。 |
| JTBD 限定允许的具体任务。 | technical_solutions → solution_comparison。 | technical_solutions → claims_drafting；组合不匹配会被拒绝。 |
| 任务限定工作视角和预期产出。 | solution_comparison → product_design ＋ comparison_matrix。 | solution_comparison ＋ trend_brief；产出不兼容会被拒绝。 |
| 主题与问题意图必须兼容。 | topic_theme = solution_comparison；question_intent = compare_approaches。 | 同主题改为 assess_risks；不在该主题允许列表中会被拒绝。 |
| 范围层级必须与细分行业一致。 | semiconductors ＋ scope_level = industry_segment。 | semiconductors ＋ scope_level = industry；会被拒绝。 |
| 固定标签批次不允许逐题改变受众和标签。 | 三个问题都继承同一个七维组合。 | 某题将 product_design 改为 system_integration；即使枚举本身合法，也因偏离固定组合被拒绝。 |
| 同批问题必须有真实研究差异。 | 比较互连、封装、器件的不同取舍。 | 只替换同义词来凑数量；语义质量需运营审核。 |
| 目录没有合适的细分行业时不强行填标签。 | industry_segment = null，并记录 broad_scope 或 not_in_catalog。 | 借用无关行业枚举；或把每个新词都造为新标签。 |
| 补充范围假设要显式记录。 | assumptions 说明选型切口与比较维度由运营扩展。 | 将运营假设说成用户已经确认的项目事实。 |
| 第一阶段只描述研究任务，不给答案和执行指令。 | 输出问题、描述、受众、标签和关键词。 | 第一阶段直接编造市场数据、研究结论或混入工具执行指令。 |

程序负责检查字段、枚举和组合；“是否真正保留原意、多个问题是否仅是改写、研究证据是否可靠”等仍需模型规则与运营审核共同保障。初始标签映射属于待验证的设计，不能声称已经由点击数据证明正确。

本次离线校验：仓库中的两个芯片互连示例通过；上述固定七维输入和三个批量问题通过；表中七种枚举／组合／继承错误均被当前项目校验器拒绝。本校验只验证结构与规则，不代表真实研究内容质量已验证。

## 六、枚举全景：三个受众维度＋七个内容标签维度

下表数量直接读取运行目录，不是理论排列组合数。字段之间有兼容关系，不能将数量简单相乘当作可用标签组合数。基础 role、industry、JTBD 采用与 Onboarding 相同的存储值，但内容受众和用户身份仍是两份数据。

| 层级 | 字段 | 数量 | 回答的问题 | 本例 |
| --- | --- | --- | --- | --- |
| 目标受众 | role | 6 | 主要适合谁？ | rd_engineer |
| 目标受众 | industry | 11 | 属于哪个泛行业？ | electronics_manufacturing |
| 目标受众 | jtbd | 26 | 满足哪类工作需求？ | technical_solutions |
| 内容标签 | role_perspective | 18 | 从什么工作职责出发？ | product_design |
| 内容标签 | industry_segment | 42 | 聚焦哪个细分领域？ | semiconductors |
| 内容标签 | jtbd_task | 36 | 具体做什么？ | solution_comparison |
| 内容标签 | desired_output | 21 | 交付什么工作成果？ | comparison_matrix |
| 内容标签 | topic_theme | 16 | 从哪个内容主题讨论？ | solution_comparison |
| 内容标签 | question_intent | 12 | 希望获得哪类认识或判断？ | compare_approaches |
| 内容标签 | scope_level | 2 | 停留在泛行业还是细分行业？ | industry_segment |

entities／keywords 是自由文本，不计入以上枚举。classification 和 assumptions 用于解释与追溯，暂不作为用户兴趣标签。

以下保留全部真实存储值及目录原始名称，方便业务与技术对照。业务读者可先看本节总表，需要核对规则时再展开阅读后面的清单。

### 6.1 角色：6 类

| 存储值 | 目录名称 |
| --- | --- |
| rd_engineer | R&D Engineer / Inventor |
| researcher | Researcher / Scientist |
| innovation_product_strategy | Innovation & Product Strategy |
| in_house_ip_legal | In-house IP & Legal |
| patent_ip_services | Patent & IP Services |
| other | Other |

### 6.2 泛行业：11 类

| 存储值 | 目录名称 |
| --- | --- |
| medical_devices | Medical Devices |
| materials | Materials |
| automotive | Automotive |
| electronics_manufacturing | Electronics Manufacturing |
| engineering | Engineering |
| biotech | Biotechnology |
| food_farming_production | Food / Farming Production |
| energy | Energy |
| chemical | Chemical |
| construction | Construction |
| other | Other |

### 6.3 主要工作需求：26 类

| 存储值 | 目录名称 |
| --- | --- |
| technical_solutions | Find technical solutions |
| existing_technologies | Explore existing technologies |
| product_ideas | Generate product ideas |
| technical_feasibility | Assess technical feasibility |
| patent_ip_risk | Assess patent and IP risk |
| new_research_fields | Explore new research fields |
| research_methods | Find research methods |
| research_trends | Track research trends |
| research_ideas | Generate research ideas |
| patents_literature | Search patents and literature |
| technology_competitors | Track technologies and competitors |
| innovation_opportunities | Identify innovation opportunities |
| rd_directions | Evaluate R&D directions |
| patent_landscapes | Explore patent landscapes |
| product_ip_risks | Assess product IP risks |
| prior_art | Search prior art, assess novelty |
| fto_design_risks | Check FTO and design risks |
| draft_review_patents | Draft and review patents |
| office_actions | Respond to office actions |
| fto_searches | Conduct FTO searches |
| draft_review_applications | Draft and review applications |
| draft_refine_claims | Draft and refine claims |
| technology_trends | Track technology trends |
| ideas_concepts | Generate ideas and concepts |
| search_draft_patents | Search or draft patents |
| other | Other |

### 6.4 工作视角：18 类

| 存储值 | 目录名称 |
| --- | --- |
| product_design | Product and component design |
| process_engineering | Process engineering |
| system_integration | System integration |
| reliability_engineering | Reliability engineering |
| invention_development | Invention development |
| applied_research | Applied research |
| scientific_contribution | Scientific contribution |
| research_methodology | Research methodology |
| technology_scouting | Technology scouting |
| product_strategy | Product strategy |
| competitive_intelligence | Competitive intelligence |
| ip_portfolio_management | IP portfolio management |
| patent_risk_review | Patent risk review |
| commercial_legal_review | Commercial legal review |
| patent_evidence_analysis | Patent evidence analysis |
| patent_prosecution | Patent prosecution |
| ip_commercialization | IP commercialization |
| task_exploration | Task exploration |

### 6.5 细分行业：42 类

