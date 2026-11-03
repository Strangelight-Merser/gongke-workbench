const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const Module = require("node:module");
const ts = require("typescript");
function load(file) {
  const name = path.resolve(__dirname, "../src", file);
  const loaded = new Module(name, module);
  loaded.filename = name;
  loaded.paths = module.paths;
  loaded._compile(
    ts.transpileModule(fs.readFileSync(name, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    }).outputText,
    name,
  );
  return loaded.exports;
}
const { fileGroup, revisionOf, openDocument } = load("project/types.ts");
const { defaultLayout, fitLayout, panelWidth } = load("app/layout.ts");
const {
  readDocument,
  importDocuments,
} = require("../dist-electron/documents.cjs");
const { mcpForMode } = require("../dist-electron/agent-mode.cjs");
test("工程对象按内容归组，历史文件保留过期状态", () => {
  assert.equal(
    fileGroup({ name: "task.pdf", path: "inputs/task.pdf", kind: "pdf" }),
    "图纸",
  );
  assert.equal(
    fileGroup({
      name: "part.FCStd",
      path: "revisions/part.FCStd",
      kind: "fcstd",
    }),
    "模型",
  );
  assert.equal(
    fileGroup({
      name: "report.pdf",
      path: "revisions/old/report.pdf",
      kind: "pdf",
    }),
    "报告",
  );
  assert.equal(
    fileGroup({
      name: "assembly.svg",
      path: "revisions/old/assembly.svg",
      kind: "svg",
    }),
    "出图",
  );
  assert.equal(
    revisionOf(
      { generations: [{ path: "revisions/old", current: false }] },
      { path: "revisions/old/assembly.svg" },
    ).current,
    false,
  );
});
test("重复打开保持同一文档实例，独立文件可同时存在", () => {
  const first = { id: "a", title: "a.pdf", type: "file" };
  const docs = [first];
  assert.equal(openDocument(docs, { ...first }), docs);
  assert.equal(
    openDocument(docs, { id: "b", type: "file", title: "b.pdf" }).length,
    2,
  );
});
test("面板尺寸受实际界面空间约束，窄窗口保留中心", () => {
  assert.equal(panelWidth(50, "agent"), 300);
  assert.equal(panelWidth(900, "tree"), 360);
  assert.equal(fitLayout(defaultLayout, 1366).treeOpen, true);
  assert.equal(fitLayout(defaultLayout, 1080).treeOpen, false);
  assert.equal(
    fitLayout({ ...defaultLayout, agentOpen: false }, 1080).treeOpen,
    true,
  );
});
test("图纸导入不覆盖同名文件，读取不能穿越工程或符号链接", async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "gongke-documents-"));
  try {
    const root = path.join(temp, "工程"),
      source = path.join(temp, "input.pdf");
    fs.mkdirSync(root);
    fs.writeFileSync(source, "original");
    const a = (await importDocuments(root, [source]))[0],
      b = (await importDocuments(root, [source]))[0];
    assert.notEqual(a.path, b.path);
    assert.equal(fs.readFileSync(source, "utf8"), "original");
    assert.equal(
      Buffer.from(
        (await readDocument(root, a.path)).content,
        "base64",
      ).toString(),
      "original",
    );
    assert.equal(
      (await importDocuments(root, [path.join(root, a.path)]))[0].path,
      a.path,
    );
    await assert.rejects(readDocument(root, "../input.pdf"), /不属于/);
    fs.symlinkSync(temp, path.join(root, "linked"), "junction");
    await assert.rejects(readDocument(root, "linked/input.pdf"), /不属于/);
    const other = path.join(temp, "other-project"),
      outside = path.join(temp, "outside");
    fs.mkdirSync(other);
    fs.mkdirSync(outside);
    fs.symlinkSync(outside, path.join(other, "inputs"), "junction");
    await assert.rejects(importDocuments(other, [source]), /不属于/);
    assert.deepEqual(
      fs.readdirSync(outside),
      [],
      "拒绝导入时不得在工程外新建目录",
    );
    fs.writeFileSync(path.join(root, "run.exe"), "no");
    await assert.rejects(readDocument(root, "run.exe"), /原生软件/);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});
test("练习连接去除写入授权，直接建模显式加入且不改变原配置", () => {
  const original = {
    command: "python",
    args: ["-m", "gongke_app", "mcp", "--project", "/work", "--allow-writes"],
    env: {},
  };
  assert.equal(
    mcpForMode(original, "practice").args.includes("--allow-writes"),
    false,
  );
  assert.equal(
    mcpForMode(original, "model").args.filter((a) => a === "--allow-writes")
      .length,
    1,
  );
  assert.equal(original.args.includes("--allow-writes"), true);
  assert.throws(
    () => mcpForMode({ command: "unknown", args: [], env: {} }, "practice"),
    /绑定工程/,
  );
});

const { measurement, deviation, canLocate, locateModelTarget } = load(
  "operations/modelChecks.ts",
);
test("建模检查展示图纸/实测与带符号偏差，不从描述编造测量值", () => {
  assert.equal(measurement(12, "mm"), "12 mm");
  assert.equal(deviation({ expected: 12, actual: 10, unit: "mm" }), "-2 mm");
  assert.equal(deviation({ expected: 8, actual: 8.2, unit: "mm" }), "+0.2 mm");
  assert.equal(deviation({ expected: 120, actual: 120, unit: "mm" }), "0 mm");
  assert.equal(measurement(undefined), "未提供");
  assert.equal(deviation({ detail: "图纸 12 mm，模型 10 mm" }), "无法比较");
});
test("检查定位调用原生选择，沿用检查的会话、对象与修订；过期记录不调用选择", async () => {
  const target = {
    host: "freecad",
    session_id: "original-session",
    document_path: "C:/part.FCStd",
    expected_revision: 4,
    object_name: "Hole002",
  };
  assert.equal(canLocate(target), true);
  assert.equal(canLocate({ ...target, expected_revision: undefined }), false);
  assert.equal(canLocate({ ...target, object_name: undefined }), false);
  const requests = [];
  const context = {
    session_id: target.session_id,
    path: target.document_path,
    revision: 4,
  };
  await locateModelTarget(target, async (method, params) => {
    requests.push({ method, params });
    return context;
  });
  assert.deepEqual(requests[1], {
    method: "freecad.select",
    params: {
      session_id: "original-session",
      object_name: "Hole002",
      expected_revision: 4,
    },
  });
  for (const changed of [
    { revision: 5 },
    { session_id: "other-session" },
    { path: "C:/different.FCStd" },
  ]) {
    const called = [];
    await assert.rejects(
      locateModelTarget(target, async (method) => {
        called.push(method);
        return { ...context, ...changed };
      }),
      /已变化/,
    );
    assert.deepEqual(called, ["freecad.context"]);
  }
});
test("商业 CAD 检查定位使用快照中的持久引用，不凭显示名选择特征", async () => {
  const target = {
    host: "solidworks",
    host_id: "sw",
    session_id: "sw-session",
    document_path: "C:/part.SLDPRT",
    expected_revision: 9,
    configuration: "Default",
    persistent_reference: "actual-ref",
  };
  const requests = [];
  await locateModelTarget(target, async (method, params) => {
    requests.push({ method, params });
    return {
      session_id: "sw-session",
      active_document: {
        path: target.document_path,
        revision: 9,
        configuration: "Default",
      },
    };
  });
  assert.equal(requests[1].params.method, "selection.set");
  assert.equal(requests[1].params.params.persistent_reference, "actual-ref");
  assert.equal(requests[1].params.params.expected_revision, 9);
  assert.match(requests[1].params.params.operation_id, /^[a-f0-9-]{36}$/);
  assert.equal(
    canLocate({
      ...target,
      persistent_reference: undefined,
      object_name: "Hole002",
    }),
    false,
  );
});

const { darkTheme } = load("app/theme.ts");
test("深色控件常态与悬停文字/图标至少 4.5:1，禁用使用独立颜色", () => {
  const luminance = (hex) =>
    hex
      .slice(1)
      .match(/../g)
      .map((c) => parseInt(c, 16) / 255)
      .reduce(
        (sum, c, i) =>
          sum +
          (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4) *
            [0.2126, 0.7152, 0.0722][i],
        0,
      );
  const ratio = (a, b) =>
    (Math.max(luminance(a), luminance(b)) + 0.05) /
    (Math.min(luminance(a), luminance(b)) + 0.05);
  for (const background of ["#202020", "#252526", "#303033"]) {
    assert.ok(ratio(darkTheme.colorNeutralForeground2, background) >= 4.5);
  }
  assert.ok(
    ratio(
      darkTheme.colorNeutralForeground2BrandHover,
      darkTheme.colorSubtleBackgroundHover,
    ) >= 4.5,
  );
  assert.ok(
    ratio(
      darkTheme.colorNeutralForeground2BrandPressed,
      darkTheme.colorSubtleBackgroundPressed,
    ) >= 4.5,
  );
  assert.notEqual(
    darkTheme.colorNeutralForegroundDisabled,
    darkTheme.colorNeutralForeground2,
  );
});

const { guideProgress, recoveryFor } = load("agent/onboardingPresentation.ts");
test("连接与首次对话属于同一步，完成前不越过验证", () => {
  assert.equal(guideProgress("deepseek", "credentials").index, 2);
  assert.equal(guideProgress("deepseek", "connect").index, 3);
  assert.equal(guideProgress("deepseek", "verify").index, 3);
  const complete = guideProgress("deepseek", "complete");
  assert.equal(complete.index, complete.labels.length);
  assert.equal(guideProgress("workbuddy", "verify").index, 2);
});
test("仅明确的密钥或余额错误提供相应恢复入口", () => {
  const { agentError } = require("../dist-electron/onboarding/errors.cjs");
  for (const message of ["HTTP 401", "api key missing"]) {
    assert.deepEqual(recoveryFor(agentError(new Error(message))), {
      key: true,
      balance: false,
    });
  }
  assert.deepEqual(recoveryFor(agentError(new Error("HTTP 402"))), {
    key: false,
    balance: true,
  });
  for (const message of ["", "timeout", "unknown failure", "HTTP 429"]) {
    assert.deepEqual(recoveryFor(agentError(new Error(message))), {
      key: false,
      balance: false,
    });
  }
});
