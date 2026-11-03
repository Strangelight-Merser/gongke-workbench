const { test } = require("node:test");
const assert = require("node:assert/strict");
const { resolve, join } = require("node:path");
const { mkdtempSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { AgentClient } = require("../dist-electron/acp/client.cjs");
const {
  AgentConfiguration,
  validateSettings,
  resolveCommand,
} = require("../dist-electron/acp/settings.cjs");
const profile = {
  id: "fixture",
  name: "测试 Agent",
  command: process.execPath,
  args: [resolve(__dirname, "fixtures/acp-agent.mjs")],
  env: {},
};
const mcp = {
  command: process.execPath,
  args: ["engineering.mjs", "工程目录"],
  env: { GONGKE_PROJECT: "/工程" },
};
async function waitUntil(fn) {
  for (let n = 0; n < 200; n++) {
    if (fn()) return;
    await new Promise((r) => setTimeout(r, 10));
  }
  throw Error("等待状态超时");
}
const request = (client) =>
  client
    .snapshot()
    .events.find(
      (e) =>
        e.type === "permission" &&
        !client
          .snapshot()
          .events.some(
            (x) => x.type === "permission-resolved" && x.id === e.id,
          ),
    );
test("真实 stdio：登录、MCP 注入、增量、权限选项与拒绝、取消、退出", async () => {
  const client = new AgentClient(() => {});
  try {
    await assert.rejects(client.start(profile, process.cwd(), mcp), /需要登录/);
    assert.equal(client.snapshot().phase, "connected");
    await client.authenticate("login");
    assert.equal(client.snapshot().phase, "ready");
    await client.prompt("forbidden");
    assert.ok(
      client
        .snapshot()
        .events.some(
          (e) =>
            e.type === "update" &&
            e.update.content?.text === "客户端拒绝文件写入和终端执行",
        ),
    );
    const run = client.prompt("读取");
    await waitUntil(() => request(client));
    const pending = request(client);
    assert.throws(() => client.permission(pending.id, "invented"), /无效/);
    const tool = client
      .snapshot()
      .events.find(
        (e) => e.type === "update" && e.update.sessionUpdate === "tool_call",
      ).update;
    assert.deepEqual(tool.rawInput.mcpServers, [
      {
        name: "gongke",
        command: mcp.command,
        args: mcp.args,
        env: [{ name: "GONGKE_PROJECT", value: "/工程" }],
      },
    ]);
    client.permission(pending.id, "no");
    await run;
    assert.throws(() => client.permission(pending.id, "yes"), /已结束/);
    const output = client
      .snapshot()
      .events.findLast(
        (e) =>
          e.type === "update" && e.update.sessionUpdate === "tool_call_update",
      ).update.rawOutput;
    assert.equal(output.outcome.optionId, "no");
    const cancel = client.prompt("取消");
    await waitUntil(() => request(client));
    await assert.rejects(client.prompt("并发"), /建立会话/);
    await client.cancel();
    assert.equal(client.snapshot().phase, "cancelling");
    await cancel;
    assert.equal(client.snapshot().phase, "ready");
    await assert.rejects(client.prompt("crash"));
    await waitUntil(() => client.snapshot().phase === "disconnected");
  } finally {
    await client.disconnect();
  }
});
test("连接失败可重新启动，配置校验不接受 shell 字符串参数", async () => {
  const client = new AgentClient(() => {});
  await assert.rejects(
    client.start(
      { ...profile, command: "/missing/gongke-agent" },
      process.cwd(),
      mcp,
    ),
  );
  assert.equal(client.snapshot().phase, "disconnected");
  assert.throws(
    () => validateSettings({ agents: [{ ...profile, args: "--acp" }], mcp }),
    /字符串数组/,
  );
  assert.equal(resolveCommand(process.execPath), process.execPath);
  await client.disconnect();
});
test("断开时取消未决权限，不重放；新会话关闭旧 Agent 进程", async () => {
  const client = new AgentClient(() => {});
  try {
    await assert.rejects(client.start(profile, process.cwd(), mcp));
    await client.authenticate("login");
    const prompt = client.prompt("待授权");
    const rejected = assert.rejects(prompt);
    await waitUntil(() => request(client));
    const id = request(client).id;
    await client.disconnect();
    await rejected;
    assert.equal(client.snapshot().phase, "disconnected");
    assert.throws(() => client.permission(id, "yes"), /已结束/);
    await assert.rejects(client.start(profile, process.cwd(), mcp));
    await client.authenticate("login");
    await assert.rejects(client.newSession(), /需要登录/); // 替身每个进程独立，证明新会话已替换旧进程。
    assert.equal(client.snapshot().events.length, 0);
  } finally {
    await client.disconnect();
  }
});
test("DeepSeek 官方插件策略：仅会话 MCP 可见，非工程工具拒绝，工程调用逐次授权", async () => {
  const { apply } = require("../dist-electron/acp/deepseek-policy.cjs");
  const events = {};
  let guard, filter;
  apply({
    tools: { guard: (fn) => (guard = fn) },
    on: (name, fn) => (events[name] = fn),
  });
  events["agent/created"]({
    agent: { ctx: { tools: { restrict: (value) => (filter = value) } } },
  });
  assert.deepEqual(filter, { allow: [] });
  assert.match(guard({ name: "bash" }), /MCP/);
  assert.equal(guard({ name: "mcp__gongke__project_current" }), undefined);
  assert.equal(
    (
      await events["tools/pre-execute"]({ name: "bash" }, async () => ({
        kind: "allow",
      }))
    ).kind,
    "deny",
  );
  assert.equal(
    (
      await events["tools/pre-execute"](
        { name: "mcp__gongke__project_current" },
        async () => ({ kind: "allow" }),
      )
    ).kind,
    "ask",
  );
  assert.equal(
    (
      await events["tools/pre-execute"](
        { name: "mcp__gongke__project_current" },
        async () => ({ kind: "deny", reason: "上游拒绝" }),
      )
    ).kind,
    "deny",
  );
});


test("ACP 开发版与打包版使用同一状态目录的绑定工程入口", () => {
  const root = resolve(__dirname, "../..");
  const directory = mkdtempSync(join(tmpdir(), "gongke-acp-settings-"));
  try {
    const packaged = new AgentConfiguration(directory, root, process.execPath).read();
    assert.deepEqual(packaged.mcp, {
      command: process.execPath,
      args: ["mcp", "--state-dir", join(directory, "state"), "--project", "${project}"],
      env: {},
    });
    const configuration = new AgentConfiguration(directory, root);
    const settings = configuration.read();
    assert.deepEqual(settings.mcp.args, ["-m", "gongke_app", "mcp", "--state-dir",
      join(directory, "state"), "--project", "${project}"]);
    assert.equal(settings.mcp.env.PYTHONPATH, root);
    settings.agents = [profile];
    configuration.save(settings);
    const launch = configuration.launch(profile.id, join(directory, "工程"));
    assert.equal(launch.mcp.args.at(-1), join(directory, "工程"));
    assert.ok(!launch.mcp.args.includes("--allow-writes"));
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
