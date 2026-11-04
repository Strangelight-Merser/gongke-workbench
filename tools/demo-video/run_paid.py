"""用户授权的一次 robot4：low/矢量 PDF，单会话、480 秒、无重试。"""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tests.e2e.agent_modeling_result import classify, summarize

OUTPUT=ROOT/os.environ.get('GONGKE_DEMO_PAID_OUTPUT','out/demo-video/paid-robot4')
PYTHON='/private/tmp/gongke-modeling-venv/bin/python'
DSH='/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh'
FREECAD='/Applications/FreeCAD.app/Contents/MacOS/FreeCAD'


def main():
    if OUTPUT.exists():
        raise RuntimeError('本次授权目录已存在，禁止重试或覆盖')
    subprocess.run([PYTHON,str(ROOT/'scripts/agent_modeling_trial.py'),
        '--cases','robot4','--delivery','pdf','--reasoning','low','--timeout','480',
        '--background','--prepare-only','--output',str(OUTPUT)],check=True,cwd=ROOT)
    manifest=json.loads((OUTPUT/'manifest.json').read_text())
    manifest['dsh_version']=subprocess.check_output([DSH,'--version'],text=True).strip()
    (OUTPUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    env={**os.environ,'GONGKE_PYTHON':PYTHON,'GONGKE_MODELING_ROOT':str(ROOT),
         'GONGKE_FREECAD_SESSION':str(OUTPUT/'host/session.json'),
         'GONGKE_TRIAL_BACKGROUND':'1','GONGKE_TRIAL_OUTPUT':str(OUTPUT),
         'GONGKE_TRIAL_STUDY':'/Users/huaiyi/Documents/gongke-workbench/out/drawing-to-model-study',
         'GONGKE_TRIAL_DSH':DSH,'GONGKE_TRIAL_TIMEOUT':'480'}
    for k in ['GONGKE_AGENT_CONFIG','ELECTRON_RUN_AS_NODE']:env.pop(k,None)
    cadenv={k:v for k,v in env.items() if k in ['HOME','PATH','TMPDIR','USER','LOGNAME','LANG','LC_ALL','LC_CTYPE',
        'GONGKE_MODELING_ROOT','GONGKE_FREECAD_SESSION','GONGKE_TRIAL_BACKGROUND','GONGKE_TRIAL_OUTPUT']}
    (OUTPUT/'host').mkdir()
    children=[]
    try:
        with (OUTPUT/'host/freecad.log').open('w') as log:
            cad=subprocess.Popen([FREECAD,str(ROOT/'tests/e2e/native_modeling_host.FCMacro')],cwd=ROOT,env=cadenv,stdout=log,stderr=subprocess.STDOUT)
        children.append(cad)
        for _ in range(150):
            if (OUTPUT/'host/session.json').exists():break
            if cad.poll() is not None:raise RuntimeError('宿主启动失败；尚未发送模型任务')
            time.sleep(.2)
        else:raise RuntimeError('宿主端点超时；尚未发送模型任务')
        (OUTPUT/'processes.json').write_text(json.dumps({'freecad_pid':cad.pid}))
        with (OUTPUT/'runner.log').open('w') as log:
            runner=subprocess.Popen(['node',str(ROOT/'tools/demo-video/paid.cjs')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            children.append(runner)
            # 付费任务自身从发送开始有 480 秒取消计时；这里容纳连接及免费独立审计。
            runner.wait(timeout=750)
        summary=json.loads((OUTPUT/'summary.json').read_text())
        row=summary['results'][0]
        if not row.get('transport_completed') or row.get('error'):
            (OUTPUT/'STOPPED.json').write_text(json.dumps({'reason':row.get('error'),'retry':False},ensure_ascii=False))
            raise RuntimeError('唯一一次 Agent 任务失败，停止正式制作，不重试；见 result.json')
        with (OUTPUT/'reopen.log').open('w') as log:
            reopen=subprocess.Popen([FREECAD,str(ROOT/'tests/e2e/agent_modeling_reopen.FCMacro')],cwd=ROOT,env=cadenv,stdout=log,stderr=subprocess.STDOUT)
            children.append(reopen);reopen.wait(timeout=90)
        row['reopened']=json.loads((OUTPUT/'reopened.json').read_text())[0]
        classify(row)
        (OUTPUT/'robot4-1/result.json').write_text(json.dumps(row,ensure_ascii=False,indent=2))
        (OUTPUT/'summary.json').write_text(json.dumps(summarize([row]),ensure_ascii=False,indent=2))
        if row['status']!='passed':raise RuntimeError('本次独立验收未通过，停止、不重试：'+row['status'])
        print('robot4 passed',flush=True)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=8)
                except subprocess.TimeoutExpired:child.kill();child.wait()


if __name__=='__main__':main()
