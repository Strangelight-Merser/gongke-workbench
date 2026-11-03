// 真实 Electron + 已安装 dsh + 真实模型；独立教学工程，只批准一次只读工程调用。
// 会产生模型 API 用量，不在 npm test 中自动运行。
const { _electron: electron } = require("playwright");
const { mkdirSync, writeFileSync } = require("node:fs");
const { resolve, join } = require("node:path");
const assert = require("node:assert/strict");
const output = resolve(
  process.env.GONGKE_ONBOARDING_OUTPUT || "../out/onboarding-live",
);
mkdirSync(output, { recursive: true });
(async () => {
  const app = await electron.launch({
    args: [resolve(__dirname, "..")],
    env: {
      ...process.env,
      GONGKE_DESKTOP_USER_DATA: join(output, "user"),
      GONGKE_AGENT_CONFIG: "",
    },
  });
  const page = await app.firstWindow();
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  try {
    await page.waitForFunction(() => !!window.gongke?.onboarding);
    await page.evaluate(
      async (path) => {
        await window.gongke.request("project.create", { path, teaching: true });
      },
      join(output, "学生工程"),
    );
    await page.reload();
    await page.waitForFunction(async () => {
      const s = await window.gongke.onboarding.state();
      return !s.working && !!s.agents.deepseek.command;
    });
    await page.screenshot({ path: join(output, "01-detected.png") });
    await page
      .getByRole("button", { name: "已配置，直接连接", exact: true })
      .click();
    await page.getByRole("button", { name: "连接 dsh", exact: true }).click();
    await page.waitForFunction(
      async () => !(await window.gongke.onboarding.state()).working,
      null,
      { timeout: 60000 },
    );
    let guide = await page.evaluate(() => window.gongke.onboarding.state());
    assert.equal(guide.error, undefined, JSON.stringify(guide));
    assert.equal(guide.agents.deepseek.step, "verify");
    await page
      .getByRole("button", { name: "发送首次对话", exact: true })
      .click();
    let approved = 0;
    const deadline = Date.now() + 150000;
    while (Date.now() < deadline) {
      const permissions = page.getByRole("group", { name: "工程操作授权" });
      if (await permissions.count()) {
        const text = await permissions.first().innerText();
        assert.match(text, /project.current|project_current|读取当前工程/);
        await page.screenshot({ path: join(output, "02-permission.png") });
        await permissions
          .first()
          .getByRole("button", { name: "允许一次", exact: true })
          .click();
        approved++;
      }
      guide = await page.evaluate(() => window.gongke.onboarding.state());
      if (!guide.working) break;
      await page.waitForTimeout(200);
    }
    assert.equal(guide.error, undefined, JSON.stringify(guide));
    assert.equal(guide.agents.deepseek.step, "complete");
    assert.ok(approved >= 1);
    const state = await page.evaluate(() => window.gongke.agent.state());
    await page.screenshot({ path: join(output, "03-complete.png") });
    const result = {
      detected: guide.agents.deepseek.command,
      version: guide.agents.deepseek.version,
      approved,
      evidence: guide.agents.deepseek.evidence,
      session: state.session?.sessionId,
      reply: state.events
        .filter(
          (e) =>
            e.type === "update" &&
            e.update.sessionUpdate === "agent_message_chunk",
        )
        .map((e) => e.update.content.text || "")
        .join(""),
      errors,
    };
    writeFileSync(join(output, "result.json"), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
    await page.reload();
    const restored = await page.evaluate(() =>
      window.gongke.onboarding.state(),
    );
    assert.equal(restored.agents.deepseek.step, "complete");
    assert.deepEqual(errors, []);
  } catch (e) {
    await page.screenshot({ path: join(output, "failed.png") }).catch(() => {});
    console.error(e.message);
    process.exitCode = 1;
  } finally {
    await app.close();
  }
})();
