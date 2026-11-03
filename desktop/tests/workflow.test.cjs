const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("typescript");
const filename = path.resolve(__dirname, "../src/project/workflow.ts");
const compiled = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const loaded = new Module(filename, module);
loaded.filename = filename;
loaded.paths = module.paths;
loaded._compile(compiled, filename);
const { stageState } = loaded.exports;

test("旧文件不能让已改条件的图纸或说明书变成完成", () => {
  const project = {
    generations: [{ current: false }],
    files: [
      {
        kind: "svg",
        path: "revisions/old/drawings/assembly.svg",
        name: "assembly.svg",
      },
      { kind: "md", path: "revisions/old/report.md", name: "report.md" },
    ],
  };
  for (const kind of ["drawings", "report"]) {
    const value = stageState(null, project, kind);
    assert.equal(value.state, "");
    assert.match(value.note, /过期/);
  }
});

test("当前修订缺文件或生成失败不会沿用历史成功状态", () => {
  const project = {
    delivery: {
      status: "complete",
      calculation_ok: true,
      artifacts: {
        drawings: {
          status: "complete",
          available: false,
          files: ["drawings/a.svg"],
        },
      },
    },
  };
  assert.equal(stageState(null, project, "drawings").state, "fail");
  project.delivery = { status: "failed" };
  assert.equal(stageState(null, project, "drawings").state, "fail");
});

test("图纸数量只来自当前完整修订，校核失败仍明确保留", () => {
  const project = {
    delivery: {
      status: "complete",
      calculation_ok: true,
      artifacts: {
        drawings: {
          status: "complete",
          available: true,
          files: ["drawings/a.svg", "drawings/a.dxf"],
        },
      },
    },
  };
  assert.deepEqual(stageState(null, project, "drawings"), {
    state: "done",
    note: "1 张",
  });
  project.delivery.calculation_ok = false;
  assert.equal(stageState(null, project, "drawings").state, "warn");
  project.delivery.drawing_check = { total: 2 };
  assert.equal(stageState(null, project, "drawings").state, "fail");
});
