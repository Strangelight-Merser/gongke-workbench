// 只验证附件协议，不生成 CAD，也不作为真实模型证据。
import {
  agent,
  ndJsonStream,
  PROTOCOL_VERSION,
  RequestError,
} from "@agentclientprotocol/sdk";
import { Readable, Writable } from "node:stream";
import { createHash } from "node:crypto";
let model = "text";
const configOptions = () => [{ id: "model", name: "Model", type: "select", currentValue: model, options: [{ value: "text", name: "Text" }, { value: "vision", name: "Vision" }] }];
agent({ name: "image-protocol-fixture" })
  .onRequest("initialize", () => ({
    protocolVersion: PROTOCOL_VERSION,
    agentCapabilities: {
      sessionCapabilities: { close: {} },
      promptCapabilities: { image: process.env.IMAGE_CAPABLE === "yes" },
    },
  }))
  .onRequest("session/new", () => ({ sessionId: "image-fixture", configOptions: configOptions() }))
  .onRequest("session/set_config_option", async ({params, client}) => {
    model = params.value;
    await client.notify("session/update", {sessionId: params.sessionId, update: {sessionUpdate: "config_option_update", configOptions: configOptions()}});
    return {configOptions: configOptions()};
  })
  .onRequest("session/close", () => ({}))
  .onRequest("session/prompt", async ({ params, client }) => {
    if (process.env.REJECT_IMAGE === "yes") {
      process.stderr.write("image admission rejected; api_key=fixture-private\n");
      throw RequestError.invalidParams({ stage: "image-admission" }, "inline image prompts were not advertised by this connection");
    }
    const picture = params.prompt.find((p) => p.type === "image");
    await client.notify("session/update", {
      sessionId: params.sessionId,
      update: {
        sessionUpdate: "agent_message_chunk",
        content: {
          type: "text",
          text: JSON.stringify({
            sha256:
              picture &&
              createHash("sha256")
                .update(Buffer.from(picture.data, "base64"))
                .digest("hex"),
            mimeType: picture?.mimeType,
          }),
        },
      },
    });
    return { stopReason: "end_turn" };
  })
  .connect(
    ndJsonStream(Writable.toWeb(process.stdout), Readable.toWeb(process.stdin)),
  );
