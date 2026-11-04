// 演示工具专用只读 ACP 回放；不加入产品入口，不连接或调用 Agent。
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{createHash}=require('node:crypto');
const {electron}=require('../../desktop/tests/helpers/owned-electron.cjs');
const {startRecording}=require('./recorder.cjs');
const root=path.resolve(__dirname,'../..'),out=path.resolve(process.argv[2]),pause=ms=>new Promise(r=>setTimeout(r,ms));
const source=path.join(root,'out/demo-video/paid-robot4/robot4-1');
(async()=>{
 assert(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});fs.mkdirSync(path.join(out,'host'));
 const snapshot=JSON.parse(fs.readFileSync(path.join(source,'conversation.json'),'utf8'));
 const original=JSON.stringify(snapshot.events),prompt=fs.readFileSync(path.join(source,'modeling-prompt.txt'),'utf8');
 const model=path.join(out,'robot4.FCStd');fs.copyFileSync(path.join(source,'project/robot4.FCStd'),model);
 const env={...process.env,GONGKE_DESKTOP_USER_DATA:path.join(out,'user'),GONGKE_PYTHON:'/private/tmp/gongke-modeling-venv/bin/python',GONGKE_MODELING_ROOT:root,GONGKE_FREECAD_SESSION:path.join(out,'host/session.json'),GONGKE_TRIAL_BACKGROUND:'1',GONGKE_DEMO_MODEL:model};delete env.ELECTRON_RUN_AS_NODE;
 const log=fs.openSync(path.join(out,'host.log'),'w');const cad=spawn('/Applications/FreeCAD.app/Contents/Resources/bin/freecad',['--user-cfg',path.join(out,'host/user.cfg'),path.join(__dirname,'showcase_host.FCMacro')],{env,stdio:['ignore',log,log]});fs.closeSync(log);
 let app,rec;
 try{
  for(let i=0;i<150&&!fs.existsSync(path.join(out,'host/model-loaded.json'));i++)await pause(200);
  assert(fs.existsSync(path.join(out,'host/model-loaded.json')));
  app=await electron.launch({args:[path.join(root,'desktop')],env});const page=await app.firstWindow();page.setDefaultTimeout(20000);
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1920,1080));await page.getByText('就绪',{exact:true}).waitFor();
  const project=path.join(out,'project');await page.evaluate(p=>window.gongke.request('project.create',{path:p,name:'机器人零件'}),project);await page.reload();
  await app.evaluate(({dialog},p)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[p]})},path.join(root,'out/demo-video/paid-robot4/inputs/robot4.pdf'));
  await page.getByRole('button',{name:'导入图纸',exact:true}).click();await page.locator('.pdf-document[data-render-state="ready"]:visible').waitFor();
  await page.getByRole('button',{name:'Agent 连接设置',exact:true}).click();await page.getByRole('menuitem',{name:'使用已配置的 Agent',exact:true}).click();
  rec=await startRecording(page,out);rec.mark('drawing');await pause(10000);
  await page.getByText('原生 CAD',{exact:true}).click();await page.getByRole('button',{name:'连接 FreeCAD',exact:true}).click();await pause(800);await page.getByRole('button',{name:'读取 FreeCAD 工程',exact:true}).click();await page.getByRole('button',{name:'Profile · 草图',exact:true}).waitFor();
  rec.mark('workspace');await pause(13000);
  // 只替换当前独立进程的 ACP 传输。所有执行入口明确拒绝，工程真实读操作照常走产品。
  await app.evaluate(({ipcMain},s)=>{
   globalThis.demoSnapshot=s;
   ipcMain.removeHandler('acp-state');ipcMain.handle('acp-state',()=>globalThis.demoSnapshot);
   for(const channel of ['acp-start','acp-prompt','acp-authenticate','acp-new-session','acp-permission','acp-set-config-option','acp-save-settings']){
    ipcMain.removeHandler(channel);ipcMain.handle(channel,()=>{throw Error('只读会话回放，禁止执行')});
   }
  },{...snapshot,project,events:[],phase:'ready'});
  const replayed=[];const weights=snapshot.events.map(e=>e.type==='user'?3:e.type==='notice'?2:e.type==='update'&&e.update.status==='failed'?3:e.type==='update'&&['agent_thought_chunk','agent_message_chunk','tool_call_update'].includes(e.update.sessionUpdate)?1.4:.15);
  const sum=weights.reduce((a,b)=>a+b,0);let cumulative=0;const started=Date.now();rec.mark('replay-start');
  for(let i=0;i<snapshot.events.length;i++){
   const e=snapshot.events[i];replayed.push(e);
   // 原文不变；仅将旧版存储的用户参考长文本放进新版已有的折叠区域。
   const view=replayed.map(x=>x.type==='user'&&x.text.startsWith(prompt)?{...x,displayText:prompt}:x);
   await app.evaluate(({BrowserWindow},s)=>{globalThis.demoSnapshot=s;BrowserWindow.getAllWindows()[0].webContents.send('acp-state',s)}, {...snapshot,project,events:view,phase:i===snapshot.events.length-1?'ready':'prompting'});
   for(const group of await page.locator('details.agent-tool-group:not([open]) > summary').all()) await group.click();
   // 让新增原始记录保持可见；不修改节点或内容。
   await page.getByRole('log',{name:'工程对话',exact:true}).evaluate(el=>{el.scrollTop=el.scrollHeight}).catch(()=>{});
   cumulative+=weights[i];await pause(Math.max(0,started+40000*cumulative/sum-Date.now()));
  }
  assert.equal(JSON.stringify(replayed),original);rec.mark('replay-end');
  fs.writeFileSync(path.join(out,'replay-integrity.json'),JSON.stringify({source:'out/demo-video/paid-robot4/robot4-1/conversation.json',events:replayed.length,all_events_in_order:true,unchanged_event_sha256:createHash('sha256').update(original).digest('hex'),original_prompt_seconds:210.421,replay_seconds:(Date.now()-started)/1000,presentation_only:'displayText 是原始用户 prompt 的完整前缀；62k 参考原文保留在折叠区；project 为本地播放路由。未执行或重建任何原工具调用。'},null,2));
  fs.writeFileSync(path.join(out,'replayed-events.json'),original);
  await page.screenshot({path:path.join(out,'replay-end.png')});await pause(3000);
  await page.getByRole('button',{name:'收起 Agent',exact:true}).click();rec.mark('tree');await page.getByRole('button',{name:'Profile · 草图',exact:true}).click();await pause(8000);await page.getByRole('button',{name:'Plate',exact:true}).click();await pause(8000);
  rec.mark('save');await page.getByRole('button',{name:'另存工作修订',exact:true}).click();await pause(10000);
  rec.mark('orbit');await page.mouse.move(850,530);await page.mouse.down();await page.mouse.move(1010,600,{steps:100});await page.mouse.up();await pause(13000);
  await page.screenshot({path:path.join(out,'model.png')});
 }finally{try{if(rec)await rec.stop()}finally{try{if(app)await app.close()}finally{if(cad.exitCode===null)cad.kill('SIGTERM')}}}
})().catch(e=>{console.error(e);process.exitCode=1});
