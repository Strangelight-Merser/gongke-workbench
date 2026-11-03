// 真实进程 + 真实模型测试；自动批准只限显式传入的只读测试 MCP。
// 窗口内点击授权的验证见 acp-flow.cjs，不能把本脚本算作桌面验收。
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { AgentClient } = require("../dist-electron/acp/client.cjs");
const { AgentConfiguration } = require("../dist-electron/acp/settings.cjs");
const root = path.resolve(__dirname, "../..");
const output = path.resolve(
  process.env.GONGKE_ACP_OUTPUT || path.join(root, "out/acp-live"),
);
fs.mkdirSync(output, { recursive: true });
if (!process.env.GONGKE_AGENT_CONFIG || !process.env.GONGKE_TEST_PROJECT)
  throw Error(
    "需要 GONGKE_AGENT_CONFIG 与 GONGKE_TEST_PROJECT，且配置必须使用只读联调 MCP",
  );
const config = new AgentConfiguration(output, root);
(async () => {
  for (const item of config.read().agents) {
    const client = new AgentClient(() => {});
    const { profile, mcp } = config.launch(
      item.id,
      process.env.GONGKE_TEST_PROJECT,
    );
    let permissions = 0;
    const answer = setInterval(() => {
      const state = client.snapshot();
      for (const event of state.events)
        if (
          event.type === "permission" &&
          !state.events.some(
            (e) => e.type === "permission-resolved" && e.id === event.id,
          )
        ) {
          permissions++;
          client.permission(
            event.id,
            event.request.options.find((o) => o.kind === "allow_once").optionId,
          );
        }
    }, 50);
    const timeout = setTimeout(() => client.disconnect(), 150_000);
    try {
      await client.start(profile, process.env.GONGKE_TEST_PROJECT, mcp);
      await client.prompt(
        "先调用 project_current 读取当前工程，再调用 design_calculate 计算。只需告诉我电机型号和额定功率。不要用 shell、文件或其他工具。",
      );
      const state = client.snapshot();
      const text = state.events
        .filter(
          (e) =>
            e.type === "update" &&
            e.update.sessionUpdate === "agent_message_chunk",
        )
        .map((e) => e.update.content.text || "")
        .join("");
      assert.match(text, /Y132S-4/);
      assert.ok(permissions >= 2);
      fs.writeFileSync(
        path.join(output, `${item.id}.json`),
        JSON.stringify(state, null, 2),
      );
      console.log(
        JSON.stringify({
          agent: item.name,
          permissions,
          session: state.session.sessionId,
          result: text,
        }),
      );
    } finally {
      clearInterval(answer);
      clearTimeout(timeout);
      await client.disconnect();
    }
  }
})().catch((error) => {
  console.error(String(error), error.data);
  process.exitCode = 1;
});
