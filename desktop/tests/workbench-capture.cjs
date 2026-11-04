// 真实 Electron renderer + 已有确定性服务样例；不启动模型、不调用付费服务。
const { electron } = require("./helpers/owned-electron.cjs");
const fs = require("node:fs"),
  path = require("node:path"),
  os = require("node:os");
(async () => {
  const output = path.resolve(process.argv[2]);
  fs.mkdirSync(output, { recursive: true });
  const env = {
    ...process.env,
    GONGKE_VISUAL_USER_DATA: fs.mkdtempSync(
      path.join(os.tmpdir(), "workbench-"),
    ),
  };
  delete env.ELECTRON_RUN_AS_NODE;
  const app = await electron.launch({
    args: [path.join(__dirname, "fixtures/workbench-main.cjs")],
    env,
  });
  try {
    const page = await app.firstWindow();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    for (const width of [1366, 1920])
      for (const dark of [false, true]) {
        await app.evaluate(
          ({ BrowserWindow }, s) =>
            BrowserWindow.getAllWindows()[0].setContentSize(s.width, s.height),
          { width, height: width === 1366 ? 768 : 1080 },
        );
        await page.evaluate(
          (dark) =>
            localStorage.setItem(
              "gongke.layout",
              JSON.stringify({
                tree: 232,
                agent: 352,
                treeOpen: true,
                agentOpen: true,
                dark,
              }),
            ),
          dark,
        );
        await page.reload();
        await page
          .getByRole("heading", { name: "支架建模练习", exact: true })
          .waitFor();
        await page.evaluate(() =>
          window.visualReview.setScenario("drawing-image"),
        );
        await page
          .getByLabel("工程树", { exact: true })
          .getByText("支架图纸.svg", { exact: true })
          .click();
        await page.waitForFunction(
          () => document.querySelector("img.drawing")?.naturalWidth > 0,
        );
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({
          path: path.join(output, `${width}-${dark ? "dark" : "light"}.png`),
          scale: "css",
        });
      }
    fs.writeFileSync(
      path.join(output, "errors.json"),
      JSON.stringify(errors, null, 2),
    );
  } finally {
    await app.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
