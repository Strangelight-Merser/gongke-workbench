// 官方 MCP 客户端连接桌面 Service 的同一 Python 进程，不模拟事件。
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { mkdtempSync, rmSync, existsSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join, resolve } = require("node:path");
const { execFile } = require("node:child_process");
const { promisify } = require("node:util");
const { Service } = require("../dist-electron/service.cjs");
const { AgentConfiguration } = require("../dist-electron/acp/settings.cjs");

test("外部 MCP 操作进入桌面同一工程、任务与实时收据", async () => {
  const root = resolve(__dirname, "../..");
  const directory = mkdtempSync(join(tmpdir(), "gongke-desktop-mcp-"));
  const state = join(directory, "state"), project = join(directory, "project");
  const python = process.env.GONGKE_PYTHON || "python3";
  const env = { ...process.env, PYTHONPATH: root };
  const service = new Service(python, ["-m", "gongke_app.service", "--state-dir", state], directory, env);
  const events = [];
  service.on("event", (event) => events.push(event));
  service.start();
  try {
    await service.request("project.create", { path: project, teaching: true });
    const { stdout } = await promisify(execFile)(python, [join(root, "tests/e2e/app_mcp_client.py"),
      "--state-dir", state, "--project", project], { env, timeout: 60000, maxBuffer: 4 * 1024 * 1024 });
    const result = JSON.parse(stdout);
    const generation = result["design.generate"];
    const task = await service.request("task.get", { task_id: generation.task_id });
    assert.equal(task.project, result["project.current"].result.path);
    assert.deepEqual(task.result, generation.result);
    assert.ok(existsSync(join(generation.result.out_dir, "report.md")));
    assert.ok(events.some(e => e.event === "task.updated" && e.task.task_id === task.task_id && e.task.status === "running"));
    assert.ok(events.some(e => e.event === "task.updated" && e.task.task_id === task.task_id && e.task.status === "complete"));
    assert.deepEqual(events.filter(e => e.event === "task.receipt" && e.task_id === task.task_id).map(e => e.receipt.phase), ["prepared", "finished"]);
  } finally {
    await service.stop();
    rmSync(directory, { recursive: true, force: true });
  }
});

test("ACP 默认配置连接真实工程 MCP，读取计算共用桌面任务且默认只读", async () => {
  const root = resolve(__dirname, "../..");
  const directory = mkdtempSync(join(tmpdir(), "gongke-acp-mcp-"));
  const state = join(directory, "state"), project = join(directory, "工程");
  const python = process.env.GONGKE_PYTHON || "python3";
  const env = { ...process.env, PYTHONPATH: root };
  const service = new Service(python, ["-m", "gongke_app.service", "--state-dir", state], directory, env);
  service.start();
  try {
    await service.request("project.create", { path: project, teaching: true });
    const configuration = new AgentConfiguration(directory, root);
    const settings = configuration.read();
    settings.agents = [{ id: "fixture", name: "协议 Agent", command: process.execPath,
      args: [join(__dirname, "fixtures/acp-agent.mjs")], env: {} }];
    configuration.save(settings);
    const { mcp } = configuration.launch("fixture", project);
    assert.ok(mcp.args.includes(project));
    assert.ok(mcp.args.includes(state));
    const script = `
import asyncio, json, sys
from mcp import Client, StdioServerParameters
async def run():
    async with Client(StdioServerParameters(**json.loads(sys.argv[1]))) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
        assert "project.current" in names and "design.calculate" in names
        assert "project.set_task" not in names and "design.generate" not in names
        results = {}
        for name in ("project.current", "design.calculate"):
            result = await client.call_tool(name, {})
            assert not result.is_error, result.content
            results[name] = result.structured_content
        refused = await client.call_tool("design.generate", {"name": "forbidden"})
        assert refused.is_error
        print(json.dumps(results))
asyncio.run(run())
`;
    const { stdout } = await promisify(execFile)(python, ["-c", script, JSON.stringify(mcp)],
      { env, timeout: 60000, maxBuffer: 4 * 1024 * 1024 });
    const results = JSON.parse(stdout);
    const current = await service.request("project.current");
    assert.equal(results["project.current"].result.path, current.path);
    const calculation = results["design.calculate"];
    assert.ok(calculation.result.motor.power_kw > 0);
    const task = await service.request("task.get", { task_id: calculation.task_id });
    assert.equal(task.project, current.path);
    assert.deepEqual(task.result, calculation.result);
    assert.equal(task.receipts[0].command, "design.calculate");
    assert.ok(!existsSync(join(project, "revisions/forbidden")));
  } finally {
    await service.stop();
    rmSync(directory, { recursive: true, force: true });
  }
});
