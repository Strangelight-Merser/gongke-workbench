// 真实 Electron + FreeCAD 的无付费录屏。原验收脚本只调用，不改写。
const fs = require('node:fs');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');
const { electron } = require('../../desktop/tests/helpers/owned-electron.cjs');
const root = path.resolve(__dirname, '../..');
const output = path.resolve(process.argv[2] || path.join(root, 'out/demo-video/capture'));
const python = process.env.GONGKE_PYTHON || '/private/tmp/gongke-modeling-venv/bin/python';
const pause = ms => new Promise(r => setTimeout(r, ms));
async function main() {
  if (fs.existsSync(output)) throw Error('录制目录已存在；请指定新的目录，保留原始证据');
  fs.mkdirSync(path.join(output, 'host'), { recursive: true });
  fs.mkdirSync(path.join(output, 'frames'));
  const env = { ...process.env, GONGKE_MODELING_ROOT: root,
    GONGKE_FREECAD_SESSION: path.join(output, 'host/session.json'),
    GONGKE_DESKTOP_USER_DATA: path.join(output, 'user'),
    GONGKE_PYTHON: python, GONGKE_TRIAL_BACKGROUND: '1' };
  delete env.ELECTRON_RUN_AS_NODE;
  const cadEnv = Object.fromEntries(Object.entries(env).filter(([k]) =>
    ['HOME','PATH','TMPDIR','USER','LOGNAME','LANG','LC_ALL','LC_CTYPE',
     'GONGKE_MODELING_ROOT','GONGKE_FREECAD_SESSION','GONGKE_TRIAL_BACKGROUND'].includes(k)));
  const log = fs.openSync(path.join(output,'freecad.log'), 'w');
  const cad = spawn('/usr/bin/open',
    ['-n','-g','-j','-W',...Object.entries(cadEnv).flatMap(([k,v])=>['--env',`${k}=${v}`]),
     '-a','/Applications/FreeCAD.app','--args',path.join(root,'tests/e2e/native_modeling_host.FCMacro')],
    { cwd: root, env: cadEnv, stdio: ['ignore',log,log] });
  fs.closeSync(log);
  let app;
  try {
    for (let i=0; i<150 && !fs.existsSync(env.GONGKE_FREECAD_SESSION); i++) {
      if (cad.exitCode !== null) throw Error('FreeCAD 启动失败，见 freecad.log');
      await pause(200);
    }
    if (!fs.existsSync(env.GONGKE_FREECAD_SESSION)) throw Error('FreeCAD 端点超时');
    app = await electron.launch({args:[path.join(root,'desktop')],env});
    const page = await app.firstWindow();
    await app.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows()[0].setContentSize(1920,1080));
    await page.waitForFunction(() => !!window.gongke);
    const errors=[]; page.on('pageerror', e=>errors.push(String(e)));
    await page.evaluate(p=>window.gongke.request('project.create',{
      path:p, name:'凸台尺寸检查'}), path.join(output,'project'));
    await page.reload();
    await page.getByText('原生 CAD',{exact:true}).click();
    const phases=[];
    async function phase(name) {
      const start=Date.now();
      await new Promise((resolve,reject)=>{
        const child=spawn(python,[path.join(root,'tests/e2e/live_modeling_visual.py'),output,name],
          {cwd:root,env,stdio:['ignore','pipe','pipe']});
        let text='';child.stdout.on('data',b=>text+=b);child.stderr.on('data',b=>text+=b);
        child.on('error',reject);child.on('exit',code=>{
          fs.writeFileSync(path.join(output,name+'.log'),text);
          code===0?resolve():reject(Error(name+' failed: '+text.slice(-1800)));
        });
      });
      phases.push({name,start,end:Date.now()});
    }
    for(const name of ['sketch','base','tube-sketch','tube','fail']) await phase(name);
    await page.getByRole('button',{name:'Agent 连接设置',exact:true}).click();
    await page.getByRole('menuitem',{name:'使用已配置的 Agent',exact:true}).click();
    await page.locator('.modeling-steps .agent-tool[data-state="failed"] > summary').click();
    await pause(1200);
    await page.screenshot({path:path.join(output,'before.png')});
    fs.writeFileSync(path.join(output,'before.txt'),await page.locator('body').innerText());
    const cdp=await page.context().newCDPSession(page);
    const frames=[]; let index=0;
    cdp.on('Page.screencastFrame',event=>{
      const file=String(index++).padStart(6,'0')+'.jpg';
      fs.writeFileSync(path.join(output,'frames',file),Buffer.from(event.data,'base64'));
      frames.push({file,timestamp:event.metadata.timestamp});
      cdp.send('Page.screencastFrameAck',{sessionId:event.sessionId}).catch(()=>{});
    });
    const started=Date.now();
    await cdp.send('Page.startScreencast',{format:'jpeg',quality:95,maxWidth:1920,maxHeight:1080,everyNthFrame:1});
    await pause(3500);
    // 模型检查的不符面来自真实回执；下面是真实特征修改，非 Agent 会话。
    await phase('repaired');
    await pause(3500);
    await page.getByRole('button',{name:'TubeSketch · 草图',exact:true}).click();
    await pause(2500);
    await page.getByRole('button',{name:'TubePad',exact:true}).click();
    await pause(3000);
    await phase('save');
    await pause(1500);
    const ended=Date.now();
    await cdp.send('Page.stopScreencast');
    await page.screenshot({path:path.join(output,'after.png')});
    fs.writeFileSync(path.join(output,'recording.json'),JSON.stringify({
      source:'真实 Electron 界面；真实 FreeCAD；确定性 MCP 操作；无 Agent 推理',
      started,ended,phases,frames,errors,git:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim()
    },null,2));
    if(errors.length) throw Error(errors.join('\n'));
    console.log(output);
  } finally {
    if(app) await app.close();
    const bootstrap=path.join(output,'host/bootstrap.json');
    if(fs.existsSync(bootstrap)) {
      const owned=JSON.parse(fs.readFileSync(bootstrap));
      if(owned.root===root) process.kill(owned.pid,'SIGTERM');
    }
    if(cad.exitCode===null) cad.kill('SIGTERM');
  }
}
main().catch(e=>{console.error(e);process.exitCode=1});
