const {click,pause}=require('./app-recorder.cjs');
module.exports=async function(page,run,out,mark){
 for(let i=4;i<10;i++){
  mark(['新建零件','绘制草图','拉伸成体','读取模型','原会话检查调用','保存原生模型'][i-4]+'：调用开始');
  await run('reexecute_session.py',[out,String(i)]);
  await click(page,page.getByRole('button',{name:'读取 FreeCAD 工程',exact:true}));
  for(const summary of await page.locator('details.agent-tool-group:not([open]) > summary').all())await click(page,summary);
  mark(['新建零件','绘制草图','拉伸成体','读取模型','原会话检查调用','保存原生模型'][i-4]+'：界面更新');
  await pause(i===5||i===6?2500:1000);
 }
};
