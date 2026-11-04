"""验证已编码交付规格，逐镜从 MP4 抽帧，整理原片与素材来源。"""
import hashlib,json,subprocess
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'out/demo-video'
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
  t=shot['start']+shot['duration']/2
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(t),'-i',str(film),'-frames:v','1',str(qa/f"shot-{shot['id']:02}.png")],check=True)
 for shot in plan:
  offset={7:9,8:4.5,9:10,10:3}.get(shot['id'],3)
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(shot['start']+offset),'-i',str(film),'-frames:v','1',str(qa/f"shot-{shot['id']:02}-detail.png")],check=True)
 contact=Image.new('RGB',(1200,4*247),'#101e30');draw=ImageDraw.Draw(contact)
 for i,shot in enumerate(plan):
  im=Image.open(qa/f"shot-{shot['id']:02}.png");im.thumbnail((394,222));x=i%3*400;y=i//3*247;contact.paste(im,(x,y));draw.text((x+8,y+226),f"{shot['id']:02} / {shot['start']:.1f}s",fill='white')
 contact.save(qa/'contact-sheet.jpg')
 lines=['# 素材来源与剪辑清单','',f'成片 {duration:g} 秒，1920×1080，30 fps，H.264 / AAC。无配乐。全片使用真实连续界面或 CAD 视口采集，没有静态截图镜头。','',
 '时间均为相应原片 raw.mp4 起点后的秒数。每一段的画面只做裁剪、缩放、外框、实际光标强调和字幕处理，没有替换界面文本或模型。剪掉的等待不是连续运行耗时；唯一 Agent 任务实际 210.421 秒。','',
 '| 镜头 | 成片起点 | 原片 | 原片区间（秒） | 播放倍率 |','|---|---:|---|---|---:|']
 for s in sources:
  raw=s['source']+'/raw.mp4'
  lines.append(f"| {s['shot']:02} | {s['film_start']:.2f} | `{raw}` | {s['begin']:.2f}–{s['end']:.2f} | {s['speed']:g} |")
 lines+=['','## 来源说明','',
 '- paid-robot4/raw：唯一一次付费 DeepSeek Harness 会话；robot4 矢量 PDF 读图，FreeCAD 原生建模。原片及会话用量、工具回执、独立图纸审计、重开结果一起保留。',
 '- showcase-01：本次生成模型的工作副本；特征树点击、真实鼠标旋转、另存工作修订、Agent 配置/引导、减速器已有结果与 CI JSON 文件查看。',
 '- manual-02：独立 FreeCAD Qt 窗口连续采集，以 Qt 输入事件操作实际 Pad 参数编辑器，4→5 mm，保存副本。Qt 全窗抓取不能可靠包含 OpenGL 视口，因此只采用真实参数编辑器特写，没有补造模型图像。',
 '- showcase-02：重新打开手改后副本；厚度 5 mm 的实际只读检查见 manual-check.jsonl。它是修改练习，不是对原图 4 mm 的符合性声明。',
 '- preflight-03：真实凸台模型的确定性 MCP 检查与修正，明确标为尺寸检查示例，不说成 Agent 自主纠错。',
 '- reducer-viewport：FreeCAD 运行中持续采集真实视口；实际导入同修订 reducer_assembly.step，记录每帧时间，缓慢旋转，不生成或替换几何；110 个实体。不是工作台内 STEP 预览功能的演示。',
 '- 减速器来源：out/desktop-validation/1793769105330/传动设计，修订 6f2c35f49d77；三维 STEP、二维 PDF、report.md/report.docx 均来自此修订。操作发生在复制工程。reducer-01 展示将工作拉力从 2500 改为 2600 并计算后真实出现的过期状态。documents-01 展示恢复 2500 后的当前成果 PDF。',
 '- CI 工件原始 result.json：ci-41822011858/installer/result.json，ok=true。影片中的表格来自产品真实 JSON 查看器对该原文件的渲染（ok 显示为“通过：是”）。GitHub run 41822011858 / 41ec469，详情见 handoff.md。',
 '- 图纸：用户已明确批准 robot4 出镜；源 PDF 不提交 Git，不扩展到其他学生资料。',
 '- 声音：Microsoft Edge zh-CN-XiaoxiaoNeural，逐句使用原始时间边界，剪入停顿而非强行变速；旁白另附 narration.txt。没有配乐。',
 '- 字体：项目 Noto Sans SC，OFL；没有使用第三方演示片的图像、声音或音乐。',
 '', '## 原片校验','']
 checks={}
 for name in sorted({s['source'] for s in sources}):
  p=ROOT/name/'raw.mp4';assert p.exists(),p;checks[name]={'raw_sha256':digest(p),'recording_sha256':digest(ROOT/name/'recording.json')};lines.append(f"- `{name}/raw.mp4` SHA256：`{checks[name]['raw_sha256']}`")
 (OUT/'sources.md').write_text('\n'.join(lines)+'\n')
 report={'ok':True,'duration_seconds':duration,'video':v,'audio':a,'full_decode':'passed','qa_frames':len(plan)*2,'film_sha256':digest(film),'sources':checks}
 (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('validated',duration,'seconds',len(plan),'shots')
if __name__=='__main__':main()
