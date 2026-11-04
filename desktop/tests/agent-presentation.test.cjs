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
const { toolState, toolResult, featureDescription, ToolDetails } =
  load("ToolCall.tsx");
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
  assert.equal(
    toolState(
      "completed",
      toolResult({
        rawOutput: { checks: [{ status: "fail" }] },
        content: [
          { type: "content", content: { type: "text", text: "检查已完成" } },
        ],
      }),
    ),
    "failed",
  );
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

test("特征详情优先中文名称，无名称使用类型和 SI 换算尺寸，编号仅留在原始回执", () => {
  assert.equal(
    featureDescription(
      "host.feature",
      { name: "底板拉伸", feature: { kind: "pad", length: 0.008 } },
      { native_ref: "Feature0" },
    ),
    "底板拉伸",
  );
  assert.equal(
    featureDescription(
      "host.feature",
      { name: "Feature0", feature: { kind: "pad", length: 0.008 } },
      { native_ref: "Feature0" },
    ),
    "拉伸 8 mm",
  );
  assert.equal(
    featureDescription("host.write", {
      method: "model.feature",
      params: { feature: { kind: "hole", diameter: 0.014, through_all: true } },
    }),
    "贯穿切孔 φ14 mm",
  );
  assert.equal(
    featureDescription(
      "host.feature",
      { name: "旧名称" },
      { label: "安装孔", native_ref: "Feature1" },
    ),
    "安装孔",
  );
  assert.equal(
    featureDescription(
      "host.feature_delete",
      { feature_ref: "Feature0" },
      { deleted_ref: "Feature0" },
    ),
    "未提供特征名称",
  );
  const html = require("react-dom/server").renderToStaticMarkup(
    require("react").createElement(ToolDetails, {
      result: { native_ref: "Feature0" },
      raw: { native_ref: "Feature0" },
      featureLabel: "底板拉伸",
    }),
  );
  assert.match(html, /特征：底板拉伸/);
  assert.doesNotMatch(html, /特征：Feature0/);
  assert.match(html, /Feature0/);
});

test("用户请求与图纸参考分开，跨工具的思考按轮次收拢", () => {
  const update = (sessionUpdate, extra) => ({
    type: "update",
    update: { sessionUpdate, ...extra },
  });
  const events = [
    { type: "user", text: '建模\n{"items":[1]}', displayText: "建模" },
    update("agent_thought_chunk", {
      content: { type: "text", text: "读图。" },
    }),
    update("tool_call", {
      toolCallId: "one",
      title: "host.sketch",
      status: "completed",
    }),
    update("agent_thought_chunk", {
      content: { type: "text", text: "建模。" },
    }),
    { type: "user", text: "检查" },
    update("agent_thought_chunk", {
      content: { type: "text", text: "核对。" },
    }),
  ];
  const rows = rowsOf(events);
  assert.equal(rows[0].text, "建模");
  assert.match(rows[0].reference, /items/);
  assert.deepEqual(
    rows.filter((r) => r.kind === "thought").map((r) => r.text),
    ["读图。建模。", "核对。"],
  );
});
test("真实 dsh 带哈希工具名与人工操作共用工程名称和尺寸", () => {
  const { stepTitle } = load("modelingSteps.ts");
  for (const [command, params] of [
    ["host.sketch", { name: "轮廓" }],
    ["host.feature", { feature: { kind: "pad", length: 0.004 } }],
    ["host.model_new", {}],
    ["project.read_drawing", {}],
    ["host.check", {}],
  ]) {
    assert.equal(
      stepTitle(
        "mcp__gongke__" + command.replace(".", "_") + "_b5d6e9ebda25",
        params,
      ),
      stepTitle(command, params),
    );
  }
});

test("自填期望值不进入成功折叠，图纸依据与未知原因保留", () => {
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const result = {
    status: "unverified",
    scope: "仅所选截面",
    checks: [
      { id: "self", status: "unverified", source_kind: "agent_defined" },
      {
        id: "dimension",
        status: "pass",
        source_kind: "drawing_annotation",
        evidence: { text: "36", page: 1, item: "page-1/text/0" },
      },
      {
        id: "outline",
        status: "unknown",
        source_kind: "drawing_geometry",
        reason: "曲线尚未支持",
      },
    ],
  };
  assert.equal(
    toolState("completed", { ...result, checks: result.checks.slice(0, 2) }),
    "unverified",
  );
  const html = renderToStaticMarkup(
    React.createElement(ToolDetails, { result, raw: {} }),
  );
  for (const text of [
    "未经独立核对",
    "Agent 自定",
    "图纸标注",
    "图纸几何",
    "曲线尚未支持",
    "仅所选截面",
  ])
    assert.ok(html.includes(text), text);
});

test("真实 MCP 任务完成外壳不能掩盖内部未独立核对", () => {
  for (const status of ["unverified", "unknown", "fail"]) {
    const receipt = {
      task_id: "receipt",
      status: "complete",
      result: { status, checks: [{ id: "x", status }] },
    };
    for (const rawOutput of [
      { structuredContent: receipt },
      { content: [{ type: "text", text: JSON.stringify(receipt) }] },
      receipt,
    ]) {
      const result = toolResult({ rawOutput });
      assert.equal(result.status, status);
      assert.equal(
        toolState("completed", result),
        status === "fail" ? "failed" : status,
      );
    }
  }
});
