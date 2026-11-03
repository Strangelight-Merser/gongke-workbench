const { test } = require("node:test");
const assert = require("node:assert/strict");
const {
  mkdtempSync,
  rmSync,
  readFileSync,
  writeFileSync,
  mkdirSync,
  readdirSync,
} = require("node:fs");
const { tmpdir } = require("node:os");
const { join } = require("node:path");
const { createHash } = require("node:crypto");
const {
  Onboarding,
  validReceipt,
  links,
} = require("../dist-electron/onboarding/controller.cjs");
const { installRelease } = require("../dist-electron/onboarding/installer.cjs");
const { agentError } = require("../dist-electron/onboarding/errors.cjs");
const { installation } = require("../dist-electron/onboarding/discovery.cjs");
const { launchSpec, spawnAgent } = require("../dist-electron/acp/process.cjs");
const { resolveCommand } = require("../dist-electron/acp/settings.cjs");
const { releases } = require("../dist-electron/onboarding/releases.cjs");
const id = "a".repeat(32);
function fixture(t) {
  const directory = mkdtempSync(join(tmpdir(), "gongke-onboarding-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  let project = "/工程";
  const effects = [];
  const record = () => ({
    kind: "mcp",
    status: "complete",
    project,
    created_at: new Date().toISOString(),
    result: { path: project },
    receipts: [
      {
        command: "project.current",
        phase: "finished",
        result: { path: project },
      },
    ],
  });
  const d = {
    directory,
    canInstall: true,
    project: () => project,
    detect: async (provider) =>
      provider === "deepseek"
        ? { command: "/Program Files/dsh.cmd", version: "0.2.1-rc.5" }
        : { application: "/WorkBuddy.app" },
    locate: async () => ({ command: "/chosen/dsh", version: "1.0.0" }),
    openAgent: async () => effects.push("open"),
    openLink: async (url) => effects.push(url),
    configuration: {
      read: () => ({
        agents: [{ id: "deepseek", command: "dsh", args: [], env: {} }],
      }),
      save: (s) => effects.push(s),
      launch: () => ({ profile: {}, mcp: {} }),
    },
    agent: {
      busy: false,
      start: async () => effects.push("start"),
      snapshot: () => ({ phase: "ready", project, agentId: "deepseek" }),
      prompt: async () => ({
        completed: true,
        events: [{ text: "工程回复", rawOutput: { task_id: id } }],
        sessionId: "live",
      }),
    },
    install: async (release, signal, report) => {
      report("正在下载", 100);
      effects.push(release);
    },
    configureWorkbuddy: async () => { effects.push("configure"); return { status: "configured", service_name: "gongke" }; },
    task: async () => record(),
    publish: () => {},
  };
  return {
    d,
    effects,
    directory,
    setProject: (value) => (project = value),
    record,
  };
}
test("检测→官方页面→退出恢复→连接→本轮真实回复和工程回执→完成", async (t) => {
  const f = fixture(t);
  let flow = new Onboarding(f.d);
  await flow.act({ type: "detect" });
  assert.equal(flow.snapshot().agents.deepseek.step, "account");
  await flow.act({ type: "link", link: "balance" });
  assert.ok(f.effects.includes(links.balance));
  await flow.act({ type: "advance", step: "credentials" });
  flow = new Onboarding(f.d);
  assert.equal(flow.snapshot().agents.deepseek.step, "credentials");
  await flow.act({ type: "open-agent" });
  await flow.act({ type: "connect" });
  assert.equal(flow.snapshot().agents.deepseek.step, "verify");
  await flow.act({ type: "verify" });
  assert.equal(flow.snapshot().agents.deepseek.step, "complete");
  assert.equal(new Onboarding(f.d).snapshot().agents.deepseek.evidence, id);
  assert.deepEqual(
    Object.keys(
      JSON.parse(readFileSync(join(f.directory, "agent-onboarding.json"))),
    ).sort(),
    ["agents", "selected"],
  );
  f.setProject("/另一工程");
  assert.equal(flow.snapshot().agents.deepseek.step, "connect");
});
test("未同意不安装，同意后使用固定清单并重新检测", async (t) => {
  const f = fixture(t);
  f.d.detect = async () => ({});
  const flow = new Onboarding(f.d);
  await flow.act({ type: "detect" });
  assert.equal(flow.snapshot().agents.deepseek.step, "install");
  await flow.act({ type: "install", consent: false });
  assert.equal(f.effects.length, 0);
  assert.match(flow.snapshot().error, /同意/);
  f.d.install = async (release) => {
    assert.equal(release, releases[0]);
    f.d.detect = async () => ({ command: "/installed/dsh" });
  };
  await flow.act({ type: "install", consent: true });
  assert.equal(flow.snapshot().agents.deepseek.step, "account");
});
test("下载可取消，不并发安装；重启保留待安装步骤", async (t) => {
  const f = fixture(t);
  const flow = new Onboarding(f.d);
  let started;
  const running = new Promise((r) => (started = r));
  f.d.install = async (_r, signal) =>
    new Promise((_resolve, reject) => {
      started();
      signal.addEventListener("abort", () => reject(Error("abort")), {
        once: true,
      });
    });
  const install = flow.act({ type: "install", consent: true });
  await running;
  await assert.rejects(flow.act({ type: "install", consent: true }), /等待/);
  assert.equal(new Onboarding(f.d).snapshot().agents.deepseek.step, "install");
  await flow.act({ type: "cancel-install" });
  await install;
  assert.match(flow.snapshot().error, /取消/);
  assert.equal(flow.snapshot().working, false);
});
test("401/402/429/503/网络错误有下一步，未知错误不暴露凭据", () => {
  for (const [code, match] of [
    [401, /更新 Key/],
    [402, /充值/],
    [429, /稍后/],
    [503, /稍后/],
  ])
    assert.match(agentError(Error(String(code))), match);
  assert.match(agentError(Error("fetch failed")), /网络/);
  assert.doesNotMatch(agentError(Error("Bearer sk-private")), /sk-private/);
});
test("取消、空回复、失败回执、旧回执、其他工程均不能完成", async (t) => {
  const f = fixture(t);
  const flow = new Onboarding(f.d);
  await flow.act({ type: "detect" });
  await flow.act({ type: "connect" });
  f.d.agent.prompt = async () => ({ completed: false, events: [] });
  await flow.act({ type: "verify" });
  assert.equal(flow.snapshot().agents.deepseek.step, "verify");
  f.d.agent.prompt = async () => ({
    completed: true,
    events: [{ task_id: id }],
  });
  f.d.task = async () => ({ ...f.record(), status: "failed" });
  await flow.act({ type: "verify" });
  assert.match(flow.snapshot().error, /尚未核实/);
  assert.equal(
    validReceipt(f.record(), "/错误工程", new Date(0).toISOString()),
    false,
  );
  assert.equal(
    validReceipt(
      { ...f.record(), created_at: "2000-01-01" },
      "/工程",
      new Date().toISOString(),
    ),
    false,
  );
  f.d.agent.prompt = async () => {
    throw Error("402 balance");
  };
  await flow.act({ type: "verify" });
  assert.match(flow.snapshot().error, /充值/);
});
test("WorkBuddy 必须确认真实回复并核对本工程成功回执", async (t) => {
  const f = fixture(t);
  const flow = new Onboarding(f.d);
  await flow.act({ type: "detect" });
  await flow.act({ type: "select", provider: "workbuddy" });
  await flow.act({ type: "connect" });
  assert.equal(flow.snapshot().agents.workbuddy.step, "verify");
  await flow.act({ type: "confirm-workbuddy", taskId: id, sawReply: false });
  assert.equal(flow.snapshot().agents.workbuddy.step, "verify");
  await flow.act({ type: "confirm-workbuddy", taskId: id, sawReply: true });
  assert.equal(flow.snapshot().agents.workbuddy.step, "complete");
});
test("检测失败可选位置，单个失败不丢另一项结果", async (t) => {
  const f = fixture(t);
  const flow = new Onboarding(f.d);
  f.d.detect = async (provider) => {
    if (provider === "deepseek") throw Error("bad installation");
    return { application: "/WorkBuddy.app" };
  };
  await flow.act({ type: "detect" });
  assert.equal(flow.snapshot().agents.workbuddy.application, "/WorkBuddy.app");
  assert.match(flow.snapshot().error, /选择安装位置/);
  await flow.act({ type: "locate" });
  assert.equal(flow.snapshot().agents.deepseek.command, "/chosen/dsh");
});
test("伪造页面/阶段不能打开任意 URL 或标记完成", async (t) => {
  const f = fixture(t);
  const flow = new Onboarding(f.d);
  await flow.act({ type: "link", link: "https://attacker.invalid" });
  assert.equal(f.effects.length, 0);
  await flow.act({ type: "advance", step: "complete" });
  assert.notEqual(flow.snapshot().agents.deepseek.step, "complete");
});
test("固定发行物有大小、摘要和签名者，不含 latest", () => {
  for (const r of releases) {
    assert.equal(new URL(r.url).protocol, "https:");
    assert.ok(r.url.includes(r.version));
    assert.doesNotMatch(r.url, /latest/);
    assert.ok(r.size > 0);
    assert.equal(Buffer.from(r.sha512, "base64").length, 64);
    assert.match(r.signerThumbprint, /^[A-F0-9]{40}$/);
  }
});
test("先摘要后签名，成功才执行，失败时清理下载", async (t) => {
  const f = fixture(t);
  const bytes = Buffer.from("official installer fixture");
  const calls = [];
  const r = {
    ...releases[0],
    size: bytes.length,
    sha512: createHash("sha512").update(bytes).digest("base64"),
  };
  const deps = {
    fetch: async () => new Response(bytes),
    signature: async (file) => {
      assert.deepEqual(readFileSync(file), bytes);
      calls.push("signature");
    },
    launch: async () => calls.push("launch"),
  };
  await installRelease(
    r,
    f.directory,
    new AbortController().signal,
    () => {},
    deps,
  );
  assert.deepEqual(calls, ["signature", "launch"]);
  assert.deepEqual(readdirSync(f.directory), []);
  calls.length = 0;
  await assert.rejects(
    installRelease(
      { ...r, sha512: "wrong" },
      f.directory,
      new AbortController().signal,
      () => {},
      deps,
    ),
    /摘要/,
  );
  assert.deepEqual(calls, []);
  deps.signature = async () => {
    throw Error("bad signature");
  };
  await assert.rejects(
    installRelease(
      r,
      f.directory,
      new AbortController().signal,
      () => {},
      deps,
    ),
    /signature/,
  );
  assert.deepEqual(calls, []);
  assert.deepEqual(readdirSync(f.directory), []);
});
test("断网、响应错误、截断、超长、取消均不运行安装器", async (t) => {
  const f = fixture(t);
  const bytes = Buffer.from("1234");
  let executed = 0;
  const r = {
    ...releases[0],
    size: 4,
    sha512: createHash("sha512").update(bytes).digest("base64"),
  };
  for (const fetch of [
    async () => {
      throw Error("offline");
    },
    async () => new Response("", { status: 500 }),
    async () => new Response("12"),
    async () => new Response("123456"),
  ])
    await assert.rejects(
      installRelease(r, f.directory, new AbortController().signal, () => {}, {
        fetch,
        signature: async () => executed++,
        launch: async () => executed++,
      }),
    );
  const abort = new AbortController();
  abort.abort();
  await assert.rejects(
    installRelease(r, f.directory, abort.signal, () => {}, {
      fetch: async () => new Response(bytes),
      signature: async () => executed++,
      launch: async () => executed++,
    }),
  );
  assert.equal(executed, 0);
  assert.deepEqual(readdirSync(f.directory), []);
});
test("Windows .cmd 保留空格和中文参数边界；禁用自动运行与变量扩展", () => {
  const command = "C:\\Users\\学生\\App Data\\DeepSeek Harness\\dsh.cmd";
  const args = ["--profile", "acp", "--patch", "C:\\App Data\\policy.yml"];
  const spec = launchSpec(command, args, "win32");
  assert.match(spec.command, /cmd.exe$/);
  assert.equal(
    spec.args.at(-1),
    `""${command}" "--profile" "acp" "--patch" "${args[3]}""`,
  );
  assert.equal(spec.windowsVerbatimArguments, true);
  assert.throws(() => launchSpec(command, ["%PATH%"], "win32"), /百分号/);
  assert.throws(() => launchSpec(command, ['a" & whoami'], "win32"), /双引号/);
  assert.deepEqual(launchSpec("/usr/bin/dsh", args, "darwin").args, args);
});
test("安装目录定位 Desktop dsh.cmd（带空格路径）", (t) => {
  const f = fixture(t);
  const base = join(f.directory, "DeepSeek Harness");
  mkdirSync(join(base, "resources/runtime/cli/bin"), { recursive: true });
  writeFileSync(join(base, "resources/runtime/cli/bin/dsh.cmd"), "");
  writeFileSync(join(base, "DeepSeek Harness.exe"), "");
  const found = installation("deepseek", base);
  assert.equal(found.command, join(base, "resources/runtime/cli/bin/dsh.cmd"));
  assert.equal(found.application, join(base, "DeepSeek Harness.exe"));
});
test(
  "Windows 真 cmd.exe 执行 PATH 上带空格的 dsh.cmd",
  { skip: process.platform !== "win32" },
  async (t) => {
    const f = fixture(t);
    const dir = join(f.directory, "Agent 安装");
    mkdirSync(dir);
    const shim = join(dir, "dsh.cmd");
    writeFileSync(
      shim,
      "@echo off\r\nsetlocal DisableDelayedExpansion\r\necho %~1\r\n",
    );
    assert.equal(resolveCommand("dsh", { PATH: dir }), shim);
    const child = spawnAgent(shim, ["path with space"], { windowsHide: true });
    let out = "";
    child.stdout.on("data", (b) => (out += b));
    await new Promise((resolve, reject) => {
      child.on("error", reject);
      child.on("close", (code) =>
        code ? reject(Error(String(code))) : resolve(),
      );
    });
    assert.match(out, /path with space/);
  },
);
test("签名必须同时满足 Windows Valid 和固定发布者指纹", async () => {
  const {
    verifySignature,
  } = require("../dist-electron/onboarding/installer.cjs");
  for (const [status, thumbprint, success] of [
    ["Valid", releases[0].signerThumbprint, true],
    ["NotSigned", "", false],
    ["HashMismatch", releases[0].signerThumbprint, false],
    ["Valid", "unrelated-publisher", false],
  ]) {
    const run = async (script) => {
      assert.match(
        script,
        /Get-AuthenticodeSignature -LiteralPath 'C:\\学生''s folder\\setup.exe'/,
      );
      return { stdout: JSON.stringify({ status, thumbprint }) };
    };
    const result = verifySignature(
      "C:\\学生's folder\\setup.exe",
      releases[0],
      run,
    );
    if (success) await result;
    else await assert.rejects(result, /签名或发布者/);
  }
});
test("真实 ACP 子进程：新一轮取消不复用上一轮成功回复", async () => {
  const { AgentClient } = require("../dist-electron/acp/client.cjs");
  const { resolve } = require("node:path");
  const client = new AgentClient(() => {});
  const profile = {
    id: "fixture",
    name: "fixture",
    command: process.execPath,
    args: [resolve(__dirname, "fixtures/acp-agent.mjs")],
    env: {},
  };
  try {
    await assert.rejects(
      client.start(profile, process.cwd(), {
        command: process.execPath,
        args: [],
        env: {},
      }),
    );
    await client.authenticate("login");
    const first = await client.prompt("forbidden");
    assert.equal(first.completed, true);
    const prompt = client.prompt("取消本轮");
    while (!client.snapshot().events.some((e) => e.type === "permission"))
      await new Promise((r) => setTimeout(r, 10));
    await client.cancel();
    assert.equal((await prompt).completed, false);
  } finally {
    await client.disconnect();
  }
});
test("同步启动错误结束 starting，允许用户重新选择路径", async () => {
  const { AgentClient } = require("../dist-electron/acp/client.cjs");
  const client = new AgentClient(() => {});
  await assert.rejects(
    client.start(
      {
        id: "fixture",
        name: "fixture",
        command: "bad\0command",
        args: [],
        env: {},
      },
      process.cwd(),
      { command: process.execPath, args: [], env: {} },
    ),
  );
  assert.equal(client.busy, false);
  assert.equal(client.snapshot().phase, "disconnected");
});

test("引导保留原始 ACP 详情且只记录一次，MCP 失败回执提供具体原因", async (t) => {
  const {
    AgentFailure,
    diagnosticFor,
    logDiagnostic,
  } = require("../dist-electron/acp/diagnostics.cjs");
  const f = fixture(t);
  const flow = new Onboarding(f.d);
  await flow.act({ type: "detect" });
  await flow.act({ type: "connect" });
  const original = Object.assign(new Error("model unavailable"), {
    code: -32603,
    data: { details: "unknown model" },
  });
  const details = diagnosticFor(original, "session/prompt");
  logDiagnostic(details, join(f.directory, "agent-errors.jsonl"));
  f.d.agent.prompt = async () => {
    throw new AgentFailure(agentError(original), details);
  };
  const failed = await flow.act({ type: "verify" });
  assert.equal(failed.errorDetails.code, -32603);
  assert.match(failed.errorDetails.details, /unknown model/);
  assert.equal(
    readFileSync(details.logPath, "utf8").trim().split("\n").length,
    1,
  );
  f.d.agent.snapshot = () => ({
    phase: "ready",
    project: "/工程",
    agentId: "deepseek",
    events: [
      {
        type: "update",
        update: {
          sessionUpdate: "tool_call_update",
          toolCallId: "bad",
          status: "failed",
          rawOutput: { error: "MCP project is not open" },
        },
      },
    ],
  });
  f.d.agent.prompt = async () => ({ completed: true, events: [] });
  const missing = await flow.act({ type: "verify" });
  assert.notEqual(missing.agents.deepseek.step, "complete");
  assert.match(missing.errorDetails.tools, /MCP project is not open/);
});


test("WorkBuddy 用户级写入须明确确认，工程切换使旧确认失效", async (t) => {
  const f = fixture(t);
  const confirmations = [];
  f.d.configureWorkbuddy = async (consent) => {
    confirmations.push(consent);
    return { status: consent ? "configured" : "confirmation_required", service_name: "gongke-project123",
      conflicts: [{ name: "gongke", reason: "旧工程入口", path: "/home/.workbuddy/mcp.json" }] };
  };
  const flow = new Onboarding(f.d);
  await flow.act({ type: "select", provider: "workbuddy" });
  await flow.act({ type: "detect" });
  await flow.act({ type: "connect" });
  let p = flow.snapshot().agents.workbuddy;
  assert.equal(p.step, "connect");
  assert.equal(p.configuredAt, undefined);
  assert.equal(p.conflicts[0].name, "gongke");
  f.setProject("/另一个工程");
  await flow.act({ type: "connect", confirmUserConfig: true });
  assert.match(flow.snapshot().error, /工程已切换/);
  assert.deepEqual(confirmations, [false]);
  f.setProject("/工程");
  await flow.act({ type: "connect", confirmUserConfig: true });
  p = flow.snapshot().agents.workbuddy;
  assert.equal(p.step, "verify");
  assert.equal(p.serviceName, "gongke-project123");
  assert.equal(p.conflicts, undefined);
  assert.deepEqual(confirmations, [false, true]);
  assert.equal(new Onboarding(f.d).snapshot().agents.workbuddy.serviceName, "gongke-project123");
});
