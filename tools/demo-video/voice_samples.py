"""仅使用已有 edge-tts / ffmpeg，制作口语稿前三种声线的对比样音。"""
import asyncio,json,re,subprocess,wave
from pathlib import Path
import edge_tts
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'out/demo-video/voice-samples'
# 文本与 narration-spoken.md 的第1、2段一致；停顿为去除句尾静音后的实插值。
LINES=[('看着图纸建模，最麻烦的是什么？',.38),('图纸、CAD，来回切。',.25),('改一个尺寸，又得回去核对。',.60),('我们做的构想引擎，',.16),('把这些操作，放进同一个工作台。',.32),('让智能体帮你读图、建模，',.16),('你再接着改。',.28)]
VOICES=[('01-Yunxi','zh-CN-YunxiNeural',['-12%','-20%']),('02-Yunyang','zh-CN-YunyangNeural',['-12%','-20%']),('03-Xiaoyi','zh-CN-XiaoyiNeural',['-12%','-20%'])]
def duration(p):
 return float(subprocess.check_output(['ffprobe','-v','quiet','-show_entries','format=duration','-of','csv=p=0',str(p)]))
def command(args):subprocess.run(args,check=True)
async def candidate(name,voice,rate):
 folder=OUT/'takes'/f'{name}-{rate}';folder.mkdir(parents=True,exist_ok=True)
 chunks=[];timeline=[];pos=.12
 chunks.append(b'\0'*round(.12*24000)*2)
 for i,(text,pause) in enumerate(LINES):
  mp3=folder/f'{i+1:02}.mp3';wav=folder/f'{i+1:02}.wav'
  if not mp3.exists():await edge_tts.Communicate(text,voice,rate=rate,pitch='+0Hz').save(str(mp3))
  # 只清理片头尾静音；不截断句中停顿，不改变语速或音高。
  command(['ffmpeg','-v','error','-y','-i',str(mp3),'-af','silenceremove=start_periods=1:start_duration=0:start_threshold=-50dB:start_silence=0.04,areverse,silenceremove=start_periods=1:start_duration=0:start_threshold=-50dB:start_silence=0.06,areverse','-ar','24000','-ac','1','-c:a','pcm_s16le',str(wav)])
  with wave.open(str(wav)) as f:data=f.readframes(f.getnframes());length=f.getnframes()/f.getframerate()
  chunks.extend([data,b'\0'*round(pause*24000)*2]);timeline.append({'text':text,'start':round(pos,3),'speech_seconds':round(length,3),'pause_after':pause});pos+=length+pause
 joined=folder/'joined.wav'
 with wave.open(str(joined),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(b''.join(chunks))
 return {'name':name,'voice':voice,'rate':rate,'pitch':'+0Hz','seconds':duration(joined),'timeline':timeline,'source':str(joined.relative_to(ROOT))}
async def main():
 OUT.mkdir(parents=True,exist_ok=True);selected=[];trials=[]
 for name,voice,rates in VOICES:
  takes=[]
  for rate in rates:
   r=await candidate(name,voice,rate);takes.append(r);trials.append(r);print(voice,rate,round(r['seconds'],2),flush=True)
  # 以接近19.2秒且不靠后期时间拉伸为筛选依据；音色偏好留给用户对照试听。
  best=min(takes,key=lambda x:abs(x['seconds']-19.2));target=OUT/f"{name}_rate{best['rate'].replace('%','pct')}_pauses.wav"
  command(['ffmpeg','-v','error','-y','-i',str(ROOT/best['source']),'-af','loudnorm=I=-18:TP=-2:LRA=9','-ar','24000','-ac','1','-c:a','pcm_s16le',str(target)])
  best['output']=str(target.relative_to(ROOT));selected.append(best)
 (OUT/'settings.json').write_text(json.dumps({'edge_tts_version':edge_tts.__version__,'target_seconds':19.2,'selection':'按实测时长选择更接近19.2秒的原生合成语速，未后期变速；不代表已经完成主观听感评价','selected':selected,'trials':trials},ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':asyncio.run(main())
