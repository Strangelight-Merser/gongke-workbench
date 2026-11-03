// 真实 Electron；可传入真实 Agent 配置，否则使用确定性 ACP 协议替身。
const { _electron: electron } = require("playwright");
const { mkdirSync, writeFileSync } = require("node:fs");
const { resolve, join } = require("node:path");
const assert = require("node:assert/strict");
const root = resolve(__dirname, "../..");
const output = resolve(
  process.env.GONGKE_ACP_OUTPUT ||
    join(root, "out/acp-desktop", String(Date.now())),
);
mkdirSync(output, { recursive: true });
const live = !!process.env.GONGKE_TEST_AGENT_CONFIG;
const configPath =
  process.env.GONGKE_TEST_AGENT_CONFIG || join(output, "agents.json");
if (!live)
  writeFileSync(
    configPath,
    JSON.stringify({
      agents: [
        {
          id: "fixture",
          name: "协议测试 Agent",
          command: process.execPath,
          args: [join(__dirname, "fixtures/acp-agent.mjs")],
          env: {},
        },
      ],
      mcp: { command: process.execPath, args: [], env: {} },
    }),
  );
(async () => {
  const app = await electron.launch({
    args: [resolve(__dirname, "..")],
    env: {
      ...process.env,
      GONGKE_DESKTOP_USER_DATA: join(output, "user"),
      GONGKE_AGENT_CONFIG: configPath,
    },
  });
  const page = await app.firstWindow();
  page.setDefaultTimeout(20_000);
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  try {
    await page.waitForFunction(() => !!window.gongke);
    await page.evaluate(
      async (path) => {
        await window.gongke.request("project.create", { path, teaching: true });
      },
      join(output, "project"),
    );
    await page.reload();
    await page
      .getByRole("button", { name: "Agent 连接设置", exact: true })
      .click();
    await page
      .getByRole("menuitem", { name: "使用已配置的 Agent", exact: true })
      .click();
    await page.getByLabel("选择 Agent", { exact: true }).waitFor();
    const settings = await page.evaluate(() => window.gongke.agent.settings());
    const evidence = [];
    for (const profile of settings.agents) {
      await page.getByLabel("选择 Agent").selectOption(profile.id);
      await page.getByRole("button", { name: "连接", exact: true }).click();
      if (!live) {
        await page
          .getByRole("button", { name: "测试登录", exact: true })
          .click();
      }
      await page.waitForFunction(
        async () => (await window.gongke.agent.state()).phase === "ready",
        null,
        { timeout: 60_000 },
      );
      await page
        .getByLabel("工程任务")
        .fill(
          live
            ? "先调用 project.current 读取当前工程，再调用 design.calculate 计算。只需告诉我电机型号和额定功率。不要用 shell、文件或其他工具。"
            : "读取工程",
        );
      await page.getByRole("button", { name: "发送", exact: true }).click();
      let approved = 0,
        deadline = Date.now() + 180_000;
      while (Date.now() < deadline) {
        const permission = page.getByRole("group", { name: "工程操作授权" });
        if (await permission.count()) {
          if (!approved)
            await page.screenshot({
              path: join(output, `${profile.id}-permission.png`),
            });
          await permission
            .first()
            .getByRole("button", { name: "允许一次", exact: true })
            .click();
          approved++;
        }
        const state = await page.evaluate(() => window.gongke.agent.state());
        if (state.phase === "ready") break;
        if (state.phase === "disconnected") throw new Error(state.error);
        await page.waitForTimeout(150);
      }
      const state = await page.evaluate(() => window.gongke.agent.state());
      assert.equal(state.phase, "ready", JSON.stringify(state));
      assert.ok(approved > 0, "真实窗口应显示并批准权限请求");
      assert.ok(
        state.events.some(
          (e) =>
            e.type === "update" &&
            e.update.sessionUpdate === "tool_call_update" &&
            e.update.status === "completed",
        ),
      );
      if (live) {
        const text = state.events
          .filter(
            (e) =>
              e.type === "update" &&
              e.update.sessionUpdate === "agent_message_chunk",
          )
          .map((e) => e.update.content.text || "")
          .join("");
        assert.match(text, /Y132S-4/);
      }
      await page.screenshot({ path: join(output, `${profile.id}-result.png`) });
      writeFileSync(
        join(output, `${profile.id}-events.json`),
        JSON.stringify(state, null, 2),
      );
      evidence.push({
        agent: profile.name,
        session: state.session.sessionId,
        approved,
        events: state.events.length,
      });
      await page
        .getByRole("button", { name: "Agent 操作", exact: true })
        .click();
      await page
        .getByRole("menuitem", { name: "断开连接", exact: true })
        .click();
    }
    assert.deepEqual(errors, []);
    writeFileSync(
      join(output, "result.json"),
      JSON.stringify({ live, evidence, errors }, null, 2),
    );
    console.log(JSON.stringify({ output, live, evidence }, null, 2));
  } catch (error) {
    await page.screenshot({ path: join(output, "failure.png") });
    console.error(await page.locator("[role=alert]").allTextContents());
    throw error;
  } finally {
    await app.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
