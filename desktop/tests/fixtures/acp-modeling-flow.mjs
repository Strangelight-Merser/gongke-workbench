// 延迟连接与仅含 toolCallId 的授权替身；不调用模型或 CAD。
import {
  agent,
  ndJsonStream,
  PROTOCOL_VERSION,
  RequestError,
} from "@agentclientprotocol/sdk";
import { Readable, Writable } from "node:stream";
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
agent({ name: "modeling-flow-fixture" })
  .onRequest("initialize", async () => {
    await pause(80);
    return {
      protocolVersion: PROTOCOL_VERSION,
      agentCapabilities: { promptCapabilities: { image: true } },
    };
  })
  .onRequest("session/new", async () => {
    await pause(100);
    if (process.env.FAIL_SESSION)
      throw RequestError.internalError(undefined, "fixture session rejected");
    return { sessionId: "delayed-session" };
  })
  .onRequest("session/prompt", async ({ params, client }) => {
    const update = (update) =>
      client.notify("session/update", { sessionId: params.sessionId, update });
    for (const [toolCallId, title] of [
      ["context", "mcp__gongke__host_context"],
      ["image", "mcp__gongke__project_read_image"],
    ]) {
      await update({
        sessionUpdate: "tool_call",
        toolCallId,
        title,
        kind: "other",
        status: "pending",
        rawInput: { marker: toolCallId },
      });
      await update({
        sessionUpdate: "tool_call_update",
        toolCallId,
        status: "in_progress",
      });
    }
    // 故意与 tool_call 顺序相反，不能用最后一条工具名或界面第一个授权框冒充匹配。
    for (const toolCallId of ["image", "context"]) {
      const result = await client.request("session/request_permission", {
        sessionId: params.sessionId,
        toolCall: { toolCallId },
        options: [
          {
            optionId: `allow-${toolCallId}`,
            name: "允许一次",
            kind: "allow_once",
          },
        ],
      });
      if (result.outcome.optionId !== `allow-${toolCallId}`)
        throw Error("wrong permission selection");
      await update({
        sessionUpdate: "tool_call_update",
        toolCallId,
        status: "completed",
        rawOutput: { fixture: true },
      });
    }
    await update({
      sessionUpdate: "agent_message_chunk",
      content: { type: "text", text: "协议替身完成，不是建模结果" },
    });
    return { stopReason: "end_turn" };
  })
  .connect(
    ndJsonStream(Writable.toWeb(process.stdout), Readable.toWeb(process.stdin)),
  );
