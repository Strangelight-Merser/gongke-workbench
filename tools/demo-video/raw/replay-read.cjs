// 演示专用只读原会话回放；不调用 Agent，不替换工具返回内容。
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {pause}=require('./app-recorder.cjs');
module.exports=async function(app,page,root,project,target){
 const source=path.join(root,'out/demo-video/paid-robot4/robot4-1');
 const archive=JSON.parse(fs.readFileSync(path.join(source,'conversation.json')));
 const connection=await page.evaluate(()=>window.gongke.agent.state());
 if(connection.phase!=='ready')throw Error('录制前必须真实连接 Agent');
 const snapshot={...archive,...connection,events:archive.events};
 const prompt=fs.readFileSync(path.join(source,'modeling-prompt.txt'),'utf8');
 const original=snapshot.events.slice(0,16);
 await app.evaluate(({ipcMain},s)=>{
  globalThis.rawReplay=s;ipcMain.removeHandler('acp-state');ipcMain.handle('acp-state',()=>globalThis.rawReplay);
  for(const ch of ['acp-start','acp-prompt','acp-new-session','acp-authenticate']){ipcMain.removeHandler(ch);ipcMain.handle(ch,()=>{throw Error('只读回放禁止执行')});}
 },{...snapshot,project,events:[],phase:'ready'});
 for(let i=0;i<original.length;i++){
  const events=original.slice(0,i+1).map(e=>e.type==='user'?{...e,displayText:prompt}:e);
  await app.evaluate(({BrowserWindow},s)=>{globalThis.rawReplay=s;BrowserWindow.getAllWindows()[0].webContents.send('acp-state',s)},{...snapshot,project,events,phase:i===15?'ready':'prompting'});
  if(original[i].type==='update'&&original[i].update.sessionUpdate==='tool_call')await pause(800);else await pause(180);
 }
 fs.mkdirSync(path.join(target,'events'),{recursive:true});
 fs.writeFileSync(path.join(target,'events/replayed-events.json'),JSON.stringify(original,null,2));
 const userText=original.find(e=>e.type==='user').text;
 const reference=JSON.parse(userText.slice(userText.indexOf('{"path"')));
 const row=fs.readFileSync(path.join(source,'tool-calls.jsonl'),'utf8').trim().split('\n').map(JSON.parse).find(r=>r.command==='project.read_drawing');
 const read={source:'首次成功会话的原始读图返回，含产品附加参考与 Agent 补读结果',chunks:[reference,row.result]};
 fs.writeFileSync(path.join(target,'events/read_drawing.json'),JSON.stringify(read,null,2));
 fs.writeFileSync(path.join(target,'events/replay-source.json'),JSON.stringify({source:path.join(source,'conversation.json'),indices:[0,15],sha256:crypto.createHash('sha256').update(JSON.stringify(original)).digest('hex'),unchanged:true,paid_agent:false},null,2));
};
