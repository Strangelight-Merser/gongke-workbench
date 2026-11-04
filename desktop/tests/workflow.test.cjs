const test = require("node:test"),
  assert = require("node:assert/strict");
const fs = require("node:fs"),
  path = require("node:path"),
  Module = require("node:module"),
  ts = require("typescript");
function load(name) {
  const file = path.resolve(__dirname, "../src", name),
    m = new Module(file, module);
  m.filename = file;
  m.paths = module.paths;
  m._compile(
    ts.transpileModule(fs.readFileSync(file, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    }).outputText,
    file,
  );
  return m.exports;
}
const { documentLabel, revisionOf } = load("project/types.ts");
const { checkSuperseded } = load("agent/modelingSteps.ts");
test("文件导航不显示输入存储目录，成果仍沿用同一修订状态", () => {
  const file = {
    path: "inputs/6bbb178a-e04/robot4.pdf",
    name: "robot4.pdf",
    kind: "pdf",
  };
  assert.equal(documentLabel({ type: "file", file }), "图纸 › robot4.pdf");
  const revision = {
    path: "revisions/part",
    current: false,
    status: "complete",
  };
  const project = { generations: [revision] };
  for (const name of ["model.FCStd", "drawing.pdf", "report.pdf"])
    assert.equal(
      revisionOf(project, { path: "revisions/part/" + name }),
      revision,
    );
});
test("原生模型改变后旧检查过期；其他文档不使本模型检查过期", () => {
  const doc = {
    host_instance: "host",
    document_id: "part",
    configuration: "",
    revision: 1,
  };
  const check = {
    command: "host.check",
    phase: "finished",
    result: { document: doc, checks: [{ ok: true }] },
  };
  const edit = {
    command: "host.feature_edit",
    phase: "finished",
    result: { document: { ...doc, revision: 2 } },
  };
  assert.equal(checkSuperseded(check, [check]), false);
  assert.equal(checkSuperseded(check, [check, edit]), true);
  assert.equal(
    checkSuperseded(check, [
      check,
      {
        ...edit,
        result: { document: { ...doc, document_id: "other", revision: 2 } },
      },
    ]),
    false,
  );
  assert.equal(
    checkSuperseded(
      { ...check, result: { document: edit.result.document, checks: [] } },
      [check, edit],
    ),
    false,
  );
});
