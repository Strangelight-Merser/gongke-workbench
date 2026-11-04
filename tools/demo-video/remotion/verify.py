"""核对样片编码与原 MCP 参数，导出字幕、来源时间段和每秒抽帧。"""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];out=ROOT/'out/demo-video/rebuild';samples=out/'samples';growth=out/sys.argv[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=json.loads((growth/'recording.json').read_text());marks={m['name']:m['at']/1000-record['frames'][0]['timestamp'] for m in record['inputs'] if m['kind']=='mark'}
calls=json.loads((growth/'reexecution.json').read_text())['calls'];original=[json.loads(l) for l in (ROOT/'out/demo-video/paid-robot4/robot4-1/tool-calls.jsonl').read_text().splitlines()]
assert len(calls)==len(original)==10
for i,(new,old) in enumerate(zip(calls,original)):
    assert new['index']==i and new['command']==old['command']
    assert new['original_params']==old['params']
    assert {k:v for k,v in new['params'].items() if k not in new['bindings']}=={k:v for k,v in old['params'].items() if k not in new['bindings']}
    assert set(new['bindings'])<= {'host_instance','document'}
    assert not new['is_error'] and new['response']['status']=='complete'
first=marks['start-5']-.8;second=marks['start-6']-.6
sources={'opening':{'duration':12,'kind':'真实图纸与模型数据的品牌动画','drawing':str(growth/'project/inputs/f00b1b9d-e9b/robot4.pdf'),'geometry':str(out/'assets/geometry.json'),'mesh':str(growth/'scene-06.json'),'watermark':'只取正视图原矢量轮廓和尺寸/界线，不包含水印对象；原 PDF 不改动'},'growth':{'duration':13,'kind':'新 FreeCAD 经 MCP 原参数重执行的真实连续录屏剪辑','raw':str(out/'assets/growth.mp4'),'capture':str(growth/'recording.json'),'receipts':str(growth/'reexecution.json'),'segments':[{'output':[0,5],'source':[round(first*60)/60,round(first*60)/60+5],'speed':1},{'output':[5,13],'source':[round(second*60)/60,round(second*60)/60+8],'speed':1}],'cuts':'只省略两次工具调用间的一段静置；没有重排调用、改参数或画出不存在的步骤'},'voice':'本轮无配音、无配乐'}
qa=samples/'qa';qa.mkdir(exist_ok=True)
for name in ['opening','growth']:
    file=samples/(name+'.mp4');probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(file)]));v=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert (v['width'],v['height'],v['codec_name'],v['avg_frame_rate'])==(1920,1080,'h264','60/1')
    assert abs(float(probe['format']['duration'])-sources[name]['duration'])<.05
    sources[name]['sha256']=sha(file);sources[name]['probe']=probe
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(file),'-vf','fps=1',str(qa/(name+'-%02d.png'))],check=True)
(samples/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2))
(samples/'growth.srt').write_text('1\n00:00:02,600 --> 00:00:04,833\n草图先建立起来\n\n2\n00:00:08,683 --> 00:00:12,667\n再拉伸，成为可编辑的零件\n')
(samples/'README.md').write_text(f'''# 大纲 v2 样片

opening.mp4：12 秒品牌开场。growth.mp4：13 秒真实建模。styleboard.png：字体、配色、字幕、标注样式。均为 1080p60；本轮没有声音。

高潮原片：{growth.name}，Retina 3840×2160 CDP 连续采集。第一段取原片 {first:.3f}–{first+5:.3f} 秒，第二段取 {second:.3f}–{second+8:.3f} 秒。原速，只剪掉静置。第一段显示草图生成，第二段显示拉伸和原生特征树；工具卡来自此次真实 MCP 回执。原会话 10 次工程调用完整重执行，只有宿主、文档运行时身份重绑定。

片头用同一份图纸的完整正视轮廓、原标注及尺寸线，模型网格由真实宿主输出。没有改原 PDF，没有绘制或遮挡原图的尺寸、线条；水印对象未进入动画。

来源、精确时间段和文件 SHA-256 见 sources.json；逐秒抽帧在 qa/。复现方式与大纲 13 项问题对照见 docs/demo-video/remake-samples.md。

到此停止，等待样片审阅；全片、最终声音及 GUI 修正段尚未制作。
''')
print('视频规格、时长、10 次原参数调用、来源、字幕、逐秒抽帧：通过')
