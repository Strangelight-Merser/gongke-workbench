// 沙箱外真实桌面验收。工程写入只由真实 dsh 发起；自动点击授权仅用于隔离工程试验。
const { electron } = require("./helpers/owned-electron.cjs");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { collectDshSession } = require("./helpers/dsh-session.cjs");
const { AgentConfiguration } = require("../dist-electron/acp/settings.cjs");
const { redactRecord } = require("../dist-electron/acp/diagnostics.cjs");
const {
  waitForReady,
  verifyInput,
  turnResult,
  engineeringPermission,
  visionModelOption,
  compareVision,
  saveAgentDiagnostics,
} = require("./helpers/modeling-trial.cjs");
const root = path.resolve(__dirname, "../..");
const output = process.env.GONGKE_TRIAL_OUTPUT;
if (!output) throw Error("请从 scripts/agent_modeling_trial.py 启动");
const manifest = JSON.parse(
  fs.readFileSync(path.join(output, "manifest.json"), "utf8"),
);
const write = (file, value) =>
  fs.writeFileSync(file, JSON.stringify(redactRecord(value), null, 2) + "\n");
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

function audit(directory, stateDir, project, caseName) {
  return new Promise((resolve, reject) => {
    const log = fs.openSync(path.join(directory, "audit.log"), "w");
    const child = spawn(
      process.env.GONGKE_PYTHON,
      [
        path.join(root, "tests/e2e/agent_modeling_check.py"),
        "--state-dir",
        stateDir,
        "--project",
        project,
        "--case",
        caseName,
        "--study",
        process.env.GONGKE_TRIAL_STUDY,
        "--output",
        directory,
        "--delivery",
        manifest.delivery,
        "--input-sha256",
        (manifest.delivery === "dimensions"
          ? manifest.structured
          : manifest.crops)[caseName].sha256,
      ],
      {
        cwd: root,
        env: process.env,
        stdio: ["ignore", log, log],
      },
    );
    fs.closeSync(log);
    const timer = setTimeout(() => child.kill(), 180_000);
    child.once("error", (e) => {
      clearTimeout(timer);
      reject(e);
    });
    child.once("exit", (code) => {
      clearTimeout(timer);
      const file = path.join(directory, "audit.json");
      if (!fs.existsSync(file))
        return reject(Error(`独立检查未留下报告，退出 ${code}；见 audit.log`));
      try {
        const report = JSON.parse(fs.readFileSync(file, "utf8"));
        resolve({
          ...report,
          process_exit: code,
          accepted: code === 0 && report.accepted === true,
        });
      } catch (error) {
        reject(error);
      }
    });
  });
}

async function trial(caseName, repetition) {
  const directory = path.join(output, `${caseName}-${repetition}`);
  const user = path.join(directory, "user"),
    project = path.join(directory, "project");
  fs.mkdirSync(user, { recursive: true });
  const configuration = new AgentConfiguration(user, root);
  const config = configuration.read();
  config.agents = config.agents.filter((a) => a.id === "deepseek");
  config.agents[0].command = process.env.GONGKE_TRIAL_DSH;
  configuration.save(config);
  if (manifest.acp_initial_model) {
    // dsh 的图片接收门在 initialize 时锁定；会话内选模不会更新该门。
    // 仅修改本轮隔离 patch，沿用 dsh 既有 provider 和凭据。
    const patch =
      config.agents[0].args[config.agents[0].args.indexOf("--patch") + 1];
    fs.appendFileSync(
      patch,
      "- id: acp\n  config:\n    provider: deepseek-official\n    model: deepseek-flash\n",
    );
  }
  const evidence = {
    case: caseName,
    repetition,
    delivery: manifest.delivery,
    input_scope: manifest.input_scope,
    acp_initial_model: manifest.acp_initial_model,
    status: "failed",
    started_at: new Date().toISOString(),
    permissions: [],
    errors: [],
  };
  const start = Date.now();
  let app, page, lastState, promptStart;
  const stage = (name) => {
    evidence.stage = name;
    const row = { at: new Date().toISOString(), stage: name };
    fs.appendFileSync(
      path.join(directory, "lifecycle.jsonl"),
      JSON.stringify(row) + "\n",
    );
    console.log(`${caseName}-${repetition}: ${name}`);
  };
  let lastTransition;
  const readState = async () => {
    lastState = await page.evaluate(() => window.gongke.agent.state());
    const row = {
      stage: evidence.stage,
      phase: lastState.phase,
      sessionId: lastState.session?.sessionId,
      error: lastState.error,
      eventCount: lastState.events.length,
    };
    const key = JSON.stringify([
      row.stage,
      row.phase,
      row.sessionId,
      row.error,
    ]);
    if (key !== lastTransition) {
      fs.appendFileSync(
        path.join(directory, "lifecycle.jsonl"),
        JSON.stringify(redactRecord({ at: new Date().toISOString(), ...row })) +
          "\n",
      );
      lastTransition = key;
    }
    return lastState;
  };
  try {
    stage("launch");
    app = await electron.launch({
      args: [path.join(root, "desktop"), `--user-data-dir=${user}`],
      env: {
        ...process.env,
        GONGKE_DESKTOP_USER_DATA: user,
        GONGKE_AGENT_CONFIG: configuration.path,
      },
    });
    page = await app.firstWindow();
    page.setDefaultTimeout(30_000);
    page.on("pageerror", (e) => evidence.errors.push(String(e)));
    await page.waitForFunction(() => !!window.gongke);
    await page.evaluate(
      (p) => window.gongke.request("project.create", { path: p }),
      project,
    );
    await page.reload();
    stage("drawing");
    // 仅替代系统文件选择器；真正点击产品的“打开图纸”，走主进程导入和预览。
    await app.evaluate(({ dialog }, image) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [image],
      });
    }, manifest.crops[caseName].path);
    await page.getByRole("button", { name: "导入图纸", exact: true }).click();
    if (manifest.delivery === "pdf") {
      await page
        .getByLabel("PDF 图纸", { exact: true })
        .locator("canvas")
        .waitFor();
    } else {
      await page.waitForFunction(() =>
        [...document.images].some(
          (im) =>
            im.src.startsWith("data:image/") &&
            im.complete &&
            im.naturalWidth > 0,
        ),
      );
    }
    const current = await page.evaluate(() =>
      window.gongke.request("project.current"),
    );
    const drawing = current.files.find(
      (f) =>
        f.name === `${caseName}.${manifest.delivery === "pdf" ? "pdf" : "png"}`,
    ).path;
    evidence.drawing = drawing;
    await page.screenshot({ path: path.join(directory, "drawing.png") });
    let reference = drawing;
    if (manifest.delivery === "dimensions") {
      stage("structured-input");
      await app.evaluate(({ dialog }, file) => {
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [file],
        });
      }, manifest.structured[caseName].path);
      await page.getByRole("button", { name: "导入图纸", exact: true }).click();
      await page
        .locator(".file-path", { hasText: `${caseName}-dimensions.json` })
        .waitFor();
      const files = await page.evaluate(() =>
        window.gongke.request("project.files"),
      );
      reference = files.find(
        (f) => f.name === `${caseName}-dimensions.json`,
      ).path;
      evidence.dimensions = reference;
      await page.screenshot({ path: path.join(directory, "dimensions.png") });
    }
    await page
      .getByRole("button", { name: "Agent 连接设置", exact: true })
      .click();
    await page
      .getByRole("menuitem", { name: "使用已配置的 Agent", exact: true })
      .click();
    await page
      .getByLabel("选择 Agent", { exact: true })
      .selectOption("deepseek");
    stage("connect");
    await page.getByRole("button", { name: "连接", exact: true }).click();
    let state = await waitForReady(async () => {
      const state = await readState();
      const alerts = await page.getByRole("alert").allTextContents();
      if (alerts.length) throw Error(alerts.join("\n"));
      return state;
    });
    write(path.join(directory, "initialization.json"), state);
    if (state.project !== project || state.agentId !== "deepseek")
      throw Error("Agent 绑定的工程或配置与本轮不符");
    evidence.connected = true;
    evidence.session_id = state.session.sessionId;
    if (manifest.acp_initial_model) {
      stage("select-trial-model");
      const selection = visionModelOption(state);
      write(path.join(directory, "model-selection-request.json"), selection);
      await page.evaluate(
        ({ configId, value }) =>
          window.gongke.agent.setConfigOption(configId, value),
        selection,
      );
      state = await readState();
      write(path.join(directory, "model-selection-result.json"), state);
      if (
        state.session.configOptions.find((c) => c.id === selection.configId)
          ?.currentValue !== selection.value
      )
        throw Error("Agent 未确认切换到 deepseek-flash");
      evidence.model_selection = selection;
      evidence.advertised_image =
        state.initialization?.agentCapabilities?.promptCapabilities?.image;
    }
    if (manifest.reasoning) {
      const option = state.session.configOptions.find(
        (c) => c.id === "reasoning_effort",
      );
      if (
        !option ||
        !option.options.some((o) => o.value === manifest.reasoning)
      )
        throw Error("Agent 未提供所选推理强度：" + manifest.reasoning);
      await page.evaluate(
        ({ id, value }) => window.gongke.agent.setConfigOption(id, value),
        { id: option.id, value: manifest.reasoning },
      );
      state = await readState();
      write(path.join(directory, "reasoning-selection-result.json"), state);
      if (
        state.session.configOptions.find((c) => c.id === option.id)
          ?.currentValue !== manifest.reasoning
      )
        throw Error("Agent 未确认推理强度");
      evidence.reasoning = manifest.reasoning;
    }
    const coordinate = {
      p7: "为便于复核，以槽左端圆心为 XY 原点，X 指向右侧圆筒，底面 z=0。",
      p8: "为便于复核，以鼻端底孔圆心为 XY 原点，X 指向后立板，底面 z=0。",
      p6: "以底板左前下角为原点，X 向右、Y 向后、Z 向上。",
      robot4:
        "以主视图水平和竖直中心线交点为 XY 原点，轮廓置于 XY 面，X 向右、Y 向图上方，底面 Z=0，厚度沿 +Z。",
      robot14:
        "以大平板左前下角为原点，主视图轮廓放在 XY 面，X 向右、Y 向图上方，凸柱沿 +Z。",
      robot13:
        "以主视图左右中心为 X=0、底面为 Z=0、前端为 Y=0；主视图轮廓置于 XZ 面，Y 向后。",
    }[caseName];
    let prompt =
      `根据${manifest.delivery === "dimensions" ? "这份从图纸人工提取的尺寸说明" : "这张图"}建模。只做这个零件，在 FreeCAD 中建立可编辑的原生草图和特征树，保存到当前工程 ${caseName}.FCStd。\n` +
      `先说明读出的标注尺寸、推导关系和看不清或缺失的尺寸；本次无标题栏，单位暂按 mm，推断必须明确说明。不要读取其他工程或参考答案，不使用 shell、脚本或导入实体。${coordinate}\n` +
      "通过构想引擎 MCP 完成建模；使用检查工具对照图纸逐项自查，发现问题就修正，最后保存并告诉我建了什么、哪些尺寸为推断、哪些还没确认。看不清时不要伪造确定尺寸。" +
      (manifest.delivery === "dimensions"
        ? `\n实际尺寸说明已随当前参考发送，可按需要通过工程工具继续查看 ${reference}。本次只检验你自行规划、建模和自查，不声称你看到了照片。说明中的推断按假设试建并在最终答复保留。`
        : manifest.delivery === "mcp"
          ? `\n图纸位于 ${drawing}，请先用 project.read_image 读取图片。`
          : "");
    if (manifest.delivery === "pdf") {
      prompt =
        `根据当前矢量 PDF 的这一个零件建模，保存到当前工程 ${caseName}.FCStd。原始图纸第 ${manifest.crops[caseName].source_page} 页已在本地摘为单页，文件 ${drawing}。` +
        "只使用 project.read_drawing 的矢量几何、尺寸文字与位置理解图纸；不使用图片/截图/OCR，不读其他工程或参考模型。当前参考已包含解析结果，按 next_offset 补齐该页即可，不重复读同一批。" +
        "页面坐标 pt 不等于 mm。标注文字可能含旋转、由矢量绘制的符号；结合视图边线、引线与投影关系，先列各正投影视图在页面的位置、对应的模型平面及尺寸链，再简要列关键尺寸和不确定项，自行规划原生特征。不要默认左上就是主视图，不得擅自交换指定模型轴；小尺寸与凹口不能因难解释而省略后声称完成。" +
        coordinate +
        "使用构想引擎 MCP 创建草图/特征，长度传 m。一次草图提交完整轮廓和必要约束，不追求全约束；检查依据图纸，合并 host.check 条件，最后保存并简短列结果和推断。";
    }
    if (manifest.delivery === "mcp") {
      // 切离图纸，明确测试 MCP 图片工具；不同时偷偷附上 ACP 图片。
      await page.getByRole("button", { name: "进入建模", exact: true }).click();
    }
    evidence.turns = [];
    async function runTurn(name, prompt, attachInput) {
      const firstEvent = (await readState()).events.length;
      fs.writeFileSync(path.join(directory, `${name}-prompt.txt`), prompt);
      await page.getByLabel("工程任务", { exact: true }).fill(prompt);
      stage(name);
      const turnStart = Date.now();
      promptStart ??= turnStart;
      await page.getByRole("button", { name: "发送", exact: true }).click();
      const deadline =
        promptStart + Number(process.env.GONGKE_TRIAL_TIMEOUT) * 1000;
      let seenPrompt = false;
      const answered = new Set();
      while (Date.now() < deadline) {
        const fullState = await readState();
        state = { ...fullState, events: fullState.events.slice(firstEvent) };
        seenPrompt ||= state.events.some((e) => e.type === "user");
        if (seenPrompt && name === "modeling")
          evidence.modeling_prompt_sent = true;
        if (seenPrompt && attachInput && !evidence.input) {
          evidence.prompt_sent = true;
          evidence.input = verifyInput(
            state,
            manifest.delivery,
            reference,
            (manifest.delivery === "dimensions"
              ? manifest.structured
              : manifest.crops)[caseName].sha256,
          );
        }
        for (const event of state.events.filter(
          (e) => e.type === "permission",
        )) {
          if (
            answered.has(event.id) ||
            state.events.some(
              (e) => e.type === "permission-resolved" && e.id === event.id,
            )
          )
            continue;
          const title = event.request.toolCall.title;
          const { allow, option } = engineeringPermission(event.request);
          evidence.permissions.push({
            title,
            permission_id: event.id,
            tool_call_id: event.request.toolCall.toolCallId,
            option_id: option?.optionId,
            allow,
            at: new Date().toISOString(),
          });
          if (!allow) {
            await page.evaluate(
              (id) => window.gongke.agent.permission(id, null),
              event.id,
            );
            throw Error(`不是绑定工程 MCP 的工具：${title}`);
          }
          // 在可见授权控件点击，保留请求及选择的 ACP 记录。
          await page
            .locator(`[data-permission-id="${event.id}"]`)
            .getByRole("button", {
              name: option.kind === "allow_once" ? "允许一次" : "始终允许",
              exact: true,
            })
            .click();
          answered.add(event.id);
        }
        if (state.error) throw Error(state.error);
        const alerts = await page.getByRole("alert").allTextContents();
        if (!seenPrompt && alerts.length) throw Error(alerts.join("\n"));
        if (seenPrompt && state.phase === "ready") break;
        if (state.phase === "disconnected") throw Error("Agent 意外断开");
        await pause(200);
      }
      evidence.prompt_elapsed_seconds = (Date.now() - promptStart) / 1000;
      if (!seenPrompt || state.phase !== "ready") {
        await page.evaluate(() => window.gongke.agent.cancel());
        throw Error("模型任务超时；已取消，未自动重发写操作，FreeCAD 保留现场");
      }
      const result = turnResult(state, evidence.session_id);
      const text = state.events
        .filter(
          (e) =>
            e.type === "update" &&
            e.update.sessionUpdate === "agent_message_chunk" &&
            e.update.content.type === "text",
        )
        .map((e) => e.update.content.text)
        .join("");
      const report = {
        name,
        elapsed_seconds: (Date.now() - turnStart) / 1000,
        result,
        events: state.events,
        text,
      };
      write(path.join(directory, `${name}-result.json`), report);
      evidence.turns.push({
        name,
        elapsed_seconds: report.elapsed_seconds,
        result,
      });
      return report;
    }
    if (manifest.delivery === "vision") {
      // 首轮只发图片与字段含义；期望值仅在试验进程，不复制进工程或提示词。
      const probe =
        "请先只读这张图片，不建模。先核对尺寸界线和剖面：小字或底部是否留实体看不清时，调用 project.read_image 的 crop/scale 局部复读。不能只根据阴影猜孔槽是否贯通。已有整图，不必重复读全图；同一区域复读仍无法确认时填 null，不靠反复放大或像素比例强行补数字。" +
        "按图中明确标注给出以下字段，长度单位 mm，数值为数字，布尔字段为 true/false，看不清填 null：" +
        Object.entries(manifest.vision_fields[caseName])
          .map(([field, label]) => `${field}（${label}）`)
          .join("、") +
        "。只输出一个 JSON 对象，另加 evidence 说明关键读数/拓扑的视图依据、uncertain 数组列出未确认项；不要读取其他工程或参考答案。";
      const response = await runTurn("vision-read", probe, true);
      evidence.vision = compareVision(
        response.text,
        manifest.vision_expectations[caseName],
      );
      if (manifest.vision_review_required[caseName]) {
        evidence.vision.confirmed_fields_passed = evidence.vision.verified;
        evidence.vision.verified = null;
        evidence.vision.review_required = true;
      }
      write(path.join(directory, "vision-check.json"), evidence.vision);
      // 不把对照数值反馈给模型；误读仍保留，让它继续自行检查和建模。
    }
    const completed = await runTurn(
      "modeling",
      prompt,
      manifest.delivery !== "vision",
    );
    evidence.stop_reason = completed.result.stopReason;
    evidence.transport_completed = true;
  } catch (error) {
    evidence.error = String(error);
    evidence.failed_stage = evidence.stage;
  } finally {
    if (promptStart)
      evidence.prompt_elapsed_seconds = (Date.now() - promptStart) / 1000;
    if (page && !page.isClosed()) {
      // 截图先于取消/断开，避免用清理引发的错误覆盖真正失败现场。
      await page
        .screenshot({ path: path.join(directory, "final.png") })
        .catch((e) => evidence.errors.push(String(e)));
      let state = await readState().catch(() => lastState);
      // 在取消/关闭前提取原始故障；后续 session/close 的错误不能覆盖它。
      saveAgentDiagnostics(directory, evidence, state);
      if (state && !fs.existsSync(path.join(directory, "initialization.json")))
        write(path.join(directory, "initialization.json"), state);
      if (state && ["prompting", "cancelling"].includes(state.phase)) {
        stage("cancel");
        await page
          .evaluate(() => window.gongke.agent.cancel())
          .catch((e) => evidence.errors.push(String(e)));
        const deadline = Date.now() + 30_000;
        while (
          Date.now() < deadline &&
          ["prompting", "cancelling"].includes(state.phase)
        ) {
          await pause(100);
          state = await readState().catch(() => state);
        }
        if (["prompting", "cancelling"].includes(state.phase))
          evidence.cancel_pending = true;
      }
      if (state) {
        write(path.join(directory, "conversation.json"), state);
        evidence.session_id = state.session?.sessionId;
        evidence.usage = state.events.filter(
          (e) =>
            e.type === "turn-result" ||
            (e.type === "update" && e.update.sessionUpdate === "usage_update"),
        );
        evidence.usage_note =
          "原样保留 ACP usage 和 prompt 结果；上下文占用不等于计费 token，未报告费用时不估算。";
        fs.writeFileSync(
          path.join(directory, "conversation.txt"),
          state.events
            .filter(
              (e) =>
                e.type === "user" ||
                (e.type === "update" &&
                  e.update.sessionUpdate === "agent_message_chunk"),
            )
            .map((e) =>
              e.type === "user"
                ? `\n学生：${e.text}\n`
                : e.update.content.text || "",
            )
            .join(""),
        );
        // 结束会话后检查，阻止模型与独立审计并行修改文档。
        await page
          .evaluate(() => window.gongke.agent.disconnect())
          .catch((e) => evidence.errors.push(String(e)));
        write(path.join(directory, "close.json"), await readState());
        if (state.stderrLogPath && fs.existsSync(state.stderrLogPath))
          fs.copyFileSync(
            state.stderrLogPath,
            path.join(directory, "dsh-stderr.log"),
          );
        try {
          evidence.dsh_usage = collectDshSession(
            evidence.session_id,
            directory,
          );
        } catch (e) {
          evidence.dsh_usage = { available: false, reason: String(e) };
        }
      }
      if (fs.existsSync(path.join(project, "gongke-project.json"))) {
        stage("audit");
        try {
          evidence.audit = await audit(
            directory,
            path.join(user, "state"),
            project,
            caseName,
          );
        } catch (e) {
          evidence.audit_error = String(e);
        }
      }
    }
    if (app) await app.close().catch((e) => evidence.errors.push(String(e)));
    evidence.elapsed_seconds = (Date.now() - start) / 1000;
    // 最终状态由 Python 在重开验收后统一计算，初次读数错误不阻止模型后续纠正。
    evidence.status = "awaiting_reopen";
    write(path.join(directory, "result.json"), evidence);
  }
  return evidence;
}

(async () => {
  const results = [];
  for (const caseName of manifest.cases) {
    for (
      let i = manifest.repetition_index;
      i < manifest.repetition_index + manifest.repeats;
      i++
    ) {
      console.log(`开始 ${caseName}-${i}`);
      const result = await trial(caseName, i);
      results.push(result);
      const passed = results.filter((r) => r.status === "passed").length;
      write(path.join(output, "summary.json"), {
        attempted: results.length,
        prompts_sent: results.filter((r) => r.prompt_sent).length,
        modeling_prompts_sent: results.filter((r) => r.modeling_prompt_sent)
          .length,
        passed,
        automatic_pass_rate: passed / results.length,
        results,
      });
      console.log(`${caseName}-${i}: ${result.status} ${result.error || ""}`);
      // 能力/连接缺失时继续花费模型调用没有意义，保留本次失败的分母。
      if (!result.transport_completed) {
        process.exitCode = 1;
        return;
      }
    }
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
