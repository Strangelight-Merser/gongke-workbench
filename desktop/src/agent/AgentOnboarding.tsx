import { useEffect, useState } from "react";
import type {
  OnboardingAction,
  OnboardingState,
} from "../../electron/onboarding/types.cjs";
import { errorText } from "../api";
import "./onboarding.css";

export function AgentOnboarding({
  project,
  onConnected,
}: {
  project?: string;
  onConnected(): void;
}) {
  const [state, setState] = useState<OnboardingState>();
  const [error, setError] = useState("");
  const [consent, setConsent] = useState(false);
  const [taskId, setTaskId] = useState("");
  const [sawReply, setSawReply] = useState(false);
  const [expanded, setExpanded] = useState(true);
  async function act(action: OnboardingAction) {
    setError("");
    if (action.type === "verify") setExpanded(false);
    try {
      const next = await window.gongke.onboarding.act(action);
      setState(next);
      if (next.error) setExpanded(true);
      if (
        action.type === "connect" &&
        next.selected === "deepseek" &&
        !next.error
      )
        onConnected();
    } catch (e) {
      setError(errorText(e));
    }
  }
  useEffect(() => {
    let active = true;
    const stop = window.gongke.onboarding.onState((s) => {
      if (active) setState(s);
    });
    window.gongke.onboarding
      .state()
      .then((s) => {
        if (!active) return;
        setState(s);
        setExpanded(s.agents[s.selected].step !== "complete");
      })
      .catch((e) => active && setError(errorText(e)));
    return () => {
      active = false;
      stop();
    };
  }, [project]);
  useEffect(() => {
    setConsent(false);
    setTaskId("");
    setSawReply(false);
  }, [state?.selected, project]);
  if (!state)
    return <p className="agent-onboarding">{error || "正在检测 Agent…"}</p>;
  const p = state.agents[state.selected];
  const dsh = state.selected === "deepseek";
  const release = state.releases.find((r) => r.provider === state.selected)!;
  const busy = state.working;
  const installed = dsh ? p.command : p.application;
  const button = (
    label: string,
    action: OnboardingAction,
    disabled = false,
  ) => (
    <button disabled={busy || disabled} onClick={() => act(action)}>
      {label}
    </button>
  );
  const link = (
    label: string,
    name: "register" | "balance" | "keys" | "help" | "workbuddy",
  ) => button(label, { type: "link", link: name });
  const labels = {
    detect: "检测 Agent",
    install: "安装 Agent",
    account: "开通 DeepSeek API",
    credentials: "在 dsh 填写 Key",
    connect: "连接工程",
    verify: "首次对话",
    complete: "引导已完成",
  };
  return (
    <div className="agent-onboarding">
      <button
        className="onboarding-heading"
        aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}
      >
        {labels[p.step]} <span>{expanded ? "收起" : "展开"}</span>
      </button>
      {expanded && (
        <div className="onboarding-body">
          <div
            className="onboarding-actions"
            role="group"
            aria-label="引导 Agent 选择"
          >
            <button
              aria-pressed={dsh}
              disabled={busy}
              onClick={() => act({ type: "select", provider: "deepseek" })}
            >
              DeepSeek Harness
            </button>
            <button
              aria-pressed={!dsh}
              disabled={busy}
              onClick={() => act({ type: "select", provider: "workbuddy" })}
            >
              WorkBuddy
            </button>
          </div>
          {installed && (
            <p className="onboarding-location" title={installed}>
              {dsh ? "dsh" : "WorkBuddy"}
              {p.version ? ` ${p.version}` : ""} · {installed}
            </p>
          )}
          <div className="onboarding-actions">
            {button("重新检测", { type: "detect" })}
            {button("选择安装位置", { type: "locate" })}
          </div>
          {p.step === "detect" && <p>检测已有的 Agent，或选择它的安装目录。</p>}
          {p.step === "install" && (
            <>
              <p>
                {dsh
                  ? "安装 dsh，在当前面板对话。API 按 DeepSeek 平台用量计费。"
                  : "WorkBuddy 在自己的窗口中对话，通过 MCP 操作当前工程；账号与费用在 WorkBuddy 内管理。"}
              </p>
              {state.canInstall ? (
                <>
                  <p>
                    {release.version} ·{" "}
                    {(release.size / 1024 / 1024).toFixed(1)} MiB · Windows x64
                  </p>
                  <details>
                    <summary>下载来源与校验</summary>
                    <p className="onboarding-url">{release.url}</p>
                    <p className="onboarding-url">SHA-512: {release.sha512}</p>
                  </details>
                  <label className="onboarding-check">
                    <input
                      type="checkbox"
                      checked={consent}
                      disabled={busy}
                      onChange={(e) => setConsent(e.target.checked)}
                    />
                    同意下载并打开官方安装器，安装目录在向导中选择。
                  </label>
                  {button(
                    "下载并安装",
                    { type: "install", consent: true },
                    !consent,
                  )}
                </>
              ) : (
                <p>
                  自动安装目前支持 Windows
                  x64。此电脑请先安装官方客户端，再重新检测或选择安装位置。
                </p>
              )}
              {!dsh && link("WorkBuddy 官网", "workbuddy")}
            </>
          )}
          {state.installing && (
            <div role="status">
              <p>{state.installing.phase}</p>
              <progress
                value={state.installing.received}
                max={state.installing.total}
              />
              {state.installing.phase !== "请完成安装向导" && (
                <button onClick={() => act({ type: "cancel-install" })}>
                  取消下载
                </button>
              )}
              <p>
                离开后可以继续；若安装向导已打开，请在向导中取消或完成安装。
              </p>
            </div>
          )}
          {dsh && p.step === "account" && (
            <>
              <ol>
                <li>
                  {link("注册或登录 DeepSeek", "register")}
                  <p>按平台提示完成账号验证。</p>
                </li>
                <li>
                  {link("余额与充值", "balance")}
                  <p>由你在平台付款，金额以平台页面为准。</p>
                </li>
                <li>{link("创建 API Key", "keys")}</li>
              </ol>
              {button("下一步：在 dsh 配置", {
                type: "advance",
                step: "credentials",
              })}
              {button("已配置，直接连接", { type: "advance", step: "connect" })}
            </>
          )}
          {dsh && p.step === "credentials" && (
            <>
              <p>
                打开 dsh → Settings → Models → DeepSeek，填写 API Key
                并保存。Key 仅由 dsh 管理。
              </p>
              <div className="onboarding-actions">
                {button("打开 dsh", { type: "open-agent" })}
                {button("已保存，下一步", { type: "advance", step: "connect" })}
              </div>
            </>
          )}
          {p.step === "connect" && (
            <>
              <p>
                {dsh
                  ? "连接当前工程后，发送首次对话验证模型与工程工具。"
                  : "生成当前工程的 .workbuddy/mcp.json，保留其他 MCP 服务。随后在 WorkBuddy 选择同一个工程目录。"}
              </p>
              {!project && <p>先创建或打开一个工程。</p>}
              {button(
                dsh ? "连接 dsh" : "生成工程 MCP 配置",
                { type: "connect" },
                !project,
              )}
            </>
          )}
          {p.step === "verify" &&
            (dsh ? (
              <>
                <p>
                  发送一次真实对话，读取工程名称与状态。出现工程授权时请选择“允许一次”。本次对话会产生
                  API 用量。
                </p>
                {button("发送首次对话", { type: "verify" }, !project)}
                {button("重新连接 dsh", { type: "connect" }, !project)}
              </>
            ) : (
              <>
                <p>打开 WorkBuddy 并登录，工作目录选择：</p>
                <p className="onboarding-url">{project}</p>
                <p>在 MCP 服务器中信任 gongke，确认绿色状态，再发送：</p>
                <blockquote>
                  请只调用 gongke 的
                  project.current，告诉我当前工程名称、路径和状态，并列出工具返回的
                  task_id。
                </blockquote>
                {button("打开 WorkBuddy", { type: "open-agent" })}
                <label className="onboarding-check">
                  <input
                    type="checkbox"
                    checked={sawReply}
                    onChange={(e) => setSawReply(e.target.checked)}
                  />
                  我已看到绿色 MCP 状态和本次真实回复，工程名称、路径正确。
                </label>
                <label>
                  回复中的 task_id
                  <input
                    aria-label="WorkBuddy 任务编号"
                    value={taskId}
                    maxLength={32}
                    placeholder="32 位任务编号"
                    onChange={(e) => setTaskId(e.target.value.trim())}
                  />
                </label>
                {button(
                  "核对工程回执并完成",
                  { type: "confirm-workbuddy", taskId, sawReply: true },
                  !sawReply || !/^[a-f0-9]{32}$/.test(taskId),
                )}
                {button("重新生成配置", { type: "connect" }, !project)}
              </>
            ))}
          {p.step === "complete" && (
            <>
              <p>
                {dsh
                  ? "真实对话与当前工程读取已验证。"
                  : "工程读取回执已验证；WorkBuddy 回复由你确认。"}
              </p>
              {button(
                dsh ? "重新连接 dsh" : "重新配置工程",
                { type: "connect" },
                !project,
              )}
            </>
          )}
          {(error || state.error) && (
            <p role="alert" className="onboarding-error">
              {error || state.error}
            </p>
          )}
          {dsh && installed && (
            <div className="onboarding-actions">
              {button("去 dsh 更新 Key", { type: "open-agent" })}
              {link("去充值", "balance")}
              {link("API Keys", "keys")}
              {link("官方帮助", "help")}
            </div>
          )}
          <small>进度自动保存。可以先离开，返回后继续。</small>
        </div>
      )}
    </div>
  );
}
