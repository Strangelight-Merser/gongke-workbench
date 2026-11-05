const test = require("node:test"),
  assert = require("node:assert/strict");
const fs = require("node:fs"),
  path = require("node:path"),
  Module = require("node:module"),
  ts = require("typescript"),
  THREE = require("three");
async function render(props) {
  const addons = {};
  for (const name of [
    "lines/Line2.js",
    "lines/LineGeometry.js",
    "lines/LineMaterial.js",
    "utils/BufferGeometryUtils.js",
    "controls/OrbitControls.js",
  ])
    addons["three/addons/" + name] = await import("three/addons/" + name);
  const effects = [],
    overlays = new THREE.Group(),
    models = new THREE.Group();
  const mesh = new THREE.Mesh(
    new THREE.BufferGeometry(),
    new THREE.MeshStandardMaterial(),
  );
  mesh.userData.id = "body";
  models.add(mesh);
  const view = {
    models,
    overlays,
    fitted: "session",
    camera: new THREE.PerspectiveCamera(),
    controls: { target: new THREE.Vector3(), update() {} },
  };
  let ref = 0;
  const filename = path.resolve(__dirname, "../src/workspace/ModelView.tsx"),
    m = new Module(filename, module);
  m.paths = module.paths;
  m.require = (n) =>
    n === "react"
      ? {
          useEffect: (f) => effects.push(f),
          useRef: (v) => ({
            current: [
              0,
              { clientWidth: 800, clientHeight: 600 },
              view,
              () => {},
            ][ref++],
          }),
        }
      : addons[n] || require(n);
  m._compile(
    ts.transpileModule(fs.readFileSync(filename, "utf8"), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
      },
    }).outputText,
    filename,
  );
  m.exports.ModelView({
    scene: { session_id: "session" },
    selected: "body",
    onSelect() {},
    ...props,
  });
  effects[2]();
  return { mesh, overlays };
}
const edges = [
  { start: [0, 0, 0], end: [0.01, 0.01, 0] },
  { start: [0, 0.02, 0], end: [0.01, 0.03, 0] },
];
test("草图使用可读的屏幕像素宽线，而非 WebGL 单像素线", async () => {
  const { overlays } = await render({
    detail: { object_ref: "sketch", edges },
  });
  assert.equal(overlays.children.length, 2);
  for (const line of overlays.children) {
    assert.equal(line.material.linewidth, 3);
    assert.equal(line.material.color.getHexString(), "f4c99e");
    assert.equal(line.material.resolution.x, 800);
  }
});
test("检查定位只强调两条模型错边，保持实体原色且不叠加整件边线", async () => {
  const { mesh, overlays } = await render({
    locateCheck: true,
    focusRequest: 1,
    detail: { object_ref: "body", edges: [...edges, ...edges] },
    checks: {
      status: "fail",
      checks: [
        {
          status: "fail",
          actual: {
            locations: [
              { difference: "extra_or_shifted", edges },
              { difference: "missing_or_shifted", edges },
            ],
          },
        },
      ],
    },
  });
  assert.equal(mesh.material.color.getHexString(), "8e8b86");
  assert.equal(overlays.children.length, 2);
  for (const line of overlays.children) {
    assert.equal(line.material.color.getHexString(), "e8742a");
    assert.equal(line.material.linewidth, 5);
  }
});

test("定位缺少边的精确位置时，不回退为整件轮廓高亮", async () => {
  const { mesh, overlays } = await render({
    locateCheck: true,
    detail: { object_ref: "body", edges },
    checks: {
      status: "fail",
      checks: [
        { status: "fail", actual: { locations: [{ native_ref: "body" }] } },
      ],
    },
  });
  assert.equal(mesh.material.color.getHexString(), "8e8b86");
  assert.equal(overlays.children.length, 0);
});
