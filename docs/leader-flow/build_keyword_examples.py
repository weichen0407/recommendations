from pathlib import Path
from collections import Counter
import json

P=Path(__file__).resolve().parent
groups=[
 {'user':'甲','field':'电子制造／芯片互连','profile':'近期聚焦混合键合的细间距互连，关注互连间距、对准误差与信号损耗，常从方案取舍和工艺容差角度研究。','recommend':'增加混合键合、微凸点、互连间距与对准工艺的相关问题。','rows':[
  {'question':'混合键合与微凸点用于芯片互连时，如何比较互连间距和信号损耗？','tech':['混合键合','微凸点'],'focus':['互连间距','信号损耗'],'view':'方案取舍','impressions':20,'clicks':16,'uses':12,'copies':8,'downloads':3},
  {'question':'混合键合的对准误差与互连间距应如何权衡？','tech':['混合键合'],'focus':['对准误差','互连间距'],'view':'工艺容差','impressions':20,'clicks':14,'uses':8,'copies':5,'downloads':4},
  {'question':'芯片封装的散热材料如何影响温升？','tech':['散热材料'],'focus':['温升'],'view':'热性能分析','impressions':20,'clicks':6,'uses':2,'copies':1,'downloads':1}]},
 {'user':'乙','field':'医疗器械／体外诊断检测芯片','profile':'近期聚焦毛细驱动微流控，关注气泡干扰、流量稳定性与重复性，偏向设计验证实验。','recommend':'增加毛细驱动结构、排泡条件、流量稳定性与重复性验证的相关问题。','rows':[
  {'question':'毛细驱动微流控芯片的气泡干扰应如何设计验证实验？','tech':['毛细驱动','微流控芯片'],'focus':['气泡干扰'],'view':'实验验证','impressions':20,'clicks':15,'uses':11,'copies':3,'downloads':9},
  {'question':'毛细驱动微流控芯片应如何验证流量稳定性和重复性？','tech':['毛细驱动','微流控芯片'],'focus':['流量稳定性','重复性'],'view':'实验验证','impressions':20,'clicks':14,'uses':9,'copies':2,'downloads':7},
  {'question':'荧光检测的光学噪声应如何分析？','tech':['荧光检测'],'focus':['光学噪声'],'view':'噪声分析','impressions':20,'clicks':7,'uses':3,'copies':1,'downloads':2}]},
 {'user':'丙','field':'能源／储能电池组','profile':'近期聚焦液冷板热管理，关注流道设计、流量分配及电池组温差，常从热问题排查和结构优化角度研究。','recommend':'增加液冷板流道、流量分配、温差控制与局部温升排查的相关问题。','rows':[
  {'question':'液冷板流道设计如何改善储能电池组温差？','tech':['液冷板','流道设计'],'focus':['电池组温差'],'view':'流道优化','impressions':20,'clicks':14,'uses':10,'copies':4,'downloads':3},
  {'question':'液冷板流量分配不均时，如何排查电池组局部温升？','tech':['液冷板'],'focus':['流量分配','局部温升'],'view':'热问题排查','impressions':20,'clicks':12,'uses':8,'copies':3,'downloads':2},
  {'question':'储能电池 SOC 估算方法有哪些？','tech':['SOC 估算'],'focus':['估算方法'],'view':'方法调研','impressions':20,'clicks':6,'uses':2,'copies':1,'downloads':1}]},
]

def table(headers,rows):
 def clean(x):return str(x).replace('|','／').replace('\n',' ')
 return '| '+' | '.join(headers)+' |\n| '+' | '.join('---' for _ in headers)+' |\n'+''.join('| '+' | '.join(map(clean,row))+' |\n' for row in rows)+'\n'

doc='''## 后续：按关键词找出用户关注的小技术与问题视角

分析对象细化到“用户在研究哪项技术、哪个部件、哪个指标或故障，以及从什么角度研究”。复用内容已有的 entities、keywords，并结合问题和描述补充抽取。行业、角色等标签用于限定背景；这里的技术词、关注点和细视角都是自由文本分析结果，不新增为固定枚举。

实现链路：内容关键词 → 同义词归并 → 关联用户使用记录 → 汇总技术词、关注点和视角 → 形成细分需求描述。

1. 保存原词和来源。优先使用已有 entities／keywords，并从问题、描述中抽取小技术、部件、性能指标、故障点和提问角度；保留 source_text，能追溯每个词从哪句话提取。
2. 归并同义表达。例如“混合键合／hybrid bonding”归为同一个词；“SOC 估算／荷电状态估算”合并统计。“温差”和“温升”有关联但不相同，应分别保留。把词分成技术对象、问题关注点和具体视角，避免混在同一排名里。
3. 将曝光、点击、复制、下载、使用通过 content_id 关联到关键词快照，再按 user_id＋标准化关键词＋时间窗口汇总。同时观察关键词组合，例如“混合键合＋互连间距”，以获得更具体的需求线索。

以下为三个模拟用户、九个模拟问题，用来演示统计与结论，不是线上数据，也不是已验证的技术结论。沿用最近 30 天、观察窗口完整的记录；每个问题 20 次有效曝光。“使用”指阅读会话中至少一次应用到工作区或基于内容启动研究任务，同会话重复操作只算一次。复制、下载另外记录，可与使用重叠，不能相加。

'''
summaries=[];records=[]
for g in groups:
 doc+=f'**用户{g["user"]}：{g["field"]}**\n\n'
 rows=[];use=Counter();exp=Counter();views=Counter()
 for i,r in enumerate(g['rows'],1):
  assert 0<=r['uses']<=r['clicks']<=r['impressions']
  assert r['copies']<=r['clicks'] and r['downloads']<=r['clicks']
  for typ in ['tech','focus']:
   for word in dict.fromkeys(r[typ]):
    assert word in r['question'],word
    use[(typ,word)]+=r['uses'];exp[(typ,word)]+=r['impressions']
  views[r['view']]+=r['uses']
  records.append({'simulation':True,'user_id':f'示例用户{g["user"]}','content_id':f'keyword-demo-{g["user"]}-{i}',**r})
  rows.append((r['question'],'技术：'+'、'.join(r['tech'])+'；关注点：'+'、'.join(r['focus']),r['view'],f'{r["impressions"]}／{r["clicks"]}／{r["uses"]}',f'{r["copies"]}／{r["downloads"]}'))
 doc+=table(['问题','关键词','具体视角','曝光／点击／使用','复制／下载'],rows)
 summaries.append({'user':g['user'],'field':g['field'],'keyword_counts':[{'kind':t,'keyword':w,'associated_uses':n,'associated_impressions':exp[(t,w)]} for (t,w),n in use.items()],'view_counts':dict(views),'profile':g['profile']})

doc+='**关键词统计：具体哪些词反复出现在被使用的内容里？**\n\n'
doc+='下表采用“相关内容使用次数／有效曝光”的口径；同一关键词在一条问题里出现多次，只关联一次该内容的行为。\n\n'
summaryrows=[]
for s in summaries:
 cols=[]
 for typ in ['tech','focus']:
  cols.append('；'.join(f'{r["keyword"]}：{r["associated_uses"]}／{r["associated_impressions"]}' for r in sorted(s['keyword_counts'],key=lambda row:-row['associated_uses']) if r['kind']==typ))
 summaryrows.append((s['user'],*cols,'；'.join(f'{w}：{n} 次' for w,n in s['view_counts'].items())))
doc+=table(['用户','小技术／对象关键词','指标／问题关键词','具体视角对应使用次数'],summaryrows)
doc+='例如甲使用了两条含“混合键合”的内容，分别 12 次、8 次，所以该词关联 20 次使用、40 次曝光；这两条也都包含“互连间距”，可进一步观察这个词组的共同使用记录。散热材料相关内容只有 2 次使用、20 次曝光，因此当前证据更支持其关注混合键合的细间距互连问题。\n\n'
doc+='“混合键合关联 20 次使用”不等于“用户主动搜索混合键合 20 次”，也不能证明内容中的每个词都吸引了用户。若后续有用户输入的问题或选中复制片段，可另行提取其中的词，区分主动表达与整篇内容关联两种证据。一次使用同时对应多个词，各词次数不能相加当成总使用量。\n\n'
doc+='**画像描述要落到具体技术需求**\n\n'
doc+=table(['用户','根据模拟记录形成的近期需求描述','下一步推荐什么'],[(f'用户{g["user"]}（{g["field"]}）',g['profile'],g['recommend']) for g in groups])
doc+='实现时保存“标准化关键词、原词、提取来源、共现词、具体视角、曝光／使用次数、最近使用时间”，再生成可追溯的需求描述。保持用户主动填写的角色／行业与这些行为推断分开。上述三种细分需求来自三个模拟用户各自的记录，不能直接推广到整个行业。\n'
(P/'keyword-examples-section.md').write_text(doc)
(P/'keyword-examples-data.json').write_text(json.dumps({'simulation':True,'records':records,'summary':summaries,'validation':{'keyword_source_checked':True,'counts_checked':True,'questions':len(records)}},ensure_ascii=False,indent=2)+'\n')

source=(P/'dingtalk-content-with-usage.md').read_text()
source=source.split('## 后续：从不同产品的使用记录，看用户需要什么')[0].rstrip()
old='接下来主要补三件事：把完整 tags、标签版本和 brief_id／content_id 映射传到产品；将曝光、点击、复制、下载、使用事件关联回内容；按标签统计曝光及后续使用表现，用于调整推荐排序和下一批选题。当前产品 JSON 的导出字段还没有包含完整 tags 和上述追溯字段，需要补齐。'
new='接下来把 content_id、entities／keywords 及其版本与曝光、点击、复制、下载、使用事件打通。归并同义词，提取具体小技术、指标／故障和问题视角，按用户汇总行为，形成“研究对象＋关键技术＋关注问题”的需求描述，用于推荐和选题；行业与受众标签保留作背景筛选。关键词标准化、细视角抽取和事件关联属于后续实现。'
assert old in source
source=source.replace(old,new)+'\n\n'+doc
(P/'keyword-next-step.txt').write_text(new)
(P/'dingtalk-content-with-keywords.md').write_text(source)
print(json.dumps({'section_characters':len(doc),'full_characters':len(source),'questions':len(records),'keyword_examples':[(s['user'],[(r['keyword'],r['associated_uses'],r['associated_impressions']) for r in s['keyword_counts'] if r['kind']=='tech']) for s in summaries]},ensure_ascii=False))
