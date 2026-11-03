"""官方 SDK 客户端实测运行中应用；可切换为发行包入口。"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

from mcp import Client, StdioServerParameters


async def run(args):
    command = str(args.executable) if args.executable else sys.executable
    prefix = [] if args.executable else ["-m", "gongke_app"]
    params = StdioServerParameters(command=command, args=[*prefix, "mcp", "--state-dir", str(args.state_dir),
        "--project", str(args.project), "--allow-writes"],
        cwd=str(args.project if args.executable else Path(__file__).resolve().parents[2]))
    results = {}
    async with Client(params) as client:
        results["tools"] = [tool.name for tool in (await client.list_tools()).tools]
        for name, arguments in [("project.current", {}), ("design.calculate", {}),
                                ("design.generate", {"name": "mcp-" + uuid4().hex[:10], "drawings": False, "report_docx": False})]:
            response = await client.call_tool(name, arguments)
            assert not response.is_error, response.content
            results[name] = response.structured_content
        hosts = await client.call_tool("hosts.list", {})
        native = next(host for host in hosts.structured_content["result"]["hosts"] if host["host"] == "freecad")
        if native["connected"]:
            response = await client.call_tool("freecad.context", {})
            assert not response.is_error, response.content
            results["freecad.context"] = response.structured_content
        else:
            results["freecad"] = {"connected": False, "reason": native["error"]}
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--executable", type=Path)
    print(json.dumps(asyncio.run(run(parser.parse_args())), ensure_ascii=False))
