const { test } = require("node:test");
const assert = require("node:assert/strict");
const { zstdCompressSync } = require("node:zlib");
const {
  decodeZstdFrames,
  summarizeUsage,
} = require("./helpers/dsh-session.cjs");

test("dsh 多帧 Zstd 会话读取所有事件，非法帧头不吞错", () => {
  const rows = [
    { type: "session", id: "sample" },
    { type: "assistant/message", data: { usage: { inputTokens: 12 } } },
  ];
  const text = rows.map((r) => JSON.stringify(r) + "\n");
  const frames = Buffer.concat(text.map((t) => zstdCompressSync(t)));
  assert.equal(decodeZstdFrames(frames).toString(), text.join(""));
  const corrupt = Buffer.concat([
    zstdCompressSync(text[0]),
    Buffer.from("invalid frame"),
  ]);
  assert.throws(() => decodeZstdFrames(corrupt));
});

test("usage 按顶层事件类型汇总，不累加内嵌 stream 或把缓存重复加到 total", () => {
  const rows = [
    {
      type: "assistant/message",
      usage: {
        inputTokens: 10,
        cacheReadTokens: 100,
        outputTokens: 5,
        totalTokens: 115,
      },
      stream: { usage: { totalTokens: 115 } },
    },
    {
      type: "assistant/message",
      usage: {
        inputTokens: 20,
        cacheReadTokens: 200,
        outputTokens: 7,
        totalTokens: 227,
      },
    },
    { type: "assistant/attempt", usage: { totalTokens: 3 } },
  ];
  const totals = summarizeUsage(rows);
  assert.equal(totals["assistant/message"].count, 2);
  assert.deepEqual(totals["assistant/message"].tokens, {
    inputTokens: 30,
    cacheReadTokens: 300,
    outputTokens: 12,
    totalTokens: 342,
  });
  assert.equal(totals["assistant/attempt"].tokens.totalTokens, 3);
});
