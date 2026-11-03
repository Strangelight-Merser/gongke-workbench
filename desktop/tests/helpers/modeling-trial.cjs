// 真实验收脚本的等待与验收条件。每次先 await IPC，不向 waitForFunction 传异步谓词。
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForReady(
  readState,
  { timeoutMs = 120_000, intervalMs = 100 } = {},
) {
  const deadline = Date.now() + timeoutMs;
  let state;
  while (Date.now() < deadline) {
    state = await readState();
    if (state.error) throw Error(state.error);
    if (state.phase === "ready" && state.session?.sessionId) return state;
    await pause(intervalMs);
  }
  throw Error(`等待 Agent 会话超时；最后状态 ${state?.phase || "unknown"}`);
}

function verifyInput(state, delivery, drawing, sha256) {
  const user = state.events.find((event) => event.type === "user");
  if (!user) return null;
  const images = user.images || [];
  if (delivery === "attachment" || delivery === "vision") {
    if (
      images.length !== 1 ||
      images[0].path !== drawing ||
      images[0].sha256 !== sha256
    )
      throw Error("实际发送的 ACP 图片与本轮图纸不一致；停止试验");
  } else if ((delivery === "dimensions" || delivery === "pdf")) {
    if (
      images.length ||
      !user.text.includes(sha256) ||
      !user.text.includes(drawing)
    )
      throw Error("实际发送的结构化尺寸内容缺少对应文件/哈希，或混入图片");
  } else if (images.length) {
    throw Error("MCP 读图对照试验不应同时发送 ACP 图片");
  }
  return { delivery, drawing, sha256, images };
}

function turnResult(state, sessionId) {
  if (state.session?.sessionId !== sessionId)
    throw Error("建模途中 ACP 会话发生改变");
  const result = state.events.findLast(
    (event) => event.type === "turn-result",
  )?.result;
  if (!result) throw Error("未收到 session/prompt 结束响应");
  if (result.stopReason !== "end_turn")
    throw Error(`本轮未正常结束：${result.stopReason}`);
  if (
    !state.events.some(
      (event) =>
        event.type === "update" &&
        event.update.sessionUpdate === "agent_message_chunk" &&
        event.update.content.type === "text" &&
        event.update.content.text.trim(),
    )
  )
    throw Error("本轮结束但未收到给学生的回复");
  return result;
}

module.exports = { waitForReady, verifyInput, turnResult };

// 只约束工具来源，不限制名称、调用顺序或读写粒度。工程路径与写入权限由执行端检查。
function engineeringPermission(request) {
  const option =
    request.options.find((o) => o.kind === "allow_once") ||
    request.options.find((o) => o.kind === "allow_always");
  return {
    allow:
      request.toolCall.title?.startsWith("mcp__gongke__") === true && !!option,
    option,
  };
}

function visionModelOption(state) {
  const config = state.session?.configOptions?.find(
    (c) => c.category === "model" || c.id === "model",
  );
  const options = config?.options?.flatMap((o) => o.options || [o]) || [];
  const value = JSON.stringify(["deepseek-official", "deepseek-flash"]);
  if (!options.some((o) => o.value === value))
    throw Error("会话未提供 deepseek-official / deepseek-flash 选项");
  return { configId: config.id, value };
}

function compareVision(text, expected) {
  let observed;
  try {
    observed = JSON.parse(
      text.slice(text.indexOf("{"), text.lastIndexOf("}") + 1),
    );
  } catch (error) {
    return {
      verified: false,
      response: text,
      reason: "读图回复未能解析为尺寸 JSON，保留原文供人工检查",
    };
  }
  const checks = Object.entries(expected).map(([field, value]) => ({
    field,
    expected: value,
    observed: observed[field] ?? null,
    passed:
      typeof value === "boolean"
        ? observed[field] === value
        : typeof observed[field] === "number" &&
          Math.abs(observed[field] - value) < 1e-6,
  }));
  return {
    verified: checks.every((c) => c.passed),
    observed,
    checks,
    scope:
      "仅与人工复核的指定读数和贯通关系比较；不据此保证完整视图理解或图纸符合性",
  };
}
module.exports.engineeringPermission = engineeringPermission;
module.exports.visionModelOption = visionModelOption;
module.exports.compareVision = compareVision;

// 在取消/关闭前保存，供 result.json 直接引用，避免只能在嵌套 conversation 中找到原因。
function saveAgentDiagnostics(directory, evidence, state) {
  if (!state) return;
  const fs = require("node:fs"),
    path = require("node:path");
  if (state.errorDetails && !evidence.acp_error) {
    evidence.acp_error = state.errorDetails;
    fs.writeFileSync(
      path.join(directory, "acp-error.json"),
      JSON.stringify(state.errorDetails, null, 2) + "\n",
    );
  }
  evidence.dsh_stderr = {
    path: path.join(directory, "dsh-stderr.log"),
    source: state.stderrLogPath,
    tail: state.stderr || "",
  };
  fs.writeFileSync(evidence.dsh_stderr.path, state.stderr || "");
}
module.exports.saveAgentDiagnostics = saveAgentDiagnostics;
