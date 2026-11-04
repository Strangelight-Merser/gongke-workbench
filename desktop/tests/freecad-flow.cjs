// 已打开隔离 FreeCAD 教学轴和关联 TechDraw 页；通过真实桌面控件修订。
const { electron } = require("./helpers/owned-electron.cjs");
const fs = require("node:fs"),
  path = require("node:path"),
  crypto = require("node:crypto"),
  assert = require("node:assert/strict");
if (!process.env.GONGKE_FREECAD_SESSION)
  throw new Error("请指定隔离宿主的 GONGKE_FREECAD_SESSION");
const out = path.resolve(
  __dirname,
  "../../out/freecad-app-validation",
  Date.now().toString(),
);
fs.mkdirSync(out, { recursive: true });
const hash = (file) =>
  crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
(async () => {
  const env = {
    ...process.env,
    GONGKE_DESKTOP_USER_DATA: path.join(out, "user"),
  };
  delete env.ELECTRON_RUN_AS_NODE;
  const app = await electron.launch({
    ...(env.GONGKE_TEST_EXECUTABLE
      ? { executablePath: env.GONGKE_TEST_EXECUTABLE, args: [] }
      : { args: [path.resolve(__dirname, "..")] }),
    cwd: out,
    env,
  });
  let page;
  try {
    page = await app.firstWindow();
    page.setDefaultTimeout(20000);
    await page.getByText("就绪", { exact: true }).waitFor();
    const project = path.join(out, "原生轴修订");
    fs.mkdirSync(project);
    await app.evaluate(({ dialog }, p) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [p] });
    }, project);
    await page.getByRole("button", { name: "工程操作", exact: true }).click();
    await page.getByRole("menuitem", { name: "新建工程", exact: true }).click();
    await page.locator("footer").getByTitle(project, { exact: true }).waitFor();
    await page
      .getByLabel("工程树", { exact: true })
      .getByText("原生 CAD", { exact: true })
      .click();
    if (
      await page
        .getByRole("button", { name: "工程检查", exact: true })
        .isVisible()
    )
      await page.getByRole("button", { name: "工程检查", exact: true }).click();
    await page
      .getByRole("button", { name: "读取 FreeCAD 工程", exact: true })
      .click();
    await page.getByLabel("目标直径", { exact: true }).waitFor();
    const original = await page.evaluate(() =>
      window.gongke.request("freecad.context"),
    );
    const originalHash = hash(original.path);
    const source = await page.evaluate(
      (c) =>
        window.gongke.request("freecad.read", {
          session_id: c.session_id,
          entity_id: c.objects[0].entity_id,
        }),
      original,
    );
    const inputMm =
      source.snapshot.segments.find((s) => s.segment_id === "middle")
        .diameter_m * 1000;
    const targetMm = inputMm - 2;
    await page
      .getByRole("button", { name: "另存工作修订", exact: true })
      .click();
    await page.waitForFunction(
      (p) =>
        document
          .querySelector(".native-inspection > :not([hidden]) .native .toolbar")
          .textContent.includes(p),
      project,
    );
    await page.getByLabel("目标直径", { exact: true }).fill(String(targetMm));
    await page
      .getByRole("button", { name: "计算修改影响", exact: true })
      .click();
    await page.getByRole("button", { name: "应用修改", exact: true }).click();
    await page
      .locator(".property")
      .filter({ hasText: "middle" })
      .filter({ hasText: targetMm.toFixed(2) })
      .waitFor();
    await page.waitForFunction(
      () =>
        !document.querySelector(".statusbar").getAttribute("aria-busy") ||
        document.querySelector(".statusbar").getAttribute("aria-busy") ===
          "false",
    );
    await page
      .getByRole("button", { name: "校核当前模型", exact: true })
      .click();
    await page.getByRole("button", { name: "校核结果", exact: true }).waitFor();
    await page.screenshot({ path: path.join(out, "native-model.png") });
    const scene = await page.evaluate(() =>
      window.gongke.request("freecad.scene"),
    );
    await page
      .locator(".native-tabs")
      .getByRole("button", { name: scene.pages[0].label, exact: true })
      .click();
    await page.getByRole("button", { name: "更新图纸", exact: true }).click();
    await page.locator("img.drawing").waitFor();
    await page
      .getByRole("button", { name: "导出 DXF 修订", exact: true })
      .click();
    const deadline = Date.now() + 20000;
    let current;
    do {
      current = await page.evaluate(() =>
        window.gongke.request("project.current"),
      );
      if (current.files.some((f) => f.kind === "dxf")) break;
      await new Promise((r) => setTimeout(r, 100));
    } while (Date.now() < deadline);
    assert.ok(current.files.some((f) => f.kind === "dxf"));
    await page
      .locator(".project-pane [role=treeitem]:not([aria-expanded])")
      .filter({ hasText: /\.dxf/ })
      .first()
      .waitFor();
    await page
      .getByRole("button", { name: "另存工作修订", exact: true })
      .click();
    await page.waitForFunction(
      () =>
        !document.querySelector(".statusbar").getAttribute("aria-busy") ||
        document.querySelector(".statusbar").getAttribute("aria-busy") ===
          "false",
    );
    await page.screenshot({ path: path.join(out, "native-drawing.png") });
    assert.equal(hash(original.path), originalHash);
    const context = await page.evaluate(() =>
      window.gongke.request("freecad.context"),
    );
    const actual = await page.evaluate(
      (c) =>
        window.gongke.request("freecad.read", {
          session_id: c.session_id,
          entity_id: c.objects[0].entity_id,
        }),
      context,
    );
    assert.equal(
      actual.snapshot.segments.find((s) => s.segment_id === "middle")
        .diameter_m,
      targetMm / 1000,
    );
    fs.writeFileSync(
      path.join(out, "result.json"),
      JSON.stringify(
        {
          ok: true,
          packaged: !!env.GONGKE_TEST_EXECUTABLE,
          host: "real macOS FreeCAD",
          synthetic_fixture: true,
          checks: [
            "real_native_mesh",
            "save_working_copy",
            "diameter_edit_and_readback",
            "recalculate",
            "update_drawing",
            "native_dxf",
            "source_bytes_unchanged",
          ],
          input_diameter_mm: inputMm,
          output_diameter_mm: targetMm,
          original: original.path,
          original_sha256: originalHash,
          project,
          files: current.files,
        },
        null,
        2,
      ),
    );
    console.log(JSON.stringify({ ok: true, output: out }));
  } catch (error) {
    if (page)
      fs.writeFileSync(
        path.join(out, "failure.txt"),
        await page.locator("body").innerText(),
      );
    if (page)
      await page
        .screenshot({ path: path.join(out, "failure.png") })
        .catch(() => {});
    fs.writeFileSync(
      path.join(out, "failure.json"),
      JSON.stringify({ error: String(error), stack: error.stack }),
    );
    throw error;
  } finally {
    await app.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
