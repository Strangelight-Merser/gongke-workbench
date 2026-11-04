"""在当前录屏工程中只读检查手工修改后的真实模型；不调用 Agent。"""
import asyncio,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from mcp import Client,StdioServerParameters
async def main():
 out=Path(sys.argv[1]).resolve()
 env={**os.environ,'GONGKE_FREECAD_SESSION':str(out/'host/session.json')}
 params=StdioServerParameters(command=sys.executable,args=['-m','gongke_app','mcp','--state-dir',str(out/'user/state'),'--project',str(out/'project')],cwd=str(ROOT),env=env)
 async with Client(params) as client:
  async def call(name,**kwargs):
   r=await client.call_tool(name,{'host_id':'freecad',**kwargs});p=r.structured_content
   with (out/'manual-check.jsonl').open('a') as f:f.write(json.dumps({'tool':name,'params':kwargs,'response':p},ensure_ascii=False)+'\n')
   assert not r.is_error,p
   return p['result']
  c=await call('host.context')
  print(json.dumps(c,ensure_ascii=False))
  doc=c['active_document']
  r=await call('host.check',document=doc,object_ref='Robot4Fender',conditions=[{'id':'修改后厚度','source':'本次工作副本的参数编辑目标：厚度5 mm，不代表原图4 mm','measurement':{'kind':'plane_distance','selectors':[{'kind':'plane','direction':[0,0,1],'offset':0},{'kind':'plane','direction':[0,0,1],'offset':.005}]},'expected':5,'tolerance':.001,'unit':'mm'}])
  assert r['status']=='pass',r
  print('manual check passed')
asyncio.run(main())
