const { showProjectTree } = require("./helpers/workspace.cjs");
// 真实 Electron/Python/文件；Agent 协议和窗口联调见 acp-flow.cjs。
const { electron } = require("./helpers/owned-electron.cjs");
const fs = require("node:fs"),
  path = require("node:path");
const assert = require("node:assert/strict");
const output = path.resolve(
  __dirname,
  "../../out/workflow-validation",
  Date.now().toString(),
);
fs.mkdirSync(output, { recursive: true });
const project = path.join(output, "我的课程工程"),
  other = path.join(output, "另一个工程");
fs.mkdirSync(project);
fs.mkdirSync(other);
let app, page;
async function launch() {
  const env = {
    ...process.env,
    GONGKE_DESKTOP_USER_DATA: path.join(output, "user"),
  };
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.PYTHONHOME;
  delete env.PYTHONPATH;
  app = await electron.launch({
    ...(process.env.GONGKE_TEST_EXECUTABLE
      ? { executablePath: process.env.GONGKE_TEST_EXECUTABLE, args: [] }
      : { args: [path.resolve(__dirname, "..")] }),
    cwd: output,
    env,
  });
  page = await app.firstWindow();
  page.setDefaultTimeout(15000);
  await page.getByText("就绪", { exact: true }).waitFor();
}
async function choose(target, create, fromProject = false) {
  await app.evaluate(({ dialog }, value) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [value],
    });
  }, target);
  const name = create ? "新建工程" : "打开工程";
  if (fromProject) {
    await showProjectTree(page);
    await page
      .getByLabel("工程树", { exact: true })
      .getByRole("button", { name: "工程操作", exact: true })
      .click();
    await page.getByRole("menuitem", { name, exact: true }).click();
  } else {
    await page
      .locator(".start-page")
      .getByRole("button", { name, exact: true })
      .click();
  }
  await page.locator("footer").getByTitle(target, { exact: true }).waitFor();
}
async function until(read, timeout = 240000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await read()) return;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("workflow condition timed out");
}
async function settled(kind) {
  await until(async () => {
    const tasks = await page.evaluate(() => window.gongke.request("task.list"));
    const finished = tasks.find(
      (t) => t.kind === kind && !["queued", "running"].includes(t.status),
    );
    if (finished)
      assert.equal(finished.status, "complete", JSON.stringify(finished));
    return (
      !!finished && !tasks.some((t) => ["queued", "running"].includes(t.status))
    );
  });
}
(async () => {
  try {
    await launch();
    await choose(project, true);
    await showProjectTree(page);
    await page
      .getByLabel("工程树", { exact: true })
      .getByText("减速器课程设计", { exact: true })
      .click();
    assert.equal(await page.getByLabel("工作拉力 / N").inputValue(), "");
    await page.getByLabel("工作拉力 / N").fill("2500");
    await page.getByLabel("带速 / m·s⁻¹").fill("1.4");
    await page.getByLabel("卷筒直径 / mm").fill("400");
    await page.getByRole("button", { name: "计算方案", exact: true }).click();
    await page
      .getByRole("button", { name: /^电动机与传动比/ })
      .filter({ hasText: "Y132S-4" })
      .waitFor();
    assert.equal(
      (await page.evaluate(() => window.gongke.request("project.current")))
        .teaching,
      false,
    );
    await page.screenshot({ path: path.join(output, "task.png") });
    await page
      .getByRole("button", { name: "生成模型、图纸与说明书", exact: true })
      .click();
    await settled("generation");
    await page
      .getByRole("button", { name: /^图纸/ })
      .filter({ hasText: "9 张" })
      .waitFor();
    const original = await page.evaluate(() =>
      window.gongke.request("project.current"),
    );
    assert.ok(
      fs.existsSync(path.join(project, original.delivery.path, "report.docx")),
    );
    assert.ok(
      fs.existsSync(
        path.join(project, original.delivery.path, "reducer_assembly.step"),
      ),
    );
    await page.getByLabel("工作拉力 / N").fill("2600");
    await page.getByRole("button", { name: "计算方案", exact: true }).click();
    await page
      .getByRole("button", { name: /^图纸/ })
      .filter({ hasText: "旧成果已过期" })
      .waitFor();
    await page.getByRole("button", { name: /^图纸/ }).click();
    await page.getByRole("heading", { name: /已过期/ }).waitFor();
    await page.screenshot({ path: path.join(output, "stale-revision.png") });
    await app.close();
    app = null;
    await launch();
    await choose(project, false);
    const reopened = await page.evaluate(() =>
      window.gongke.request("project.current"),
    );
    assert.equal(reopened.task.conveyor.belt_pull_N, 2600);
    assert.equal(reopened.delivery, null);
    await choose(other, true, true);
    const isolated = await page.evaluate(() =>
      window.gongke.request("project.current"),
    );
    assert.equal(isolated.task, null);
    fs.writeFileSync(
      path.join(output, "result.json"),
      JSON.stringify(
        {
          ok: true,
          output,
          packaged: !!process.env.GONGKE_TEST_EXECUTABLE,
          checks: [
            "blank_task_entry",
            "real_calculation",
            "step_drawings_docx",
            "old_outputs_stale",
            "project_isolation",
          ],
        },
        null,
        2,
      ),
    );
    console.log(JSON.stringify({ ok: true, output }));
  } catch (error) {
    if (page)
      await page
        .screenshot({ path: path.join(output, "failure.png") })
        .catch(() => {});
    fs.writeFileSync(
      path.join(output, "failure.json"),
      JSON.stringify({ error: String(error), stack: error.stack }, null, 2),
    );
    throw error;
  } finally {
    if (app) await app.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
