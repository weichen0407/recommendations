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
