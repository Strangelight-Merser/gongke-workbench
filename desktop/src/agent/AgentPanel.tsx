import { useModelingProgress } from "./ModelingProgress";
import { ModelingSteps } from "./ModelingTimeline";
import {
  ToolCall,
  ToolDetails,
  CompletedTools,
  toolResult,
  toolState,
} from "./ToolCall";
import { AgentErrorDetails } from "./AgentErrorDetails";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Button,
  Select,
  Textarea,
  Tab,
  TabList,
  Tooltip,
  Menu,
  MenuTrigger,
  MenuPopover,
  MenuList,
  MenuItem,
} from "@fluentui/react-components";
import {
  SendRegular,
  StopRegular,
  SettingsRegular,
  DismissRegular,
  AddRegular,
  MoreHorizontalRegular,
  ArrowRightRegular,
} from "@fluentui/react-icons";
import type {
  AgentSettings as Settings,
  AgentSnapshot,
} from "../../electron/acp/types.cjs";
import type { Step } from "../../electron/onboarding/types.cjs";
import { AgentOnboarding } from "./AgentOnboarding";
import { AgentSettings } from "./AgentSettings";
import { rowsOf, groupCompletedTools } from "./events";
import { errorText } from "../api";
const phases = {
  disconnected: "未连接",
  starting: "连接中",
  connected: "待登录",
  authenticating: "登录中",
  ready: "已连接",
  prompting: "执行中",
  cancelling: "取消中",
};
export function AgentPanel({
  project,
  context,
  referencePath,
  removeContext,
  mode,
  onMode,
  onTurnEnd,
  openModel,
  headerActions,
}: {
  headerActions?: ReactNode;
  project?: string;
  context?: string;
  referencePath?: string;
  removeContext(): void;
  mode: "model" | "practice";
  onMode(value: "model" | "practice"): void;
  onTurnEnd(): void;
  openModel(): void;
}) {
  const modeling = useModelingProgress();
  const [state, setState] = useState<AgentSnapshot>({
    phase: "disconnected",
    project: "",
    agentId: "",
    authMethods: [],
    events: [],
  });
  const [settings, setSettings] = useState<Settings>();
  const [onboardingRequest, setOnboardingRequest] = useState(0);
  const [onboardingStep, setOnboardingStep] = useState<Step>();
  const onboardingComplete = onboardingStep === "complete";
  const [configuredConnection, setConfiguredConnection] = useState(false);
  const conversationVisible = onboardingComplete || configuredConnection;
  const [selected, setSelected] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>(() =>
    JSON.parse(localStorage.getItem("gongke.agent.drafts") || "{}"),
  );
  const key = `${project || ""}:${selected}`;
  const prompt = drafts[key] || "";
  function setPrompt(value: string) {
    setDrafts((d) => ({ ...d, [key]: value }));
  }
  useEffect(() => {
    localStorage.setItem("gongke.agent.drafts", JSON.stringify(drafts));
  }, [drafts]);
  const [history, setHistory] = useState<
    Record<string, ReturnType<typeof rowsOf>>
  >({});
  const [error, setError] = useState(""),
    [editing, setEditing] = useState(false);
  const followTail = useRef(true);
  const end = useRef<HTMLDivElement>(null),
    refresh = useRef(onTurnEnd),
    prior = useRef(state.phase);
  refresh.current = onTurnEnd;
  const openWhenPrompting = useRef(() => {});
  openWhenPrompting.current = () => {
    if (mode === "model") openModel();
  };
  async function perform(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
    } catch (e) {
      setError(errorText(e));
    }
  }
  useEffect(() => {
    const accept = (next: AgentSnapshot) => {
      if (next.phase === "prompting" && prior.current !== "prompting")
        openWhenPrompting.current();
      if (
        ["prompting", "cancelling"].includes(prior.current) &&
        next.phase === "ready"
      )
        refresh.current();
      prior.current = next.phase;
      setState(next);
    };
    const stop = window.gongke.agent.onState(accept);
    void perform(async () => {
      onMode(await window.gongke.getAgentMode());
      const config = await window.gongke.agent.settings();
      setSettings(config);
      const current = await window.gongke.agent.state();
      setSelected(current.agentId || config.agents[0].id);
      accept(current);
    });
    return stop;
  }, []);
  const active = state.project === project && state.agentId === selected;
  const events = active ? state.events : [];
  const rows = useMemo(
    () => [...(history[key] || []), ...(active ? rowsOf(state.events) : [])],
    [state.events, active, history, key],
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
  useEffect(() => {
    if (followTail.current) end.current?.scrollIntoView({ block: "nearest" });
  }, [state.events.length]);
  async function changeMode(next: "model" | "practice") {
    await perform(async () => {
      if (next === mode) return;
      const previous = active ? rowsOf(state.events) : [];
      await window.gongke.setAgentMode(next);
      setHistory((h) => ({
        ...h,
        [key]: [
          ...(h[key] || []),
          ...previous,
          {
            kind: "notice",
            text:
              next === "practice"
                ? "已切换为练习，重新连接只读工程工具。"
                : "已切换为直接建模，重新连接工程工具。",
          },
        ],
      }));
      onMode(next);
    });
  }
  function send() {
    if (!ready || !prompt.trim()) return;
    const message = prompt;
    void perform(async () => {
      setPrompt("");
      try {
        await window.gongke.agent.prompt(
          `${mode === "practice" ? "练习：请只讲解和检查，让我自己完成模型。\n" : ""}${message}${context ? "\n当前参考：" + context : ""}`,
          referencePath ? [referencePath] : [],
        );
      } catch (e) {
        setPrompt(message);
        throw e;
      }
    });
  }
  return (
    <section
      className="agent-panel"
      aria-label="Agent 面板"
      data-onboarding={!conversationVisible}
    >
      <div className="panel-heading">
        <strong>Agent</strong>
        <span className="agent-connection">
          <i className={"led " + (ready ? "on" : "")} />
          {phases[active ? state.phase : "disconnected"]}
        </span>
        <Tooltip content="新会话" relationship="label">
          <Button
            size="small"
            appearance="subtle"
            icon={<AddRegular />}
            aria-label="新会话"
            disabled={!ready}
            onClick={() => perform(() => window.gongke.agent.newSession())}
          />
        </Tooltip>
        {headerActions}
        <Menu>
          <MenuTrigger disableButtonEnhancement>
            <Button
              size="small"
              appearance="subtle"
              icon={<SettingsRegular />}
              aria-label="Agent 连接设置"
              disabled={busy || !settings}
            />
          </MenuTrigger>
          <MenuPopover>
            <MenuList>
              <MenuItem onClick={() => setEditing(true)}>连接设置</MenuItem>
              <MenuItem onClick={() => setConfiguredConnection(true)}>
                使用已配置的 Agent
              </MenuItem>
              <MenuItem
                onClick={() => {
                  setConfiguredConnection(false);
                  setOnboardingRequest((n) => n + 1);
                }}
              >
                安装与连接引导
              </MenuItem>
            </MenuList>
          </MenuPopover>
        </Menu>
      </div>
      <AgentOnboarding
        project={project}
        hidden={configuredConnection}
        openRequest={onboardingRequest}
        onStep={setOnboardingStep}
        onConnected={async () => {
          setSelected("deepseek");
          setSettings(await window.gongke.agent.settings());
          await window.gongke.agent.start("deepseek");
        }}
      />
      <div className="agent-controls" hidden={!conversationVisible}>
        <Select
          aria-label="选择 Agent"
          value={selected}
          disabled={busy || mode === "practice"}
          onChange={(e) => setSelected(e.target.value)}
        >
          {settings?.agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
        {(!active || state.phase === "disconnected") && (
          <Button
            size="small"
            disabled={!project || busy || !selected}
            onClick={() => perform(() => window.gongke.agent.start(selected))}
          >
            连接
          </Button>
        )}
        <Menu>
          <MenuTrigger disableButtonEnhancement>
            <Button
              size="small"
              appearance="subtle"
              icon={<MoreHorizontalRegular />}
              aria-label="Agent 操作"
            />
          </MenuTrigger>
          <MenuPopover>
            <MenuList>
              <MenuItem
                disabled={!active || state.phase === "disconnected" || busy}
                onClick={() => perform(() => window.gongke.agent.disconnect())}
              >
                断开连接
              </MenuItem>
            </MenuList>
          </MenuPopover>
        </Menu>
      </div>
      <TabList
        className="agent-modes"
        hidden={!conversationVisible}
        size="small"
        selectedValue={mode}
        onTabSelect={(_, d) => changeMode(d.value as "model" | "practice")}
        aria-label="Agent 模式"
      >
        <Tab value="model" disabled={busy}>
          直接建模
        </Tab>
        <Tab value="practice" disabled={busy || selected !== "deepseek"}>
          练习
        </Tab>
      </TabList>
      {conversationVisible && mode === "practice" && (
        <p className="mode-note">
          只讲解与检查；模型由你完成。工程工具为只读。
        </p>
      )}
      {conversationVisible && context && (
        <div className="agent-context">
          <div>
            <span title={context}>{context}</span>
            <Button
              size="small"
              appearance="subtle"
              icon={<DismissRegular />}
              aria-label="移除参考上下文"
              onClick={removeContext}
            />
          </div>
        </div>
      )}
      {conversationVisible &&
        active &&
        state.session?.configOptions
          ?.filter(
            (c) =>
              c.type === "select" &&
              (c.category === "model" || c.id === "model"),
          )
          .map(
            (c) =>
              c.type === "select" && (
                <Select
                  key={c.id}
                  aria-label="会话模型"
                  value={c.currentValue}
                  disabled={!ready}
                  onChange={(_, data) => {
                    void perform(() =>
                      window.gongke.agent.setConfigOption(c.id, data.value),
                    );
                  }}
                >
                  {c.options.map((o) =>
                    "group" in o ? (
                      <optgroup key={o.group} label={o.name}>
                        {o.options.map((v) => (
                          <option key={v.value} value={v.value}>
                            {v.name}
                          </option>
                        ))}
                      </optgroup>
                    ) : (
                      <option key={o.value} value={o.value}>
                        {o.name}
                      </option>
                    ),
                  )}
                </Select>
              ),
          )}
      {active &&
        state.authMethods
          .filter((m) => !("type" in m) || m.type !== "terminal")
          .map((m) => (
            <Button
              key={m.id}
              disabled={busy}
              onClick={() =>
                perform(() => window.gongke.agent.authenticate(m.id))
              }
            >
              {m.name}
            </Button>
          ))}
      <div
        className="conversation"
        onScroll={(e) => {
          const el = e.currentTarget;
          followTail.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 48;
        }}
        hidden={
          !conversationVisible &&
          !modeling.steps.length &&
          !modeling.error &&
          !(onboardingStep === "verify" && rows.length > 0)
        }
        role="log"
        aria-label="工程对话"
        aria-live="polite"
      >
        {conversationVisible && !rows.length && (
          <div className="agent-welcome">
            <h3>{project ? "从一个具体任务开始" : "先打开工程"}</h3>
            <p>
              {project
                ? "打开图纸后，描述要建的零件，或询问一个建模步骤。"
                : "连接你的 Agent，在同一个窗口里建模和检查。"}
            </p>
            {project && (
              <Button
                appearance="secondary"
                icon={<ArrowRightRegular />}
                iconPosition="after"
                disabled={!ready}
                onClick={() =>
                  setPrompt(
                    mode === "practice"
                      ? "请先讲解这张图纸的基准选择和建模顺序。"
                      : "请读取当前图纸，确认关键尺寸后建立可编辑的原生模型。",
                  )
                }
              >
                {mode === "practice"
                  ? "讲解图纸的建模顺序"
                  : "根据图纸建立模型"}
              </Button>
            )}
          </div>
        )}
        <ModelingSteps openModel={openModel} />
        {groupCompletedTools(
          rows,
          (tool) => toolState(tool.status, toolResult(tool)) === "completed",
        ).map((row, i) =>
          row.kind === "tool-group" ? (
            <CompletedTools
              key={row.tools![0].toolCallId}
              count={row.tools!.length}
            >
              {row.tools!.map((tool) => (
                <ToolCall key={tool.toolCallId} tool={tool} />
              ))}
            </CompletedTools>
          ) : row.kind === "tool" ? (
            <ToolCall key={row.tool.toolCallId} tool={row.tool} />
          ) : row.kind === "thought" ? (
            <details key={i} className="agent-thought">
              <summary>思考过程</summary>
              <p>{row.text}</p>
            </details>
          ) : (
            <article key={i} className={"message " + row.kind}>
              <div className="message-author">
                {row.kind === "user"
                  ? "你"
                  : row.kind === "assistant"
                    ? settings?.agents.find((a) => a.id === state.agentId)
                        ?.name || "Agent"
                    : ""}
              </div>
              <div>{row.text}</div>
            </article>
          ),
        )}
        <div ref={end} />
      </div>
      {permissions.map(
        (event) =>
          event.type === "permission" && (
            <div
              className="agent-permission"
              role="group"
              aria-label="工程操作授权"
              data-permission-id={event.id}
              key={event.id}
            >
              <strong>{event.request.toolCall.title || "工程操作"}</strong>
              <ToolDetails raw={event.request.toolCall.rawInput} />
              <div className="permission-actions">
                {event.request.options
                  .filter(
                    (o) => mode !== "practice" || o.kind !== "allow_always",
                  )
                  .map((o) => (
                    <Button
                      key={o.optionId}
                      size="small"
                      appearance={
                        o.kind === "allow_once" ? "primary" : "secondary"
                      }
                      onClick={() =>
                        perform(() =>
                          window.gongke.agent.permission(event.id, o.optionId),
                        )
                      }
                    >
                      {
                        {
                          allow_once: "允许一次",
                          allow_always: "始终允许",
                          reject_once: "拒绝一次",
                          reject_always: "始终拒绝",
                        }[o.kind]
                      }
                    </Button>
                  ))}
              </div>
            </div>
          ),
      )}
      {(error || (active && state.error)) && (
        <div className="agent-error" role="alert">
          {error || state.error}
          <AgentErrorDetails diagnostic={state.errorDetails} />
        </div>
      )}
      <div className="compose" hidden={!conversationVisible}>
        <Textarea
          aria-label="工程任务"
          placeholder={
            mode === "practice"
              ? "描述你卡住的步骤…"
              : "描述要建的模型或需要检查的地方…"
          }
          value={prompt}
          onChange={(_, d) => setPrompt(d.value)}
          resize="none"
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              (e.ctrlKey || e.metaKey) &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              send();
            }
          }}
        />
        <div>
          <span>Ctrl + Enter 发送</span>
          {["prompting", "cancelling"].includes(state.phase) ? (
            <Button
              icon={<StopRegular />}
              disabled={state.phase === "cancelling"}
              onClick={() => perform(() => window.gongke.agent.cancel())}
            >
              停止
            </Button>
          ) : (
            <Button
              appearance="primary"
              icon={<SendRegular />}
              disabled={!ready || !prompt.trim()}
              onClick={send}
            >
              发送
            </Button>
          )}
        </div>
      </div>
      {editing && settings && (
        <AgentSettings
          value={settings}
          close={() => setEditing(false)}
          save={async (value) => {
            await window.gongke.agent.saveSettings(value);
            setSettings(value);
            setSelected(value.agents[0].id);
          }}
        />
      )}
    </section>
  );
}
