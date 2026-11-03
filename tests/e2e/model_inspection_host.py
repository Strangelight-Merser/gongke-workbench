"""通过真实 MCP/应用服务检查已打开的样本；适用于 FreeCAD 和 SOLIDWORKS。

不打开、导入或改写 CAD 文档。先在宿主打开样本，加载新插件并启动绑定工程的服务。
python tests/e2e/model_inspection_host.py --state-dir ... --project ... --host-id freecad --case p7_reference
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "tests/fixtures/model_inspection/cases.json").read_text(encoding="utf-8"))


async def run(args):
    params = StdioServerParameters(command=sys.executable, args=["-m", "gongke_app", "mcp", "--state-dir", str(args.state_dir),
        "--project", str(args.project)], cwd=str(ROOT))
    async with Client(params) as client:
        async def call(name, arguments):
            response = await client.call_tool(name, arguments)
            assert not response.is_error, response.content
            result = response.structured_content
            assert result["status"] == "complete", result
            assert "error" not in result["result"], result
            return result["result"]
        info = await call("host.context", {"host_id": args.host_id})
        active = info["active_document"]
        document = next(d for d in info["documents"] if d["document"] == active)
        objects = document["objects"]
        if args.object_ref:
            target = next(o for o in objects if o["native_ref"] == args.object_ref)
        else:
            assert len(objects) == 1, "多个形体时需 --object-ref 明确选择，不检查所有对象"
            target = objects[0]
        base = {"host_id": args.host_id, "document": active, "object_ref": target["native_ref"]}
        snapshot = await call("host.inspect", base)
        report = await call("host.check", {**base, "conditions": CASES[args.case[:2]]})
        expected = CASES["expected"][args.case]
        if expected == "pass":
            assert report["status"] == "pass", report
        else:
            assert next(c for c in report["checks"] if c["id"] == expected)["status"] == "fail", report
        return {"host": info, "case": args.case, "snapshot": snapshot, "report": report, "status": "passed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--case", choices=list(CASES["expected"]), required=True)
    parser.add_argument("--object-ref")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS", args.case, args.output)
