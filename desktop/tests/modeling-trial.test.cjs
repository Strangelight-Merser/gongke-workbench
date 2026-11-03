const { test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { AgentClient } = require("../dist-electron/acp/client.cjs");
const {
  waitForReady,
  verifyInput,
  turnResult,
} = require("./helpers/modeling-trial.cjs");
const profile = {
  id: "fixture",
  name: "fixture",
  command: process.execPath,
  args: [path.join(__dirname, "fixtures/acp-modeling-flow.mjs")],
  env: {},
};
const mcp = { command: process.execPath, args: [], env: {} };

test("延迟 initialize/session-new 必须等待真正 ready；按 ID 补齐 dsh 授权且记录选择", async () => {
  const client = new AgentClient(() => {});
  try {
    const starting = client.start(profile, process.cwd(), mcp);
    const observed = [];
    const state = await waitForReady(
      async () => {
        await new Promise((r) => setTimeout(r, 5));
        const snapshot = client.snapshot();
        observed.push(snapshot.phase);
        return snapshot;
      },
      { timeoutMs: 5000, intervalMs: 5 },
    );
    await starting;
    assert.ok(observed.includes("starting"));
    assert.equal(state.phase, "ready");
    assert.equal(state.session.sessionId, "delayed-session");
    const prompt = client.prompt("协议验收");
    const handled = new Set();
    const deadline = Date.now() + 5000;
    while (client.snapshot().phase !== "ready" && Date.now() < deadline) {
      for (const event of client.snapshot().events) {
        if (event.type !== "permission" || handled.has(event.id)) continue;
        handled.add(event.id);
        const id = event.request.toolCall.toolCallId;
        assert.equal(
          event.request.toolCall.title,
          id === "image"
            ? "mcp__gongke__project_read_image"
            : "mcp__gongke__host_context",
        );
        assert.deepEqual(event.request.toolCall.rawInput, { marker: id });
        client.permission(event.id, `allow-${id}`);
      }
      await new Promise((r) => setTimeout(r, 5));
    }
    assert.equal(client.snapshot().phase, "ready");
    await prompt;
    assert.equal(handled.size, 2);
    const final = client.snapshot();
    assert.deepEqual(
      final.events
        .filter((e) => e.type === "permission-resolved")
        .map((e) => e.outcome.optionId),
      ["allow-image", "allow-context"],
    );
    assert.equal(turnResult(final, "delayed-session").stopReason, "end_turn");
  } finally {
    await client.disconnect();
  }
});

test("真实 session-new 错误即时保留；等待超时保留最后状态而非假定就绪", async () => {
  const client = new AgentClient(() => {});
  try {
    const starting = assert.rejects(
      client.start(
        { ...profile, env: { FAIL_SESSION: "1" } },
        process.cwd(),
        mcp,
      ),
      /fixture session rejected/,
    );
    await assert.rejects(
      waitForReady(async () => client.snapshot(), {
        intervalMs: 5,
        timeoutMs: 5000,
      }),
      /fixture session rejected/,
    );
    await starting;
    await assert.rejects(
      waitForReady(async () => ({ phase: "starting" }), {
        timeoutMs: 20,
        intervalMs: 2,
      }),
      /超时.*starting/,
    );
  } finally {
    await client.disconnect();
  }
});

test("核对实际图片哈希、MCP 对照无附件、会话未切换及学生回复", () => {
  const user = {
    type: "user",
    text: "根据图建模",
    images: [{ path: "inputs/p7.png", sha256: "hash" }],
  };
  assert.equal(
    verifyInput({ events: [] }, "attachment", "inputs/p7.png", "hash"),
    null,
  );
  assert.equal(
    verifyInput({ events: [user] }, "attachment", "inputs/p7.png", "hash")
      .sha256,
    "hash",
  );
  assert.throws(
    () =>
      verifyInput({ events: [user] }, "attachment", "inputs/p7.png", "wrong"),
    /不一致/,
  );
  assert.throws(
    () =>
      verifyInput(
        { events: [{ type: "user" }] },
        "attachment",
        "inputs/p7.png",
        "hash",
      ),
    /不一致/,
  );
  assert.throws(
    () => verifyInput({ events: [user] }, "mcp", "inputs/p7.png", "hash"),
    /同时发送/,
  );
  const state = {
    session: { sessionId: "a" },
    events: [{ type: "turn-result", result: { stopReason: "end_turn" } }],
  };
  assert.throws(() => turnResult(state, "b"), /会话发生改变/);
  assert.throws(() => turnResult(state, "a"), /未收到给学生的回复/);
  assert.throws(
    () => turnResult({ ...state, events: [] }, "a"),
    /未收到 session/,
  );
});

test("真实 dsh 哈希后缀及任意只读工程工具均放行，不设建模调用路径白名单", () => {
  const { engineeringPermission } = require("./helpers/modeling-trial.cjs");
  for (const title of [
    "mcp__gongke__project_current_50a8c7a5bd98",
    "mcp__gongke__project_files_ab1234567890",
    "mcp__gongke__host_read_abc",
    "mcp__gongke__future_readonly",
    "mcp__gongke__host_feature_abc",
  ]) {
    assert.equal(
      engineeringPermission({
        toolCall: { title },
        options: [{ kind: "allow_once", optionId: "yes" }],
      }).allow,
      true,
    );
  }
  assert.equal(
    engineeringPermission({
      toolCall: { title: "shell" },
      options: [{ kind: "allow_once" }],
    }).allow,
    false,
  );
});

test("先选明确的视觉模型；按人工复核值判定读图，不能从回复中取期望值", () => {
  const {
    visionModelOption,
    compareVision,
  } = require("./helpers/modeling-trial.cjs");
  const value = '["deepseek-official","deepseek-flash"]';
  assert.equal(
    visionModelOption({
      session: {
        configOptions: [
          {
            id: "model",
            options: [{ group: "deepseek", options: [{ value }] }],
          },
        ],
      },
    }).value,
    value,
  );
  assert.equal(
    compareVision('```json\n{"radius":3,"height":20}\n```', {
      radius: 3,
      height: 20,
    }).verified,
    true,
  );
  assert.equal(
    compareVision('{"radius":5,"height":20}', { radius: 3, height: 20 })
      .verified,
    false,
  );
  assert.equal(compareVision("未收到图片", { radius: 3 }).verified, false);
  assert.equal(
    compareVision('{"slot_through":true,"height":8}', {
      slot_through: true,
      height: 8,
    }).verified,
    true,
  );
  assert.equal(
    compareVision('{"slot_through":"true","height":8}', {
      slot_through: true,
      height: 8,
    }).verified,
    false,
  );
  assert.equal(
    compareVision('{"slot_through":null,"height":8}', {
      slot_through: true,
      height: 8,
    }).verified,
    false,
  );
});
