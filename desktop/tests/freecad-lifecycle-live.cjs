// 真实 Electron -> 应用服务 -> FreeCAD；只清理本轮 endpoint 对应的自建子进程。
const { electron } = require('./helpers/owned-electron.cjs');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const output = fs.mkdtempSync(path.join(os.tmpdir(), 'gongke-lifecycle-live-'));
const endpoint = path.join(output, 'session.json');
const env = {...process.env, GONGKE_FREECAD_SESSION: endpoint, GONGKE_DESKTOP_USER_DATA: path.join(output,'desktop')};
delete env.ELECTRON_RUN_AS_NODE;
const python = process.env.GONGKE_PYTHON || 'python3';
let app, hostPid;
function alive(pid) { try { process.kill(pid,0); return true; } catch(e) { if(e.code==='ESRCH')return false; throw e; } }
(async () => {
 try {
  app = await electron.launch({args:[path.join(root,'desktop')],env});
  const page = await app.firstWindow();
  await page.waitForFunction(() => !!window.gongke);
  await page.evaluate(p => window.gongke.request('project.create', {path:p}), path.join(output,'project'));
  await page.reload();
  await page.getByText('原生 CAD', {exact:true}).click();
  await page.getByRole('button', {name:'连接 FreeCAD',exact:true}).click();
  const first = await page.evaluate(() => window.gongke.request('freecad.connect'));
  hostPid=first.pid;
  const second = await page.evaluate(() => window.gongke.request('freecad.connect'));
  assert.deepEqual(first,second);
  await page.getByText('原生连接已中断', {exact:true}).waitFor({state:'hidden'});
  await page.screenshot({path:path.join(output,'connected.png')});
  const cad = code => execFileSync(python,['-c',code],{cwd:root,env,encoding:'utf8'});
  cad("import json; from pathlib import Path; from gongke_core.native_client import call; call('create_project', snapshot=json.loads(Path('gongke_core/resources/native_shaft.json').read_text()))");
  await app.evaluate(({dialog,app})=>{
    globalThis.quitPrompts=[];
    dialog.showMessageBox=async(...args)=>{globalThis.quitPrompts.push(args.at(-1));return {response:0};};
    app.quit();
  });
  for(let i=0;i<100;i++) {
    if(await app.evaluate(()=>globalThis.quitPrompts.length))break;
    await new Promise(r=>setTimeout(r,100));
  }
  const prompts=await app.evaluate(()=>globalThis.quitPrompts);
  assert.equal(prompts[0].message,'FreeCAD 中有未保存的文档');
  assert(alive(hostPid));
  assert.equal(await page.evaluate(()=>window.gongke.request('system.status').then(s=>s.ready)),true);
  fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({hostPid,reused:true,dirtyQuitBlocked:true,prompts},null,2));
  console.log(JSON.stringify({output,hostPid,reused:true,dirtyQuitBlocked:true}));
 } finally {
  // 这是丢弃隔离验收文档的测试收尾，产品退出不使用 kill。
  if(hostPid && alive(hostPid)) process.kill(hostPid,'SIGTERM');
  if(app)await app.close();
  for(let i=0;hostPid && alive(hostPid) && i<100;i++)await new Promise(r=>setTimeout(r,100));
  if(hostPid)assert(!alive(hostPid),'本轮 FreeCAD 不得残留');
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
