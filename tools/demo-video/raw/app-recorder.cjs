// 应用内真实帧采集。时间来自单调时钟，所有输入坐标转换为最终录屏像素。
const fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function encode(out,frames,duration){
 const rows=[];
 for(let i=0;i<frames.length;i++){
  rows.push(`file 'frames/${frames[i].file}'`,`duration ${Math.max(.001,(frames[i+1]?.seconds??duration)-frames[i].seconds)}`);
 }
 rows.push(`file 'frames/${frames.at(-1).file}'`);
 fs.writeFileSync(path.join(out,'frames.ffconcat'),rows.join('\n'));
 await new Promise((resolve,reject)=>{
  const p=spawn('ffmpeg',['-v','error','-y','-f','concat','-safe','0','-i',path.join(out,'frames.ffconcat'),'-vf','scale=2560:1440:flags=lanczos,fps=60','-t',String(duration),'-c:v','libx264','-preset','fast','-crf','17','-pix_fmt','yuv420p','-an','-movflags','+faststart',path.join(out,'clip.mp4')],{stdio:'inherit'});
  p.on('exit',c=>c===0?resolve():reject(Error('编码失败')));
 });
}
async function startRecording(page,out){
 fs.mkdirSync(path.join(out,'frames'),{recursive:true});
 const start=performance.now(),frames=[],events=[];let active=true;
 const clock=()=> (performance.now()-start)/1000;
 const size=await page.evaluate(()=>({width:innerWidth,height:innerHeight}));
 const channel='rawInput'+Date.now();
 await page.exposeFunction(channel,e=>events.push({...e,seconds:clock(),x:e.x*2560/size.width,y:e.y*1440/size.height}));
 await page.evaluate(channel=>{
  const last={x:0,y:0};
  window.__rawInputController?.abort();const controller=new AbortController();window.__rawInputController=controller;
  for(const type of ['pointermove','pointerdown','pointerup','wheel','keydown','keyup','input'])window.addEventListener(type,e=>{
   if('clientX'in e){last.x=e.clientX;last.y=e.clientY;}
   window[channel]({kind:type,...last,key:e.key,button:e.button,deltaX:e.deltaX,deltaY:e.deltaY,text:type==='input'?e.target.value:undefined});
  },{capture:true,signal:controller.signal});
 },channel);
 const loop=(async()=>{while(active){
  const before=clock(),file=String(frames.length).padStart(6,'0')+'.jpg';
  const frame=await page.screenshot({type:'jpeg',quality:92,timeout:15000});
  fs.writeFileSync(path.join(out,'frames',file),frame);frames.push({file,seconds:before});
  await pause(Math.max(0,1000/30-(clock()-before)*1000));
 }})();
 await pause(1000);
 return {mark(description){events.push({kind:'event',seconds:clock(),description})},async stop(){
  await pause(1000);active=false;await loop;const duration=clock();
  await page.evaluate(()=>window.__rawInputController.abort());
  const report={width:2560,height:1440,fps:60,duration,source:'Electron / Playwright 实际界面逐帧采集',system_cursor:false,overlays:false,timebase:'seconds from first capture',coordinate_space:'output pixels; top left origin',frame_timing:'真实采集时间戳，按时间保持原帧补足 60 fps，不生成虚构中间状态',capture_frames:frames.length,events};
  fs.writeFileSync(path.join(out,'events.json'),JSON.stringify(report,null,2));
  fs.writeFileSync(path.join(out,'frames.json'),JSON.stringify(frames));
  await encode(out,frames,duration);return report;
 }};
}
async function click(page,locator){const box=await locator.boundingBox();if(!box)throw Error('目标不可见');await page.mouse.move(box.x+box.width/2,box.y+box.height/2,{steps:24});await pause(180);await page.mouse.click(box.x+box.width/2,box.y+box.height/2);}
module.exports={startRecording,encode,click,pause};
