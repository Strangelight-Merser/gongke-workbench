import type { StdioCommand } from "./acp/types.cjs";
export type EngineeringMode = "model" | "practice";
/** 复用已有工程 MCP 绑定权限；切换模式须重连，旧绑定不会被原地提权。 */
export function mcpForMode(
  command: StdioCommand,
  mode: EngineeringMode,
): StdioCommand {
  const projectMcp =
    command.args.includes("mcp") && command.args.includes("--project");
  if (!projectMcp) {
    if (mode === "practice") throw new Error("练习模式需要绑定工程的 MCP 服务");
    return command;
  }
  const args = command.args.filter((arg) => arg !== "--allow-writes");
  if (mode === "model") args.push("--allow-writes");
  return { ...command, args };
}
