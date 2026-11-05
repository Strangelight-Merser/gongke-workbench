const path=require('node:path'),fs=require('node:fs');
const {electron}=require('../../desktop/tests/helpers/owned-electron.cjs');
const {startRecording}=require('./recorder.cjs');
const root=path.resolve(__dirname,'../..'),out=path.resolve(process.argv[2]);
(async()=>{
 if(fs.existsSync(out))throw Error('目录已存在');fs.mkdirSync(out,{recursive:true});
 const env={...process.env,GONGKE_DEMO_PDF:path.join(root,'out/demo-video/paid-robot4/inputs/robot4.pdf')};delete env.ELECTRON_RUN_AS_NODE;
 const app=await electron.launch({args:[path.join(__dirname,'pdf-viewer.cjs'),'--user-data-dir='+path.join(out,'user')],env});let rec;
 try{
  const page=await app.firstWindow();await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1920,1080));await new Promise(r=>setTimeout(r,5000));
  rec=await startRecording(page,out);await new Promise(r=>setTimeout(r,4000));await page.mouse.move(1050,650);await page.mouse.wheel(0,100);await new Promise(r=>setTimeout(r,4000));await page.mouse.wheel(0,-100);await new Promise(r=>setTimeout(r,4000));await page.screenshot({path:path.join(out,'viewer.png')});
 }finally{try{if(rec)await rec.stop()}finally{await app.close()}}
})().catch(e=>{console.error(e);process.exitCode=1});
