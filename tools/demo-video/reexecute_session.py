"""在全新宿主逐条执行历史工程 MCP 调用；只重绑定实例/文档身份，不改工程参数。"""
import asyncio,json,os,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from mcp import Client,StdioServerParameters
async def main(out,index):
 rows=[json.loads(l) for l in (ROOT/'out/demo-video/paid-robot4/robot4-1/tool-calls.jsonl').read_text().splitlines()]
 statefile=out/'reexecution.json';state=json.loads(statefile.read_text()) if statefile.exists() else {'calls':[]}
 params=StdioServerParameters(command=sys.executable,args=['-m','gongke_app','mcp','--state-dir',str(out/'user/state'),'--project',str(out/'project'),'--allow-writes'],cwd=str(ROOT),env=dict(os.environ))
 async with Client(params) as client:
  row=rows[index];p=json.loads(json.dumps(row['params']));bindings={}
  if 'host_instance' in p:
   bindings['host_instance']={'from':p['host_instance'],'to':state['host_instance']};p['host_instance']=state['host_instance']
  if 'document' in p:
   bindings['document']={'from':p['document'],'to':state['document']};p['document']=state['document']
  result=await client.call_tool(row['command'],p);payload=result.structured_content
  entry={'index':index,'command':row['command'],'original_params':row['params'],'params':p,'bindings':bindings,'response':payload,'is_error':result.is_error}
  state['calls'].append(entry);statefile.write_text(json.dumps(state,ensure_ascii=False,indent=2))
  assert not result.is_error and payload['status']=='complete',entry
  r=payload['result'];assert 'error' not in r,r
  if row['command']=='host.context':state['host_instance']=r['host_instance']
  if r.get('document'):state['document']=r['document']
  # 工程几何、条件、操作ID、输出相对路径逐项完全相同。
  assert {k:v for k,v in p.items() if k not in bindings}=={k:v for k,v in row['params'].items() if k not in bindings}
  statefile.write_text(json.dumps(state,ensure_ascii=False,indent=2))
  if row['command'].startswith('host.'):
   scene=await client.call_tool('freecad.scene',{});(out/f'scene-{index:02}.json').write_text(json.dumps(scene.structured_content['result'],ensure_ascii=False))
  print(row['command'],r.get('status',r.get('outcome','complete'))),
if __name__=='__main__':asyncio.run(main(Path(sys.argv[1]).resolve(),int(sys.argv[2])))
