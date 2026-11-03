import type { AgentEvent } from "../../electron/acp/types.cjs";
type Row = { kind: string; text?: string; tool?: any };
export function rowsOf(events: AgentEvent[]): Row[] {
  const rows: Row[] = [];
  const tools = new Map<string, Row>();
  for (const event of events) {
    if (event.type === "user" || event.type === "notice") {
      rows.push({
        kind: event.type,
        text:
          event.text +
          (event.type === "user" && event.images?.length
            ? "\n图片：" + event.images.map((image) => image.path).join("、")
            : ""),
      });
      continue;
    }
    if (event.type !== "update") continue;
    const update = event.update;
    if (
      update.sessionUpdate === "agent_message_chunk" ||
      update.sessionUpdate === "agent_thought_chunk"
    ) {
      const kind =
        update.sessionUpdate === "agent_thought_chunk"
          ? "thought"
          : "assistant";
      const content = update.content;
      const text =
        content.type === "text"
          ? content.text
          : content.type === "resource_link"
            ? `${content.name}: ${content.uri}`
            : `[${content.type}]`;
      const last = rows.at(-1);
      if (last?.kind === kind) last.text += text;
      else rows.push({ kind, text });
    } else if (
      update.sessionUpdate === "tool_call" ||
      update.sessionUpdate === "tool_call_update"
    ) {
      let row = tools.get(update.toolCallId);
      if (!row) {
        row = { kind: "tool", tool: { toolCallId: update.toolCallId } };
        tools.set(update.toolCallId, row);
        rows.push(row);
      }
      row.tool = {
        ...row.tool,
        ...Object.fromEntries(
          Object.entries(update).filter(
            ([, v]) => v !== undefined && v !== null,
          ),
        ),
      };
    } else if (update.sessionUpdate === "plan") {
      rows.push({
        kind: "plan",
        text: update.entries
          .map((e) => `${e.status} · ${e.content}`)
          .join("\n"),
      });
    }
  }
  return rows;
}
