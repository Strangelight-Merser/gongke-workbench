// 真实 Electron/Python/文件；仅模型服务由本机 SSE 替身提供，不计真实账号验收。
const { _electron: electron } = require("playwright");
const fs = require("node:fs"),
  path = require("node:path"),
  http = require("node:http");
const assert = require("node:assert/strict");
const output = path.resolve(
  __dirname,
  "../../out/workflow-validation",
  Date.now().toString(),
);
fs.mkdirSync(output, { recursive: true });
const project = path.join(output, "我的课程工程"),
  other = path.join(output, "另一个工程");
fs.mkdirSync(project);
fs.mkdirSync(other);
const requests = [];
const server = http.createServer((req, res) => {
  let body = "";
  req.on("data", (part) => (body += part));
  req.on("end", () => {
    const payload = JSON.parse(body);
    requests.push(payload);
    fs.appendFileSync(
      path.join(output, "model-requests.jsonl"),
      JSON.stringify(payload) + "\n",
    );
    const last = payload.messages.at(-1);
    const reply =
      last.role === "tool"
        ? { content: "已核对实际工程，保留候选 B；尚未修改。" }
        : {
            tool_calls: [
              {
                index: 0,
                id: "read-" + requests.length,
                type: "function",
                function: { name: "project_current", arguments: "{}" },
              },
            ],
          };
    res.writeHead(200, { "Content-Type": "text/event-stream" });
    res.end(
      "data: " +
        JSON.stringify({
          choices: [
            {
              delta: reply,
              finish_reason: last.role === "tool" ? "stop" : "tool_calls",
            },
          ],
        }) +
        "\n\ndata: [DONE]\n\n",
    );
  });
});
let app, page;
async function launch() {
  const env = {
    ...process.env,
    GONGKE_DESKTOP_USER_DATA: path.join(output, "user"),
  };
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.PYTHONHOME;
  delete env.PYTHONPATH;
  app = await electron.launch({
    ...(process.env.GONGKE_TEST_EXECUTABLE
      ? { executablePath: process.env.GONGKE_TEST_EXECUTABLE, args: [] }
      : { args: [path.resolve(__dirname, "..")] }),
    cwd: output,
    env,
  });
  page = await app.firstWindow();
  page.setDefaultTimeout(15000);
  await page.getByText("工程服务运行中", { exact: true }).waitFor();
}
async function choose(target, create) {
  await app.evaluate(({ dialog }, value) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [value],
    });
  }, target);
  await page
    .getByRole("button", {
      name: create ? "新建工程" : "打开工程",
      exact: true,
    })
    .click();
  await page.locator("footer").getByText(target, { exact: true }).waitFor();
}
async function until(read, timeout = 240000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await read()) return;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("workflow condition timed out");
}
async function settled(kind) {
  await until(async () => {
    const tasks = await page.evaluate(() => window.gongke.request("task.list"));
    const finished = tasks.find((t) => t.kind === kind && !["queued", "running"].includes(t.status));
    if (finished) assert.equal(finished.status, "complete", JSON.stringify(finished));
    return !!finished && !tasks.some((t) => ["queued", "running"].includes(t.status));
  });
}
(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  try {
    await launch();
    await choose(project, true);
    assert.equal(await page.getByLabel("工作拉力 / N").inputValue(), "");
    await page.getByLabel("工作拉力 / N").fill("2500");
    await page.getByLabel("带速 / m·s⁻¹").fill("1.4");
    await page.getByLabel("卷筒直径 / mm").fill("400");
    await page.getByRole("button", { name: "计算方案", exact: true }).click();
    await page
      .getByRole("button", { name: /^电动机与传动比/ })
      .filter({ hasText: "Y132S-4" })
      .waitFor();
    assert.equal(
      (await page.evaluate(() => window.gongke.request("project.current")))
        .teaching,
      false,
    );
    await page.screenshot({ path: path.join(output, "task.png") });
    await page
      .getByRole("button", { name: "生成模型与图纸", exact: true })
      .click();
    await settled("generation");
    await page
      .getByRole("button", { name: /^图纸/ })
      .filter({ hasText: "9 张" })
      .waitFor();
    const original = await page.evaluate(() =>
      window.gongke.request("project.current"),
    );
    assert.ok(
      fs.existsSync(path.join(project, original.delivery.path, "report.docx")),
    );
    assert.ok(
      fs.existsSync(
        path.join(project, original.delivery.path, "reducer_assembly.step"),
      ),
    );
    await page.getByLabel("工作拉力 / N").fill("2600");
    await page.getByRole("button", { name: "计算方案", exact: true }).click();
    await page
      .getByRole("button", { name: /^图纸/ })
      .filter({ hasText: "旧成果已过期" })
      .waitFor();
    await page.getByRole("button", { name: /^图纸/ }).click();
    await page.getByRole("heading", { name: /已过期/ }).waitFor();
    await page.screenshot({ path: path.join(output, "stale-revision.png") });
    await page.getByRole("button", { name: /^传动零件/ }).click();
    await page.locator(".ck").first().click();
    await page.evaluate(
      async (base_url) =>
        window.gongke.configure({
          base_url,
          model: "local-protocol-fixture",
          api_key: "fixture-only",
        }),
      `http://127.0.0.1:${server.address().port}/v1`,
    );
    assert.equal((await page.evaluate(() => window.gongke.settings())).has_key, false);
    assert.ok(!fs.readFileSync(path.join(output, "user/provider.json"), "utf8").includes("fixture-only"));
    await page.getByLabel("工程任务").fill("选择候选 B，只核对，不修改。");
    await page.getByRole("button", { name: "发送 ↑", exact: true }).click();
    await settled("agent");
    await page
      .locator(".conversation .message.assistant")
      .filter({ hasText: "已核对实际工程，保留候选 B；尚未修改。" })
      .waitFor();
    assert.ok(
      requests[0].messages.some((m) => m.content?.includes("齿面接触")),
    );
    await app.close();
    app = null;
    await launch();
    await choose(project, false);
    await page
      .locator(".conversation .message.user")
      .filter({ hasText: "选择候选 B，只核对，不修改。" })
      .waitFor();
    await page.evaluate(
      async (base_url) =>
        window.gongke.configure({
          base_url,
          model: "local-protocol-fixture",
          api_key: "fixture-only",
        }),
      `http://127.0.0.1:${server.address().port}/v1`,
    );
    await page.getByLabel("工程任务").fill("继续刚才的候选，再核对一次。");
    await page.getByRole("button", { name: "发送 ↑", exact: true }).click();
    await until(async () => {
      const history = await page.evaluate(() =>
        window.gongke.request("agent.history"),
      );
      return (
        history.turns.length === 2 &&
        history.turns.every((t) => t.status === "complete") &&
        requests.length === 4
      );
    });
    assert.ok(
      requests[2].messages.some(
        (m) => m.role === "user" && m.content.includes("选择候选 B"),
      ),
    );
    assert.ok(requests[2].messages.some((m) => m.role === "tool"));
    await page.screenshot({
      path: path.join(output, "conversation-reopened.png"),
    });
    await choose(other, true);
    await page.waitForFunction(
      () => document.querySelectorAll(".conversation .message").length === 0,
    );
    assert.equal(
      (await page.evaluate(() => window.gongke.request("agent.history"))).turns
        .length,
      0,
    );
    fs.writeFileSync(
      path.join(output, "result.json"),
      JSON.stringify(
        {
          ok: true,
          output,
          packaged: !!process.env.GONGKE_TEST_EXECUTABLE,
          checks: [
            "blank_task_entry",
            "real_calculation",
            "step_drawings_docx",
            "old_outputs_stale",
            "selected_check_context",
            "conversation_reopen",
            "tool_history_continuity",
            "project_isolation",
            "session_only_key_not_persisted",
          ],
          model: "local SSE fixture, not a real model account",
          requests: requests.length,
        },
        null,
        2,
      ),
    );
    console.log(JSON.stringify({ ok: true, output }));
  } catch (error) {
    if (page)
      await page
        .screenshot({ path: path.join(output, "failure.png") })
        .catch(() => {});
    fs.writeFileSync(
      path.join(output, "failure.json"),
      JSON.stringify({ error: String(error), stack: error.stack }, null, 2),
    );
    throw error;
  } finally {
    if (app) await app.close();
    server.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
