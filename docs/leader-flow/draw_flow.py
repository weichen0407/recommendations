from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE=Path(__file__).resolve().parent
W,H=2400,1620
im=Image.new('RGB',(W,H),'#F7F9FC')
d=ImageDraw.Draw(im)
FONT='/System/Library/Fonts/Hiragino Sans GB.ttc'
def font(size):return ImageFont.truetype(FONT,size)
def txt(x,y,s,size=30,fill='#24354B'):
    d.text((x,y),s,font=font(size),fill=fill)
def arrow(points,fill='#71849D',width=6):
    d.line(points,fill=fill,width=width,joint='curve')
    x,y=points[-1];px,py=points[-2]
    if abs(x-px)>abs(y-py):
        sign=1 if x>px else -1
        d.polygon([(x,y),(x-sign*18,y-11),(x-sign*18,y+11)],fill=fill)
    else:
        sign=1 if y>py else -1
        d.polygon([(x,y),(x-11,y-sign*18),(x+11,y-sign*18)],fill=fill)

txt(100,62,'从话题与 Tags，到推荐内容与需求学习',60,'#142C4A')
txt(103,158,'内容生产建立供给；用户使用反馈改善推荐，并指导下一批选题',31,'#63748B')
for x,label,color,bg in [(100,'已有生产基础','#3871AA','#E9F2FC'),(405,'后续完善闭环','#A47424','#FFF1D7')]:
    d.rounded_rectangle((x,231,x+275,287),radius=18,fill=bg)
    txt(x+22,240,label,28,color)

xs=[130,700,1270,1840]; bw=440;bh=330;y1=370;y2=950
nodes=[
 (1,xs[0],y1,'构建选题',['业务｜话题变成工作问题','技术｜LLM 扩展＋枚举校验','例子｜芯片互连方案比较'],'话题／固定 Tags 两种入口'),
 (2,xs[1],y1,'明确研究要求',['业务｜确定研究重点与成果','技术｜生成 Prompt，继承标签','例子｜比较带宽、功耗、成本'],'标签在后续阶段保持关联'),
 (3,xs[2],y1,'生成与检查',['业务｜产出报告或网页','技术｜Eureka 执行与状态检查','例子｜形成方案对比矩阵'],'运营抽查内容质量'),
 (4,xs[3],y1,'结构化内容库',['业务｜内容可检索、可复用','技术｜问题＋标签＋结果链接','例子｜半导体／方案比较'],'当前以 JSON／CSV 资产交付'),
 (5,xs[3],y2,'推荐分发',['业务｜匹配用户工作需求','技术｜画像匹配、排序与探索','例子｜向相关研发用户展示'],'记录有效曝光机会'),
 (6,xs[2],y2,'行为采集',['业务｜观察是否进入实际工作','技术｜事件关联内容与标签','例子｜点击、复制、下载、使用'],'从首次曝光开始采集'),
 (7,xs[1],y2,'偏好学习',['业务｜识别兴趣与当前需求','技术｜转化率＋贝叶斯更新','例子｜偏好方案比较、对比表'],'考虑样本量、时效与可信程度'),
 (8,xs[0],y2,'策略更新',['业务｜改善推荐与内容供给','技术｜更新排序，A/B 验证','例子｜提高相关内容匹配度'],'个人偏好＋群体需求'),
]
for i,x,y,title,lines,foot in nodes:
    future=i>=5
    bg='#FFF8E9' if future else '#EEF5FE'
    stroke='#D5B67C' if future else '#8CB0D9'
    accent='#A47424' if future else '#3871AA'
    d.rounded_rectangle((x,y,x+bw,y+bh),radius=26,fill=bg,outline=stroke,width=3)
    txt(x+25,y+22,f'{i:02d}',31,accent)
    txt(x+88,y+20,title,38,'#1A3450')
    d.line((x+25,y+88,x+bw-25,y+88),fill=stroke,width=2)
    for j,line in enumerate(lines):txt(x+25,y+117+j*50,line,25)
    txt(x+25,y+280,foot,22,'#64758B')

for j in range(3):arrow([(xs[j]+bw+10,y1+bh//2),(xs[j+1]-13,y1+bh//2)])
arrow([(xs[3]+bw//2,y1+bh+10),(xs[3]+bw//2,y2-14)])
txt(1640,801,'产品接入与推荐反馈',27,'#936B2F')
for j in range(3,0,-1):arrow([(xs[j]-10,y2+bh//2),(xs[j-1]+bw+13,y2+bh//2)],'#B48E4D')
arrow([(xs[0],y2+190),(60,y2+190),(60,y1+164),(xs[0]-13,y1+164)],'#3E80B3')
txt(118,805,'群体需求 → 补充高价值选题',30,'#3871AA')
arrow([(xs[0]+bw//2,y2+bh+10),(xs[0]+bw//2,1380),(xs[3]+bw//2,1380),(xs[3]+bw//2,y2+bh+14)],'#B48E4D')
txt(855,1400,'个人偏好 → 调整推荐排序',30,'#936B2F')
txt(130,1510,'评估：点击率、复制率、下载率、使用转化率、任务完成率；按曝光机会与归因窗口比较',27,'#63748B')
im.save(HERE/'recommendation-feedback-flow.png')
print(str(HERE/'recommendation-feedback-flow.png'))
