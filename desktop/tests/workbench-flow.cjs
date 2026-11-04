// 生产 renderer 的布局/键盘验收；沿用确定性服务样例，不调用真实 Agent。
const { electron } = require("./helpers/owned-electron.cjs");
const assert = require("node:assert/strict");
const fs = require("node:fs"),
  path = require("node:path"),
  os = require("node:os");
(async () => {
  const output = path.resolve(
    process.argv[2] || "../out/ide-workbench/interactions",
  );
  fs.mkdirSync(output, { recursive: true });
  const env = {
    ...process.env,
    GONGKE_VISUAL_USER_DATA: fs.mkdtempSync(
      path.join(os.tmpdir(), "ide-flow-"),
    ),
  };
  delete env.ELECTRON_RUN_AS_NODE;
  const app = await electron.launch({
    args: [path.join(__dirname, "fixtures/workbench-main.cjs")],
    env,
  });
  const results = [],
    errors = [];
  try {
    const page = await app.firstWindow();
    page.on("pageerror", (e) => errors.push(String(e)));
    page.setDefaultTimeout(15000);
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setContentSize(1366, 768),
    );
    await page
      .getByRole("heading", { name: "支架建模练习", exact: true })
      .waitFor();
    await page.evaluate(() => window.visualReview.setScenario("drawing-image"));
    const explorer = page.getByLabel("工程树", { exact: true });
    const group = page.locator('[data-editor-group="1"]');
    const treeFile = (name) => explorer.getByText(name, { exact: true });
    await treeFile("支架图纸.svg").click();
    await page.waitForFunction(
      () => document.querySelector("img.drawing")?.naturalWidth > 0,
    );
    await treeFile("支架图纸.pdf").click();
    assert.equal(
      await group
        .getByRole("tab", { name: "支架图纸.svg", exact: true })
        .count(),
      0,
    );
    await treeFile("支架图纸.pdf").dblclick();
    await treeFile("支架图纸.svg").click();
    assert.equal(
      await group
        .getByRole("tab", { name: "支架图纸.pdf", exact: true })
        .count(),
      1,
    );
    assert.equal(await group.locator(".document-tab.preview").count(), 1);
    results.push("单击替换预览，双击保留标签");
    await group
      .getByRole("tab", { name: "支架图纸.svg", exact: true })
      .dblclick();
    assert.equal(await group.locator(".document-tab.preview").count(), 0);
    await page.keyboard.press("Control+Tab");
    results.push("双击标签固定，Ctrl+Tab 切换");
    await page.keyboard.press("Control+p");
    await page
      .getByRole("combobox", { name: "搜索工程文件" })
      .fill("bracket.svg");
    await page.keyboard.press("Enter");
    await group
      .getByRole("tab", { name: "支架图纸.svg", exact: true })
      .waitFor();
    await page.keyboard.press("Control+Shift+p");
    await page.getByRole("combobox", { name: "搜索命令" }).fill("输出");
    await page.keyboard.press("Enter");
    await page.getByRole("tab", { name: "输出 / 日志", exact: true }).waitFor();
    results.push(
      "Quick Open 与 Command Palette 可搜索并执行，Enter 回到工作区",
    );
    await page.keyboard.press("Control+Shift+p");
    assert.equal(
      await page.locator(".workbench").count(),
      1,
      "Portal 不得复制整个工作台外壳",
    );
    await page.screenshot({
      path: path.join(output, "command-palette.png"),
      scale: "css",
      animations: "disabled",
    });
    await page.keyboard.press("Escape");
    await page.keyboard.press("Control+j");
    assert.equal(
      await page.getByLabel("底部面板", { exact: true }).isVisible(),
      false,
    );
    await page.keyboard.press("Control+b");
    assert.equal(await explorer.isVisible(), false);
    await page.keyboard.press("Control+b");
    assert.equal(await explorer.isVisible(), true);
    await page.getByLabel("工程任务", { exact: true }).fill("保留这个草稿");
    await page.keyboard.press("Control+Alt+b");
    assert.equal(await page.getByLabel("辅助侧栏").isVisible(), false);
    await page.keyboard.press("Control+Alt+b");
    assert.equal(
      await page.getByLabel("工程任务", { exact: true }).inputValue(),
      "保留这个草稿",
    );
    results.push("侧栏/Panel 快捷键与 Agent 折叠保留草稿");
    await treeFile("支架图纸.svg").click({ button: "right" });
    await page
      .getByRole("menuitem", { name: "在右侧打开", exact: true })
      .click();
    await page.locator('[data-editor-group="2"] img.drawing').waitFor();
    await page.waitForFunction(() =>
      Array.from(document.querySelectorAll("img.drawing")).every(
        (i) => i.naturalWidth > 0,
      ),
    );
    assert.equal(await page.locator("[data-editor-group]").count(), 2);
    for (const button of await page
      .getByRole("button", { name: "适应", exact: true })
      .all())
      await button.click();
    await page.screenshot({
      path: path.join(output, "split-editors.png"),
      scale: "css",
      animations: "disabled",
    });
    await page.keyboard.press("Control+2");
    await page.keyboard.press("Control+w");
    assert.equal(await page.locator("[data-editor-group]").count(), 1);
    results.push("文件右键在右侧打开，Ctrl+2 / Ctrl+W 关闭分屏");
    await page.evaluate(() => window.visualReview.setScenario("checks"));
    await page.keyboard.press("Control+Shift+m");
    await page
      .getByRole("button", { name: "定位 安装孔直径", exact: true })
      .waitFor();
    await page.getByRole("button", { name: "适应", exact: true }).click();
    await page.screenshot({
      path: path.join(output, "problems-panel.png"),
      scale: "css",
      animations: "disabled",
    });
    await page
      .getByRole("button", { name: "定位 安装孔直径", exact: true })
      .click();
    await page.waitForFunction(
      () => window.visualReview.selections().length === 1,
    );
    assert.deepEqual(
      await page.evaluate(() => window.visualReview.selections()[0]),
      {
        session_id: "fixture-session",
        object_name: "Hole002",
        expected_revision: 4,
      },
    );
    results.push("问题定位沿用文档身份/修订检查");
    await page.getByRole("separator", { name: "底部面板高度" }).focus();
    await page.keyboard.press("ArrowUp");
    assert.equal(
      await page
        .getByRole("separator", { name: "底部面板高度" })
        .getAttribute("aria-valuenow"),
      "256",
    );
    await page.getByRole("separator", { name: "Agent 面板宽度" }).focus();
    await page.keyboard.press("ArrowLeft");
    assert.equal(
      await page
        .getByRole("separator", { name: "Agent 面板宽度" })
        .getAttribute("aria-valuenow"),
      "368",
    );
    results.push("横向/纵向分隔条键盘调整");
    await page.getByRole("button", { name: "对话历史", exact: true }).click();
    await page.getByRole("dialog").waitFor();
    assert.match(await page.getByRole("dialog").textContent(), /尚不支持/);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "新会话", exact: true }).click();
    results.push("历史入口说明实际能力，新会话使用既有 handler");
    assert.deepEqual(errors, []);
    assert.equal(
      await page.locator("body").evaluate((e) => e.scrollWidth > e.clientWidth),
      false,
    );
    fs.writeFileSync(
      path.join(output, "checks.json"),
      JSON.stringify(
        {
          ok: true,
          results,
          errors,
          boundary:
            "真实 Electron，确定性服务/CAD 样例；非原生宿主或付费 Agent 验收",
        },
        null,
        2,
      ),
    );
    console.log(JSON.stringify({ ok: true, results, output }, null, 2));
  } catch (e) {
    fs.writeFileSync(
      path.join(output, "failure.json"),
      JSON.stringify({ error: String(e), results, errors }, null, 2),
    );
    throw e;
  } finally {
    await app.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
