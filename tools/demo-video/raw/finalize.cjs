// 只统一编码规格并按叙事顺序接合第 07 段的应用切换；不加任何视觉元素。
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'../../..'),base=path.join(root,'out/demo-video/raw');
function probe(file){const p=spawnSync('ffprobe',['-v','error','-select_streams','v:0','-show_entries','stream=width,height,codec_name,r_frame_rate:format=duration','-of','json',file],{encoding:'utf8'});if(p.status!==0)throw Error(p.stderr);return JSON.parse(p.stdout);}
const ids=['02-pdf','03-overview','04-read','05-growth','06-check','07-fix','08-agent'];
const dir=path.join(base,'07-fix'),parts=['01-edit','02-check','03-save-reopen','04-tree'];let offset=0,events=[],segments=[];
for(const part of parts){const p=path.join(dir,'parts',part),e=JSON.parse(fs.readFileSync(path.join(p,'events.json'))),duration=Number(probe(path.join(p,'clip.mp4')).format.duration);segments.push({source:`parts/${part}/clip.mp4`,start:offset,duration});events.push(...e.events.map(x=>({...x,kind:({'2':'pointerdown','3':'pointerup','5':'pointermove','6':'keydown','7':'keyup'})[x.kind]||x.kind,seconds:x.seconds+offset,source:part})));offset+=duration;}
fs.writeFileSync(path.join(dir,'concat.txt'),parts.map(p=>`file 'parts/${p}/clip.mp4'`).join('\n'));
const concat=spawnSync('ffmpeg',['-v','error','-y','-f','concat','-safe','0','-i',path.join(dir,'concat.txt'),'-c','copy','-movflags','+faststart',path.join(dir,'clip.mp4')],{encoding:'utf8'});if(concat.status!==0)throw Error(concat.stderr);
fs.writeFileSync(path.join(dir,'events.json'),JSON.stringify({width:2560,height:1440,fps:60,duration:offset,system_cursor:false,overlays:false,coordinate_space:'output pixels; top left origin',source:'按叙事顺序接合四段应用内原始采集；每段原片均保留',segments,events},null,2));
const index=[];
for(const id of ids){const p=path.join(base,id),media=probe(path.join(p,'clip.mp4')),v=media.streams[0],e=JSON.parse(fs.readFileSync(path.join(p,'events.json')));if(v.width!==2560||v.height!==1440||v.r_frame_rate!=='60/1'||v.codec_name!=='h264')throw Error(id+'规格不符');if(e.events.some(x=>x.seconds<0||x.seconds>Number(media.format.duration)+.2))throw Error(id+'事件越界');fs.writeFileSync(path.join(p,'probe.json'),JSON.stringify(media,null,2));index.push({id,path:`${id}/clip.mp4`,duration:Number(media.format.duration),events:e.events.filter(x=>x.kind==='event').map(({seconds,description})=>({seconds,description}))});}
fs.writeFileSync(path.join(base,'index.json'),JSON.stringify(index,null,2));console.log(JSON.stringify(index,null,2));
