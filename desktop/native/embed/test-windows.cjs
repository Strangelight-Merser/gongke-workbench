// 仅用于合成窗口；真实 CAD 菜单、草图与文档保存另按 README 操作。
const { electron } = require('../../tests/helpers/owned-electron.cjs');
const { readFileSync, mkdirSync, writeFileSync } = require('node:fs');
const { resolve, join } = require('node:path');
const assert = require('node:assert/strict');
if (process.platform !== 'win32') throw new Error('此脚本必须在 Windows 运行，不能把静态检查记成通过');
const root = resolve(__dirname, '../..');
const output = join(root, '../out/embed-fixture');
mkdirSync(output, { recursive: true });
const fixture = join(__dirname, 'fixture/publish/SLDWORKS.exe');
const observations = [];
let application, launchedPid;
(async () => {
  application = await electron.launch({ args: [join(root, 'dist-electron/embed/prototype.cjs')], env: {
    ...process.env, GONGKE_EMBED_TEST_DATA: output, GONGKE_FREECAD_EXE: fixture,
  } });
  const page = await application.firstWindow();
  const call = (method, ...args) => page.evaluate(({method,args}) => window.cadEmbed[method](...args), {method,args});
  const discovered = await call('discover');
  assert(discovered.installations.some(i => i.path.toLowerCase() === fixture.toLowerCase()));
  const install = discovered.installations.find(i => i.path.toLowerCase() === fixture.toLowerCase());
  const launched = await call('launch', install.id);
  launchedPid = launched.pid;
  let target;
  for (let i = 0; i < 100 && !target; i++) {
    target = (await call('discover')).windows.find(w => w.pid === launched.pid);
    if (!target) await new Promise(r => setTimeout(r, 100));
  }
  assert(target, '替身主窗口未出现');
  for (const mode of ['embed', 'dock']) {
    const state = await call('attach', target.hwnd, target.pid, mode);
    assert.equal(state.attached.pid, launched.pid);
    await application.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows()[0].setBounds({x:100,y:100,width:1280,height:850}));
    // 等待 Win32 异步定位及 renderer ResizeObserver，随后读取真实 HWND 状态。
    await new Promise(r => setTimeout(r, 500));
    const report = JSON.parse(readFileSync((await call('diagnose')).path,'utf8'));
    assert.equal(report.actualParent, report.parent);
    assert.equal(!!(report.actualStyle & 0x40000000), mode === 'embed');
    assert(report.viewport.width > 100 && report.viewport.height > 100);
    assert.equal(report.state.attached.pid, launched.pid);
    assert(Math.abs(report.actualBounds.x - report.viewport.x) <= 1);
    assert(Math.abs(report.actualBounds.y - report.viewport.y) <= 1);
    assert(Math.abs(report.actualBounds.width - report.viewport.width) <= 1);
    assert(Math.abs(report.actualBounds.height - report.viewport.height) <= 1);
    observations.push({ mode, parentMatches: true, childStyle: mode === 'embed', report });
    await application.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows()[0].minimize());
    await new Promise(r => setTimeout(r, 300));
    const hidden = JSON.parse(readFileSync((await call('diagnose')).path,'utf8'));
    assert.equal(hidden.viewport.visible, false);
    assert.equal(hidden.actualBounds.visible, false);
    await application.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows()[0].restore());
    await call('detach');
    assert.equal((await call('status')).attached, null);
    assert((await call('discover')).windows.some(w => w.hwnd === target.hwnd));
  }
  await call('attach', target.hwnd, target.pid, 'embed');
  await call('closeCad');
  for (let i=0;i<100 && (await call('status')).pendingPids.length;i++) await new Promise(r=>setTimeout(r,100));
  assert.deepEqual((await call('status')).pendingPids, []);
  writeFileSync(join(output,'result.json'),JSON.stringify({scope:'synthetic-window-only',passed:true,observations},null,2));
  await application.close(); application=null;
  console.log(`合成窗口嵌入/停靠、移动缩放、最小化、释放、关闭通过：${output}`);
})().catch(async error => {
  writeFileSync(join(output,'result.json'),JSON.stringify({scope:'synthetic-window-only',passed:false,error:String(error),observations},null,2));
  // 仅关闭本轮 helper 返回的合成窗口 PID，不处理任何实际 CAD。
  if (launchedPid) { try { process.kill(launchedPid, 'SIGTERM'); } catch (e) { if (e.code !== 'ESRCH') console.error(e); } }
  if (application) await application.close().catch(e => console.error(e));
  console.error(error); process.exitCode=1;
});
