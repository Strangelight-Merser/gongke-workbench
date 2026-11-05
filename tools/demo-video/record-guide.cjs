const fs=require('node:fs'),path=require('node:path');
const {electron}=require('../../desktop/tests/helpers/owned-electron.cjs');
const {startRecording}=require('./recorder.cjs');
const root=path.resolve(__dirname,'../..'),out=path.resolve(process.argv[2]),pause=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 if(fs.existsSync(out))throw Error('目录已存在');fs.mkdirSync(out,{recursive:true});
 const env={...process.env,GONGKE_DESKTOP_USER_DATA:path.join(out,'user'),GONGKE_PYTHON:'/private/tmp/gongke-modeling-venv/bin/python'};delete env.ELECTRON_RUN_AS_NODE;
 const app=await electron.launch({args:[path.join(root,'desktop')],env});let rec;
 try{
  const page=await app.firstWindow();await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1920,1080));await page.getByText('就绪',{exact:true}).waitFor();
  rec=await startRecording(page,out);rec.mark('fresh-start');await pause(10000);
  await page.evaluate(p=>window.gongke.request('project.create',{path:p,name:'机器人零件'}),path.join(out,'project'));await page.reload();
  await page.getByRole('button',{name:'Agent 连接设置',exact:true}).click();await page.getByRole('menuitem',{name:'使用已配置的 Agent',exact:true}).click();rec.mark('configured');await pause(8500);
  await page.getByRole('button',{name:'Agent 连接设置',exact:true}).click();await page.getByRole('menuitem',{name:'安装与连接引导',exact:true}).click();rec.mark('guide');await pause(8500);
  await page.screenshot({path:path.join(out,'guide.png')});
 }finally{try{if(rec)await rec.stop()}finally{await app.close()}}
})().catch(e=>{console.error(e);process.exitCode=1});
