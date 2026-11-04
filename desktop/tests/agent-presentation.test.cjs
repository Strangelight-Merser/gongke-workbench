const test = require("node:test"),
  assert = require("node:assert/strict");
const fs = require("node:fs"),
  path = require("node:path"),
  Module = require("node:module"),
  ts = require("typescript");
function load(file) {
  const filename = path.resolve(__dirname, "../src/agent", file),
    m = new Module(filename, module);
  m.filename = filename;
  m.paths = module.paths;
  m.require = (n) =>
    n === "./modelingSteps" ? load("modelingSteps.ts") : require(n);
  m._compile(
    ts.transpileModule(fs.readFileSync(filename, "utf8"), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
      },
    }).outputText,
    filename,
  );
  return m.exports;
}
const { rowsOf, groupCompletedTools } = load("events.ts");
const { toolState, toolResult } = load("ToolCall.tsx");
const { conversation } = require("./fixtures/long-conversation.cjs");
test("长对话成功组不吞掉失败重试、检查不符与授权", () => {
  const rows = rowsOf(conversation()),
    grouped = groupCompletedTools(
      rows,
      (t) => toolState(t.status, toolResult(t)) === "completed",
    );
  assert.equal(rows.filter((r) => r.kind === "tool").length, 36);
  assert.equal(grouped.find((r) => r.kind === "tool-group").tools.length, 32);
  assert.deepEqual(
    grouped.filter((r) => r.kind === "tool").map((r) => r.tool.toolCallId),
    ["failed", "retry", "check", "save"],
  );
});
test("MCP 文本/结构化回执与 ACP 失败状态均保留；未知不冒充通过", () => {
  const result = toolResult({
    rawOutput: {
      content: [{ type: "text", text: '{"checks":[{"status":"fail"}]}' }],
    },
  });
  assert.equal(toolState("completed", result), "failed");
  assert.equal(
    toolState(
      "completed",
      toolResult({
        rawOutput: {
          isError: true,
          content: [{ type: "text", text: "宿主拒绝" }],
        },
      }),
    ),
    "failed",
  );
  assert.equal(
    toolState(
      "completed",
      toolResult({ rawOutput: { structuredContent: { status: "unknown" } } }),
    ),
    "unknown",
  );
  assert.equal(toolState("completed", toolResult({
    rawOutput: {checks:[{status:"fail"}]},
    content:[{type:"content",content:{type:"text",text:"检查已完成"}}]
  })), "failed");
  assert.equal(toolState("failed", {}), "failed");
  assert.equal(toolState("completed", { state: "pending" }), "unknown");
  assert.equal(toolState("in_progress", {}), "in_progress");
});
test("同一调用更新原行；正文和思考切断成功分组", () => {
  const events = conversation();
  events.push({
    type: "update",
    update: {
      sessionUpdate: "tool_call_update",
      toolCallId: "save",
      status: "completed",
    },
  });
  assert.equal(rowsOf(events).filter((r) => r.kind === "tool").length, 36);
  const rows = [
    ...Array.from({ length: 4 }, () => ({
      kind: "tool",
      tool: { status: "completed" },
    })),
    { kind: "assistant", text: "检查后继续" },
    { kind: "thought", text: "检查" },
    { kind: "tool", tool: { status: "in_progress" } },
  ];
  assert.deepEqual(
    groupCompletedTools(rows, (t) => t.status === "completed").map(
      (r) => r.kind,
    ),
    ["tool-group", "assistant", "thought", "tool"],
  );
});
