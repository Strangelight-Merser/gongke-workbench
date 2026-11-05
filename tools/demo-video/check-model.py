"""经工程 MCP 对副本进行真实只读图纸核验。"""
import asyncio,json,os,sys
from pathlib import Path
from mcp import Client,StdioServerParameters
async def main():
    out=Path(sys.argv[1]).resolve();entry=next(x for x in json.loads(Path(sys.argv[2]).read_text()) if x['name']=='demo-bad')
    params=StdioServerParameters(command=sys.executable,args=['-m','gongke_app','mcp','--state-dir',str(out/'user/state'),'--project',str(out/'project')],cwd=os.getcwd(),env=dict(os.environ))
    async with Client(params) as client:
        c=await client.call_tool('host.context',{'host_id':'freecad'})
        context=c.structured_content['result']
        (out/'context.json').write_text(json.dumps(context,ensure_ascii=False,indent=2))
        r=await client.call_tool('host.check',{'host_id':'freecad','document':context['active_document'],'object_ref':'robot4','conditions':[],'drawing':entry['drawing']})
        assert not r.is_error,r
        (out/'report.json').write_text(json.dumps(r.structured_content['result'],ensure_ascii=False,indent=2))
if __name__=='__main__':asyncio.run(main())
