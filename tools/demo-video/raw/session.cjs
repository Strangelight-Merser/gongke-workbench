// 自有应用交互式采集会话。stdin 动作归档；不启动 dsh。
const fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process'),readline=require('node:readline');
const {electron}=require('../../../desktop/tests/helpers/owned-electron.cjs');
const {startRecording,click,pause}=require('./app-recorder.cjs');
const root=path.resolve(__dirname,'../../..'),out=path.resolve(process.argv[2]);
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const env={...process.env,GONGKE_DESKTOP_USER_DATA:path.join(out,'user'),GONGKE_PYTHON:'/private/tmp/gongke-modeling-venv/bin/python',GONGKE_MODELING_ROOT:root,GONGKE_FREECAD_SESSION:process.env.GONGKE_EXISTING_HOST||path.join(out,'host/session.json'),GONGKE_TRIAL_BACKGROUND:'1',FREECAD_USER_HOME:path.join(out,'host/home')};delete env.ELECTRON_RUN_AS_NODE;
 fs.mkdirSync(path.join(out,'host/home'),{recursive:true});
 const log=fs.openSync(path.join(out,'host.log'),'w');
 const cad=process.env.GONGKE_EXISTING_HOST?null:spawn('/Applications/FreeCAD.app/Contents/Resources/bin/freecad',['--user-cfg',path.join(out,'host/user.cfg'),path.join(__dirname,'host.FCMacro')],{env,stdio:['ignore',log,log]});fs.closeSync(log);
 let app,rec;
 try{
  for(let i=0;i<150&&!fs.existsSync(env.GONGKE_FREECAD_SESSION);i++)await pause(200);
  app=await electron.launch({args:['--force-device-scale-factor=2',path.join(root,'desktop')],env});
  const page=await app.firstWindow();page.setDefaultTimeout(20000);
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1440,810));
  await page.getByText('就绪',{exact:true}).waitFor();
  if(await page.getByRole('button',{name:'切换深色主题',exact:true}).count())await click(page,page.getByRole('button',{name:'切换深色主题',exact:true}));
  const run=async (script,args=[])=>new Promise((resolve,reject)=>{const p=spawn(env.GONGKE_PYTHON,[path.join(root,'tools/demo-video',script),...args],{cwd:root,env,stdio:'inherit'});p.on('exit',c=>c===0?resolve():reject(Error(script+' failed')))});
  console.log('READY',cad?.pid,app.process().pid);
  const rl=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
  for await(const line of rl){if(!line.trim())continue;const action=JSON.parse(line);if(action.stop)break;
   fs.appendFileSync(path.join(out,'actions.jsonl'),JSON.stringify(action)+'\n');
   try{
    if(action.start)rec=await startRecording(page,path.join(root,'out/demo-video/raw',action.start));
    if(action.mark)rec?.mark(action.mark);
    const result=action.code?await new Function('page','app','pause','out','root','fs','path','click','run','env',`return (async()=>{${action.code}})()`)(page,app,pause,out,root,fs,path,click,run,env):null;
    if(action.end){console.log('DURATION',(await rec.stop()).duration);rec=null;}
    fs.writeFileSync(path.join(out,'current.txt'),await page.locator('body').innerText());await page.screenshot({path:path.join(out,'current.png')});console.log('OK',result??'');
   }catch(e){fs.writeFileSync(path.join(out,'current.txt'),await page.locator('body').innerText());await page.screenshot({path:path.join(out,'current.png')});console.log('ERROR',String(e));}
  }
 }finally{if(rec)await rec.stop();if(app)await app.close();if(cad&&cad.exitCode===null)cad.kill('SIGTERM');process.stdin.pause();process.stdin.unref?.();}
})().catch(e=>{console.error(e);process.exitCode=1});
