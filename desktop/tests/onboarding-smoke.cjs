// 真实 dsh/ACP/MCP 与引导控制器。无窗口运行，不作为 Electron 窗口验收。
const { AgentClient } = require("../dist-electron/acp/client.cjs");
const { AgentConfiguration } = require("../dist-electron/acp/settings.cjs");
const { Onboarding } = require("../dist-electron/onboarding/controller.cjs");
const { detect } = require("../dist-electron/onboarding/discovery.cjs");
const { Service } = require("../dist-electron/service.cjs");
const { mkdirSync, writeFileSync } = require("node:fs");
const { resolve, join } = require("node:path");
const assert = require("node:assert/strict");
const root = resolve(__dirname, "../..");
const output = resolve(
  process.env.GONGKE_ONBOARDING_OUTPUT || join(root, "out/onboarding-smoke"),
);
mkdirSync(output, { recursive: true });
const project = join(output, "学生工程");
const service = new Service(
  process.env.GONGKE_PYTHON || "python3",
  ["-m", "gongke_app.service", "--state-dir", join(output, "state")],
  root,
  { ...process.env, PYTHONPATH: root },
);
let approved = 0;
const handled = new Set();
const agent = new AgentClient((state) => {
  for (const e of state.events)
    if (e.type === "permission" && !handled.has(e.id)) {
      handled.add(e.id);
      const tool = state.events.findLast(
        (x) =>
          x.type === "update" &&
          x.update.sessionUpdate === "tool_call" &&
          x.update.toolCallId === e.request.toolCall.toolCallId,
      )?.update;
      const read = /project.current|project_current/.test(
        JSON.stringify(tool || e.request),
      );
      setImmediate(() => {
        if (read) approved++;
        agent.permission(
          e.id,
          read
            ? e.request.options.find((o) => o.kind === "allow_once").optionId
            : null,
        );
      });
    }
});
(async () => {
  service.start();
  const timer = setTimeout(() => agent.disconnect(), 150000);
  try {
    await service.request("project.create", { path: project, teaching: true });
    const configuration = new AgentConfiguration(output, root);
    if (process.env.GONGKE_TEST_DSH_HOME) {
      const settings = configuration.read();
      settings.agents.find((a) => a.id === "deepseek").env.DSH_HOME =
        process.env.GONGKE_TEST_DSH_HOME;
      configuration.save(settings);
    }
    const flow = new Onboarding({
      directory: output,
      canInstall: false,
      agent,
      configuration,
      project: () => project,
      detect,
      locate: async () => undefined,
      openAgent: async () => {},
      openLink: async () => {},
      install: async () => {
        throw Error("no install in smoke");
      },
      configureWorkbuddy: () =>
        service.request("mcp.configure", { allow_writes: false }),
      task: (id) => service.request("task.get", { task_id: id }),
      publish: () => {},
    });
    const detected = await flow.act({ type: "detect" });
    console.log("detected", JSON.stringify(detected.agents));
    const connected = await flow.act({ type: "connect" });
    assert.equal(connected.error, undefined, connected.error);
    console.log(
      "connected",
      agent.snapshot().phase,
      JSON.stringify(agent.snapshot().session?.configOptions),
    );
    if (process.argv.includes("--connect-only")) {
      writeFileSync(
        join(output, "connection.json"),
        JSON.stringify(
          {
            command: connected.agents.deepseek.command,
            version: connected.agents.deepseek.version,
            phase: agent.snapshot().phase,
            session: agent.snapshot().session,
            isolated: !!process.env.GONGKE_TEST_DSH_HOME,
            modelReplyVerified: false,
          },
          null,
          2,
        ),
      );
      return;
    }
    const verified = await flow.act({ type: "verify" });
    assert.equal(verified.error, undefined, verified.error);
    assert.equal(verified.agents.deepseek.step, "complete");
    const state = agent.snapshot();
    const result = {
      ...verified.agents.deepseek,
      approved,
      session: state.session?.sessionId,
      reply: state.events
        .filter(
          (e) =>
            e.type === "update" &&
            e.update.sessionUpdate === "agent_message_chunk",
        )
        .map((e) => e.update.content.text || "")
        .join(""),
    };
    writeFileSync(join(output, "result.json"), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally {
    clearTimeout(timer);
    await agent.disconnect();
    await service.stop();
  }
})().catch((e) => {
  console.error(e.message);
  process.exitCode = 1;
});
