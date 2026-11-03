const { test } = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { recordCase } = require("./visual-runner.cjs");

test("截图评审单项超时或页面错误后仍记录全部场景，错误不污染下一项", async (t) => {
  const output = fs.mkdtempSync(path.join(os.tmpdir(), "visual-runner-test-"));
  t.after(() => fs.rmSync(output, { recursive: true, force: true }));
  const page = new EventEmitter();
  page.evaluate = async () => {};
  page.screenshot = async ({ path: file }) =>
    fs.writeFileSync(file, "test capture");
  const records = [];
  for (const width of [1366, 1920]) {
    for (let i = 0; i < 8; i++) {
      records.push(
        await recordCase({
          page,
          output,
          name: `scene-${i}`,
          size: { width, height: width === 1366 ? 768 : 1080 },
          run: async () => {
            if (width === 1366 && i === 1)
              throw new Error("PDF render timeout");
            if (width === 1366 && i === 3)
              page.emit("pageerror", new Error("DXF render failed"));
          },
        }),
      );
    }
  }
  assert.equal(records.length, 16);
  assert.equal(records.filter((r) => r.status === "passed").length, 14);
  assert.match(records[1].error, /PDF render timeout/);
  assert.match(records[3].error, /DXF render failed/);
  assert.deepEqual(records[4].errors, []);
  assert.equal(records[15].status, "passed");
  for (const record of records)
    assert.ok(fs.existsSync(path.join(output, record.file)));
  const error = JSON.parse(
    fs.readFileSync(path.join(output, "1366x768-scene-1-failure.json"), "utf8"),
  );
  assert.equal(error.file, "1366x768-scene-1-failure.png");
  assert.equal(page.listenerCount("pageerror"), 0);
});

const { inspectContrast } = require("./visual-contrast.cjs");
test("对比度检查计算透明按钮在实际深色底上的文字与图标，能识别浅色主题残留", (t) => {
  const prior = global.getComputedStyle;
  global.getComputedStyle = (element) => element.style;
  t.after(() => {
    if (prior) global.getComputedStyle = prior;
    else delete global.getComputedStyle;
  });
  const background = {
    style: { color: "rgb(242, 242, 242)", backgroundColor: "rgb(32, 32, 32)" },
    parentElement: null,
  };
  const button = {
    style: { color: "rgb(214, 214, 214)", backgroundColor: "rgba(0, 0, 0, 0)" },
    parentElement: background,
    matches: () => false,
  };
  assert.ok(inspectContrast(button).ratio > 11);
  button.style.color = "rgb(66, 66, 66)";
  assert.ok(
    inspectContrast(button).ratio < 2,
    "截图中的浅色主题前景必须被拒绝",
  );
  button.style.color = "rgb(255, 255, 255)";
  button.parentElement.style.backgroundColor = "rgb(255, 255, 255)";
  assert.equal(inspectContrast(button).ratio, 1);
  button.style.color = "rgb(0, 0, 0)";
  assert.equal(inspectContrast(button).ratio, 21);
});
