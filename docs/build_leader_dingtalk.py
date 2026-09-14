from pathlib import Path
import copy
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from recommendation_contents.brief_schema import load_brief_catalog, validate_briefs
from recommendation_contents.profile_topic_generation import validate_profile_request, validate_profile_briefs, profile_tag_set_id

C = load_brief_catalog()
OUT = ROOT / 'docs' / 'leader-flow'
OUT.mkdir(exist_ok=True)
original = json.loads((ROOT / 'docs/recommendation-tags/v2/example-chip-interconnect-variants.json').read_text())
assert not validate_briefs(original, C, 2)
audience = copy.deepcopy(original['briefs'][0]['audience'])
tags = dict(original['briefs'][0]['tags'], topic_theme='solution_comparison', question_intent='compare_approaches', scope_level='industry_segment')
request = dict(audience=audience, tag_bundle=tags, language='zh-CN', count=3)
assert not validate_profile_request(request)[2]
questions = [
    ('半导体互连技术路线在带宽、功耗与制造成本上有哪些主要取舍？', '从产品设计视角比较半导体互连技术路线在带宽、功耗与制造成本上的取舍，形成支持方案选择的对比矩阵。', ['芯片互连'], ['芯片互连','带宽','功耗','制造成本']),
    ('半导体封装技术路线在集成能力、散热与制造复杂度上有哪些差异？', '从产品设计视角比较半导体封装技术路线在集成能力、散热与制造复杂度上的差异，形成支持方案选择的对比矩阵。', ['半导体封装'], ['半导体封装','集成能力','散热','制造复杂度']),
    ('半导体器件技术路线在性能、可靠性与集成成本上应如何比较？', '从产品设计视角比较半导体器件技术路线在性能、可靠性与集成成本上的取舍，形成支持方案选择的对比矩阵。', ['半导体器件'], ['半导体器件','性能','可靠性','集成成本']),
]
payload = {'briefs': []}
for title, desc, entities, keywords in questions:
    payload['briefs'].append(dict(title=title, description=desc, entities=entities, keywords=keywords, audience=copy.deepcopy(audience), tags=copy.deepcopy(tags), classification={'rationale':'问题属于半导体领域的技术方案比较，采用产品设计视角，以对比矩阵支持后续选择。','industry_status':'classified'}, assumptions=['运营在半导体范围内选择该比较对象及维度，未指定用户的具体项目、产品参数或已发生事件。']))
assert not validate_profile_briefs(payload, C, 3, audience, tags)
invalid = []
for name, field, value in [
    ('行业父子不匹配', 'industry_segment', 'automotive_chassis_body'),
    ('任务与产出不匹配', 'desired_output', 'trend_brief'),
    ('主题与问题意图不匹配', 'question_intent', 'assess_risks'),
    ('范围与细分行业不一致', 'scope_level', 'industry'),
    ('擅自新增行业枚举', 'industry_segment', 'chip_interconnect'),
    ('JTBD 与具体任务不匹配', 'jtbd_task', 'claims_drafting'),
]:
    changed=copy.deepcopy(request)
    changed['tag_bundle'][field]=value
    errors=validate_profile_request(changed)[2]
    assert errors, name
    invalid.append({'case':name, 'field':field, 'value':value, 'errors':errors})
changed=copy.deepcopy(payload)
changed['briefs'][1]['tags']['role_perspective']='system_integration'
drift=validate_profile_briefs(changed,C,3,audience,tags)
assert any('exactly match' in s for s in drift)
invalid.append({'case':'固定标签批次中途改换工作视角','field':'role_perspective','value':'system_integration','errors':drift})
validation={'taxonomy_version':C['taxonomy_version'],'source_examples_valid':True,'fixed_request_valid':True,'fixed_examples_valid':True,'tag_set_id':profile_tag_set_id(audience,tags),'invalid_cases':invalid}
(OUT/'validated-example.json').write_text(json.dumps({'request':request,'response':payload,'validation':validation},ensure_ascii=False,indent=2)+'\n')
(OUT/'validation-results.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')

body = '''# 从话题与 Tags，到推荐内容库与用户需求学习

本项目把运营话题和标准化标签转成可复用的推荐内容；下一阶段通过曝光、点击、下载、复制与实际使用，持续学习用户需求，同时改进推荐排序和内容供给。

阅读顺序：先看总流程和建设计划；再看文末“芯片互连”的完整案例、真实规则摘录和全部枚举目录。正文兼顾业务和技术，细节集中在后半部分。

## 一、总流程：生产内容，再通过使用反馈持续优化

图 1｜推荐内容生产与用户需求学习闭环。蓝色表示已有生产基础，黄色表示后续完善环节。

话题入口／Tags 入口 → ①构建选题 → ②明确研究要求 → ③生成与检查 → ④结构化内容库 → ⑤推荐分发 → ⑥行为采集 → ⑦偏好学习 → ⑧策略更新。

两条反馈：个人行为回到推荐排序；群体需求回到下一批选题。

| 步骤 | 业务目的 | 技术实现与产出 |
| --- | --- | --- |
| ① 构建选题 | 明确研究什么、为谁解决什么问题。 | 维护受控标签目录；LLM 生成标题和描述，程序校验枚举与组合。支持话题驱动、固定标签组合驱动两种入口。 |
| ② 明确研究要求 | 将选题转成清晰的研究任务。 | 生成研究 Prompt，继承原标签；明确研究重点、证据要求与预期成果。 |
| ③ 生成与检查 | 批量产出可阅读、可使用的内容。 | Eureka 执行研究，支持 report／HTML；保存任务和分享链接，检查完成状态，运营抽查内容质量。 |
| ④ 结构化内容库 | 把一次生成变成可检索、可复用的资产。 | 保存问题、标签、关键词、答案链接和状态；以 JSON／CSV 交付，并为产品集成保留追溯关系。 |
| ⑤ 推荐分发 | 将内容匹配给有相关工作需求的用户。 | 初期按用户主动填写的角色、行业、任务匹配；后续结合行为偏好排序，保留探索机会。 |
| ⑥ 行为采集 | 识别内容是否进入真实工作。 | 将曝光、点击、下载、复制、使用及任务完成关联到用户、内容、曝光记录与标签版本。 |
| ⑦ 偏好学习 | 识别近期需求、长期兴趣和工作方式。 | 分动作分析标签转化率，结合初始信息、样本量和时间变化，估计偏好及可信程度。 |
| ⑧ 策略更新 | 改善个人推荐，并指导下一批内容供给。 | 个人偏好用于排序；群体需求用于选题规划；通过 A/B 实验验证使用转化和任务完成是否提升。 |

当前边界：项目已有选题、研究要求生成、内容执行、完成检查和结构化导出，以及曝光、点击和激活分析材料。内容库目前主要体现为内容资产文件；完整线上数据库接入、深度行为归因、偏好模型和自动排序回写需要后续建设。完成状态检查不等于内容事实和语义质量已自动审核。

## 二、后续建设：把内容标签接到用户行为上

| 优先级 | 建设内容 | 可检查的交付物 |
| --- | --- | --- |
| 第一步 | 统一内容、标签和事件的关联。 | 内容 ID／brief_id 映射、标签版本快照、曝光 ID、用户或匿名访客 ID、展示位置、策略版本和动作时间。当前产品 JSON 需补齐完整受控 tags 与追溯字段。 |
| 第二步 | 从首次曝光就采集深度行为。 | 点击、复制、下载、实际使用、启动任务、完成任务的事件定义；去重规则与归因窗口。无需等点击很多以后才开始采集。 |
| 第三步 | 建立用户—标签偏好模型。 | 对每个用户与标签保存曝光量、各类动作、近期／长期偏好估计与可信程度；低样本使用初始画像、同类人群和上层标签信息。 |
| 第四步 | 接回排序和内容供给。 | 小流量 A/B 实验、探索策略、有效使用和任务完成看板，以及下一批标签覆盖计划。 |

| 指标 | 建议口径 | 业务解释 |
| --- | --- | --- |
| 点击率 | 至少发生一次有效点击的曝光数 ÷ 有效曝光数。 | 内容是否吸引用户查看。 |
| 复制率 | 发生复制的去重阅读会话数 ÷ 有复制机会的阅读会话数。 | 内容是否被带入后续工作。 |
| 下载率 | 发生下载的去重阅读会话数 ÷ 有下载机会的阅读会话数。 | 用户是否希望保留或使用成果。 |
| 使用转化率 | 在归因窗口内产生已定义使用动作的曝光数 ÷ 已具备完整观察窗口的有效曝光数。 | 推荐是否带来实际使用。 |
| 任务完成率 | 完成且可归因的任务数 ÷ 由推荐内容启动且观察窗口完整的任务数。 | 内容是否帮助用户推进工作。 |

“使用”必须是可观测动作，例如应用到工作区、基于内容启动研究任务；启动和完成分别统计。下载和复制的信号强度不预先固定为某个分数，应根据最终使用与完成结果验证。重复操作去重，延迟转化要留出归因窗口。

标签频次要结合曝光机会。例如某 tag 点击 30 次／曝光 1,000 次，另一个点击 20 次／曝光 100 次，仅按点击次数会得出不同于转化率的判断。归一化后仍需比较人群、位置、时间和策略条件。多个标签同时出现在一条内容上，一个动作不能视为多个独立证据；也不能据此证明某个标签造成了转化。

## 三、数学概念：隐式反馈学习与贝叶斯更新

业务名称是“基于隐式反馈的用户偏好学习”：用户没有直接评分，系统通过点击、复制、下载、使用等行为学习偏好。数学上，若结合初始画像并随行为持续修正判断，更贴近“贝叶斯更新”。

后验 ∝ 先验 × 似然。可以理解为：初始判断与新增行为证据共同形成更新后的判断，并保留不确定性。

- 最大似然估计（MLE）：寻找最能解释已观察行为的参数。例如在简化的独立同分布二元点击模型中，20 次有效曝光、8 次点击，点击概率的 MLE 是 40%。
- 贝叶斯更新：再考虑合理的初始信息。若先验为 Beta(2,8)，观察到 8 次点击和 12 次未点击后，后验为 Beta(10,20)，后验均值约 33.3%。这是说明平滑和有限样本的例子，先验参数不是已上线配置。
- 最大后验估计（MAP）：取后验概率密度最大的参数值；它是贝叶斯方法的一种点估计，不等同于后验均值。

这些概率估计描述行为倾向和需求证据，不能直接当作用户职业身份的概率。真实系统需要处理行为相关性、展示偏差、多个标签与时间变化；样本足够与否应看覆盖和不确定性，不设一个适用于所有用户的固定点击门槛。

方法参考：[隐式反馈研究](https://yifanhu.net/PUB/cf.pdf)、[MLE 与 MAP](https://chrispiech.github.io/probabilityForComputerScientists/en/part5/map/)。后续若需要平衡利用已有偏好与探索新内容，可进一步采用[上下文多臂老虎机](https://arxiv.org/abs/1003.0146)。

## 四、完整案例：从“芯片互连”走到内容与行为反馈

### 4.1 先输入话题：还没有研究结论

运营输入：idea = 芯片互连；language = zh-CN；count = 2。

普通话题模式只要求输入 idea。role、industry、JTBD 是生成后判断的目标受众，不要求先有某个真实用户的画像。

项目仓库已经维护以下两个规则示例：

| 字段 | 选题 A：方案选择 | 选题 B：失效改进 |
| --- | --- | --- |
| title | 芯片互连方案的功耗、带宽与成本取舍 | 芯片互连的失效路径与改进方向 |
| description | 从产品设计视角比较芯片互连方案在功耗、带宽与制造成本上的取舍，形成支持方案选择的对比矩阵。 | 从可靠性工程视角梳理芯片互连的典型失效路径与影响因素，形成包含验证要点的改进方案。 |
| audience.role | rd_engineer：研发工程师／发明者 | rd_engineer |
| audience.industry | electronics_manufacturing：电子制造 | electronics_manufacturing |
| audience.jtbd | technical_solutions：寻找技术方案 | technical_solutions |
| tags.role_perspective | product_design：产品设计 | reliability_engineering：可靠性工程 |
| tags.industry_segment | semiconductors：半导体 | semiconductors |
| tags.jtbd_task | solution_comparison：方案比较 | failure_resolution：失效处理 |
| tags.desired_output | comparison_matrix：对比矩阵 | improvement_plan：改进方案 |
| entities | 芯片互连 | 芯片互连 |
| keywords | 芯片互连、功耗、带宽、制造成本 | 芯片互连、失效分析、可靠性、验证 |
| 补充假设 | 运营选择方案选型切口与比较维度。 | 运营选择一般失效分析切口，没有声称发生过真实失效事件。 |

这里同一个话题产生了两个不同工作需求。后续即使两个内容都被点击，系统也可分别观察“方案比较”和“失效改进”的使用情况。“芯片互连”属于自由文本研究对象，不能新增为行业第三级标签。

### 4.2 要批量覆盖时，固定“三个受众字段＋七维标签”

普通 idea 模式目前输出四项基础内容标签。固定标签批量模式增加主题、问题意图和范围层级，共七维；两种模式不能在汇报中混成同一输出结构。

下面以选题 A 所属方向为参照，配置一组“半导体方案比较”内容。输入固定后，同批问题必须完整继承，不能逐题换标签。

| 维度 | 本例固定值 | 为什么选择它 |
| --- | --- | --- |
| role | rd_engineer | 面向研发工作需求。 |
| industry | electronics_manufacturing | 半导体所属一级行业。 |
| JTBD | technical_solutions | 内容帮助寻找和比较技术方案。 |
| role_perspective | product_design | 从产品功能、结构与方案取舍出发。 |
| industry_segment | semiconductors | 限定在半导体应用领域。 |
| jtbd_task | solution_comparison | 主要任务是用共同维度比较路线。 |
| desired_output | comparison_matrix | 目录规定方案比较的产出为对比矩阵。 |
| topic_theme | solution_comparison | 内容角度聚焦方案比较。 |
| question_intent | compare_approaches | 希望用户获得不同路线的比较判断。 |
| scope_level | industry_segment | 已选择 semiconductors，因此范围必须是细分行业。 |

其中 jtbd_task 与 topic_theme 虽然都可能取值 solution_comparison，但它们是两个独立字段：一个表示具体工作任务，一个表示内容主题。统计时必须带上字段名。

在这组标签下，可以编制三个有差异的问题：

1. 半导体互连技术路线在带宽、功耗与制造成本上有哪些主要取舍？
2. 半导体封装技术路线在集成能力、散热与制造复杂度上有哪些差异？
3. 半导体器件技术路线在性能、可靠性与集成成本上应如何比较？

变化的是研究对象、比较维度和关键词；不变的是受众与七维标签。代码按组合计算稳定的 tag_set_id，三个问题属于同一标签组。固定标签 CLI 当前锁定受众和标签，并没有独立的“必须围绕芯片互连”实体约束；如果运营只要芯片互连内容，应走话题入口或审核筛选，后续也可补充实体约束。

### 4.3 研究 Prompt：把“要研究什么”变成“怎么交付”

以下为供汇报阅读的研究要求示意，并非本次实际调用模型的结果：

> 从产品设计视角比较芯片互连技术路线，围绕带宽、功耗和制造成本整理公开证据，说明适用条件、取舍和待核实信息，形成方案对比矩阵。不得编造性能数据或替用户假定具体产品参数。

节点 2 继承问题、描述、受众、标签和关键词，生成核心研究要求及最终 Prompt；节点 3 再选择报告或 HTML 形式。comparison_matrix 是工作成果，report／HTML 是承载形式，二者分别保存。

### 4.4 内容记录：每个成果都能追溯回选题和标签

| 信息 | 该例如何保存 | 当前／后续 |
| --- | --- | --- |
| 选题标识 | brief_id；批次有 generation_id。 | 已有生成与执行记录。 |
| 标签组合 | 固定批量模式保存 tag_set_id。 | 已有。 |
| 分类版本 | taxonomy_version = 2.2.0。 | 已有生成记录；需贯通产品与埋点。 |
| 受众与标签 | 研发、电子制造、技术方案，以及上表各项内容标签。 | 生成记录已有；当前产品导出需补齐完整七维标签。 |
| 内容结果 | session_id、share_id、报告或网页链接、format、完成状态。 | 已有执行与产品导出能力；实际值由执行后产生。 |
| 产品关联 | 统一 content_id，并保留到 brief_id 的映射。 | 后续集成。 |
| 行为关联 | impression_id、动作时间、用户／访客 ID、标签快照、位置与策略版本。 | 后续补齐端到端关系。 |

本次只编写汇报材料与离线校验，没有真实提交新的 Eureka 内容，因此不展示虚构会话、报告链接或完成状态。

### 4.5 用户使用后，如何反过来调整推荐

假设用户主动选择“研发／电子制造／技术方案”。系统首先推荐相关内容。随后发生以下示例行为：

| 观察到的行为 | 关联到什么 | 可以支持什么判断 |
| --- | --- | --- |
| 曝光芯片互连方案比较内容。 | 本次曝光与对应内容的全部标签快照。 | 用户获得过查看机会；尚不能推断喜欢。 |
| 点击进入报告。 | 同一曝光及阅读会话。 | 对该内容有进一步了解的意愿。 |
| 复制对比表或下载报告。 | 内容、动作类型与发生时间。 | 内容可能进入后续工作；复制和下载分别统计。 |
| 基于内容启动并完成研究任务。 | 推荐内容到后续任务的归因关系。 | 为内容的实际使用价值提供更直接证据。 |
| 多次使用“方案比较＋对比矩阵”内容。 | 跨内容、跨时间的去重行为与曝光分母。 | 支持提高这类需求的偏好估计与可信程度。 |

更新后的画像可以表达为：“近期更关注半导体技术方案比较，偏好能直接用于判断的对比矩阵。”它补充的是需求与工作方式，不覆盖用户主动填写的角色。个人层面调整排序；群体层面若同类内容持续有效，则补充该标签方向的选题。仍需保留其他方向的探索，避免推荐结果越来越单一。

## 五、把项目规则直接拿出来展示

规则目录版本：2.2.0；结构版本：2.0.0。下面是项目已有规则的汇报式摘录，并附程序可验证的例子。

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

'''

def table(headers, rows):
    def esc(v): return str(v).replace('|','／').replace('\n',' ')
    return '| '+' | '.join(headers)+' |\n| '+' | '.join('---' for _ in headers)+' |\n'+''.join('| '+' | '.join(esc(v) for v in row)+' |\n' for row in rows)+'\n'

for field, name in [('role','角色'),('industry','泛行业'),('jtbd','主要工作需求')]:
    items=C['audience'][field]
    body+=f'### 6.{["role","industry","jtbd"].index(field)+1} {name}：{len(items)} 类\n\n'
    body+=table(['存储值','目录名称'],[(x['value'],x['label_en']) for x in items])

for i,(key,name) in enumerate([('role_perspectives','工作视角'),('industry_segments','细分行业'),('jtbd_tasks','具体任务'),('desired_outputs','预期产出'),('topic_themes','内容主题'),('question_intents','问题意图'),('scope_levels','范围层级')],4):
    items=C[key]
    body+=f'### 6.{i} {name}：{len(items)} 类\n\n'
    if key=='industry_segments':
        body+=table(['存储值','目录名称','所属一级行业'],[(x['value'],x['label_en'],x['entry_industry']) for x in items])
    else:
        body+=table(['存储值','目录名称'],[(x['value'],x['label_en']) for x in items])

body+='''## 七、规则映射摘录：枚举之间如何连接

### 7.1 寻找技术方案，可以拆成哪几种具体任务？

'''
tasks={r['value']:r for r in C['jtbd_tasks']}
body+=table(['一级需求','允许的具体任务','允许的成果'], [('technical_solutions',v,', '.join(tasks[v]['allowed_outputs'])) for v in C['jtbd_allowed_tasks']['technical_solutions']])
body+='### 7.2 “方案比较”的视角与成果边界\n\n'
body+='solution_comparison 允许的工作视角：'+ '、'.join(tasks['solution_comparison']['allowed_perspectives'])+'。\n\n'
body+='允许的预期产出：'+ '、'.join(tasks['solution_comparison']['allowed_outputs'])+'。如果主要工作变成研究方法比较，应使用 research_method_comparison；如果变成寻找候选方案，应使用 solution_search。\n\n'
body+='### 7.3 主题与提问意图的映射示例\n\n'
body+=table(['内容主题','允许的问题意图'],[(v,', '.join(C['topic_theme_allowed_question_intents'][v])) for v in ['ai_impact','technology_trends','solution_comparison','safety_reliability','patent_prosecution']])
body+='### 7.4 角色与工作视角的关系\n\n'
body+=table(['角色','首选工作视角'],[(k,', '.join(v)) for k,v in C['role_preferred_perspectives'].items()])
body+='角色—视角是首选参考，不是职位资格限制；任务允许的视角与产出仍须满足。跨首选视角要说明分类理由，不能把内容的工作视角直接解释成用户的细分身份。\n\n'
body+='### 7.5 目录未覆盖时的处理\n\n'
body+=table(['情况','industry_segment','classification.industry_status','范围处理'], [('已归入明确细分行业','目录合法值','classified','固定批量使用 industry_segment'),('只明确泛行业','null','broad_scope','固定批量使用 industry'),('目录没有合适细分行业','null','not_in_catalog','保留原词；固定批量使用 industry')])
body+='''资料来源：项目 README.md、CONTEXT.md、运营选题_第一阶段生成规则.md、content_brief_catalog.json（2.2.0）、profile_topic.schema.json、example-chip-interconnect-variants.json、profile_topic_generation.py、brief_schema.py、plg_cli.py。所有枚举值和映射表直接取自本次读取的运行目录；中文解释为汇报用释义。完整例子是规则示例，行为段为假设情境，不是线上用户数据。
'''

(OUT/'dingtalk-content.md').write_text(body)
print(json.dumps({'markdown':str(OUT/'dingtalk-content.md'),'characters':len(body),'taxonomy_version':C['taxonomy_version'],'enumeration_values':sum(len(x) for x in C['audience'].values())+sum(len(C[k]) for k in ['role_perspectives','industry_segments','jtbd_tasks','desired_outputs','topic_themes','question_intents','scope_levels']),'validation':validation},ensure_ascii=False,indent=2))
