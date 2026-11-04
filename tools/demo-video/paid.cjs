// 包装既有真实 Agent 验收入口，仅添加录屏；不修改用户测试、提示词或验收答案。
const fs=require('node:fs'), path=require('node:path');
const {startRecording}=require('./recorder.cjs');
const owned=require('../../desktop/tests/helpers/owned-electron.cjs');
const original=owned.electron.launch;
owned.electron.launch=async options=>{
  const app=await original(options);
  const page=await app.firstWindow();
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1920,1080));
  const recording=await startRecording(page,path.join(process.env.GONGKE_TRIAL_OUTPUT,'raw'));
  const close=app.close.bind(app);
  let switched=false,busy=false;
  const watcher=setInterval(async()=>{
    if(busy || switched || page.isClosed())return;
    busy=true;
    try{
      const tasks=await page.evaluate(()=>window.gongke.request('task.list'));
      if(tasks.some(t=>/新建零件|草图|拉伸/.test(t.title))){
        await page.getByText('原生 CAD',{exact:true}).click();
        recording.mark('native-model-visible');switched=true;
      }
    }catch{}finally{busy=false;}
  },1000);
  app.close=async()=>{
    clearInterval(watcher);
    try { await recording.stop(); } finally { await close(); }
  };
  return app;
};
require('../../desktop/tests/agent-modeling-live.cjs');
