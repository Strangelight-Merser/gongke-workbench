// npm run build && node tests/agent-visual-review.cjs <输出目录> before|after
const { electron } = require("./helpers/owned-electron.cjs");
const { conversation } = require("./fixtures/long-conversation.cjs");
const fs = require("node:fs"),
  path = require("node:path"),
  os = require("node:os"),
  assert = require("node:assert/strict");
const output = path.resolve(process.argv[2]),
  phase = process.argv[3] || "after";
fs.mkdirSync(output, { recursive: true });
(async () => {
  const evidence = [];
  for (const size of [
    { width: 1366, height: 768 },
    { width: 1920, height: 1080 },
  ])
    for (const dark of [false, true]) {
      const env = {
        ...process.env,
        GONGKE_VISUAL_USER_DATA: fs.mkdtempSync(
          path.join(os.tmpdir(), "agent-review-"),
        ),
      };
      delete env.ELECTRON_RUN_AS_NODE;
      const app = await electron.launch({
        args: [path.join(__dirname, "fixtures/workbench-main.cjs")],
        env,
      });
      try {
        const page = await app.firstWindow(),
          errors = [];
        page.on("pageerror", (e) => errors.push(String(e)));
        await app.evaluate(
          ({ BrowserWindow }, s) =>
            BrowserWindow.getAllWindows()[0].setContentSize(s.width, s.height),
          size,
        );
        if (dark)
          await page
            .getByRole("button", { name: "切换深色主题", exact: true })
            .click();
        const theme = dark ? "dark" : "light";
        // macOS 会把原生窗口限在显示器可用高度；显式固定 renderer 视口。
        await page.setViewportSize(size);
        assert.deepEqual(
          await page.evaluate(() => ({
            width: innerWidth,
            height: innerHeight,
          })),
          size,
        );
        await page
          .getByRole("heading", { name: "支架建模练习", exact: true })
          .waitFor();
        await page.evaluate(() =>
          window.visualReview.setScenario("drawing-pdf"),
        );
        await page
          .getByRole("button", { name: "Agent 连接设置", exact: true })
          .click();
        await page
          .getByRole("menuitem", { name: "使用已配置的 Agent", exact: true })
          .click();
        await page.evaluate(
          (events) => window.visualReview.conversation(events),
          conversation(),
        );
        await page
          .getByLabel("工程树", { exact: true })
          .getByText("支架图纸.pdf", { exact: true })
          .click();
        await page
          .locator('.pdf-document[data-render-state="ready"]')
          .waitFor();
        await page
          .locator(".agent-tool")
          .first()
          .waitFor({ state: "attached" });
        const tool = page.locator(".agent-tool").first();
        if (phase === "after")
          await page.locator(".agent-tool-group > summary").first().click();
        await tool.locator(":scope > summary").click();
        await tool.scrollIntoViewIfNeeded();
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({
          scale: "css",
          path: path.join(
            output,
            phase + "-" + size.width + "x" + size.height + "-" + theme + ".png",
          ),
        });
        if (phase === "after") {
          assert.equal(await page.locator(".agent-tool").count(), 36);
          assert.match(
            await tool.locator(".tool-details > p").first().textContent(),
            /特征：底板拉伸/,
          );
          const second = page.locator(".agent-tool").nth(1);
          await second.locator(":scope > summary").click();
          assert.match(
            await second.locator(".tool-details > p").first().textContent(),
            /贯穿切孔 φ14 mm/,
          );
          await second.locator(":scope > summary").click();
          const heading = page.locator(".agent-panel > .panel-heading");
          for (const name of ["新会话", "对话历史", "Agent 连接设置"]) {
            const button = heading.getByRole("button", { name, exact: true });
            assert.equal(await button.count(), 1);
            const rect = await button.boundingBox(),
              parent = await heading.boundingBox();
            assert.ok(
              rect.y >= parent.y &&
                rect.y + rect.height <= parent.y + parent.height,
            );
          }
          await heading
            .getByRole("button", { name: "对话历史", exact: true })
            .click();
          assert.match(
            await page.getByRole("dialog").textContent(),
            /尚不支持列出和恢复/,
          );
          await page.keyboard.press("Escape");
          assert.ok(await tool.locator(".agent-raw:not([open])").count());
          const body = await tool.boundingBox();
          assert.ok(body.height < 300);
          const fonts = await page.evaluate(() => ({
            body: parseFloat(
              getComputedStyle(document.querySelector(".message")).fontSize,
            ),
            tool: parseFloat(
              getComputedStyle(document.querySelector(".agent-tool")).fontSize,
            ),
          }));
          assert.ok(fonts.tool < fonts.body);
          await tool.locator(".agent-raw > summary").click();
          const raw = tool.locator(".agent-raw pre");
          assert.ok(
            await raw.evaluate(
              (e) => e.scrollHeight > e.clientHeight && e.clientHeight <= 200,
            ),
          );
          await tool.locator(".agent-raw > summary").click();
          await page.locator(".agent-tool-group > summary").first().click();
          await page
            .locator('.agent-tool[data-state="failed"]')
            .last()
            .locator(":scope > summary")
            .click();
          await page
            .locator(".agent-tool-group")
            .first()
            .scrollIntoViewIfNeeded();
          await page.screenshot({
            scale: "css",
            path: path.join(
              output,
              "overview-" +
                size.width +
                "x" +
                size.height +
                "-" +
                theme +
                ".png",
            ),
          });
          await page
            .getByRole("button", { name: "允许一次", exact: true })
            .click();
          assert.equal(await page.locator(".agent-permission").count(), 0);
          const updated = conversation().filter((e) => e.type !== "permission");
          updated.push({
            type: "update",
            update: {
              sessionUpdate: "tool_call_update",
              toolCallId: "save",
              status: "in_progress",
            },
          });
          await page.evaluate(
            (events) => window.visualReview.conversation(events),
            updated,
          );
          await page.locator('.agent-tool[data-state="in_progress"]').waitFor();
          updated.push({
            type: "update",
            update: {
              sessionUpdate: "tool_call_update",
              toolCallId: "save",
              status: "completed",
              rawOutput: { message: "已保存工作副本" },
            },
          });
          await page.evaluate(
            (events) => window.visualReview.conversation(events),
            updated,
          );
          await page
            .locator('.agent-tool[data-state="in_progress"]')
            .waitFor({ state: "detached" });
          assert.equal(await page.locator(".agent-tool").count(), 36);
          assert.equal(
            await page.locator(".agent-tool[data-state=failed]").count(),
            2,
          );
          assert.equal(
            await page
              .locator("body")
              .evaluate((e) => e.scrollWidth > e.clientWidth),
            false,
          );
        }
        assert.deepEqual(errors, []);
        evidence.push({
          ...size,
          phase,
          theme,
          toolCalls: 36,
          errors,
          status: "passed",
        });
      } finally {
        await app.close();
      }
    }
  fs.writeFileSync(
    path.join(output, phase + "-evidence.json"),
    JSON.stringify(evidence, null, 2),
  );
  console.log(JSON.stringify(evidence));
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
