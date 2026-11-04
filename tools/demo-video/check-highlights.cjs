// 真实错误模型的产品端验收；只复制原模型，不修改它。
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict"),
  { spawn } = require("node:child_process");
const { electron } = require("../../desktop/tests/helpers/owned-electron.cjs");
const root = path.resolve(__dirname, "../.."),
  out = path.resolve(process.argv[2]),
  manifest = JSON.parse(fs.readFileSync(process.argv[3])),
  entry = manifest.find((x) => x.name === "demo-bad"),
  pause = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  assert(!fs.existsSync(out));
  fs.mkdirSync(path.join(out, "host"), { recursive: true });
  fs.mkdirSync(path.join(out, "project"));
  fs.copyFileSync(entry.model, path.join(out, "project/robot4.FCStd"));
  fs.copyFileSync(
    path.join(entry.project, entry.drawing.path),
    path.join(out, "project/drawing.pdf"),
  );
  const env = {
    ...process.env,
    GONGKE_MODELING_ROOT: root,
    GONGKE_FREECAD_SESSION: path.join(out, "host/session.json"),
    GONGKE_CHECK_MODEL: path.join(out, "project/robot4.FCStd"),
    GONGKE_TRIAL_BACKGROUND: "1",
    GONGKE_DESKTOP_USER_DATA: path.join(out, "user"),
    GONGKE_PYTHON: "/private/tmp/gongke-modeling-venv/bin/python",
  };
  delete env.ELECTRON_RUN_AS_NODE;
  const log = fs.openSync(path.join(out, "host.log"), "w");
  const cad = spawn(
    "/Applications/FreeCAD.app/Contents/Resources/bin/freecad",
    [
      "--user-cfg",
      path.join(out, "host/user.cfg"),
      path.join(__dirname, "check-host.FCMacro"),
    ],
    { env, stdio: ["ignore", log, log] },
  );
  fs.closeSync(log);
  let app;
  try {
    for (
      let i = 0;
      i < 150 && !fs.existsSync(path.join(out, "host/opened.json"));
      i++
    )
      await pause(200);
    assert(fs.existsSync(env.GONGKE_FREECAD_SESSION));
    app = await electron.launch({ args: [path.join(root, "desktop")], env });
    const page = await app.firstWindow();
    page.setDefaultTimeout(20000);
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setContentSize(1920, 1080),
    );
    await page.getByText("就绪", { exact: true }).waitFor();
    await page.evaluate(
      (p) =>
        window.gongke.request("project.create", {
          path: p,
          name: "机器人零件核对",
        }),
      path.join(out, "project"),
    );
    await page.reload();
    await page.getByText("原生 CAD", { exact: true }).click();
    await page
      .getByRole("button", { name: "连接 FreeCAD", exact: true })
      .click();
    await new Promise((resolve, reject) => {
      const child = spawn(
        env.GONGKE_PYTHON,
        [path.join(__dirname, "check-model.py"), out, process.argv[3]],
        { cwd: root, env, stdio: "inherit" },
      );
      child.on("exit", (code) =>
        code === 0 ? resolve() : reject(Error("核验进程失败")),
      );
    });
    await page
      .getByRole("button", { name: "Agent 连接设置", exact: true })
      .click();
    await page
      .getByRole("menuitem", { name: "使用已配置的 Agent", exact: true })
      .click();
    const report = JSON.parse(fs.readFileSync(path.join(out, "report.json")));
    assert.equal(report.status, "fail");
    await page
      .getByRole("button", { name: "读取 FreeCAD 工程", exact: true })
      .click();
    await page
      .locator('.check-drawing .pdf-document[data-render-state="ready"]')
      .waitFor();
    assert.equal(await page.locator("[data-drawing-item]").count(), 2);
    await page.screenshot({ path: path.join(out, "both.png") });
    for (let i = 1; i <= 2; i++) {
      await page
        .getByRole("button", { name: `差异 ${i}`, exact: true })
        .click();
      assert.equal(await page.locator("[data-drawing-item]").count(), 1);
      assert.equal(
        await page
          .locator("[data-drawing-item]")
          .getAttribute("data-drawing-item"),
        report.checks[0].drawing_view.segments[i - 1].item,
      );
      await pause(400);
      await page.screenshot({ path: path.join(out, `difference-${i}.png`) });
    }
    await page.getByRole("button", { name: "全部差异", exact: true }).click();
    assert.equal(await page.locator("[data-drawing-item]").count(), 2);
    // 缩放后仍以 PDF 原始坐标对齐；真实 canvas/SVG 尺寸一致。
    await page
      .locator(".check-drawing")
      .getByRole("button", { name: "放大 PDF", exact: true })
      .click();
    await pause(700);
    const size = await page.locator(".pdf-sheet").evaluate((e) => {
      const c = e.querySelector("canvas").getBoundingClientRect(),
        s = e.querySelector("svg").getBoundingClientRect();
      return [c.width, c.height, s.width, s.height];
    });
    assert(Math.abs(size[0] - size[2]) < 1 && Math.abs(size[1] - size[3]) < 1);
    // 已核验图纸被换内容后，不能将旧高亮画在新文件上。
    fs.appendFileSync(
      path.join(out, "project/drawing.pdf"),
      "\n% highlight-test-changed-copy\n",
    );
    await page.reload();
    await page.getByText("原生 CAD", { exact: true }).click();
    await page.getByRole("alert").filter({ hasText: "图纸已改变" }).waitFor();
    assert.equal(await page.locator("[data-drawing-item]").count(), 0);
    fs.writeFileSync(
      path.join(out, "acceptance.json"),
      JSON.stringify(
        {
          ok: true,
          changedPdfRejected: true,
          segments: report.checks[0].drawing_view.segments.map((s) => s.item),
          zoomSize: size,
        },
        null,
        2,
      ),
    );
  } finally {
    try {
      if (app) await app.close();
    } finally {
      if (cad.exitCode === null) cad.kill("SIGTERM");
    }
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
