const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createHash } = require("node:crypto");
const { AgentClient } = require("../dist-electron/acp/client.cjs");
const { readPromptImages } = require("../dist-electron/documents.cjs");
const { redactRecord } = require("../dist-electron/acp/diagnostics.cjs");
const { saveAgentDiagnostics } = require("./helpers/modeling-trial.cjs");
const image = {
  path: "drawing.png",
  mimeType: "image/png",
  data: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6nGAAAAAASUVORK5CYII=",
};
const profile = {
  id: "fixture",
  name: "fixture",
  command: process.execPath,
  args: [path.join(__dirname, "fixtures/acp-image-agent.mjs")],
  env: { IMAGE_CAPABLE: "yes" },
};
const mcp = { command: process.execPath, args: [], env: {} };

test("图片经真实 ACP stdio 传递，记录哈希与轮次结果；能力缺失不能降级成文字路径", async (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "gongke-images-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const trace = path.join(directory, "trace.jsonl");
  const client = new AgentClient(() => {}, path.join(directory, "agent-errors.jsonl"), trace);
  try {
    await client.start(profile, directory, mcp);
    await client.prompt("看图", [image]);
    const events = client.snapshot().events;
    const answer = JSON.parse(
      events.find((e) => e.type === "update").update.content.text,
    );
    const hash = createHash("sha256")
      .update(Buffer.from(image.data, "base64"))
      .digest("hex");
    assert.equal(answer.sha256, hash);
    assert.equal(answer.mimeType, image.mimeType);
    assert.equal(events.find((e) => e.type === "user").images[0].sha256, hash);
    assert.equal(
      events.find((e) => e.type === "turn-result").result.stopReason,
      "end_turn",
    );
    const rows = fs
      .readFileSync(trace, "utf8")
      .trim()
      .split("\n")
      .map(JSON.parse);
    assert.deepEqual(
      rows.map((r) => r.event),
      events,
    );
    assert.ok(!fs.readFileSync(trace, "utf8").includes(image.data));
    await client.start({ ...profile, env: {} }, directory, mcp);
    await client.setConfigOption("model", "vision");
    assert.equal(client.snapshot().session.configOptions[0].currentValue, "vision");
    await client.prompt("初始化 image=false，切模型后仍发送实际图片", [image]);
    const request = client.snapshot().events.findLast(e => e.type === "request" && e.method === "session/prompt");
    assert.equal(request.params.advertisedImage, false);
    assert.equal(request.params.prompt[1].sha256, hash);
    const reply = client.snapshot().events.findLast(e => e.type === "update" && e.update.sessionUpdate === "agent_message_chunk");
    assert.equal(JSON.parse(reply.update.content.text).sha256, hash);
    await client.start({ ...profile, env: { REJECT_IMAGE: "yes" } }, directory, mcp);
    await assert.rejects(client.prompt("实际尝试后 Agent 拒收", [image]));
    assert.equal(client.snapshot().errorDetails.operation, "session/prompt");
    assert.equal(client.snapshot().errorDetails.code, -32602);
    assert.match(client.snapshot().errorDetails.details, /image-admission/);
    assert.match(JSON.stringify(client.snapshot().errorDetails), /not advertised/);
    const stderr = fs.readFileSync(client.snapshot().stderrLogPath, "utf8");
    assert.match(stderr, /image admission rejected/);
    assert.ok(!stderr.includes("fixture-private"));
    const evidence = {};
    saveAgentDiagnostics(directory, evidence, client.snapshot());
    assert.equal(evidence.acp_error.code, -32602);
    assert.match(fs.readFileSync(evidence.dsh_stderr.path, "utf8"), /image admission rejected/);
    assert.equal(JSON.parse(fs.readFileSync(path.join(directory, "acp-error.json"))).code, -32602);
    saveAgentDiagnostics(directory, evidence, { ...client.snapshot(), errorDetails: { operation: "session/close", message: "cleanup error" } });
    assert.equal(evidence.acp_error.operation, "session/prompt");
    assert.ok(client.snapshot().events.some(e => e.type === "request" && e.method === "session/prompt"));
  } finally {
    await client.disconnect();
  }
});

test("主进程附件读取拒绝工程外和 symlink 越界，结构化脱敏保留 token 数值", async (t) => {
  const directory = fs.mkdtempSync(
    path.join(os.tmpdir(), "gongke-image-path-"),
  );
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const project = path.join(directory, "project");
  fs.mkdirSync(project);
  fs.writeFileSync(
    path.join(project, "drawing.png"),
    Buffer.from(image.data, "base64"),
  );
  assert.deepEqual(await readPromptImages(project, [image.path]), [image]);
  fs.writeFileSync(path.join(directory, "private.png"), "outside");
  fs.symlinkSync(
    path.join(directory, "private.png"),
    path.join(project, "escape.png"),
  );
  await assert.rejects(readPromptImages(project, ["escape.png"]), /不属于/);
  await assert.rejects(readPromptImages(project, ["../private.png"]), /不属于/);
  await assert.rejects(readPromptImages(project, ["drawing.pdf"]), /PNG/);
  const clean = redactRecord({
    inputTokens: 123,
    total_tokens: 200,
    api_key: "private",
    message: "Bearer private",
  });
  assert.deepEqual(JSON.parse(JSON.stringify(clean)), {
    inputTokens: 123,
    total_tokens: 200,
    api_key: "[REDACTED]",
    message: "Bearer [REDACTED]",
  });
});
