// 隔离的生产 Electron + Python 服务。仅原生选择框固定到临时测试文件，不连接 Agent。
const { electron } = require("./helpers/owned-electron.cjs");
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
(async () => {
  const output = path.resolve(process.argv[2] || "../out/ide-workbench/live");
  fs.mkdirSync(output, { recursive: true });
  const project = path.join(output, "project"),
    input = path.join(output, "layout-reference.svg");
  fs.mkdirSync(project, { recursive: true });
  fs.writeFileSync(
    input,
    '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="620"><rect width="900" height="620" fill="white"/><g fill="none" stroke="#333" stroke-width="2"><rect x="30" y="30" width="840" height="560"/><path d="M160 440 V180 H260 V340 H610 V440 Z"/><circle cx="210" cy="240" r="26"/><circle cx="420" cy="390" r="20"/></g><text x="70" y="80" font-family="sans-serif" font-size="20">Layout verification - imported SVG</text></svg>',
  );
  const env = {
    ...process.env,
    GONGKE_DESKTOP_USER_DATA: path.join(output, "user"),
    GONGKE_TRIAL_BACKGROUND: "1",
  };
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.PYTHONPATH;
  delete env.PYTHONHOME;
  const app = await electron.launch({
    args: [path.resolve(__dirname, "..")],
    env,
    timeout: 60000,
  });
  const errors = [];
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(20000);
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.getByText("就绪", { exact: true }).waitFor();
    await app.evaluate(({ dialog }, p) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [p] });
    }, project);
    await page.getByRole("button", { name: "工程操作", exact: true }).click();
    await page.getByRole("menuitem", { name: "新建工程", exact: true }).click();
    await page.getByRole("heading", { name: "project", exact: true }).waitFor();
    await app.evaluate(({ dialog }, p) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [p] });
    }, input);
    await page.getByRole("button", { name: "导入图纸", exact: true }).click();
    await page.waitForFunction(
      () => document.querySelector("img.drawing")?.naturalWidth > 0,
    );
    assert.ok(fs.existsSync(path.join(project, "gongke-project.json")));
    for (const width of [1366, 1920])
      for (const dark of [false, true]) {
        await app.evaluate(
          ({ BrowserWindow }, s) =>
            BrowserWindow.getAllWindows()[0].setContentSize(s.width, s.height),
          { width, height: width === 1366 ? 768 : 1080 },
        );
        const theme = await page
          .locator(".workbench")
          .getAttribute("data-theme");
        if (theme !== (dark ? "dark" : "light"))
          await page
            .getByRole("button", {
              name: dark ? "切换深色主题" : "切换浅色主题",
              exact: true,
            })
            .click();
        await page.getByRole("button", { name: "适应", exact: true }).click();
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({
          path: path.join(output, `${width}-${dark ? "dark" : "light"}.png`),
          scale: "css",
        });
      }
    const modifier = process.platform === "darwin" ? "Meta" : "Control";
    await page.keyboard.press(`${modifier}+p`);
    await page.getByRole("combobox", { name: "搜索工程文件" }).waitFor();
    await page.keyboard.press("Escape");
    await page.keyboard.press(`${modifier}+w`);
    await page.getByRole("tab", { name: "开始", exact: true }).waitFor();
    const current = await page.evaluate(() =>
      window.gongke.request("project.current"),
    );
    const agent = await page.evaluate(() => window.gongke.agent.state());
    assert.equal(agent.phase, "disconnected");
    assert.equal(current.path, project);
    assert.ok(current.files.some((f) => f.name === "layout-reference.svg"));
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(output, "checks.json"),
      JSON.stringify(
        {
          ok: true,
          project: current,
          agentPhase: agent.phase,
          errors,
          boundary:
            "生产 Electron + 实际 Python 服务 + 实际导入 SVG；选择框指定测试路径；未连接 Agent、未写原生 CAD",
        },
        null,
        2,
      ),
    );
    console.log(JSON.stringify({ ok: true, output }));
  } finally {
    await app.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
