| 存储值 | 目录名称 |
| --- | --- |
| ai_impact | AI impact and enablement |
| technology_trends | Technology and research trends |
| technology_explainer | Technology explainer |
| industry_landscape | Industry technology landscape |
| technical_challenges | Industry technical challenges |
| performance_improvement | Performance and efficiency improvement |
| solution_comparison | Solution comparison |
| innovation_opportunities | Emerging applications and innovation opportunities |
| feasibility_validation | Feasibility and validation |
| research_methods | Research methods |
| sustainability | Sustainability |
| safety_reliability | Safety and reliability |
| competitive_landscape | Competitive landscape |
| patent_landscape | Patent landscape |
| ip_risk | IP risk |
| patent_prosecution | Patent drafting and prosecution |

### 6.9 问题意图：12 类

| 存储值 | 目录名称 |
| --- | --- |
| explain_concept | Explain a concept |
| scan_trends | Scan trends |
| identify_applications | Identify applications |
| identify_opportunities | Identify opportunities |
| identify_challenges | Identify challenges |
| compare_approaches | Compare approaches |
| evaluate_feasibility | Evaluate feasibility |
| improve_performance | Improve performance |
| assess_risks | Assess risks |
| track_competitors | Track competitors |
| plan_validation | Plan validation |
| support_decision | Support a decision |

### 6.10 范围层级：2 类

| 存储值 | 目录名称 |
| --- | --- |
| industry | Industry |
| industry_segment | Industry segment |

## 七、规则映射摘录：枚举之间如何连接

### 7.1 寻找技术方案，可以拆成哪几种具体任务？

| 一级需求 | 允许的具体任务 | 允许的成果 |
| --- | --- | --- |
| technical_solutions | solution_search | candidate_shortlist, evidence_table |
| technical_solutions | solution_comparison | comparison_matrix |
| technical_solutions | failure_resolution | improvement_plan, validation_plan |
| technical_solutions | process_optimization | improvement_plan, comparison_matrix |

### 7.2 “方案比较”的视角与成果边界

solution_comparison 允许的工作视角：product_design、process_engineering、system_integration、reliability_engineering、invention_development、applied_research、technology_scouting、product_strategy。

允许的预期产出：comparison_matrix。如果主要工作变成研究方法比较，应使用 research_method_comparison；如果变成寻找候选方案，应使用 solution_search。

### 7.3 主题与提问意图的映射示例

| 内容主题 | 允许的问题意图 |
| --- | --- |
| ai_impact | identify_applications, scan_trends, identify_opportunities, identify_challenges, assess_risks |
| technology_trends | scan_trends, identify_opportunities, support_decision |
| solution_comparison | compare_approaches, evaluate_feasibility, support_decision |
| safety_reliability | assess_risks, improve_performance, plan_validation |
| patent_prosecution | support_decision, plan_validation |

### 7.4 角色与工作视角的关系

| 角色 | 首选工作视角 |
| --- | --- |
| rd_engineer | product_design, process_engineering, system_integration, reliability_engineering, invention_development |
| researcher | applied_research, scientific_contribution, research_methodology |
| innovation_product_strategy | technology_scouting, product_strategy, competitive_intelligence |
| in_house_ip_legal | ip_portfolio_management, patent_risk_review, patent_evidence_analysis, patent_prosecution, commercial_legal_review |
| patent_ip_services | patent_evidence_analysis, patent_prosecution, patent_risk_review, ip_commercialization |
| other | task_exploration |

角色—视角是首选参考，不是职位资格限制；任务允许的视角与产出仍须满足。跨首选视角要说明分类理由，不能把内容的工作视角直接解释成用户的细分身份。

### 7.5 目录未覆盖时的处理

| 情况 | industry_segment | classification.industry_status | 范围处理 |
| --- | --- | --- | --- |
| 已归入明确细分行业 | 目录合法值 | classified | 固定批量使用 industry_segment |
| 只明确泛行业 | null | broad_scope | 固定批量使用 industry |
| 目录没有合适细分行业 | null | not_in_catalog | 保留原词；固定批量使用 industry |

资料来源：项目 README.md、CONTEXT.md、运营选题_第一阶段生成规则.md、content_brief_catalog.json（2.2.0）、profile_topic.schema.json、example-chip-interconnect-variants.json、profile_topic_generation.py、brief_schema.py、plg_cli.py。所有枚举值和映射表直接取自本次读取的运行目录；中文解释为汇报用释义。完整例子是规则示例，行为段为假设情境，不是线上用户数据。

