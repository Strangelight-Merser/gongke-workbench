// 全新宿主 + 原工程 MCP 参数重执行。记录真实模型变化，不使用 ACP 回放或结果注入。
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict"),
  { spawn } = require("node:child_process");
const { electron } = require("../../desktop/tests/helpers/owned-electron.cjs");
const { startRecording } = require("./recorder.cjs");
const root = path.resolve(__dirname, "../.."),
  out = path.resolve(process.argv[2]),
  pause = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  assert(!fs.existsSync(out));
  fs.mkdirSync(path.join(out, "host"), { recursive: true });
  const env = {
    ...process.env,
    GONGKE_MODELING_ROOT: root,
    GONGKE_FREECAD_SESSION: path.join(out, "host/session.json"),
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
      path.join(root, "tests/e2e/native_modeling_host.FCMacro"),
    ],
    { env, stdio: ["ignore", log, log] },
  );
  fs.closeSync(log);
  let app, rec;
  try {
    for (let i = 0; i < 150 && !fs.existsSync(env.GONGKE_FREECAD_SESSION); i++)
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
          name: "机器人零件",
        }),
      path.join(out, "project"),
    );
    const input = path.join(out, "project/inputs/f00b1b9d-e9b");
    fs.mkdirSync(input, { recursive: true });
    fs.copyFileSync(
      path.join(root, "out/demo-video/paid-robot4/inputs/robot4.pdf"),
      path.join(input, "robot4.pdf"),
    );
    await page.reload();
    await page.getByText("原生 CAD", { exact: true }).click();
    await page
      .getByRole("button", { name: "连接 FreeCAD", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Agent 连接设置", exact: true })
      .click();
    await page
      .getByRole("menuitem", { name: "使用已配置的 Agent", exact: true })
      .click();
    const run = async (i) =>
      new Promise((resolve, reject) => {
        const child = spawn(
          env.GONGKE_PYTHON,
          [path.join(__dirname, "reexecute_session.py"), out, String(i)],
          { cwd: root, env },
        );
        let logs = "";
        child.stdout.on("data", (b) => (logs += b));
        child.stderr.on("data", (b) => (logs += b));
        child.on("exit", (code) => {
          fs.writeFileSync(path.join(out, `step-${i}.log`), logs);
          code === 0 ? resolve() : reject(Error(logs));
        });
      });
    for (let i = 0; i < 4; i++) await run(i);
    rec = await startRecording(page, out, { width: 3840, height: 2160 });
    rec.mark("empty");
    await pause(2500);
    for (let i = 4; i < 10; i++) {
      rec.mark("start-" + i);
      await run(i);
      rec.mark("end-" + i);
      for (const group of await page
        .locator("details.agent-tool-group:not([open]) > summary")
        .all())
        await group.click();
      if (i === 4)
        await page
          .getByRole("button", { name: "读取 FreeCAD 工程", exact: true })
          .click();
      if (i === 5)
        await page
          .getByRole("button", { name: "Profile · 草图", exact: true })
          .click();
      if (i === 6)
        await page.getByRole("button", { name: "Plate", exact: true }).click();
      if (i === 5 || i === 6) {
        await pause(600);
        await page.mouse.move(800, 600, { steps: 30 });
        await page.mouse.wheel(0, -460);
        await pause(800);
      }
      await pause(3500);
      await page.screenshot({ path: path.join(out, `stage-${i}.png`) });
    }
    rec.mark("orbit");
    await page.mouse.move(700, 580);
    await page.mouse.down();
    await page.mouse.move(860, 620, { steps: 90 });
    await page.mouse.up();
    await pause(4500);
    fs.writeFileSync(
      path.join(out, "body.txt"),
      await page.locator("body").innerText(),
    );
  } finally {
    try {
      if (rec) await rec.stop();
    } finally {
      try {
        if (app) await app.close();
      } finally {
        if (cad.exitCode === null) cad.kill("SIGTERM");
      }
    }
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
