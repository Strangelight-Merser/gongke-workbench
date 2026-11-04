"""独立应用的真实窗口录屏；只结束自己创建的 PID。无需 Agent。"""
import argparse, json, os, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser();parser.add_argument('--output',default='out/demo-video/revision-native');args=parser.parse_args()
OUT=ROOT/args.output
OUT.mkdir(exist_ok=True)
subprocess.run(['swiftc','-parse-as-library',str(ROOT/'tools/demo-video/window-record.swift'),'-o','/tmp/gongke-window-record'],check=True)
cases=[
 ('pdf',['/System/Applications/Preview.app/Contents/MacOS/Preview','-ApplePersistenceIgnoreState','YES','-NSQuitAlwaysKeepsWindows','NO',str(ROOT/'out/demo-video/paid-robot4/inputs/robot4.pdf')]),
 ('cad',['/Applications/FreeCAD.app/Contents/Resources/bin/freecad','--user-cfg',str(OUT/'freecad.cfg'),str(ROOT/'tools/demo-video/opening-cad.FCMacro')]),
 ('report',['/Applications/LibreOffice.app/Contents/MacOS/soffice','-env:UserInstallation=file:///tmp/gongke-demo-native-writer','--norestore','--view',str(ROOT/'out/demo-video/showcase-01/reducer/revisions/6f2c35f49d77/report.docx')]),
]
for name,cmd in cases:
 target=OUT/name
 if target.exists(): raise RuntimeError('保留已有原片，请指定新目录')
 env=dict(os.environ,GONGKE_DEMO_MODEL=str(ROOT/'out/demo-video/paid-robot4/robot4-1/project/robot4.FCStd'))
 with (OUT/(name+'.log')).open('w') as log:
  process=subprocess.Popen(cmd,env=env,stdout=log,stderr=log)
  try:
   time.sleep(7)
   subprocess.run(['/tmp/gongke-window-record',str(process.pid),str(target),'12'],check=True)
  finally:
   if process.poll() is None:
    process.terminate()
    try: process.wait(timeout=8)
    except subprocess.TimeoutExpired: process.kill();process.wait()
   (OUT/(name+'-process.json')).write_text(json.dumps({'pid':process.pid,'command':cmd,'exit':process.returncode},ensure_ascii=False,indent=2))
