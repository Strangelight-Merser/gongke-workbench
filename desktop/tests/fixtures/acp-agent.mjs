// 确定性协议替身：与真实 Agent 运行证据分开。
import {
  agent,
  ndJsonStream,
  PROTOCOL_VERSION,
  RequestError,
} from "@agentclientprotocol/sdk";
import { Readable, Writable } from "node:stream";
let authenticated = false;
let seq = 0;
let canceled = false;
let setup;
const app = agent({ name: "gongke-test-agent" })
  .onRequest("initialize", ({ params }) => {
    if (
      params.clientCapabilities?.terminal ||
      params.clientCapabilities?.fs?.writeTextFile
    )
      throw new Error("不应提供通用写工具");
    return {
      protocolVersion: PROTOCOL_VERSION,
      agentCapabilities: {},
      authMethods: [{ id: "login", name: "测试登录" }],
    };
  })
  .onRequest("authenticate", ({ params }) => {
    if (params.methodId !== "login") throw new Error("bad login");
    authenticated = true;
    return {};
  })
  .onRequest("session/new", ({ params }) => {
    if (!authenticated) {
      throw RequestError.authRequired(undefined, "需要登录");
    }
    setup = params;
    return { sessionId: `session-${++seq}` };
  })
  .onNotification("session/cancel", () => {
    canceled = true;
  })
  .onRequest("session/prompt", async ({ params, client }) => {
    canceled = false;
    const sessionId = params.sessionId;
    const update = (update) =>
      client.notify("session/update", { sessionId, update });
    if (params.prompt[0].text === "crash") process.exit(7);
    if (params.prompt[0].text === "diagnostic") {
      process.stderr.write(
        "MCP startup failed: ModuleNotFoundError: mcp\nAuthorization: Bearer sk-",
      );
      await new Promise((r) => setTimeout(r, 10));
      process.stderr.write(
        "stderr-private\n" + process.env.FIXTURE_API_KEY + "\n",
      );
      await update({
        sessionUpdate: "tool_call_update",
        toolCallId: "failed-tool",
        status: "failed",
        rawOutput: { error: "gongke MCP unavailable", api_key: "data-private" },
      });
      throw RequestError.internalError(
        {
          details: "MCP connection refused",
          headers: { Authorization: "Bearer sk-header-private" },
        },
        "first prompt failed",
      );
    }

    if (params.prompt[0].text === "forbidden") {
      for (const [method, args] of [
        [
          "fs/write_text_file",
          { sessionId, path: "/tmp/forbidden", content: "bad" },
        ],
        ["terminal/create", { sessionId, command: "echo", args: ["bad"] }],
      ]) {
        try {
          await client.request(method, args);
          throw Error("client granted arbitrary execution");
        } catch (error) {
          if (error.code !== -32601) throw error;
        }
      }
      await update({
        sessionUpdate: "agent_message_chunk",
        content: { type: "text", text: "客户端拒绝文件写入和终端执行" },
      });
      return { stopReason: "end_turn" };
    }
    await update({
      sessionUpdate: "agent_message_chunk",
      content: { type: "text", text: "读取" },
    });
    await update({
      sessionUpdate: "agent_message_chunk",
      content: { type: "text", text: "工程" },
    });
    await update({
      sessionUpdate: "tool_call",
      toolCallId: "t1",
      title: "读取工程",
      kind: "read",
      status: "pending",
      rawInput: setup,
    });
    const permission = await client.request("session/request_permission", {
      sessionId,
      toolCall: { toolCallId: "t1" },
      options: [
        { optionId: "yes", name: "Allow", kind: "allow_once" },
        { optionId: "no", name: "Reject", kind: "reject_once" },
      ],
    });
    await new Promise((resolve) => setTimeout(resolve, 30));
    await update({
      sessionUpdate: "tool_call_update",
      toolCallId: "t1",
      status: "completed",
      rawOutput: permission,
    });
    return { stopReason: canceled ? "cancelled" : "end_turn" };
  });
app.connect(
  ndJsonStream(Writable.toWeb(process.stdout), Readable.toWeb(process.stdin)),
);
