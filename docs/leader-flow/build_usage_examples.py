from pathlib import Path
from collections import Counter
import json
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from recommendation_contents.brief_schema import load_brief_catalog
from recommendation_contents.profile_topic_generation import validate_profile_request

HERE=Path(__file__).resolve().parent
c=load_brief_catalog()
candidate_rows=[
 ('audience.role（6 类）','researcher（科研）；innovation_product_strategy（创新与产品战略）','rd_engineer：本例研究产品技术方案，选择研发类目标受众。'),
 ('audience.industry（11 类）','medical_devices（医疗器械）；energy（能源）；automotive（汽车）','electronics_manufacturing：研究对象属于芯片设计与制造领域。'),
 ('audience.jtbd（26 类）','existing_technologies（了解现有技术）；technical_feasibility（评估可行性）；product_ideas（生成产品创意）','technical_solutions：问题要求寻找和比较方案，主要任务不是验证可行性或提出创意。'),
 ('tags.role_perspective（18 类）','process_engineering（工艺工程）；reliability_engineering（可靠性工程）；system_integration（系统集成）','product_design：比较功能、性能和成本取舍；若改成排查失效，则考虑可靠性工程。'),
 ('tags.industry_segment（42 类）','electronic_components_interconnects（电子元件与互连）；computing_network_hardware（计算与网络硬件）','semiconductors：本例限定芯片内部及封装互连，归入半导体；独立连接器或整机应重新判断。'),
 ('tags.jtbd_task（36 类）','solution_search（寻找方案）；failure_resolution（失效处理）；process_optimization（工艺优化）','solution_comparison：描述明确要求比较不同技术路线。'),
 ('tags.desired_output（21 类）','candidate_shortlist（候选清单）；improvement_plan（改进方案）；validation_plan（验证计划）','comparison_matrix：按统一维度比较；程序规定 solution_comparison 只能搭配此成果。'),
 ('tags.topic_theme（16 类）','performance_improvement（性能提升）；technical_challenges（技术挑战）；safety_reliability（安全可靠性）','solution_comparison：固定标签模式下，主题聚焦路线比较，而不是单独讨论提升或风险。'),
 ('tags.question_intent（12 类）','evaluate_feasibility（评估可行性）；support_decision（支持决策）；assess_risks（评估风险）','compare_approaches：当前问法是“如何比较”；同主题可选前两种其它意图，但不允许 assess_risks。'),
 ('tags.scope_level（2 类）','industry（泛行业）；另一个值为 industry_segment（细分行业）','industry_segment：已选 semiconductors；只有未选细分行业时才用 industry。'),
]

def md_table(headers,rows):
 def cell(v):return str(v).replace('|','／').replace('\n',' ')
 return '| '+' | '.join(headers)+' |\n| '+' | '.join('---' for _ in headers)+' |\n'+''.join('| '+' | '.join(cell(v) for v in row)+' |\n' for row in rows)

headers=['字段与规模','其它候选值举例','本例选择与依据']
table=md_table(headers,candidate_rows)
(HERE/'candidate-table.md').write_text(table)
# Use the observed table block structure, preserving the existing root block id.
def para(s):
 return ['p',{'uuid':str(uuid.uuid4())},['span',{'data-type':'text'},['span',{'data-type':'leaf'},s]]]
node=['table',{'uuid':'mtzr44byjnwjy25ivjk','colsWidth':[21,37,42],'tblW':{'type':'pct'},'styleId':'tableHeader','tblLook':{'firstRow':1,'lastRow':0,'firstColumn':0,'lastColumn':0}}]
for i,row in enumerate([headers,*candidate_rows]):
 tr=['tr',{'uuid':str(uuid.uuid4()),**({'isTblHeader':True} if i==0 else {})}]
 for value in row:tr.append(['tc',{'uuid':str(uuid.uuid4()),'rowSpan':1,'colSpan':1},para(value)])
 node.append(tr)
(HERE/'candidate-table.jsonml').write_text(json.dumps(node,ensure_ascii=False))

patterns={
 'compare': {'jtbd':'technical_solutions','role_perspective':'product_design','jtbd_task':'solution_comparison','desired_output':'comparison_matrix','topic_theme':'solution_comparison','question_intent':'compare_approaches'},
 'validate': {'jtbd':'technical_feasibility','role_perspective':'reliability_engineering','jtbd_task':'validation_planning','desired_output':'validation_plan','topic_theme':'feasibility_validation','question_intent':'plan_validation'},
 'repair': {'jtbd':'technical_solutions','role_perspective':'reliability_engineering','jtbd_task':'failure_resolution','desired_output':'improvement_plan','topic_theme':'safety_reliability','question_intent':'improve_performance'},
}
users=[
 {'user':'甲','industry':'electronics_manufacturing','segment':'semiconductors','label':'电子制造／芯片互连','profile':'近期主要需要比较半导体技术路线，偏好能直接用于选型的对比矩阵。','next':'优先推荐互连、封装等方案比较内容，保留少量可靠性内容。','rows':[
  ('芯片互连方案在带宽、功耗和成本上如何取舍？','compare',20,16,8,3,12),
  ('芯片封装散热方案在性能与集成成本上有哪些差异？','compare',20,14,5,4,8),
  ('芯片互连出现连接失效时有哪些排查与改进路径？','repair',20,6,1,1,2)]},
 {'user':'乙','industry':'medical_devices','segment':'in_vitro_diagnostics','label':'医疗器械／体外诊断仪器','profile':'近期更需要设计验证步骤、测试条件和评价指标，偏好验证计划。','next':'优先推荐体外诊断仪器与微流控检测的验证计划，保留方案比较内容。','rows':[
  ('体外诊断仪器的重复性应如何设计验证计划？','validate',20,15,3,9,11),
  ('微流控检测芯片的验证测试应覆盖哪些条件？','validate',20,14,2,7,9),
  ('体外诊断检测平台有哪些技术路线差异？','compare',20,7,1,2,3)]},
 {'user':'丙','industry':'energy','segment':'batteries_stationary_storage','label':'能源／储能电池组','profile':'近期更需要排查异常和形成改进路径，偏好失效处理与改进方案。','next':'优先推荐温升、连接和可靠性问题的排查改进内容，保留技术路线比较。','rows':[
  ('储能电池组的温升异常有哪些排查和改进路径？','repair',20,14,4,3,10),
  ('储能系统连接失效应如何排查并形成改进方案？','repair',20,12,3,2,8),
  ('储能系统技术路线如何比较寿命与成本？','compare',20,6,1,1,2)]},
]
records=[];summary=[];out='''## 后续：从不同产品的使用记录，看用户需要什么

以下全部为模拟数据，用来说明实现方式，不代表真实用户或行业结论。三个用户都主动选择“研发”，分别关注芯片互连、体外诊断仪器和储能电池组。保持角色相同，观察具体问题和任务偏好的差异。

统一看最近 30 天、观察窗口已完整的记录。每个问题设为 20 次有效曝光，方便比较。“使用 1 次”指用户进入阅读会话后，至少一次应用到工作区或基于内容启动研究任务；同会话重复操作只记一次，并关联到该次曝光。复制、下载也按阅读会话去重，单独统计，可能与使用重叠，不能相加当作总使用次数。

实现上，事件先通过 content_id 关联到内容的标签快照，再按 user_id、标签字段和值汇总。不能只统计全站哪个行业最热门，再把这个结果当作某个用户的画像。

'''
for u in users:
 out+=f'**用户{u["user"]}：{u["label"]}**\n\n'
 out+=f'这三条内容的行业标签为 {u["industry"]}，细分行业标签为 {u["segment"]}。表中列出变化的任务与成果标签；记录仍保留完整七维标签。\n\n'
 rows=[];counts=Counter();exposures=Counter();clicks=copies=downloads=uses=0
 for ix,(question,pattern,imp,click,copy,download,use) in enumerate(u['rows'],1):
  p=patterns[pattern];audience={'role':'rd_engineer','industry':u['industry'],'jtbd':p['jtbd']}
  tags={k:v for k,v in p.items() if k!='jtbd'}
  tags.update(industry_segment=u['segment'],scope_level='industry_segment')
  errors=validate_profile_request({'audience':audience,'tag_bundle':tags,'count':1,'language':'zh-CN'})[2]
  assert not errors,(u['user'],question,errors)
  assert 0<=use<=click<=imp and copy<=click and download<=click
  record={'user_id':f'示例用户{u["user"]}','content_id':f'demo-{u["user"]}-{ix}','question':question,'audience':audience,'tags':tags,'taxonomy_version':c['taxonomy_version'],'impressions':imp,'clicked_impressions':click,'copy_sessions':copy,'download_sessions':download,'used_impressions':use}
  records.append(record)
  for k,v in tags.items():
   counts[(k,v)]+=use
   exposures[(k,v)]+=imp
  clicks+=click;copies+=copy;downloads+=download;uses+=use
  rows.append((question,f'{tags["jtbd_task"]} → {tags["desired_output"]}',f'{imp}／{click}／{use}',f'{copy}／{download}'))
 out+=md_table(['问题','任务 → 成果标签','曝光／点击／使用','复制／下载'],rows)+'\n'
 if u['user']=='甲':
  out+='同为半导体内容，前两个方案比较问题共使用 20 次，失效改进问题使用 2 次；用户在当前观察窗口更常用方案比较内容。\n\n'
 elif u['user']=='乙':
  out+='两条验证计划共使用 20 次，方案比较使用 3 次；验证类内容下载 16 次，进一步支持用户希望保留验证材料的判断。\n\n'
 else:
  out+='两条失效改进内容共使用 18 次，方案比较使用 2 次；用户在当前观察窗口更常用故障排查和改进内容。\n\n'
 def group(field):
  return '；'.join(f'{value}：{n} 次' for (f,value),n in counts.items() if f==field)
 summary.append({'user':u['user'],'industry_segment':u['segment'],'total_uses':uses,'task_counts':dict((v,n) for (f,v),n in counts.items() if f=='jtbd_task'),'output_counts':dict((v,n) for (f,v),n in counts.items() if f=='desired_output'),'all_tag_use_counts':{f'{f}:{v}':n for (f,v),n in counts.items()},'all_tag_exposure_counts':{f'{f}:{v}':n for (f,v),n in exposures.items()},'copies':copies,'downloads':downloads,'clicks':clicks,'profile':u['profile']})

out+='**把问题记录汇总成标签使用次数**\n\n'
out+='每项同时列出“使用次数／有效曝光”，方便区分使用多与展示多。\n\n'
out+=md_table(['用户','细分行业标签','任务标签','成果标签'],[(s['user'],f'{s["industry_segment"]}：{s["total_uses"]}／60','；'.join(f'{k}：{v}／{s["all_tag_exposure_counts"]["jtbd_task:"+k]}' for k,v in s['task_counts'].items()),'；'.join(f'{k}：{v}／{s["all_tag_exposure_counts"]["desired_output:"+k]}' for k,v in s['output_counts'].items())) for s in summary])+'\n'
out+='例如用户甲的 solution_comparison 使用次数为两个比较问题的 12 次加 8 次，共 20 次。每次使用同时关联多个标签，但行业、任务、成果分别汇总；三个维度的次数不能相加，也不能证明是哪一个标签单独促成了使用。实际排序还要保留各标签的曝光分母，避免把展示更多误判成需求更强。\n\n'
out+='**最后形成可用于推荐的画像描述**\n\n'
out+=md_table(['用户','根据记录得到的近期需求','推荐如何调整'],[(f'用户{u["user"]}（{u["label"]}）',u['profile'],u['next']) for u in users])+'\n'
out+='这些记录体现“领域＋任务＋成果形式”的差异：甲更常用方案比较，乙更常用验证计划，丙更常用失效改进。画像保存时区分用户主动填写的角色／行业与行为推断的近期需求，并记录时间窗、曝光量和样本量；不能从这三个模拟用户推断所有同行业用户都有相同需求。\n'
(HERE/'usage-examples-section.md').write_text(out)
(HERE/'usage-examples-data.json').write_text(json.dumps({'simulation':True,'window_days':30,'records':records,'summary':summary,'validation':{'checked_tag_sets':len(records),'all_tag_sets_valid':True,'counts_checked':True}},ensure_ascii=False,indent=2)+'\n')
intro='下面是这条内容对应的字段。数量取自当前 2.2.0 版目录；前三项是受众，后面是内容标签。候选值是目录举例，实际选择会按描述和上层字段逐步收窄：先确定研究对象和主要任务，再匹配行业、任务、视角与成果，最后检查组合。'
source=(HERE/'dingtalk-content-simple.md').read_text()
old_intro='下面是这条内容对应的字段。数量取自当前 2.2.0 版目录；前三项是受众，后面是内容标签。'
source=source.replace(old_intro,intro)
start=source.index('| 字段 | 目录规模 | 示例值与含义 |')
stop=source.index('\n\n普通话题模式',start)
source=source[:start]+table+source[stop:]
source+='\n\n'+out
(HERE/'dingtalk-content-with-usage.md').write_text(source)
(HERE/'candidate-intro.txt').write_text(intro)
print(json.dumps({'candidate_rows':len(candidate_rows),'questions':len(records),'usage_section_characters':len(out),'total_characters':len(source),'summary':summary},ensure_ascii=False,indent=2))
