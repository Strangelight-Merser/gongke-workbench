// 确定性 UI 验收夹具；输出不作参赛录屏素材。
const { electron } = require("./helpers/owned-electron.cjs");
const fs = require("node:fs"),
  path = require("node:path"),
  os = require("node:os"),
  assert = require("node:assert/strict");
(async () => {
  const out = path.resolve(process.argv[2]);
  fs.mkdirSync(out, { recursive: true });
  const env = {
    ...process.env,
    GONGKE_VISUAL_USER_DATA: fs.mkdtempSync(
      path.join(os.tmpdir(), "agent-revision-"),
    ),
  };
  delete env.ELECTRON_RUN_AS_NODE;
  const app = await electron.launch({
    args: [path.join(__dirname, "fixtures/workbench-main.cjs")],
    env,
  });
  try {
    const page = await app.firstWindow();
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page
      .getByRole("heading", { name: "支架建模练习", exact: true })
      .waitFor();
    await page
      .getByRole("button", { name: "Agent 连接设置", exact: true })
      .click();
    await page
      .getByRole("menuitem", { name: "使用已配置的 Agent", exact: true })
      .click();
    const update = (sessionUpdate, extra) => ({
      type: "update",
      update: { sessionUpdate, ...extra },
    });
    await page.evaluate(
      (events) => window.visualReview.conversation(events),
      [
        {
          type: "user",
          text: '根据图纸建模\n{"source":"page-1/text/7"}',
          displayText: "根据图纸建模",
        },
        update("agent_thought_chunk", {
          content: { type: "text", text: "读取图纸。" },
        }),
        update("tool_call", {
          toolCallId: "draw",
          title: "mcp__gongke__project_read_drawing_b5d6e9ebda25",
          status: "completed",
        }),
        update("agent_thought_chunk", {
          content: { type: "text", text: "绘制轮廓。" },
        }),
        update("tool_call", {
          toolCallId: "sketch",
          title: "mcp__gongke__host_sketch_b5d6e9ebda25",
          status: "completed",
          rawInput: { name: "轮廓" },
        }),
        update("tool_call", {
          toolCallId: "check",
          title: "mcp__gongke__host_check_b5d6e9ebda25",
          status: "failed",
          rawOutput: { error: "验收夹具：尺寸不符" },
        }),
      ],
    );
    const log = page.getByRole("log");
    await log.getByText("读取图纸", { exact: true }).waitFor();
    assert.equal(await log.locator(".agent-thought").count(), 1);
    assert.equal(await log.locator(".message .agent-raw[open]").count(), 0);
    assert.doesNotMatch(await log.innerText(), /page-1|mcp__|b5d6/);
    assert.match(await log.innerText(), /失败/);
    await log.getByText("图纸参考原文", { exact: true }).click();
    assert.match(await log.innerText(), /page-1\/text\/7/);
    await log.getByText("图纸参考原文", { exact: true }).click();
    await page.screenshot({ path: path.join(out, "fixture-not-film.png") });
    fs.writeFileSync(
      path.join(out, "result.json"),
      JSON.stringify(
        { ok: true, source: "确定性 UI 验收夹具，禁止用于成片" },
        null,
        2,
      ),
    );
  } finally {
    await app.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
