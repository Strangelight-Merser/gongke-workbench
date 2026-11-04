// Chrome DevTools 的真实连续帧与输入事件；不注入模型、回执或界面内容。
const fs = require('node:fs');
const path = require('node:path');
exports.startRecording = async function(page, directory) {
  fs.mkdirSync(path.join(directory,'frames'),{recursive:true});
  const cdp=await page.context().newCDPSession(page);
  const frames=[], inputs=[];
  const started=Date.now();
  const save=()=>fs.writeFileSync(path.join(directory,'recording.json'),JSON.stringify({started,ended:Date.now(),frames,inputs}));
  await page.exposeFunction('recordDemoInput',e=>inputs.push(e));
  const listener=()=>{
    for(const kind of ['pointermove','pointerdown','pointerup'])
      window.addEventListener(kind,e=>window.recordDemoInput({kind,x:e.clientX,y:e.clientY,at:Date.now()}));
  };
  await page.addInitScript(listener);
  await page.evaluate(listener);
  cdp.on('Page.screencastFrame',e=>{
    const file=String(frames.length).padStart(6,'0')+'.jpg';
    fs.writeFileSync(path.join(directory,'frames',file),Buffer.from(e.data,'base64'));
    frames.push({file,timestamp:e.metadata.timestamp});
    cdp.send('Page.screencastFrameAck',{sessionId:e.sessionId}).catch(()=>{});
  });
  await cdp.send('Page.startScreencast',{format:'jpeg',quality:90,maxWidth:1920,maxHeight:1080,everyNthFrame:2});
  const timer=setInterval(save,2000);
  return {directory,started,mark(name){inputs.push({kind:'mark',name,at:Date.now()});save();},async stop(){
    clearInterval(timer);await cdp.send('Page.stopScreencast');save();
    if(!frames.length) throw Error('未采集到真实帧');
  }};
};
