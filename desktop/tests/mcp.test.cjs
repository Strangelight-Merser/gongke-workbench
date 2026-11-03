// 官方 MCP 客户端连接桌面 Service 的同一 Python 进程，不模拟事件。
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { mkdtempSync, rmSync, existsSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join, resolve } = require("node:path");
const { execFile } = require("node:child_process");
const { promisify } = require("node:util");
const { Service } = require("../dist-electron/service.cjs");

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
