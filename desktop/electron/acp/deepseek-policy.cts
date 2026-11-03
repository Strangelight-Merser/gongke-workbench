/** DeepSeek Harness 官方插件接口；只向模型提供会话注入的工程 MCP 工具。 */
type Execution = { name: string };
type Decision =
  { kind: "allow" | "cancel" } | { kind: "deny" | "ask"; reason?: string };
type Tools = {
  guard(fn: (execution: Execution) => string | undefined): unknown;
  restrict(filter: { allow: string[] }): unknown;
};
type Context = {
  tools: Tools;
  on(
    event: "agent/created",
    listener: (event: { agent: { ctx: { tools: Tools } } }) => void,
  ): unknown;
  on(
    event: "tools/pre-execute",
    listener: (
      execution: Execution,
      next: () => Promise<Decision>,
    ) => Promise<Decision>,
  ): unknown;
};
export const inject = ["tools"];
export function apply(ctx: Context) {
  ctx.on("agent/created", ({ agent }) => {
    agent.ctx.tools.restrict({ allow: [] });
  });
  ctx.tools.guard((exec) =>
    exec.name.startsWith("mcp__gongke__")
      ? undefined
      : "工程操作只能通过构想引擎 MCP 执行",
  );
  ctx.on("tools/pre-execute", async (exec, next) => {
    if (!exec.name.startsWith("mcp__gongke__"))
      return { kind: "deny", reason: "工程操作只能通过构想引擎 MCP 执行" };
    const decision = await next();
    return decision.kind === "allow"
      ? { kind: "ask", reason: `批准工程工具 ${exec.name}` }
      : decision;
  });
}
