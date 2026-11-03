const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path"),
  fs = require("node:fs");
(async () => {
  const { createServer } = await import("vite");
  const server = await createServer({
    root: path.resolve(__dirname, ".."),
    server: { host: "127.0.0.1", port: 0 },
  });
  await server.listen();
  const browser = await chromium.launch({
    executablePath:
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: true,
    args: ["--enable-unsafe-swiftshader"],
  });
  const out = path.resolve(__dirname, "../../out/live-model-validation");
  fs.mkdirSync(out, { recursive: true });
  try {
    const page = await browser.newPage({
        viewport: { width: 1440, height: 900 },
      }),
      errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto(
      `http://127.0.0.1:${server.httpServer.address().port}/tests/fixtures/modeling-live.html`,
    );
    await page.getByRole("heading", { name: "特征树" }).waitFor();
    const canvas = page.locator("canvas");
    await canvas.waitFor();
    await canvas.evaluate((c) => {
      c.dataset.identity = "preserved";
    });
    const before = await page.evaluate(
      () => window.fixture.calls.filter((c) => c === "freecad.scene").length,
    );
    await page.evaluate(() => window.fixture.emit("pad"));
    await page.getByText("拉伸 12 mm", { exact: false }).waitFor();
    await page.waitForFunction(() =>
      document.querySelector(".native-status")?.textContent.includes("修订 2"),
    );
    assert.equal(await canvas.getAttribute("data-identity"), "preserved");
    assert.equal(
      await page.evaluate(
        () => window.fixture.calls.filter((c) => c === "freecad.scene").length,
      ),
      before + 1,
    );
    await page.evaluate(() => window.fixture.emit("check"));
    await page.getByText("底板厚度 · 不符", { exact: false }).waitFor();
    await page.screenshot({ path: path.join(out, "headless-check.png") });
    await page.evaluate(() => window.fixture.emit("delete"));
    await page.waitForFunction(() =>
      document.querySelector(".native-status")?.textContent.includes("修订 3"),
    );
    assert.equal(
      await page.getByRole("button", { name: "底板拉伸", exact: true }).count(),
      0,
    );
    assert.equal(
      await page.getByText("底板厚度 · 不符", { exact: false }).count(),
      0,
    );
    assert.deepEqual(errors, []);
    await page.screenshot({ path: path.join(out, "headless-delete.png") });
    console.log(
      "PASS: 自动读取、回执刷新一次、保留 canvas、同步树、检查标记过期、删除刷新；合成样例，非宿主验收",
    );
  } finally {
    await browser.close();
    await server.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
