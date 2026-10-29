// 真实 Electron + Python 服务，选择目录通过原生 dialog 替身，工程动作不模拟。
const { _electron: electron } = require("playwright");
const { mkdirSync, writeFileSync } = require("node:fs");
const { resolve, join } = require("node:path");
const assert = require("node:assert/strict");
(async () => {
  const output = resolve(
    __dirname,
    "../../out/desktop-validation",
    Date.now().toString(),
  );
  mkdirSync(output, { recursive: true });
  const project = join(output, "传动设计"),
    userdata = join(output, "user");
  mkdirSync(project);
  const packaged = process.env.GONGKE_TEST_EXECUTABLE;
  const env = { ...process.env, GONGKE_DESKTOP_USER_DATA: userdata };
  delete env.PYTHONPATH;
  delete env.PYTHONHOME;
  const app = await electron.launch({
    ...(packaged
      ? { executablePath: packaged, args: [] }
      : { args: [resolve(__dirname, "..")] }),
    cwd: output,
    env,
    timeout: 60000,
  });
  try {
    const page = await app.firstWindow();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page
      .getByText("工程服务运行中", { exact: true })
      .waitFor({ timeout: 30000 });
    await app.evaluate(({ dialog }, path) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [path],
      });
    }, project);
    await page.getByRole("button", { name: "新建工程", exact: true }).click();
    await page.locator("footer").getByText(project, { exact: true }).waitFor();
    await page.getByRole("button", { name: "∑ 设计计算" }).click();
    await page.getByRole("button", { name: "载入教学条件" }).click();
    await page.getByLabel("工作拉力 / N").waitFor();
    assert.equal(await page.getByLabel("工作拉力 / N").inputValue(), "2500");
    await page.getByRole("button", { name: "计算方案", exact: true }).click();
    await page.getByText("Y132S-4", { exact: true }).waitFor();
    await page.screenshot({ path: join(output, "desktop-calculation.png") });
    await page.getByRole("button", { name: "生成模型与图纸" }).click();
    await page.getByRole("button", { name: /☷任务|☷ 任务/ }).click();
    await page.locator(".task-status.complete").waitFor({ timeout: 240000 });
    const manifest = JSON.parse(
      require("node:fs").readFileSync(join(project, "gongke-project.json")),
    );
    assert.equal(manifest.results.length, 1);
    assert.equal(manifest.results[0].exports_complete, true);
    const svg = page
      .locator(".files button")
      .filter({ hasText: ".svg" })
      .first();
    await svg.waitFor();
    await svg.click();
    await page.locator("img.drawing").waitFor();
    await page.screenshot({ path: join(output, "desktop-drawing.png") });
    await page.getByLabel("工程任务").fill("读取当前工程");
    await page.getByRole("button", { name: "发送 ↑" }).click();
    await page
      .getByRole("alert")
      .filter({ hasText: "未连接模型服务" })
      .waitFor();
    assert.deepEqual(errors, []);
    const status = await page.evaluate(() =>
      window.gongke.request("system.status"),
    );
    if (packaged) assert.equal(status.packaged, true);
    writeFileSync(
      join(output, "result.json"),
      JSON.stringify(
        {
          ok: true,
          project,
          manifest,
          packaged: status.packaged,
          renderer_errors: errors,
          provider: "not_configured; refusal verified",
        },
        null,
        2,
      ),
    );
    console.log(JSON.stringify({ ok: true, output }));
  } catch (error) {
    writeFileSync(
      join(output, "failure.json"),
      JSON.stringify(
        { ok: false, error: String(error), packaged: !!packaged },
        null,
        2,
      ),
    );
    const page = app.windows()[0];
    if (page)
      await page
        .screenshot({ path: join(output, "desktop-failure.png") })
        .catch(() => {});
    throw error;
  } finally {
    await app.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
