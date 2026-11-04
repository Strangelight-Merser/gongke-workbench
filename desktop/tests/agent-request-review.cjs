// 构建后运行：node desktop/tests/agent-request-review.cjs <证据目录>
const {electron}=require('./helpers/owned-electron.cjs');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const out=path.resolve(process.argv[2]);fs.mkdirSync(out,{recursive:true});
 const text='请按图纸建立零件，保留原生特征树。'.repeat(15)+'\n第二行：检查后保留完整回执。';
 const results=[];
 for(const width of [1366,1920]){
  const env={...process.env,GONGKE_VISUAL_USER_DATA:path.join(out,'user-'+width)};delete env.ELECTRON_RUN_AS_NODE;
  const app=await electron.launch({args:[path.join(__dirname,'fixtures/workbench-main.cjs')],env});
  try{
   const page=await app.firstWindow();await page.setViewportSize({width,height:1080});
   await page.getByRole('heading',{name:'支架建模练习',exact:true}).waitFor();
   await page.getByRole('button',{name:'Agent 连接设置',exact:true}).click();
   await page.getByRole('menuitem',{name:'使用已配置的 Agent',exact:true}).click();
   await page.evaluate(text=>window.visualReview.conversation([{type:'user',text}]),text);
   const req=page.locator('.agent-request');await req.waitFor();
   assert.equal(await req.getAttribute('open'),null);
   const single=await req.locator('summary span').evaluate(e=>({height:e.getBoundingClientRect().height,line:parseFloat(getComputedStyle(e).lineHeight),scroll:e.scrollWidth,width:e.clientWidth}));
   assert.ok(single.height<=single.line+1);assert.ok(single.scroll>single.width);
   await req.locator('summary').click();assert.notEqual(await req.getAttribute('open'),null);
   assert.equal(await req.locator('div').innerText(),text);
   await req.locator('summary').click();assert.equal(await req.getAttribute('open'),null);
   await page.screenshot({path:path.join(out,width+'.png')});
   results.push({width,collapsed:true,single_line:true,ellipsis:true,expanded_text_unchanged:true});
  }finally{await app.close()}
 }
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({ok:true,results},null,2));
})().catch(e=>{console.error(e);process.exitCode=1});
