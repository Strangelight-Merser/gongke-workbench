"""验证最终编码、逐镜抽帧、来源哈希及只读回放的原始事件完整性。"""
import os,hashlib,json,subprocess,math
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/os.environ.get('GONGKE_DEMO_OUTPUT','out/demo-video/final-v2')
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 film=OUT/'film.mp4';plan=json.loads((OUT/'timeline.json').read_text());sources=json.loads((OUT/'sources.json').read_text())
 probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(film)]))
 v=next(s for s in probe['streams'] if s['codec_type']=='video');a=next(s for s in probe['streams'] if s['codec_type']=='audio')
 assert (v['width'],v['height'],v['codec_name'],v['r_frame_rate'])==(1920,1080,'h264','30/1');assert a['codec_name']=='aac'
 duration=sum(x['duration'] for x in plan);assert abs(float(probe['format']['duration'])-duration)<.1
 subprocess.run(['ffmpeg','-hide_banner','-v','error','-i',str(film),'-f','null','-'],check=True)
 qa=OUT/'qa';qa.mkdir(exist_ok=True)
 for shot in plan:
  for suffix,offset in [('',shot['duration']/2),('-detail',min(3,shot['duration']/3))]:
   subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(shot['start']+offset),'-i',str(film),'-frames:v','1',str(qa/f"shot-{shot['id']:02}{suffix}.png")],check=True)
 contact=Image.new('RGB',(1200,math.ceil(len(plan)/3)*247),'#101e30');draw=ImageDraw.Draw(contact)
 for i,shot in enumerate(plan):
  im=Image.open(qa/f"shot-{shot['id']:02}.png");im.thumbnail((394,222));x=i%3*400;y=i//3*247;contact.paste(im,(x,y));draw.text((x+8,y+226),f"{shot['id']:02} / {shot['start']:.1f}s",fill='white')
 contact.save(qa/'contact-sheet.jpg')
 original=ROOT/'out/demo-video/paid-robot4/robot4-1/conversation.json';replayed=ROOT/os.environ.get('GONGKE_DEMO_REPLAY','out/demo-video/v2-main-02')/'replayed-events.json'
 events=json.loads(original.read_text())['events'];assert events==json.loads(replayed.read_text());assert len(events)==71
 assert any(e.get('update',{}).get('status')=='failed' for e in events)
 ci=ROOT/'out/demo-video/ci-41822011858/installer/result.json';assert json.loads(ci.read_text())['ok'] is True
 checks={}
 for name in sorted({s['source'] for s in sources if 'source' in s}):
  folder=ROOT/name;raw=folder/'raw.mp4';assert raw.exists(),raw
  record=json.loads((folder/'recording.json').read_text());last=record['ended']/1000-record['frames'][0]['timestamp']
  assert all(s['begin']>=0 and s['end']<=last+.1 for s in sources if s.get('source')==name),(name,last)
  checks[name]={'raw_sha256':digest(raw),'recording_sha256':digest(folder/'recording.json')}
 lines=['# 最终片素材来源', '',f'{duration:g} 秒；1920×1080，30 fps，H.264/AAC；神经中文旁白，烧录字幕，另附 SRT；无配乐。', '',
 '开场为 pdftoppm 渲染原图纸与真实 CAD 截图组成的示意动画，角标已标明；第 9 镜为验收文字摘录。其余视频素材为真实应用窗口/视口连续采集。首次 Agent 会话为用户授权的只读回放，全部 71 个事件原文、原序保留，包含失败；旁边模型来自同一次成功运行，不是重新执行建模。示意动画不冒充连续操作；没有伪造产品界面。验收镜头的文字摘录来自下列真实证据。','',
 '| 镜头 | 成片起点 | 原片 | 原片区间（秒） | 剪辑播放倍率 |','|---|---:|---|---|---:|']
 for s in sources:
  if 'source' not in s:
   lines.append(f"| {s['shot']:02} | {s['film_start']:.3f} | {s['graphic']} · 见下方素材 | 示意动画 / 证据文字页 | — |");continue
  lines.append(f"| {s['shot']:02} | {s['film_start']:.3f} | `{s['source']}/raw.mp4` | {s['begin']:.3f}–{s['end']:.3f} | {s['speed']:.4f} |")
 lines+=['','## 来源与事实边界','',
 '- 开场图纸：用户批准的 robot4.pdf，pdftoppm 等比栅格化后裁取主视图；CAD：v2-main-02/opening-cad.png 的真实模型视口裁切。仅对素材卡片做位移、缩放和视觉焦点切换，明确标注示意动画。',
 '- final-main-03 / v2-main-02：工作台展示首次实际生成的 robot4.FCStd、原生树、另存工作修订和真实鼠标旋转；回放源 paid-robot4/robot4-1/conversation.json，71 个事件。用户输入的完整参考原文在已有折叠区保留，displayText 只显示原始 prompt 完整前缀；project 元数据路由到独立播放工程。Agent 执行 IPC 已封禁，未调用 dsh。',
 f'- 回放源：{replayed.parent.relative_to(ROOT)}，完整进入第 3–4 镜；完整事件和校验见该目录 replayed-events.json / replay-integrity.json。原任务 210.421 秒，回放约 40 秒，总时长压缩约 ×5.3。原存档没有逐事件时间戳，按原序分配停留，不声称恢复原始延迟。用户请求默认单行折叠，可展开全文。',
 '- final-check-02：真实 FreeCAD 凸台的确定性工具操作。要求与实测不符、定位、修改和检查回执全部来自实际执行；不是 Agent 第二次运行发现轮廓错误。',
 '- manual-02：历史真实 FreeCAD 参数编辑器连续采集，Qt 输入事件操作原生入口，4→5 mm，未通过模型 API 冒充手改。只用参数窗口局部，因为 Qt 全窗不能可靠抓取 OpenGL 视口。',
 '- final-edited-01：当前工作台重开 manual-02 的实际修改后副本；是厚度修改练习，不声称满足原图 4 mm。',
 '- final-guide-03：当前工作台全新用户目录、空工程、已有 Agent 入口和安装引导。未连接或启动 Agent，无无关文件标签。',
 '- Windows 验收摘录：GitHub run 41822011858 / 41ec469，ci-41822011858/installer/result.json 的 ok=true，中文账户“学生验收”。这是历史 Windows 版本；影片明确区分本版 macOS 打包流程，不将历史结果冒称新版 Windows 验收。',
 '- 本版 macOS 证据：docs/demo-video/empty-workbench.md 列出的 1366×768、1920×1080 两种宽度四轮打包流程，覆盖空工程、保存重开、工程隔离。',
 '- 第二次会话 b7fd234f 的应用检查没有发现截面积 777.5 vs 828.5 mm² 偏差；本片不用其错误模型冒充成功，缺陷与依据保存在 handoff.md。',
 '- 声音：Microsoft Edge zh-CN-XiaoxiaoNeural；原句边界剪入停顿，未强行加快；旁白另附 narration.txt。字体为项目 Noto Sans SC（OFL）。无第三方配乐。',
 '', '## 原片校验','']
 for name,c in checks.items():lines.append(f"- `{name}/raw.mp4` SHA256：`{c['raw_sha256']}`")
 # 同一原片的时间区间不能跨镜头重复。
 for i,a in enumerate(sources):
  for b in sources[i+1:]:
   if a.get('source') and a.get('source')==b.get('source') and a['shot']!=b['shot']:
    assert min(a['end'],b['end'])-max(a['begin'],b['begin'])<.01,(a,b)
 assets={p:digest(ROOT/p) for s in sources for p in s.get('assets',[])}
 lines+=['','## 示意动画与证据页素材','']
 for name,sha in assets.items():lines.append(f'- `{name}` SHA256：`{sha}`')
 model=ROOT/'out/demo-video/paid-robot4/robot4-1/project/robot4.FCStd';shown=replayed.parent/'robot4.FCStd';assert digest(model)==digest(shown)
 integrity={'model_sha256':digest(model),'displayed_model_equals_first_run':True,'original_conversation_sha256':digest(original),'replayed_events_sha256':digest(replayed),'events_equal':True,'event_count':71,'includes_failure':True,'windows_result_sha256':digest(ci),'sources':checks,'graphic_assets':assets}
 (OUT/'sources.md').write_text('\n'.join(lines)+'\n');(OUT/'source-integrity.json').write_text(json.dumps(integrity,ensure_ascii=False,indent=2))
 report={'ok':True,'duration_seconds':duration,'video':v,'audio':a,'full_decode':'passed','qa_frames':len(plan)*2,'film_sha256':digest(film),'sources':checks,'graphic_assets':assets}
 (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('validated',duration,'seconds',len(plan),'shots')
if __name__=='__main__':main()
