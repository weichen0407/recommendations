from pathlib import Path
import json

P = Path(__file__).resolve().parent
# All IDs and events below are synthetic; overlapping users exercise group-level deduplication.
specs = [
    ('电子制造', '半导体', 'electronics_manufacturing', 'semiconductors', '混合键合与微凸点用于芯片互连时，如何比较互连间距和信号损耗？', ['混合键合', '微凸点', '互连间距', '信号损耗'], '方案比较', 1, 50, 80),
    ('电子制造', '半导体', 'electronics_manufacturing', 'semiconductors', '混合键合的对准误差与互连间距应如何权衡？', ['混合键合', '对准误差', '互连间距'], '工艺容差', 21, 80, 100),
    ('电子制造', '半导体', 'electronics_manufacturing', 'semiconductors', '芯片封装的散热材料如何选择，温升应如何评估？', ['散热材料', '温升'], '热性能评估', 79, 90, 15),
    ('电子制造', '电子元件与互连', 'electronics_manufacturing', 'electronic_components_interconnects', '高速连接器的接触电阻异常应如何排查？', ['高速连接器', '接触电阻'], '故障排查', 71, 90, 25),
    ('医疗器械', '体外诊断', 'medical_devices', 'in_vitro_diagnostics', '毛细驱动微流控芯片的气泡干扰应如何设计验证实验？', ['毛细驱动', '微流控芯片', '气泡干扰'], '干扰验证', 1, 42, 60),
    ('医疗器械', '体外诊断', 'medical_devices', 'in_vitro_diagnostics', '毛细驱动微流控芯片应如何验证流量稳定性和重复性？', ['毛细驱动', '微流控芯片', '流量稳定性', '重复性'], '重复性验证', 18, 65, 75),
    ('医疗器械', '医学影像', 'medical_devices', 'medical_imaging', '超声探头的匹配层材料如何比较？', ['超声探头', '匹配层材料'], '材料比较', 53, 70, 20),
    ('能源', '电池与固定式储能', 'energy', 'batteries_stationary_storage', '液冷板流道设计如何改善储能电池组温差？', ['液冷板', '流道设计', '电池组温差'], '流道优化', 1, 52, 80),
    ('能源', '电池与固定式储能', 'energy', 'batteries_stationary_storage', '液冷板流量分配不均时，如何排查电池组局部温升？', ['液冷板', '流量分配', '局部温升'], '热问题排查', 31, 70, 50),
    ('能源', '光伏', 'energy', 'solar_photovoltaics', '光伏组件的封装胶膜如何做耐湿热验证？', ['光伏组件', '封装胶膜', '耐湿热'], '可靠性验证', 61, 84, 30),
]

records = []
for i, (industry, segment, industry_id, segment_id, question, keywords, angle, start, end, uses) in enumerate(specs, 1):
    users = [f'sim-{industry_id}-{n:03d}' for n in range(start, end + 1)]
    exposed = [f'sim-{industry_id}-{n:03d}' for n in range(1, 201)]
    assert set(users) <= set(exposed)
    assert len(users) <= uses
    assert all(w in question for w in keywords)
    records.append(dict(question_id=f'sim-q-{i:02d}', industry=industry, segment=segment,
                        industry_id=industry_id, segment_id=segment_id, question=question,
                        keywords=keywords, angle=angle, exposed_users=exposed,
                        used_users=users, uses=uses))

def aggregate(rows):
    used = set().union(*(set(r['used_users']) for r in rows))
    exposed = set().union(*(set(r['exposed_users']) for r in rows))
    return dict(questions=len(rows), users=len(used), uses=sum(r['uses'] for r in rows),
                exposed_users=len(exposed), user_use_rate=f'{len(used) / len(exposed):.1%}')

segments = []
for segment_id in dict.fromkeys(r['segment_id'] for r in records):
    rows = [r for r in records if r['segment_id'] == segment_id]
    segments.append(dict(industry=rows[0]['industry'], segment=rows[0]['segment'],
                         segment_id=segment_id, **aggregate(rows)))
keywords = {w: aggregate([r for r in records if w in r['keywords']])
            for w in ['混合键合', '微流控芯片', '液冷板']}
assert [(s['users'], s['uses']) for s in segments] == [(90, 195), (20, 25), (65, 135), (18, 20), (70, 130), (24, 30)]
assert keywords['混合键合']['users'] == 80
assert keywords['混合键合']['uses'] == 180

def table(headers, rows):
    return ('| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join('---' for _ in headers) + ' |\n'
            + ''.join('| ' + ' | '.join(str(v).replace('|', '／') for v in row) + ' |\n' for row in rows) + '\n')

doc = '''## 后续：从问题使用看行业需求，决定往哪些方向扩展

把所有用户使用过的问题汇总起来，回答三个问题：**哪个细分行业关注的人多？其中哪些小技术、哪些提问角度更受关注？下一批应该多做哪些问题和研究内容？** 这可以称为“行业需求画像”，统计对象是各方向的内容需求。

链路：问题使用记录 → 行业／细分行业 → 小技术关键词＋提问角度 → 关注人数与使用频次 → 调整选题和推荐。

**先看哪些细分行业有人用，再下钻到具体问题。**

以下是最近 30 天的模拟数据，共 3 个行业、6 个细分行业、10 个问题，用于说明分析方法。每条问题都向所在行业样本中的同一批 200 人有效展示。“使用”指实际提交该问题、发起研究任务；一次提交按 request_id 去重。人数按统计分组去重，次数保留多次提交。行业按问题内容归类。

'''
doc += table(['行业', '细分行业', '问题数', '使用人数／曝光人数', '使用次数'],
             [(s['industry'], s['segment'], s['questions'], f"{s['users']}／{s['exposed_users']}", s['uses']) for s in segments])
doc += '在这份样本中，电子制造的需求较集中于半导体，医疗器械较集中于体外诊断，能源较集中于电池与固定式储能。继续展开这 10 个问题，才能看到具体的需求方向。\n\n'
doc += table(['细分行业', '被使用的问题', '关键词', '提问角度', '使用人数／次数'],
             [(r['segment'], r['question'], '、'.join(r['keywords']), r['angle'], f"{len(r['used_users'])}／{r['uses']}") for r in records])
doc += '''例如，两条“混合键合”问题分别有 50 人、60 人使用，其中 30 人重叠，因此该技术方向共 80 人使用、180 次提交。再按角度拆开，工艺容差是 60 人／100 次，方案比较是 50 人／80 次。这样就能知道“半导体里，混合键合的工艺容差问题更值得继续扩展”，而不只停留在“半导体标签比较热门”。

**把统计结果变成下一批开发方向。**

'''
doc += table(['需求方向', '这份模拟数据支持的判断', '下一批增加什么'], [
    ('半导体 → 混合键合', '80 人使用相关问题；其中工艺容差角度覆盖 60 人。', '围绕对准误差、互连间距扩展工艺窗口、误差控制与验证问题。'),
    ('体外诊断 → 毛细驱动微流控', '65 人使用相关问题；重复性验证 48 人，气泡干扰验证 42 人。', '增加重复性实验设计、流量波动定位和气泡干扰验证问题。'),
    ('电池与固定式储能 → 液冷板', '70 人使用相关问题；流道优化 52 人，热问题排查 40 人。', '增加流道方案比较、流量分配及局部温升排查问题。'),
])
doc += '''这里的人数表示产品当前覆盖用户中的需求广度，次数表示使用深度。比较时还要看曝光人数、问题数量与展示位置；先将热门组合列为扩展候选，再在相近展示条件下验证。新方向保留少量探索，避免已有内容越多、使用越多，就只继续生产已有方向。

实现上补三步即可：

1. **把问题和行为关联。** 产品保留 brief_id／content_id 映射、行业／细分行业、问题文本和 keywords 快照；记录曝光、点击、实际提交问题，以及结果的复制、下载、应用事件。提交问题用于判断“哪些问题被问”，复制、下载、应用用于观察结果是否有用，分开统计。
2. **汇总到方向。** 使用现有行业两级目录；从问题和 keywords 抽取小技术、关注点与具体角度，归并“混合键合／hybrid bonding”等同义词和相近问法。按“时间窗口＋行业＋细分行业＋小技术＋角度”汇总去重人数、使用次数、曝光与后续动作，保留原问题以便查看依据。小技术与细角度是分析字段，不新增固定行业枚举。
3. **反馈到生成。** 定期输出各细分行业的热门问题与技术／角度组合，调整下一批选题数量和推荐排序。将“混合键合＋对准误差＋工艺容差”等具体方向带回话题输入，经原有规则校验后生成，再观察新增问题的使用表现。也可据持续出现的需求，确定后续研究模板、数据覆盖与功能投入的优先级。

若同时接入用户自己输入的问题，单独标记为“主动提问”，归入同一行业需求统计，并用于发现题库尚未覆盖的方向；与“使用推荐问题”分别展示。上述统计与反馈属于后续实现，示例不代表真实行业市场规模。
'''
transition = '接下来打通问题、关键词与使用事件，按行业、细分行业、小技术和提问角度汇总所有用户的需求。重点看哪些方向使用人数多、哪些问题被反复提交，以及结果是否被复制、下载或应用，用来调整内容供给和推荐。产品侧还需补齐 brief_id／content_id 映射与分类、关键词快照，并实现事件关联和聚合统计。'
source = (P / 'dingtalk-content-with-keywords.md').read_text()
prefix = source.split('## 后续：按关键词找出用户关注的小技术与问题视角')[0].rstrip()
old = (P / 'keyword-next-step.txt').read_text()
assert prefix.count(old) == 1
full = prefix.replace(old, transition) + '\n\n' + doc
assert all(word not in full for word in ['用户甲', '用户乙', '用户丙', '按用户汇总', '最大似然', '贝叶斯'])
(P / 'industry-demand-section.md').write_text(doc)
(P / 'industry-demand-next-step.txt').write_text(transition)
(P / 'dingtalk-content-with-industry-demand.md').write_text(full)
(P / 'industry-demand-data.json').write_text(json.dumps(dict(simulation=True, records=records,
    segments=segments, keywords=keywords, validation=dict(question_keywords_verified=True,
    group_users_deduplicated=True, counts_verified=True)), ensure_ascii=False, indent=2) + '\n')
print(json.dumps(dict(section_characters=len(doc), full_characters=len(full),
                     segments=segments, keywords=keywords), ensure_ascii=False))
