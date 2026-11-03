import { useEffect, useMemo, useRef, useState } from "react";
import type {
  AgentEvent,
  AgentSettings,
  AgentSnapshot,
} from "../../electron/acp/types.cjs";
import { errorText } from "../api";
import { StreamText } from "../Motion";

const phases = {
  disconnected: "未连接",
  starting: "正在连接",
  connected: "待建立会话",
  authenticating: "正在登录",
  ready: "已连接",
  prompting: "执行中",
  cancelling: "正在取消",
};
type Row = { kind: string; text?: string; tool?: any };
function rowsOf(events: AgentEvent[]): Row[] {
  const rows: Row[] = [];
  const tools = new Map<string, Row>();
  for (const event of events) {
    if (event.type === "user" || event.type === "notice") {
      rows.push({ kind: event.type, text: event.text });
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
const stringify = (value: unknown) =>
  typeof value === "string" ? value : JSON.stringify(value, null, 2);
export function AgentPanel({
  project,
  context,
  onTurnEnd,
}: {
  project?: string;
  context?: string;
  onTurnEnd: () => void;
}) {
  const [state, setState] = useState<AgentSnapshot>({
    phase: "disconnected",
    project: "",
    agentId: "",
    authMethods: [],
    events: [],
  });
  const [settings, setSettings] = useState<AgentSettings>();
  const [selected, setSelected] = useState("");
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [config, setConfig] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const refresh = useRef(onTurnEnd);
  refresh.current = onTurnEnd;
  const priorPhase = useRef(state.phase);
  async function perform(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
    } catch (error) {
      setError(errorText(error));
    }
  }
  useEffect(() => {
    const accept = (next: AgentSnapshot) => {
      if (
        ["prompting", "cancelling"].includes(priorPhase.current) &&
        next.phase === "ready"
      )
        refresh.current();
      priorPhase.current = next.phase;
      setState(next);
    };
    const stop = window.gongke.agent.onState(accept);
    perform(async () => {
      const config = await window.gongke.agent.settings();
      setSettings(config);
      const current = await window.gongke.agent.state();
      setSelected(current.agentId || config.agents[0].id);
      accept(current);
    });
    return stop;
  }, []);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [state.events.length]);
  useEffect(() => {
    setPrompt("");
    setError("");
  }, [project, selected]);
  const active = state.project === project && state.agentId === selected;
  const events = active ? state.events : [];
  const rows = useMemo(
    () => (active ? rowsOf(state.events) : []),
    [state.events, active],
  );
  const resolved = new Set(
    events.filter((e) => e.type === "permission-resolved").map((e) => e.id),
  );
  const permissions = events.filter(
    (e) => e.type === "permission" && !resolved.has(e.id),
  );
  const busy = [
    "starting",
    "authenticating",
    "prompting",
    "cancelling",
  ].includes(state.phase);
  const ready = active && state.phase === "ready";
  function send() {
    if (!ready || !prompt.trim()) return;
    const message = prompt;
    setPrompt("");
    perform(() =>
      window.gongke.agent.prompt(
        context ? `${message}\n\n当前选择：${context}` : message,
      ),
    );
  }
  return (
    <section className="agent-pane acp-panel" aria-label="Agent 面板">
      <div className="pane-heading">
        Agent <span className={`led ${ready ? "on" : ""}`} />
        <span className="acp-phase">
          {phases[active ? state.phase : "disconnected"]}
        </span>
      </div>
      <div className="acp-toolbar">
        <select
          aria-label="选择 Agent"
          value={selected}
          disabled={busy}
          onChange={(e) => setSelected(e.target.value)}
        >
          {settings?.agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
        <button
          disabled={!project || busy || !selected}
          onClick={() => perform(() => window.gongke.agent.start(selected))}
        >
          连接
        </button>
        <button
          aria-label="Agent 连接设置"
          disabled={busy}
          onClick={() => {
            setConfig(JSON.stringify(settings, null, 2));
            setEditing(true);
          }}
        >
          设置
        </button>
      </div>
      {active && state.phase !== "disconnected" && (
        <div className="acp-toolbar">
          <button
            disabled={busy}
            onClick={() => perform(() => window.gongke.agent.newSession())}
          >
            新会话
          </button>
          <button
            onClick={() => perform(() => window.gongke.agent.disconnect())}
          >
            断开
          </button>
          {state.authMethods
            .filter((m) => !("type" in m) || m.type !== "terminal")
            .map((method) => (
              <button
                key={method.id}
                title={method.description || ""}
                disabled={busy}
                onClick={() =>
                  perform(() => window.gongke.agent.authenticate(method.id))
                }
              >
                {method.name}
              </button>
            ))}
        </div>
      )}
      <div className="conversation" aria-live="polite">
        {!rows.length && (
          <div className="agent-welcome">
            <p>
              {project
                ? "选择你已有的 Agent，开始工程任务。"
                : "先创建或打开工程。"}
            </p>
            {state.phase === "connected" && !state.authMethods.length && (
              <p>
                此 Agent 未提供 ACP 登录方式，请先在 Agent
                自己的账号设置中登录，再重新连接。
              </p>
            )}
          </div>
        )}
        {rows.map((row, i) =>
          row.kind === "tool" ? (
            <details
              className="acp-tool"
              key={i}
              open={row.tool.status !== "completed"}
            >
              <summary>
                {row.tool.title || row.tool.toolCallId} ·{" "}
                {(
                  {
                    pending: "等待",
                    in_progress: "执行中",
                    completed: "完成",
                    failed: "失败",
                  } as Record<string, string>
                )[row.tool.status] || row.tool.status}
              </summary>
              {row.tool.rawInput !== undefined && (
                <pre>{stringify(row.tool.rawInput)}</pre>
              )}
              {row.tool.content?.map((c: any, j: number) => (
                <pre key={j}>
                  {c.type === "content"
                    ? c.content.type === "text"
                      ? c.content.text
                      : stringify(c.content)
                    : stringify(c)}
                </pre>
              ))}
              {row.tool.rawOutput !== undefined && (
                <pre>{stringify(row.tool.rawOutput)}</pre>
              )}
            </details>
          ) : row.kind === "thought" ? (
            <details key={i} className="acp-thought">
              <summary>思考</summary>
              <StreamText content={row.text || ""} />
            </details>
          ) : (
            <div key={i} className={`message ${row.kind}`}>
              <small>
                {row.kind === "user"
                  ? "你"
                  : row.kind === "assistant"
                    ? settings?.agents.find((a) => a.id === state.agentId)?.name
                    : ""}
              </small>
              <div>
                <StreamText
                  content={row.text || ""}
                  streaming={busy && i === rows.length - 1}
                />
              </div>
            </div>
          ),
        )}
        <div ref={end} />
      </div>
      {permissions.map(
        (event) =>
          event.type === "permission" && (
            <div
              role="group"
              aria-label="工程操作授权"
              className="acp-permission"
              key={event.id}
            >
              <strong>
                {event.request.toolCall.title ||
                  rows.find(
                    (r) =>
                      r.tool?.toolCallId === event.request.toolCall.toolCallId,
                  )?.tool?.title ||
                  "批准工程操作"}
              </strong>
              {
                <pre>
                  {stringify(
                    event.request.toolCall.rawInput ??
                      rows.find(
                        (r) =>
                          r.tool?.toolCallId ===
                          event.request.toolCall.toolCallId,
                      )?.tool?.rawInput,
                  )}
                </pre>
              }
              <div>
                {event.request.options.map((option) => (
                  <button
                    key={option.optionId}
                    className={option.kind.startsWith("allow") ? "primary" : ""}
                    onClick={() =>
                      perform(() =>
                        window.gongke.agent.permission(
                          event.id,
                          option.optionId,
                        ),
                      )
                    }
                  >
                    {
                      {
                        allow_once: "允许一次",
                        allow_always: "始终允许",
                        reject_once: "拒绝一次",
                        reject_always: "始终拒绝",
                      }[option.kind]
                    }
                  </button>
                ))}
              </div>
            </div>
          ),
      )}
      {(error || (active && state.error)) && (
        <div className="acp-error" role="alert">
          {error || state.error}
        </div>
      )}
      <div className="compose">
        <textarea
          aria-label="工程任务"
          placeholder="描述工程任务…"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              (e.metaKey || e.ctrlKey) &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              send();
            }
          }}
        />
        <div>
          {["prompting", "cancelling"].includes(state.phase) ? (
            <button
              disabled={state.phase === "cancelling"}
              onClick={() => perform(() => window.gongke.agent.cancel())}
            >
              取消
            </button>
          ) : (
            <button
              className="primary"
              disabled={!ready || !prompt.trim()}
              onClick={send}
            >
              发送 ↑
            </button>
          )}
        </div>
      </div>
      {editing && (
        <div className="modal-scrim">
          <div className="modal acp-settings">
            <div className="section-bar">
              <h2>Agent 连接</h2>
              <button onClick={() => setEditing(false)}>×</button>
            </div>
            <p>
              填写本机 Agent 和工程 MCP 的 stdio 启动配置。登录与账号由 Agent
              管理。参数和环境变量中的 <code>{"${project}"}</code>{" "}
              会替换为当前工程目录。
            </p>
            <textarea
              aria-label="Agent 启动配置"
              value={config}
              onChange={(e) => setConfig(e.target.value)}
              spellCheck={false}
            />
            <button
              className="primary"
              onClick={() =>
                perform(async () => {
                  const value = JSON.parse(config);
                  await window.gongke.agent.saveSettings(value);
                  setSettings(value);
                  setSelected(value.agents[0].id);
                  setEditing(false);
                })
              }
            >
              保存
            </button>
            {error && <p role="alert">{error}</p>}
          </div>
        </div>
      )}
    </section>
  );
}
