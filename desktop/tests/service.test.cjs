const { test } = require("node:test");
const assert = require("node:assert/strict");
const { mkdtempSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join, resolve } = require("node:path");
const { Service } = require("../dist-electron/service.cjs");
test("桌面通信在源码目录之外执行真实计算，退出后不重放请求", async () => {
  const state = mkdtempSync(join(tmpdir(), "gongke-desktop-"));
  const service = new Service(
    process.env.GONGKE_PYTHON || "python3",
    ["-m", "gongke_app.service", "--state-dir", join(state, "state")],
    state,
    { ...process.env, PYTHONPATH: resolve(__dirname, "../..") },
  );
  service.start();
  try {
    assert.equal((await service.request("system.status")).ready, true);
    const project = await service.request("project.create", {
      path: join(state, "教学轴"),
      teaching: true,
    });
    assert.equal(project.teaching, true);
    const calculated = await service.request("design.calculate");
    assert.equal(calculated.motor.model, "Y132S-4");
    assert.ok(calculated.shaft_states.length >= 3);
    await assert.rejects(
      service.request("agent.run", { message: "读取工程" }),
      /未连接模型服务/,
    );
    await service.stop();
    await assert.rejects(service.request("system.status"), /未运行/);
  } finally {
    await service.stop();
    rmSync(state, { recursive: true, force: true });
  }
});
