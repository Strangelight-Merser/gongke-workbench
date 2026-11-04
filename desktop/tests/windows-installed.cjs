// 从已安装应用入口验收：真实服务、helper、随包 FreeCAD 和工程写入。
const { _electron } = require('playwright');
const { spawn, execFileSync } = require('node:child_process');
const { mkdirSync, readFileSync, writeFileSync, existsSync, copyFileSync } = require('node:fs');
const { join, resolve } = require('node:path');
const { randomUUID } = require('node:crypto');
const assert = require('node:assert/strict');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const output = resolve(process.env.GONGKE_INSTALL_EVIDENCE);
const executable = process.env.GONGKE_TEST_EXECUTABLE;
const userdata = join(process.env.USERPROFILE, '构想引擎验收', '首次启动');
const project = join(process.env.USERPROFILE, '构想引擎验收', '中文 工程');
mkdirSync(output, { recursive: true });
const env = { ...process.env, GONGKE_DESKTOP_USER_DATA: userdata, GONGKE_TEST_DIAGNOSTICS_DIR: output,
  GONGKE_FREECAD_SESSION: join(userdata, 'freecad-session.json') };
for (const name of ['PYTHONPATH', 'PYTHONHOME', 'GONGKE_PYTHON', 'GONGKE_FREECAD_EXE', 'ELECTRON_RUN_AS_NODE']) delete env[name];
function processes() {
  const script = '[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); Get-CimInstance Win32_Process | Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress';
  return JSON.parse(execFileSync('powershell.exe', ['-NoProfile', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], { encoding: 'utf8' }));
}
(async () => {
  let app;
  const evidence = { ok: false, username: process.env.USERNAME, profile: process.env.USERPROFILE, executable, steps: [] };
  try {
    const identityScript = '[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); [Security.Principal.WindowsIdentity]::GetCurrent().Name';
    const identity = execFileSync('powershell.exe', ['-NoProfile', '-EncodedCommand', Buffer.from(identityScript, 'utf16le').toString('base64')], {encoding:'utf8'}).trim();
    evidence.identity = identity;
    assert(identity.toLowerCase().endsWith('\\' + process.env.USERNAME.toLowerCase()), identity);
    assert(/[\u4e00-\u9fff]/.test(process.env.USERNAME), 'Run under a real Chinese Windows account');
    assert(/[\u4e00-\u9fff]/.test(process.env.USERPROFILE));
    app = await _electron.launch({ executablePath: executable, args: [], env, cwd: output, timeout: 60000 });
    const page = await app.firstWindow();
    await page.waitForFunction(() => !!window.gongke);
    const request = (method, params = {}) => page.evaluate(({method, params}) => window.gongke.request(method, params), {method, params});
    const status = await request('system.status');
    assert.equal(status.packaged, true);
    evidence.steps.push('installed service handshake');
    await request('project.create', { path: project });
    const second = spawn(executable, [], { env, cwd: output, stdio: 'ignore' });
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => { second.kill(); reject(new Error('Second instance did not exit')); }, 15000);
      second.once('error', reject);
      second.once('exit', code => { clearTimeout(timeout); code === 0 ? resolve() : reject(new Error('Second instance exit ' + code)); });
    });
    evidence.steps.push('single desktop instance');
    const found = await page.evaluate(() => window.cadEmbed.discover());
    const bundled = found.installations.find(item => item.kind === 'freecad' && item.path.toLowerCase().includes('resources\\freecad\\'));
    assert(bundled, JSON.stringify(found));
    const host = await request('freecad.connect');
    const again = await request('freecad.connect');
    assert.equal(again.pid, host.pid);
    evidence.steps.push('helper discovery and bundled FreeCAD handshake/reuse');
    const endpoint = JSON.parse(readFileSync(join(userdata, 'state/service.json'), 'utf8'));
    async function connection(action, params) {
      const response = await fetch(endpoint.url + '/command', { method: 'POST',
        headers: { Authorization: 'Bearer ' + endpoint.token, 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, params }), signal: AbortSignal.timeout(30000) });
      const value = await response.json();
      assert(!value.error, JSON.stringify(value));
      return value.result;
    }
    const binding = await connection('bind', { project, allow_writes: true });
    async function command(method, params) {
      const taskId = randomUUID();
      await connection('call', { binding_id: binding.binding_id, method, params, task_id: taskId });
      for (let n = 0; n < 300; n++) {
        const task = await connection('task', { binding_id: binding.binding_id, task_id: taskId });
        if (task.status === 'complete') return task.result;
        assert(!['failed', 'cancelled'].includes(task.status), JSON.stringify(task));
        await delay(100);
      }
      throw new Error('Task timeout: ' + method);
    }
    const hosts = await request('hosts.list');
    const freecad = hosts.hosts.find(item => item.host_id === 'freecad');
    assert(freecad.connected);
    let part = await command('host.model_new', { host_id: 'freecad', host_instance: freecad.host_instance,
      operation_id: randomUUID(), path: 'part.FCStd', name: 'Part' });
    const body = part.body_ref;
    const sketch = await command('host.sketch', { host_id: 'freecad', document: part.document,
      operation_id: randomUUID(), body_ref: body, name: 'Profile', support: {plane: 'XY'},
      geometry: [{kind:'rectangle', start:[0,0], end:[0.02,0.01]}], constraints: [] });
    part = await command('host.feature', { host_id:'freecad', document:sketch.document,
      operation_id:randomUUID(), body_ref:body, name:'Pad', feature:{kind:'pad', sketch_ref:sketch.sketch_ref, length:0.005} });
    const shape = await command('host.inspect', {host_id:'freecad', document:part.document, object_ref:body});
    assert.equal(shape.state, 'ready');
    assert.equal(shape.solid_count, 1);
    assert(Math.abs(shape.volume - 0.02 * 0.01 * 0.005) < 1e-12);
    evidence.shape = {volume:shape.volume, solid_count:shape.solid_count, bounds:shape.bounds};
    const saved = await command('host.model_save', {host_id:'freecad', document:part.document, operation_id:randomUUID()});
    assert(saved.document);
    assert(existsSync(join(project, 'part.FCStd')));
    evidence.steps.push('native rectangle/pad/save via bound engineering commands');
    await page.screenshot({ path:join(output, 'installed.png') });
    const owned = processes().filter(item => item.ExecutablePath && item.ExecutablePath.toLowerCase().startsWith(resolve(executable, '..').toLowerCase()));
    assert(owned.some(item => item.ProcessId === host.pid));
    assert(owned.some(item => /Gongke.Embed.exe$/i.test(item.ExecutablePath)));
    evidence.processes = owned;
    const exited = new Promise(resolve => app.process().once('exit', resolve));
    await app.evaluate(({app}) => app.quit());
    await Promise.race([exited, delay(30000).then(() => {throw new Error('Normal quit timed out');})]);
    app = null;
    let remaining;
    for (let n = 0; n < 30; n++) {
      const live = new Set(processes().map(item => item.ProcessId));
      remaining = owned.filter(item => live.has(item.ProcessId));
      if (!remaining.length) break;
      await delay(500);
    }
    assert.deepEqual(remaining, [], 'Owned processes remain after normal exit');
    evidence.steps.push('normal exit: Electron/service/helper/FreeCAD all stopped');
    evidence.ok = true;
  } catch (error) {
    evidence.error = error.stack;
    throw error;
  } finally {
    for (const [source, name] of [[join(userdata, 'freecad.log'), 'freecad.log'], [join(userdata, 'embed/helper-stderr.log'), 'helper-stderr.log']]) {
      if (existsSync(source)) copyFileSync(source, join(output, name));
    }
    writeFileSync(join(output, 'result.json'), JSON.stringify(evidence, null, 2));
    if (app) await app.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
