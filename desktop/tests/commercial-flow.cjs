// Browser UI contract checks with a mocked service boundary; no native CAD host is exercised.
// Run after npm run build; install Playwright Chromium or set GONGKE_TEST_BROWSER.
const { chromium } = require("playwright");
const http = require("node:http"),
  fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const root = path.resolve(__dirname, "../dist");
const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, "http://localhost").pathname;
  const file = path.join(root, pathname === "/" ? "index.html" : pathname);
  try {
    res.setHeader(
      "Content-Type",
      file.endsWith(".js")
        ? "text/javascript"
        : file.endsWith(".css")
          ? "text/css"
          : "text/html",
    );
    res.end(fs.readFileSync(file));
  } catch {
    res.statusCode = 404;
    res.end();
  }
});
(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.GONGKE_TEST_BROWSER
      ? { executablePath: process.env.GONGKE_TEST_BROWSER }
      : {}),
  });
  try {
    const page = await browser.newPage();
    page.setDefaultTimeout(8000);
    await page.addInitScript(() => {
      window.check = {
        calls: [],
        revision: 5,
        failText: false,
        failInspect: false,
        workingCopies: [],
        registerImport: false,
        saveMode: "needs_review",
        registerPair: false,
        acPath: "C:/work/drawing.dwg",
      };
      const ac = () => ({
        document_id: "ac-doc",
        path: window.check.acPath,
        active: true,
        revision: window.check.revision,
        units: "Millimeters",
        dirty: true,
      });
      const sw = {
        path: "C:/Course/Drawing.slddrw",
        document_type: 3,
        revision: 9,
        configuration: null,
        dirty: false,
      };
      const textEntity = (handle) => ({
        handle,
        type: "TEXT",
        layout: "Model",
        visible: true,
        editable: true,
        text: "note",
        geometry: { position: [1, 2, 0], height: 2, rotation: 0 },
        bounds: { min: [0, 0, 0], max: [10, 5, 0] },
      });
      const dimension = {
        handle: "B",
        type: "DIMENSION",
        layout: "Model",
        visible: true,
        editable: true,
        text_position: [1, 2, 0],
        geometry: { first: [0, 0, 0], second: [10, 0, 0] },
        bounds: { min: [0, 0, 0], max: [10, 5, 0] },
      };
      window.gongke = {
        onEvent: () => () => {},
        chooseProject: async () => null,
        settings: async () => ({}),
        request: async (method, params = {}) => {
          if (method === "system.status")
            return { ready: true, agent: { configured: false } };
          if (method === "project.current")
            return {
              name: "UI fixture",
              path: "/fixture",
              files: [
                { path: "input/shaft.dxf", name: "shaft.dxf", kind: "dxf" },
              ],
              working_copies: window.check.workingCopies,
              teaching: true,
            };
          if (method === "task.list") return [];
          if (method === "hosts.list")
            return {
              hosts: [
                { host: "autocad", host_id: "autocad-1", connected: true },
                {
                  host: "solidworks",
                  host_id: "solidworks-1",
                  connected: true,
                },
              ],
            };
          if (method !== "host.command") return {};
          const { method: m, params: p } = params;
          window.check.calls.push(params);
          if (m === "documents.list") return { documents: [ac()] };
          if (m === "document.snapshot")
            return {
              document: ac(),
              entities: p.offset
                ? [textEntity("C")]
                : [textEntity("A"), dimension],
              next_offset: p.offset ? null : 2,
              total_entities: 3,
              revision: window.check.revision,
            };
          if (m === "document.select") return { selected: true };
          if (m === "drawing.move_dimension_text") {
            window.check.revision++;
            return {
              outcome: "committed",
              operation_id: p.operation_id,
              document: ac(),
            };
          }
          if (m === "drawing.edit_text" && window.check.rejectText)
            return {
              error: {
                code: "command_not_submitted",
                message: "请先保存并打开新的工作副本",
                outcome: "not_applied",
              },
            };
          if (m === "drawing.edit_text")
            return {
              error: {
                code: "host_error",
                message: "fixture lost result",
                outcome: "unknown",
              },
            };
          if (m === "drawing.import_dxf") {
            window.check.importRequest = params;
            throw new Error("fixture import response lost");
          }
          if (m === "operation.status") {
            const original = window.check.importRequest;
            if (original && p.operation_id === original.params.operation_id) {
              if (window.check.queryUnknown)
                return {
                  status: "failed",
                  outcome: "unknown",
                  response: {
                    id: "old",
                    error: {
                      message: "fixture remains unknown",
                      outcome: "unknown",
                    },
                  },
                };
              if (window.check.registerImport)
                window.check.workingCopies = [
                  {
                    path: original.params.target_path,
                    host: "autocad",
                    operation_id: p.operation_id,
                  },
                ];
              return {
                status: "completed",
                outcome: "committed",
                response: {
                  id: "old",
                  result: {
                    operation_id: p.operation_id,
                    outcome: "committed",
                    path: "/fixture/" + original.params.target_path,
                  },
                },
              };
            }
            return {
              status: "completed",
              outcome: "committed",
              response: {
                id: "old",
                result: { operation_id: p.operation_id, outcome: "committed" },
              },
            };
          }
          if (m === "document.open") {
            if (params.host_id === "autocad-1")
              window.check.acPath = "/fixture/" + p.path;
            else sw.path = "/fixture/" + p.document_path;
            return { opened: true };
          }
          if (m === "operation.get") {
            const original = window.check.swCopy;
            const paths = [
              original.params.output_path,
              ...(window.check.registerPair
                ? [original.params.output_part_path]
                : []),
            ];
            window.check.workingCopies = paths.map((path) => ({
              path,
              host: "solidworks",
              operation_id: p.operation_id,
            }));
            return {
              state: "finished",
              response: {
                id: "old",
                result: {
                  status: "saved",
                  operation_id: p.operation_id,
                  path: "/fixture/" + original.params.output_path,
                  references_verified: true,
                },
              },
            };
          }
          if (m === "document.context")
            return {
              session_id: "sw-session",
              active_document: sw,
              documents: [
                sw,
                {
                  path: "C:/COURSE/SHAFT.SLDPRT",
                  revision: 7,
                  configuration: "Default",
                },
              ],
            };
          if (m === "drawing.inspect") {
            if (window.check.failInspect)
              return {
                error: {
                  message: "fixture inspection failed",
                  outcome: "not_applied",
                },
              };
            return {
              active_sheet: "Sheet2",
              sheets: [
                { name: "Cover", views: [] },
                {
                  name: "Sheet2",
                  views: [
                    {
                      model_path: "c:\\course\\shaft.sldprt",
                      configuration: "Default",
                    },
                  ],
                },
              ],
            };
          }
          if (m === "document.save_copy") {
            if (window.check.saveMode === "unknown") {
              window.check.swCopy = params;
              return {
                error: {
                  message: "fixture saved response lost",
                  outcome: "unknown",
                },
              };
            }
            return {
              status: "needs_review",
              path: p.output_path,
              references_verified: false,
            };
          }
          if (m === "drawing.update") return { rebuilt: false, document: sw };
          throw new Error("unexpected fixture method " + m);
        },
      };
    });
    await page.goto("http://127.0.0.1:" + server.address().port);
    await page.getByLabel("原生软件").selectOption("autocad");
    await page
      .getByRole("button", { name: "读取当前工程", exact: true })
      .click();
    await page
      .getByRole("button", { name: "DIMENSION · B", exact: true })
      .waitFor();
    await page.getByRole("button", { name: "继续读取", exact: true }).click();
    await page.getByRole("button", { name: "TEXT · C", exact: true }).waitFor();
    let calls = await page.evaluate(() => window.check.calls);
    assert(
      calls.some(
        (c) =>
          c.method === "document.snapshot" &&
          c.params.offset === 2 &&
          c.params.expected_revision === 5,
      ),
    );
    await page
      .getByRole("button", { name: "DIMENSION · B", exact: true })
      .click();
    await page.getByLabel("标注文字 X").fill("12");
    await page.getByLabel("标注文字 Y").fill("34");
    await page.getByLabel("标注文字 Z").fill("0");
    await page
      .getByRole("button", { name: "移动标注文字并读回", exact: true })
      .click();
    await page.getByRole("button", { name: "TEXT · A", exact: true }).waitFor();
    calls = await page.evaluate(() => window.check.calls);
    assert.deepEqual(
      calls.find((c) => c.method === "drawing.move_dimension_text").params
        .position,
      [12, 34, 0],
    );
    await page.getByRole("button", { name: "TEXT · A", exact: true }).click();
    await page.getByLabel("文字", { exact: true }).fill("new note");
    await page.evaluate(() => (window.check.rejectText = true));
    await page.getByRole("button", { name: "更新文字", exact: true }).click();
    await page
      .getByText("请先保存并打开新的工作副本", { exact: true })
      .waitFor();
    assert.equal(
      await page.evaluate(() =>
        localStorage.getItem("gongke-native-unresolved-autocad"),
      ),
      null,
    );
    assert.equal(
      await page
        .getByText("原操作结果待确认，修改已暂停", { exact: true })
        .count(),
      0,
    );
    assert.equal(
      await page
        .getByRole("button", { name: "另存工作修订", exact: true })
        .isDisabled(),
      false,
    );
    await page.evaluate(() => (window.check.rejectText = false));
    await page.getByRole("button", { name: "更新文字", exact: true }).click();
    await page
      .getByText("原操作结果待确认，修改已暂停", { exact: true })
      .waitFor();
    assert(
      await page
        .getByRole("button", { name: "另存工作修订", exact: true })
        .isDisabled(),
    );
    const pending = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("gongke-native-unresolved-autocad")),
    );
    assert(pending.operation_id);
    await page
      .getByRole("button", { name: "查询原操作结果", exact: true })
      .click();
    await page
      .getByRole("button", { name: "读取当前工程", exact: true })
      .waitFor();
    calls = await page.evaluate(() => window.check.calls);
    assert.equal(
      calls.filter(
        (c) =>
          c.method === "drawing.edit_text" &&
          c.params.operation_id === pending.operation_id,
      ).length,
      1,
    );
    assert.equal(
      calls.find((c) => c.method === "operation.status").params.operation_id,
      pending.operation_id,
    );
    await page.getByLabel("原生软件").selectOption("solidworks");
    await page
      .getByRole("button", { name: "读取当前工程", exact: true })
      .click();
    await page
      .getByRole("button", { name: "另存工作修订", exact: true })
      .click();
    await page
      .getByText(
        "原生操作需要复核。请检查完整回执，并重新读取当前模型或图纸；修改暂时停用。",
        { exact: true },
      )
      .waitFor();
    calls = await page.evaluate(() => window.check.calls);
    assert.equal(
      calls.find((c) => c.method === "document.save_copy").params
        .expected_part_revision,
      7,
    );
    assert(
      await page
        .getByRole("button", { name: "导出当前页 DXF", exact: true })
        .isDisabled(),
    );
    await page
      .getByRole("button", { name: "读取当前工程", exact: true })
      .click();
    await page.getByRole("button", { name: "更新图纸", exact: true }).click();
    await page
      .getByText(
        "原生操作需要复核。请检查完整回执，并重新读取当前模型或图纸；修改暂时停用。",
        { exact: true },
      )
      .waitFor();
    await page.evaluate(() => (window.check.failInspect = true));
    await page
      .getByRole("button", { name: "读取当前工程", exact: true })
      .click();
    await page
      .getByText("fixture inspection failed", { exact: true })
      .waitFor();
    assert.equal(
      await page.getByRole("button", { name: "更新图纸", exact: true }).count(),
      0,
    );
    // Import response loss must navigate to the existing pending UI, never replay the mutation.
    await page
      .locator(".files button")
      .filter({ hasText: "shaft.dxf" })
      .click();
    await page
      .getByRole("button", { name: "导入 AutoCAD 工作修订", exact: true })
      .click();
    await page
      .getByText("原操作结果待确认，修改已暂停", { exact: true })
      .waitFor();
    const imported = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("gongke-native-unresolved-autocad")),
    );
    assert.equal(imported.method, "drawing.import_dxf");
    assert.equal(imported.error.outcome, "unknown");
    await page
      .locator(".files button")
      .filter({ hasText: "shaft.dxf" })
      .click();
    await page
      .getByRole("button", { name: "导入 AutoCAD 工作修订", exact: true })
      .click();
    await page.evaluate(() => (window.check.queryUnknown = true));
    await page
      .getByRole("button", { name: "查询原操作结果", exact: true })
      .click();
    await page
      .getByText("原操作结果待确认，修改已暂停", { exact: true })
      .waitFor();
    assert.equal(
      (await page.evaluate(() => window.check.calls)).filter(
        (c) => c.method === "document.open",
      ).length,
      0,
    );
    await page.evaluate(() => (window.check.queryUnknown = false));
    await page
      .getByRole("button", { name: "查询原操作结果", exact: true })
      .click();
    await page
      .getByText("工作副本尚未完成工程登记；保留原操作，请查询核对后继续", {
        exact: true,
      })
      .waitFor();
    calls = await page.evaluate(() => window.check.calls);
    assert.equal(
      calls.filter((c) => c.method === "drawing.import_dxf").length,
      1,
    );
    assert.equal(calls.filter((c) => c.method === "document.open").length, 0);
    await page.evaluate(() => (window.check.registerImport = true));
    await page
      .getByRole("button", { name: "查询原操作结果", exact: true })
      .click();
    await page.getByRole("button", { name: "TEXT · A", exact: true }).waitFor();
    assert.equal(
      await page
        .getByText("原操作结果待确认，修改已暂停", { exact: true })
        .count(),
      0,
    );
    calls = await page.evaluate(() => window.check.calls);
    assert(
      calls
        .filter((c) => c.method === "operation.status")
        .slice(-2)
        .every((c) => c.params.operation_id === imported.operation_id),
    );
    assert.equal(
      calls.find((c) => c.method === "document.open").params.path,
      imported.params.target_path,
    );
    assert.equal(
      await page.evaluate(() =>
        localStorage.getItem("gongke-native-unresolved-autocad"),
      ),
      null,
    );
    // Paired SOLIDWORKS recovery requires registration of BOTH original requested outputs.
    await page.evaluate(() => {
      window.check.failInspect = false;
      window.check.saveMode = "unknown";
    });
    await page.getByLabel("原生软件").selectOption("solidworks");
    await page
      .getByRole("button", { name: "读取当前工程", exact: true })
      .click();
    await page
      .getByRole("button", { name: "另存工作修订", exact: true })
      .click();
    await page
      .getByText("原操作结果待确认，修改已暂停", { exact: true })
      .waitFor();
    const saved = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("gongke-native-unresolved-solidworks")),
    );
    await page
      .getByRole("button", { name: "查询原操作结果", exact: true })
      .click();
    await page
      .getByText("工作副本尚未完成工程登记；保留原操作，请查询核对后继续", {
        exact: true,
      })
      .waitFor();
    calls = await page.evaluate(() => window.check.calls);
    assert.equal(
      calls.filter(
        (c) => c.method === "document.open" && c.host_id === "solidworks-1",
      ).length,
      0,
    );
    await page.evaluate(() => (window.check.registerPair = true));
    await page
      .getByRole("button", { name: "查询原操作结果", exact: true })
      .click();
    await page.getByRole("button", { name: "更新图纸", exact: true }).waitFor();
    assert.equal(
      await page
        .getByText("原操作结果待确认，修改已暂停", { exact: true })
        .count(),
      0,
    );
    calls = await page.evaluate(() => window.check.calls);
    assert.equal(
      calls.find(
        (c) => c.method === "document.open" && c.host_id === "solidworks-1",
      ).params.document_path,
      saved.params.output_path,
    );
    assert.equal(
      calls.filter(
        (c) =>
          c.method === "document.save_copy" &&
          c.params.operation_id === saved.operation_id,
      ).length,
      1,
    );
    console.log(
      "Commercial UI mock-host checks passed: pagination, XYZ, preflight rejection stays unlocked, pending lock/query without replay, all-sheet SW source match, needs-review, stale refresh clear, DXF response loss and same-ID recovery, registration gate, verified AutoCAD/SW paired-copy reopen+read. No native CAD host was exercised.",
    );
  } finally {
    await browser.close();
    server.close();
  }
})().catch((e) => {
  console.error(e);
  server.close();
  process.exitCode = 1;
});
