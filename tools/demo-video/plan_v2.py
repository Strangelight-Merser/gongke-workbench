"""从新录制的时间标记生成 v2 剪辑表，保留原片与旁白。"""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=json.loads((ROOT/'tools/demo-video/timeline.json').read_text())
source='out/demo-video/v2-main-02'
r=json.loads((ROOT/source/'recording.json').read_text())
marks={x['name']:x['at']/1000-r['frames'][0]['timestamp'] for x in r['inputs'] if x['kind']=='mark'}
p[0]['segments']=[dict(graphic='opening',duration=12,badge='示意动画 · 真实图纸与 CAD 截图',assets=['out/demo-video/paid-robot4/inputs/robot4.pdf','out/demo-video/v2-assets/robot4.png',source+'/opening-cad.png'])]
# 回放源完整连续覆盖40秒。镜头沿真实正常布局平滑移动，无拼接面板。
begin=marks['replay-start']
settings=[
 (0,5,1.14,1.28,[.60,.51],[.63,.53]),
 (5,10,1.28,1.42,[.63,.53],[.83,.49]),
 (10,18,1.42,1.2,[.83,.49],[.63,.53]),
 (18,25,1.2,1.38,[.63,.53],[.80,.56]),
 (25,33,1.38,1.45,[.80,.56],[.84,.57]),
 (33,40,1.45,1.14,[.84,.57],[.60,.51])
]
for shot,selected in [(p[2],settings[:3]),(p[3],settings[3:])]:
 shot['segments']=[dict(source=source,begin=begin+a,end=begin+b,duration=b-a,zoom=[z0,z1],focus=f0,focus_end=f1,badge='真实会话回放 · 总时长压缩约 ×5.3') for a,b,z0,z1,f0,f1 in selected]
# 末尾保留最后事件，覆盖实际回放末点（毫秒级时钟误差不显示额外倍率）。
p[3]['segments'][-1]['end']=marks['replay-end']
p[8]['segments']=[dict(graphic='evidence',duration=15,badge='验收证据摘录 · Windows / macOS 分别标注',assets=['out/demo-video/ci-41822011858/installer/result.json','docs/demo-video/empty-workbench.md'])]
(ROOT/'tools/demo-video/timeline-v2.json').write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n')
