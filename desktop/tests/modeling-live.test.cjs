const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs"),
  path = require("node:path"),
  Module = require("node:module"),
  ts = require("typescript");
function load(file) {
  const filename = path.resolve(__dirname, "../src", file),
    m = new Module(filename, module);
  m.filename = filename;
  m.paths = module.paths;
  m.require = (name) =>
    name.startsWith(".")
      ? load(
          path.relative(
            path.resolve(__dirname, "../src"),
            path.resolve(path.dirname(filename), name + ".ts"),
          ),
        )
      : require(name);
  m._compile(
    ts.transpileModule(fs.readFileSync(filename, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    }).outputText,
    filename,
  );
  return m.exports;
}
const { stepTitle, commandOf, sameDocument, sameIdentity, serialRefresh } =
  load("agent/modelingSteps.ts");
const { readLiveScene } = load("workspace/liveScene.ts");
const document = {
  host_instance: "host",
  document_id: "doc",
  revision: 2,
  configuration: "",
};
test("步骤以真实参数标注单位，不从轮廓猜设计意图", () => {
  assert.equal(
    stepTitle("mcp__gongke__host_feature", {
      feature: { kind: "pad", length: 0.008 },
    }),
    "拉伸 8 mm",
  );
  assert.equal(
    stepTitle("host.feature", {
      feature: { kind: "pocket", through_all: true },
    }),
    "贯穿切除",
  );
  assert.equal(
    stepTitle("host.sketch", {
      name: "底板草图",
      geometry: [{ kind: "circle", radius: 0.007 }],
    }),
    "绘制草图 · 底板草图：圆 φ14 mm",
  );
  assert.equal(
    commandOf("host.write", { method: "model.feature_edit" }),
    "host.feature_edit",
  );
  assert.equal(
    stepTitle("host.write", {
      method: "model.feature",
      params: { feature: { kind: "fillet", radius: 0.002 } },
    }),
    "圆角 R2 mm",
  );
});
test("尺寸检查须精确修订；特征历史仅能在同一文档重新解析", () => {
  assert.equal(sameDocument(document, { ...document, revision: 3 }), false);
  assert.equal(sameIdentity(document, { ...document, revision: 3 }), true);
  assert.equal(
    sameIdentity(document, { ...document, host_instance: "other" }),
    false,
  );
});
test("慢读取期间的回执合并为一次后续读取，关闭后不再读取", async () => {
  let resolve,
    reads = 0,
    concurrent = 0,
    peak = 0;
  const first = new Promise((r) => (resolve = r)),
    errors = [];
  const queue = serialRefresh(
    async () => {
      reads++;
      concurrent++;
      peak = Math.max(peak, concurrent);
      if (reads === 1) await first;
      concurrent--;
    },
    (e) => errors.push(e),
  );
  const running = queue.request();
  await queue.request();
  await queue.request();
  resolve();
  await running;
  assert.equal(reads, 2);
  assert.equal(peak, 1);
  assert.deepEqual(errors, []);
  queue.close();
  await queue.request();
  assert.equal(reads, 2);
});
function fixture(change = false) {
  let contexts = 0;
  const calls = [];
  return {
    calls,
    request: async (method, p) => {
      calls.push(method);
      if (method === "freecad.context")
        return { session_id: "doc", revision: 2 };
      if (method === "freecad.scene")
        return { session_id: "doc", revision: 2, objects: [] };
      if (method === "host.context")
        return {
          active_document:
            change && contexts++ ? { ...document, revision: 3 } : document,
          documents: [{ document, objects: [{ native_ref: "Body" }] }],
        };
      if (method === "host.inspect")
        return {
          document,
          object_ref: p.object_ref,
          features: [
            { native_ref: "Body" },
            { native_ref: "Pad", parent: "Body" },
          ],
          edges: [],
        };
      throw Error(method);
    },
  };
}
test("一次刷新只读取一次原生网格，特征树与选中轮廓使用同一文档引用", async () => {
  const f = fixture();
  const value = await readLiveScene("Pad", f.request, document);
  assert.equal(f.calls.filter((c) => c === "freecad.scene").length, 1);
  assert.equal(value.detail.object_ref, "Pad");
  assert.equal(value.features.length, 2);
  assert.deepEqual(value.scene.nativeDocument, document);
});
test("读取期间原生修订变化拒绝混合快照", async () => {
  const f = fixture(true);
  await assert.rejects(
    readLiveScene("Pad", f.request, document),
    /模型正在变化/,
  );
});
test("旧回执不得把同名特征高亮到另一个文档", async () => {
  const f = fixture();
  const value = await readLiveScene("Pad", f.request, {
    ...document,
    document_id: "other",
  });
  assert.equal(value.selected, "");
  assert.equal(value.detail, null);
  assert.equal(f.calls.filter((c) => c === "host.inspect").length, 1);
});

test("查询原操作的确定结果可用于刷新，未知结果不冒充成功", () => {
  const { modelResult } = load("agent/modelingSteps.ts");
  const result = { outcome: "committed", document, native_ref: "Pad" };
  assert.deepEqual(
    modelResult({
      command: "host.model_operation",
      result: { state: "finished", result },
    }),
    result,
  );
  assert.equal(
    modelResult({
      command: "host.model_operation",
      result: { state: "started" },
    }).outcome,
    undefined,
  );
});

test("文档栏显示工程相对路径，工程外不泄露用户目录", () => {
  const { displayPath } = load("project/displayPath.ts");
  assert.equal(
    displayPath(
      "/Users/person/project/models/a.FCStd",
      "/Users/person/project",
    ),
    "models/a.FCStd",
  );
  assert.equal(
    displayPath(
      "C:\\Users\\person\\工程\\a.FCStd",
      "c:\\users\\person\\工程\\",
    ),
    "a.FCStd",
  );
  assert.equal(
    displayPath("/Users/person/project-old/a.FCStd", "/Users/person/project"),
    "a.FCStd",
  );
  assert.equal(displayPath("inputs/a.pdf", "/root"), "inputs/a.pdf");
});
