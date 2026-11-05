// 打包/源码共用真实通用流程：只替换文件选择对话框，无模型 API、无服务替身。
const { electron } = require("./owned-electron.cjs");
const { showProjectTree } = require("./workspace.cjs");
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict"),
  { spawn } = require("node:child_process"),
  { randomUUID } = require("node:crypto");
const root = path.resolve(__dirname, "../../.."),
  delay = (ms) => new Promise((r) => setTimeout(r, ms));
exports.run = async function (kind) {
  const width = Number(
      process.env.GONGKE_TEST_WIDTH ||
        process.env.GONGKE_TEST_WINDOW_WIDTH ||
        1366,
    ),
    height = width === 1366 ? 768 : 1080;
  const output = path.join(
    root,
    "out",
    kind + "-validation",
    Date.now() + "-" + width,
  );
  fs.mkdirSync(output, { recursive: true });
  const project = path.join(output, "零件工程"),
    other = path.join(output, "空白工程"),
    user = path.join(output, "user");
  const env = {
    ...process.env,
    GONGKE_DESKTOP_USER_DATA: user,
    GONGKE_MODELING_ROOT: root,
    GONGKE_FREECAD_SESSION: path.join(output, "host/session.json"),
    GONGKE_TRIAL_BACKGROUND: "1",
  };
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.PYTHONHOME;
  delete env.PYTHONPATH;
  fs.mkdirSync(path.join(output, "host"));
  // 独立真实宿主：Windows 使用随包分发的 FreeCAD，macOS 使用本机安装。
  let host, app, page;
  const errors = [],
    checks = [];
  let hostNumber = 0;
  async function launchHost(model) {
    const executable =
      process.env.GONGKE_TEST_FREECAD ||
      (process.platform === "darwin"
        ? "/Applications/FreeCAD.app/Contents/Resources/bin/freecad"
        : path.join(
            path.dirname(env.GONGKE_TEST_EXECUTABLE),
            "resources/freecad/bin/FreeCAD.exe",
          ));
    assert(fs.existsSync(executable), "缺少真实验收宿主：" + executable);
    if (host && host.exitCode === null) {
      host.kill("SIGTERM");
      await new Promise((r) => host.once("exit", r));
    }
    if (fs.existsSync(env.GONGKE_FREECAD_SESSION))
      fs.unlinkSync(env.GONGKE_FREECAD_SESSION);
    const log = fs.openSync(path.join(output, "host.log"), "a");
    host = spawn(
      executable,
      [
        "--user-cfg",
        path.join(output, `host/user-${++hostNumber}.cfg`),
        path.join(root, "desktop/tests/fixtures/generic-host.FCMacro"),
      ],
      {
        env: { ...env, ...(model ? { GONGKE_ACCEPT_MODEL: model } : {}) },
        stdio: ["ignore", log, log],
      },
    );
    fs.closeSync(log);
    // Windows 托管机首次冷启动 FreeCAD 可能超过 30 秒，最多等 90 秒。
    for (let n = 0; n < 450 && !fs.existsSync(env.GONGKE_FREECAD_SESSION); n++)
      await delay(200);
    assert(fs.existsSync(env.GONGKE_FREECAD_SESSION), "隔离 FreeCAD 启动超时");
    await delay(700);
  }
  async function launch() {
    app = await electron.launch({
      ...(env.GONGKE_TEST_EXECUTABLE
        ? { executablePath: env.GONGKE_TEST_EXECUTABLE, args: [] }
        : { args: [path.join(root, "desktop")] }),
      cwd: output,
      env,
    });
    page = await app.firstWindow();
    page.setDefaultTimeout(20000);
    await app.evaluate(
      ({ BrowserWindow }, s) =>
        BrowserWindow.getAllWindows()[0].setContentSize(s.width, s.height),
      { width, height },
    );
    await page.setViewportSize({ width, height });
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.getByText("就绪", { exact: true }).waitFor();
  }
  async function call(method, params = {}) {
    return page.evaluate(
      ({ method, params }) => window.gongke.request(method, params),
      { method, params },
    );
  }
  async function choose(target, create, inside = false) {
    fs.mkdirSync(target, { recursive: true });
    await app.evaluate(({ dialog }, p) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [p] });
    }, target);
    if (inside) {
      await showProjectTree(page);
      await page.getByRole("button", { name: "工程操作", exact: true }).click();
      await page
        .getByRole("menuitem", {
          name: create ? "新建工程" : "打开工程",
          exact: true,
        })
        .click();
    } else
      await page
        .locator(".start-page")
        .getByRole("button", {
          name: create ? "新建工程" : "打开工程",
          exact: true,
        })
        .click();
    await page.locator("footer").getByTitle(target, { exact: true }).waitFor();
  }
  async function shot(name) {
    await page.screenshot({ path: path.join(output, name + ".png") });
  }
  let binding;
  async function connection(action, params) {
    const endpoint = JSON.parse(
      fs.readFileSync(path.join(user, "state/service.json"), "utf8"),
    );
    const response = await fetch(endpoint.url + "/command", {
      method: "POST",
      headers: {
        Authorization: "Bearer " + endpoint.token,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ action, params }),
      signal: AbortSignal.timeout(30000),
    });
    const value = await response.json();
    assert(!value.error, JSON.stringify(value));
    return value.result;
  }
  async function command(method, params) {
    binding ||= await connection("bind", { project, allow_writes: true });
    const task_id = randomUUID();
    await connection("call", {
      binding_id: binding.binding_id,
      method,
      params: { host_id: "freecad", ...params },
      task_id,
    });
    for (let n = 0; n < 300; n++) {
      const task = await connection("task", {
        binding_id: binding.binding_id,
        task_id,
      });
      if (task.status === "complete") return task.result;
      assert(
        !["failed", "canceled", "interrupted"].includes(task.status),
        JSON.stringify(task),
      );
      await delay(100);
    }
    throw Error("任务超时 " + method);
  }
  try {
    await launchHost();
    await launch();
    assert.equal((await call("system.status")).project, null);
    assert.doesNotMatch(
      await page.locator("body").innerText(),
      /减速器|课程设计|Y132S|report\.pdf/,
    );
    await shot("first-launch-empty");
    await choose(project, true);
    let current = await call("project.current");
    assert.equal(current.task, null);
    assert.deepEqual(current.results, []);
    assert.deepEqual(current.working_copies, []);
    assert.deepEqual(await call("task.list"), []);
    assert.deepEqual(
      current.files.map((f) => f.name),
      ["gongke-project.json"],
    );
    await showProjectTree(page);
    assert.equal(
      await page
        .getByLabel("工程树", { exact: true })
        .getByText("gongke-project.json", { exact: true })
        .count(),
      0,
    );
    await shot("new-project-empty");
    checks.push(
      "fresh user directory and new project contain no examples or sessions",
    );
    // 独立生成验收图纸，导入后原文件必须逐字保持一致。
    const pdf = path.join(output, "plate.pdf");
    const objects = [
      "<< /Type /Catalog /Pages 2 0 R >>",
      "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 400] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
      "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ];
    const stream =
      "2 w 140 120 300 150 re S BT /F1 18 Tf 140 310 Td (PLATE TEST: 20 x 10 x 4 mm) Tj ET";
    objects.push(
      `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    );
    let text = "%PDF-1.4\n";
    const offsets = [0];
    objects.forEach((o, i) => {
      offsets.push(text.length);
      text += `${i + 1} 0 obj\n${o}\nendobj\n`;
    });
    const at = text.length;
    text += `xref\n0 6\n0000000000 65535 f \n${offsets
      .slice(1)
      .map((n) => String(n).padStart(10, "0") + " 00000 n \n")
      .join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${at}\n%%EOF`;
    fs.writeFileSync(pdf, text);
    await app.evaluate(({ dialog }, p) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [p] });
    }, pdf);
    await page.getByRole("button", { name: "导入图纸", exact: true }).click();
    await page
      .locator('.pdf-document[data-render-state="ready"]:visible')
      .waitFor();
    await page.getByRole("button", { name: "适应宽度", exact: true }).click();
    await delay(500);
    const box = await page.locator(".pdf-pages:visible").boundingBox(),
      canvas = await page.locator(".pdf-pages:visible canvas").boundingBox();
    assert(
      Math.abs(canvas.width - (box.width - 48)) < 5,
      JSON.stringify({ box, canvas }),
    );
    assert(Math.abs(canvas.x + canvas.width / 2 - box.x - box.width / 2) < 4);
    assert.match(
      await page.getByLabel("面包屑", { exact: true }).innerText(),
      /图纸 › plate.pdf/,
    );
    assert.doesNotMatch(
      await page.getByLabel("面包屑", { exact: true }).innerText(),
      /inputs/,
    );
    current = await call("project.current");
    const imported = current.files.find((f) => f.name === "plate.pdf");
    assert.equal(
      fs.readFileSync(path.join(project, imported.path), "utf8"),
      text,
    );
    await shot("import-centered-pdf");
    checks.push(
      "real PDF import preserves source; centered fit-width and readable breadcrumb",
    );
    await page.getByText("原生 CAD", { exact: true }).click();
    await page
      .getByRole("button", { name: "连接 FreeCAD", exact: true })
      .click();
    const context = await call("host.context", { host_id: "freecad" });
    let part = await command("host.model_new", {
        host_instance: context.host_instance,
        operation_id: randomUUID(),
        path: "plate.FCStd",
        name: "PlateBody",
      }),
      body = part.body_ref;
    const sketch = await command("host.sketch", {
      document: part.document,
      operation_id: randomUUID(),
      body_ref: body,
      name: "Profile",
      support: { plane: "XY" },
      geometry: [{ kind: "rectangle", start: [0, 0], end: [0.02, 0.01] }],
      constraints: [],
    });
    part = await command("host.feature", {
      document: sketch.document,
      operation_id: randomUUID(),
      body_ref: body,
      name: "Pad",
      feature: { kind: "pad", sketch_ref: sketch.sketch_ref, length: 0.004 },
    });
    const inspect = await command("host.inspect", {
        document: part.document,
        object_ref: body,
      }),
      scene = await call("freecad.scene");
    assert.equal(scene.revision, part.document.revision);
    assert.equal(inspect.solid_count, 1);
    assert(Math.abs(inspect.volume - 0.02 * 0.01 * 0.004) < 1e-12);
    const conditions = [
      {
        id: "板厚",
        source: "验收输入 plate.pdf: 4 mm",
        measurement: {
          kind: "plane_distance",
          selectors: [
            { kind: "plane", direction: [0, 0, 1], offset: 0 },
            { kind: "plane", direction: [0, 0, 1], offset: 0.004 },
          ],
        },
        expected: 0.004,
        tolerance: 0.000001,
        unit: "m",
      },
    ];
    const checked = await command("host.check", {
      document: part.document,
      object_ref: body,
      conditions,
    });
    // 期望值由调用方自填、没有图纸引用，按独立检查语义只能是“未经独立核对”。
    assert.equal(checked.status, "unverified");
    assert.deepEqual(checked.unverified, ["板厚"]);
    await page
      .getByRole("button", { name: "Agent 连接设置", exact: true })
      .click();
    await page
      .getByRole("menuitem", { name: "使用已配置的 Agent", exact: true })
      .click();
    await page
      .getByRole("button", { name: "读取 FreeCAD 工程", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Profile · 草图", exact: true })
      .waitFor();
    await shot("native-model-and-receipts");
    const saved = await command("host.model_save", {
      document: part.document,
      operation_id: randomUUID(),
    });
    assert(fs.existsSync(path.join(project, "plate.FCStd")));
    const edited = await command("host.feature_edit", {
      document: saved.document,
      operation_id: randomUUID(),
      feature_ref: part.native_ref || part.feature_ref,
      parameter: "Length",
      value: 0.005,
    });
    await page.getByText("已过期 · 请重新检查", { exact: true }).waitFor();
    assert.equal(
      await page
        .locator(".native")
        .getByText("板厚 · 通过", { exact: true })
        .count(),
      0,
    );
    await shot("old-check-stale");
    const after = await command("host.inspect", {
      document: edited.document,
      object_ref: body,
    });
    assert(Math.abs(after.volume - 0.02 * 0.01 * 0.005) < 1e-12);
    const old = await command("host.check", {
      document: part.document,
      object_ref: body,
      conditions,
    }).catch((e) => ({ error: String(e) }));
    assert(old.error || old.status === "failed");
    await command("host.model_save", {
      document: edited.document,
      operation_id: randomUUID(),
    });
    const tasks = await call("task.list");
    assert(tasks.length > 0);
    checks.push(
      "native sketch/pad/save; shared document revision in scene, tree and check receipts; edit invalidates previous checks",
    );
    fs.writeFileSync(
      path.join(output, "geometry.json"),
      JSON.stringify(
        {
          before: inspect,
          after,
          scene_revision: scene.revision,
          check: checked,
          old_check: old,
        },
        null,
        2,
      ),
    );
    await app.close();
    app = null;
    await launchHost(path.join(project, "plate.FCStd"));
    await launch();
    await choose(project, false);
    current = await call("project.current");
    assert(current.files.some((f) => f.name === "plate.FCStd"));
    assert((await call("task.list")).length >= tasks.length);
    await page.getByText("原生 CAD", { exact: true }).click();
    await page
      .getByRole("button", { name: "连接 FreeCAD", exact: true })
      .click();
    await page
      .getByRole("button", { name: "读取 FreeCAD 工程", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Profile · 草图", exact: true })
      .waitFor();
    await shot("reopened-project");
    await choose(other, true, true);
    current = await call("project.current");
    assert.equal(current.task, null);
    assert.deepEqual(current.results, []);
    assert.deepEqual(await call("task.list"), []);
    assert.doesNotMatch(
      await page.locator("body").innerText(),
      /plate.pdf|板厚|Profile|减速器|课程设计/,
    );
    await shot("isolated-empty-project");
    checks.push(
      "restart restores saved project and receipts; new project isolates files, tabs and tasks",
    );
    const status = await call("system.status");
    if (env.GONGKE_TEST_EXECUTABLE) assert.equal(status.packaged, true);
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(output, "result.json"),
      JSON.stringify(
        { ok: true, width, height, packaged: status.packaged, checks, errors },
        null,
        2,
      ),
    );
    console.log(JSON.stringify({ ok: true, output }));
  } catch (error) {
    fs.writeFileSync(
      path.join(output, "failure.json"),
      JSON.stringify({ error: String(error), stack: error.stack }, null, 2),
    );
    if (page && !page.isClosed())
      await page
        .screenshot({ path: path.join(output, "failure.png") })
        .catch(() => {});
    throw error;
  } finally {
    try {
      if (app) await app.close();
    } finally {
      if (host && host.exitCode === null) {
        host.kill("SIGTERM");
        await Promise.race([
          new Promise((r) => host.once("exit", r)),
          delay(4000),
        ]);
        if (host.exitCode === null) host.kill("SIGKILL");
      }
    }
  }
};
