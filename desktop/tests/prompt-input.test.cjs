const { test } = require("node:test");
const assert = require("node:assert/strict");
const { preparePrompt } = require("../dist-electron/prompt-input.cjs");
const { verifyInput } = require("./helpers/modeling-trial.cjs");

test("无视觉模型收到矢量解析结果及文本说明，路径不能代替内容", async () => {
  const calls = [];
  const result = await preparePrompt("/project", "建模", ["part.dxf", "dims.json"],
    async (method, args) => {
      calls.push([method, args]);
      return { path: args.path, sha256: "source-hash", content: "明确标注 20，R10 为推断", next_offset: 200 };
    });
  assert.deepEqual(calls.map(c => c[0]), ["project.read_drawing", "project.read_file"]);
  assert.deepEqual(result.images, []);
  assert.match(result.text, /明确标注 20/);
  assert.match(result.text, /next_offset/);
  assert.ok(verifyInput({ events: [{ type: "user", text: result.text }] }, "dimensions", "dims.json", "source-hash"));
  assert.throws(() => verifyInput({ events: [{ type: "user", text: "dims.json" }] }, "dimensions", "dims.json", "source-hash"));
});

test("提取失败原样传播，不丢掉图纸后只发建模任务", async () => {
  await assert.rejects(preparePrompt("/project", "建模", ["bad.pdf"],
    async () => { throw Error("损坏 PDF"); }), /损坏 PDF/);
});
