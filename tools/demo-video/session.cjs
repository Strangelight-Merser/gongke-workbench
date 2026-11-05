// 独立真实应用录屏。stdin JSON 动作同时存档，可逐行重放；不替换产品结果。
const fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process'),readline=require('node:readline');
const {electron}=require('../../desktop/tests/helpers/owned-electron.cjs');
const {startRecording}=require('./recorder.cjs');
const root=path.resolve(__dirname,'../..'),out=path.resolve(process.argv[2]);
const pause=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 if(fs.existsSync(out))throw Error('需要新的录制目录');
 fs.mkdirSync(out,{recursive:true});
 const env={...process.env,GONGKE_DESKTOP_USER_DATA:path.join(out,'user'),GONGKE_PYTHON:'/private/tmp/gongke-modeling-venv/bin/python'};
 delete env.ELECTRON_RUN_AS_NODE;
 let cad,app,recording;
 try{
 if(process.env.GONGKE_DEMO_MODEL){
   fs.mkdirSync(path.join(out,'host'));
   env.GONGKE_MODELING_ROOT=root;env.GONGKE_FREECAD_SESSION=path.join(out,'host/session.json');env.GONGKE_TRIAL_BACKGROUND='1';
   const model=path.join(out,'model-copy'+path.extname(process.env.GONGKE_DEMO_MODEL));fs.copyFileSync(process.env.GONGKE_DEMO_MODEL,model);env.GONGKE_DEMO_MODEL=model;
   const cadenv=Object.fromEntries(Object.entries(env).filter(([k])=>['HOME','PATH','TMPDIR','USER','LOGNAME','LANG','LC_ALL','LC_CTYPE','GONGKE_MODELING_ROOT','GONGKE_FREECAD_SESSION','GONGKE_TRIAL_BACKGROUND','GONGKE_DEMO_MODEL'].includes(k)));
   const log=fs.openSync(path.join(out,'freecad.log'),'w');
   cad=spawn('/Applications/FreeCAD.app/Contents/MacOS/FreeCAD',['--user-cfg',path.join(out,'host/user.cfg'),path.join(root,'tools/demo-video/showcase_host.FCMacro')],{env:cadenv,stdio:['ignore',log,log]});fs.closeSync(log);
   for(let i=0;i<150&&!fs.existsSync(path.join(out,'host/model-loaded.json'));i++)await pause(200);
   if(!fs.existsSync(path.join(out,'host/model-loaded.json')))throw Error('host timeout');
 }
 app=await electron.launch({args:[path.join(root,'desktop')],env});
 const page=await app.firstWindow();page.setDefaultTimeout(15000);
 await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1920,1080));
 await page.getByText('就绪',{exact:true}).waitFor();
 recording=await startRecording(page,out);
 const rl=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
 console.log('READY');
 for await(const line of rl){
   if(!line.trim())continue;
   const action=JSON.parse(line);if(action.stop)break;
   fs.appendFileSync(path.join(out,'actions.jsonl'),JSON.stringify(action)+'\n');
   try{
     if(action.mark)recording.mark(action.mark);
     const result=await new Function('page','app','pause','out','root',`return (async()=>{${action.code}})()`)(page,app,pause,out,root);
     fs.writeFileSync(path.join(out,'current.txt'),await page.locator('body').innerText());
     await page.screenshot({path:path.join(out,'current.png')});
     console.log('OK',action.mark||'',result||'');
   }catch(e){fs.writeFileSync(path.join(out,'current.txt'),await page.locator('body').innerText());await page.screenshot({path:path.join(out,'current.png')});console.log('ERROR',String(e));}
 }
 }finally{
  try{if(recording)await recording.stop();}finally{
    try{if(app)await app.close();}finally{
      if(cad&&cad.exitCode===null)cad.kill('SIGTERM');process.stdin.pause();process.stdin.unref?.();
    }
  }
 }
})().catch(e=>{console.error(e);process.exitCode=1});
