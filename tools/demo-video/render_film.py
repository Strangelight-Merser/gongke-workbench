"""真实连续帧剪辑：时间戳采样、缓动镜头、实际光标、外置字幕及逐镜检查图。"""
import bisect,hashlib,json,math,re,subprocess
from functools import lru_cache
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'out/demo-video';FPS=30
@lru_cache(None)
def font(size,weight=500):
 f=ImageFont.truetype(str(ROOT/'desktop/src/assets/preview-font.ttf'),size);f.set_variation_by_axes([weight]);return f

def sec(t):
 h,m,s,ms=map(int,re.split('[:,]',t));return h*3600+m*60+s+ms/1000

def stamp(t):
 n=round(t*1000);return f'{n//3600000:02}:{n//60000%60:02}:{n//1000%60:02},{n%1000:03}'

def ease(v):
 v=max(0,min(1,v));return v*v*(3-2*v)

class Recording:
 def __init__(self,path):
  self.path=ROOT/path;self.data=json.loads((self.path/'recording.json').read_text());self.frames=self.data['frames'];self.base=self.frames[0]['timestamp'];self.times=[f['timestamp']-self.base for f in self.frames];self.events=self.data.get('inputs',[]);self.pointer=[e for e in self.events if e['kind'] in ['pointermove','pointerdown','pointerup']];self.pt=[e['at']/1000-self.base for e in self.pointer];self.index=-1;self.picture=None
 def frame(self,t):
  i=max(0,bisect.bisect_right(self.times,t)-1)
  if i!=self.index:self.picture=Image.open(self.path/'frames'/self.frames[i]['file']).convert('RGB');self.index=i
  return self.picture
 def cursor(self,t):
  i=bisect.bisect_right(self.pt,t)-1
  return self.pointer[i] if i>=0 else None

def background():
 im=Image.new('RGB',(1920,1080));d=ImageDraw.Draw(im)
 for y in range(1080):
  q=y/1080;d.line((0,y,1920,y),fill=(int(12+6*q),int(23+9*q),int(39+12*q)))
 shadow=Image.new('RGBA',im.size);ImageDraw.Draw(shadow).rounded_rectangle((152,62,1768,975),radius=30,fill=(0,0,0,130));shadow=shadow.filter(ImageFilter.GaussianBlur(22));im.paste(shadow,(0,0),shadow)
 return im

def main():
 plan=json.loads((ROOT/'tools/demo-video/timeline.json').read_text());records={p:Recording(p) for p in {s['source'] for sh in plan for s in sh['segments']}}
 voice=json.loads((OUT/'voice/segments.json').read_text());subs=[];position=0;audio=[];sources=[]
 for shot,v in zip(plan,voice):
  duration=sum(s['duration'] for s in shot['segments']);shot['start']=position;shot['duration']=duration
  offset=.25;assert v['voice_seconds']+offset<duration+.1,(shot['id'],v['voice_seconds'],duration)
  src=OUT/f"voice/{shot['id']:02}.srt"
  blocks=src.read_text().strip().split('\n\n')
  for sentence_index,block in enumerate(blocks):
   lines=block.splitlines();a,b=map(sec,lines[1].split(' --> '));original_a=a;original_b=b
   if 'voice_starts' in shot:
    desired=shot['voice_starts'][sentence_index];a=desired-offset;b=a+original_b-original_a
   text=''.join(lines[2:]);parts=[x for x in re.split('(?<=[，。？！；])',text) if x]
   chunks=[]
   for p in parts:
    if chunks and len(chunks[-1]+p)<=24:chunks[-1]+=p
    else:chunks.append(p)
   cursor=a
   for p in chunks:
    end=cursor+(b-a)*len(p)/len(text);subs.append([position+offset+cursor,position+offset+end,p]);cursor=end
  if 'voice_starts' in shot:
   for i,block in enumerate(blocks):
    ls=block.splitlines();a,b=map(sec,ls[1].split(' --> '));clip=OUT/f"voice/{shot['id']:02}-sentence-{i}.wav"
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(a),'-i',str(ROOT/v['audio']),'-t',str(b-a),'-c:a','pcm_s16le',str(clip)],check=True)
    audio.append((clip,position+shot['voice_starts'][i]))
  else:audio.append((ROOT/v['audio'],position+offset))
  position+=duration
 for a,b in zip(subs,subs[1:]):a[1]=min(a[1],b[0])
 (OUT/'film.srt').write_text('\n\n'.join(f'{i}\n{stamp(a)} --> {stamp(b)}\n{text}' for i,(a,b,text) in enumerate(subs,1))+'\n')
 (OUT/'narration.txt').write_text('\n\n'.join(f"{s['id']:02} · {stamp(s['start'])}\n{v['text']}" for s,v in zip(plan,voice))+'\n')
 cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-']
 for p,_ in audio:cmd+=['-i',str(p)]
 filters=[]
 for i,(_,t) in enumerate(audio,1):filters.append(f'[{i}:a]adelay={round(t*1000)}:all=1[a{i}]')
 filters.append(''.join(f'[a{i}]' for i in range(1,len(audio)+1))+f'amix=inputs={len(audio)}:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=7,apad[a]')
 cmd+=['-filter_complex',';'.join(filters),'-map','0:v','-map','[a]','-t',str(position),'-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(OUT/'film.mp4')]
 process=subprocess.Popen(cmd,stdin=subprocess.PIPE);base=background();mask=Image.new('L',(1600,900));ImageDraw.Draw(mask).rounded_rectangle((0,0,1599,899),radius=19,fill=255)
 qa=OUT/'qa';qa.mkdir(exist_ok=True)
 for shot in plan:
  local=0;qa_saved=False
  for segment in shot['segments']:
   record=records[segment['source']];speed=(segment['end']-segment['begin'])/segment['duration'];assert speed>0
   sources.append({**segment,'shot':shot['id'],'film_start':shot['start']+local,'speed':speed,'source_first_timestamp':record.base})
   count=round(segment['duration']*FPS)
   for n in range(count):
    t=n/FPS;absolute=shot['start']+local+t;source_t=segment['begin']+t*speed;frame=record.frame(source_t);canvas=base.copy();draw=ImageDraw.Draw(canvas)
    draw.text((160,17),'构想引擎',font=font(25,650),fill='#ecf4fa');draw.text((330,19),shot['title'],font=font(23),fill='#9fb2c6')
    badge=segment.get('badge','')
    if speed>1.001:badge=(badge+'  ·  ' if badge else '')+f'×{speed:g} 加速'
    if badge:draw.text((1760,20),badge,font=font(22),fill='#77d6cd',anchor='ra')
    if segment.get('layout')=='agent':
     w,h=frame.size;pic=frame.crop((w*.815,h*.04,w*.999,h*.64));pic.thumbnail((690,800),Image.Resampling.LANCZOS)
     # 将真实 Agent 栏单独放大，不让无关的 CI 文档抢占该镜头。
     scale=min(690/pic.width,800/pic.height);pic=pic.resize((round(pic.width*scale),round(pic.height*scale)),Image.Resampling.LANCZOS)
     x=1030+(690-pic.width)//2;y=90+(800-pic.height)//2;m=Image.new('L',pic.size);ImageDraw.Draw(m).rounded_rectangle((0,0,pic.width-1,pic.height-1),radius=18,fill=255);canvas.paste(pic,(x,y),m)
     draw=ImageDraw.Draw(canvas);draw.text((175,280),'接入已有智能体',font=font(62,650),fill='#eef5fa');draw.text((178,385),'DeepSeek Harness',font=font(43,550),fill='#77d6cd');draw.text((180,540),'原生接口，调用工程工具',font=font(32),fill='#d4e2ee');draw.text((180,608),'未安装时，按引导开始',font=font(29),fill='#9fb2c6')
    elif segment.get('layout')=='editor':
     w,h=frame.size;pic=frame.crop((w*.725,h*.33,w*.995,h*.91));pic.thumbnail((710,780),Image.Resampling.LANCZOS);x=1030+(710-pic.width)//2;y=110+(780-pic.height)//2
     m=Image.new('L',pic.size);ImageDraw.Draw(m).rounded_rectangle((0,0,pic.width-1,pic.height-1),radius=18,fill=255);canvas.paste(pic,(x,y),m)
     draw=ImageDraw.Draw(canvas);draw.text((175,290),'学生接手',font=font(65,650),fill='#eef5fa');draw.text((175,390),'参数，由你修改',font=font(50,600),fill='#77d6cd');draw.text((180,550),'4 mm → 5 mm',font=font(43),fill='#d4e2ee');draw.text((180,635),'工作副本中的厚度修改练习',font=font(26),fill='#9fb2c6')
    else:
     w,h=frame.size;z0,z1=segment.get('zoom',[1,1.12]);progress=ease(t/min(4,max(1,segment['duration']*.65)));z=z0+(z1-z0)*progress
     cx,cy=segment.get('focus',[.5,.5]);cw=w/z;ch=h/z;left=max(0,min(w-cw,cx*w-cw/2));top=max(0,min(h-ch,cy*h-ch/2));pic=frame.crop((left,top,left+cw,top+ch)).resize((1600,900),Image.Resampling.LANCZOS);canvas.paste(pic,(160,60),mask)
     # 原始指针坐标来自1920×1080 Electron控件事件；强调真实输入，不生成演示点击。
     pointer=record.cursor(source_t)
     if pointer and 0<=pointer['x']<1920:
      px=pointer['x']/1920*w;py=pointer['y']/1080*h;x=160+(px-left)/cw*1600;y=60+(py-top)/ch*900
      if 170<x<1750 and 70<y<950:
       overlay=Image.new('RGBA',canvas.size);od=ImageDraw.Draw(overlay);od.ellipse((x-20,y-20,x+20,y+20),fill=(89,205,196,48),outline=(60,169,162,150),width=2);od.polygon([(x,y),(x+2,y+23),(x+8,y+17),(x+14,y+29),(x+19,y+26),(x+12,y+14),(x+22,y+13)],fill='white',outline='#173447');canvas.paste(overlay,(0,0),overlay)
    draw=ImageDraw.Draw(canvas)
    for a,b,text in subs:
     if a<=absolute<b:draw.text((960,1008),text,font=font(38,500),fill='#f3f7fb',anchor='mm');break
    if not qa_saved and local+t>=min(shot['duration']/2,5):canvas.save(qa/f"shot-{shot['id']:02}.png");qa_saved=True
    process.stdin.write(canvas.tobytes())
   local+=segment['duration']
  print('rendered',shot['id'],flush=True)
 process.stdin.close();assert process.wait()==0
 (OUT/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2))
 (OUT/'timeline.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
 print('complete',position,flush=True)
if __name__=='__main__':main()
