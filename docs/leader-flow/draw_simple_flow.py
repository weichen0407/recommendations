from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE=Path(__file__).resolve().parent
im=Image.new('RGB',(1880,1220),'#F7F9FC')
d=ImageDraw.Draw(im)
fontpath='/System/Library/Fonts/Hiragino Sans GB.ttc'
def text(x,y,s,size=30,color='#263C56'):
    d.text((x,y),s,font=ImageFont.truetype(fontpath,size),fill=color)
def arrow(points):
    d.line(points,fill='#6A86A5',width=6,joint='curve')
    x,y=points[-1];px,py=points[-2]
    if x==px:
        sign=1 if y>py else -1
        d.polygon([(x,y),(x-10,y-sign*17),(x+10,y-sign*17)],fill='#6A86A5')
    else:
        sign=1 if x>px else -1
        d.polygon([(x,y),(x-sign*17,y-10),(x-sign*17,y+10)],fill='#6A86A5')
text(80,47,'推荐内容生成流程',56,'#152F4F')
text(82,125,'话题／Tags → 选题 → 研究 Prompt → Eureka → 内容记录',33,'#65788F')
d.rounded_rectangle((420,212,1460,357),radius=22,fill='#EEF3F9',outline='#B0C1D5',width=3)
text(452,231,'输入：话题或固定 Tags 组合',37)
text(452,291,'例：芯片互连  |  中文  |  1 条  |  report',29,'#5C738B')
arrow([(940,363),(940,401),(325,401),(325,446)])
nodes=[
    (80,'01 生成选题','generate_topic',['LLM 生成标题、描述与标签','枚举＋组合校验，失败修复一次','输出：brief_id 与完整选题']),
    (700,'02 生成研究 Prompt','generate_research_prompt',['沿用受众与标签，补充研究要求','将标题、标签、关键词拼入 Prompt','输出：generated_prompt']),
    (1320,'03 执行 Eureka','call_curl_task',['按 report／HTML 提交生成任务','保存会话、分享链接和完成状态','输出：session_id 与结果链接'])
]
for x,title,code,lines in nodes:
    d.rounded_rectangle((x,455,x+480,770),radius=22,fill='#EAF3FF',outline='#82A9D4',width=3)
    text(x+25,478,title,35)
    text(x+25,537,code,25,'#3D6F9F')
    for j,line in enumerate(lines):text(x+25,595+j*47,line,26)
arrow([(570,610),(686,610)])
arrow([(1190,610),(1306,610)])
arrow([(1560,780),(1560,836),(940,836),(940,890)])
d.rounded_rectangle((320,899,1560,1100),radius=22,fill='#E8F3ED',outline='#8AB79C',width=3)
text(352,920,'保存记录 → 导出产品 JSON',37)
text(352,983,'JSON 保存完整结果；CSV 按 brief_id 更新；records-to-plg 转换格式',29)
text(352,1041,'内容记录：问题＋标签＋关键词＋结果链接＋执行状态',29)
text(80,1151,'各阶段可保存、检查和继续执行；已有会话可恢复查询，避免重复提交。',27,'#65788F')
im.save(HERE/'recommendation-generation-simple.png')
print(HERE/'recommendation-generation-simple.png')
