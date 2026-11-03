import { AgentErrorDetails } from "./AgentErrorDetails";
import { Link, Select } from "@fluentui/react-components";
import { guideProgress, recoveryFor } from "./onboardingPresentation";
import { Button, Input, Checkbox } from "../ui/controls";
import { useEffect, useState } from "react";
import type {
  OnboardingAction,
  OnboardingState,
  Step,
} from "../../electron/onboarding/types.cjs";
import { errorText } from "../api";

export function AgentOnboarding({
  project,
  onConnected,
  openRequest = 0,
  onStep,
  hidden = false,
}: {
  project?: string;
  onConnected(): Promise<void>;
  hidden?: boolean;
  openRequest?: number;
  onStep(step: Step): void;
}) {
  const [state, setState] = useState<OnboardingState>();
  const [error, setError] = useState("");
  const [acting, setActing] = useState(false);
  const [consent, setConsent] = useState(false);
  const [taskId, setTaskId] = useState("");
  const [sawReply, setSawReply] = useState(false);
  const [expanded, setExpanded] = useState(true);
  async function act(action: OnboardingAction) {
    setError("");
    setActing(true);
    try {
      const next = await window.gongke.onboarding.act(action);
      setState(next);
      if (next.error) setExpanded(true);
      if (
        action.type === "connect" &&
        next.selected === "deepseek" &&
        !next.error
      )
        await onConnected();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setActing(false);
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
  const step = state?.agents[state.selected].step;
  useEffect(() => {
    if (step) {
      setExpanded(step !== "complete");
      onStep(step);
    }
  }, [step, onStep]);
  useEffect(() => {
    if (openRequest) setExpanded(true);
  }, [openRequest]);
  if (!state)
    return (
      <p className="agent-onboarding" hidden={hidden}>
        {error || "正在检测 Agent…"}
      </p>
    );
  const p = state.agents[state.selected];
  if (p.step === "complete" && !expanded) return null;
  const dsh = state.selected === "deepseek";
  const release = state.releases.find((r) => r.provider === state.selected)!;
  const busy = state.working || acting;
  const progress = guideProgress(state.selected, p.step);
  const failure = error || state.error || "";
  const recovery = recoveryFor(failure);
  const installed = dsh ? p.command : p.application;
  const button = (
    label: string,
    action: OnboardingAction,
    disabled = false,
  ) => (
    <Button
      appearance="primary"
      className="onboarding-primary-action"
      disabled={busy || disabled}
      onClick={() => act(action)}
    >
      {label}
    </Button>
  );
  const secondary = (
    label: string,
    action: OnboardingAction,
    disabled = false,
  ) => (
    <Link
      as="button"
      className="onboarding-link"
      disabled={busy || disabled}
      onClick={() => act(action)}
    >
      {label}
    </Link>
  );
  const link = (
    label: string,
    name: "register" | "balance" | "keys" | "help" | "workbuddy",
  ) => secondary(label, { type: "link", link: name });
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
    <div
      hidden={hidden}
      data-step={p.step}
      className={
        "agent-onboarding" +
        (p.step !== "complete" ? " onboarding-primary" : "")
      }
    >
      {p.step !== "complete" ? (
        <h3 className="onboarding-heading">连接你的 Agent</h3>
      ) : (
        <Button
          className="onboarding-heading"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {labels[p.step]} <span>{expanded ? "收起" : "展开"}</span>
        </Button>
      )}
      {(p.step !== "complete" || expanded) && (
        <div className="onboarding-body">
          <Select
            aria-label="引导 Agent"
            size="small"
            value={state.selected}
            disabled={busy}
            onChange={(e) =>
              act({
                type: "select",
                provider: e.target.value as "deepseek" | "workbuddy",
              })
            }
          >
            <option value="deepseek">DeepSeek Harness</option>
            <option value="workbuddy">WorkBuddy</option>
          </Select>
          <ol className="onboarding-steps" aria-label="连接引导步骤">
            {progress.labels.map((label, index) => (
              <li
                key={label}
                aria-current={index === progress.index ? "step" : undefined}
                data-complete={index < progress.index}
              >
                <span>{index + 1}</span>
                {label}
              </li>
            ))}
          </ol>
          {p.step === "detect" && (
            <>
              <p>检测已有的 Agent，或选择它的安装目录。</p>
              {button("检测安装", { type: "detect" })}
            </>
          )}
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
                <>
                  <p>
                    自动安装目前支持 Windows
                    x64。此电脑请先安装官方客户端，再重新检测或选择安装位置。
                  </p>
                  {button("检测已安装的 Agent", { type: "detect" })}
                </>
              )}
              {!dsh && link("WorkBuddy 官网", "workbuddy")}
            </>
          )}
          {["detect", "install"].includes(p.step) && (
            <div className="onboarding-actions">
              {secondary("选择安装位置", { type: "locate" })}
              {p.step === "install" &&
                state.canInstall &&
                secondary("已安装，重新检测", { type: "detect" })}
            </div>
          )}
          {state.installing && (
            <div role="status">
              <p>{state.installing.phase}</p>
              <progress
                value={state.installing.received}
                max={state.installing.total}
              />
              {state.installing.phase !== "请完成安装向导" && (
                <Button onClick={() => act({ type: "cancel-install" })}>
                  取消下载
                </Button>
              )}
              <p>
                离开后可以继续；若安装向导已打开，请在向导中取消或完成安装。
              </p>
            </div>
          )}
          {dsh && p.step === "account" && (
            <>
              <p>
                注册 DeepSeek API 账号，确认余额后创建 API Key。费用和充值由
                DeepSeek 平台处理。
              </p>
              {button("注册或登录 DeepSeek", {
                type: "link",
                link: "register",
              })}
              <div className="onboarding-actions">
                {link("余额与充值", "balance")}
                {link("创建 API Key", "keys")}
              </div>
              <div className="onboarding-actions">
                {secondary("下一步：在 dsh 填 Key", {
                  type: "advance",
                  step: "credentials",
                })}
                {secondary("已配置，直接连接", {
                  type: "advance",
                  step: "connect",
                })}
              </div>
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
                {secondary("已保存，下一步", {
                  type: "advance",
                  step: "connect",
                })}
              </div>
            </>
          )}
          {p.step === "connect" && (
            <>
              <p>
                {dsh
                  ? "连接当前工程后，发送首次对话验证模型与工程工具。"
                  : "预览用户级 WorkBuddy 配置中的工程专属连接器。同意后先备份，再更新该条目，保留其他服务。"}
              </p>
              {!dsh && p.conflicts && <div role="alert">
                <p>将写入 {p.configPath}。以下旧连接器或同名条目会保留：</p>
                {p.conflicts.map((c) => <p key={c.path + c.name}>{c.path}：{c.name}（{c.reason}）</p>)}
                <p>使用 {p.serviceName}，固定绑定当前工程、默认只读。此连接器在 WorkBuddy 的其他工作空间也可见；切换工程不会改变它绑定的路径。</p>
                {button("同意备份并写入用户配置", { type: "connect", confirmUserConfig: true }, !project)}
              </div>}
              {!project && <p>先创建或打开一个工程。</p>}
              {button(
                dsh ? "连接 dsh" : "预览 WorkBuddy 配置",
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
                {secondary("重新连接 dsh", { type: "connect" }, !project)}
              </>
            ) : (
              <>
                <p>配置已写入 {p.configPath}。{p.backupPath && `备份：${p.backupPath}`}</p>
                <p>退出并重新打开 WorkBuddy，在“专家·技能·连接器 → 连接器 → 自定义连接器”信任并启用新服务；再新建任务，工作目录选择：</p>
                <p className="onboarding-url">{project}</p>
                <p>在 WorkBuddy 中启用 {p.serviceName || "gongke"}，确认包含 project.current，再发送：</p>
                <blockquote>
                  请只调用 {p.serviceName || "gongke"} 的
                  project.current，告诉我当前工程名称、路径和状态，并列出工具返回的
                  task_id。
                </blockquote>
                {secondary("打开 WorkBuddy", { type: "open-agent" })}
                <label className="onboarding-check">
                  <Checkbox
                    checked={sawReply}
                    onChange={(_, data) => setSawReply(data.checked === true)}
                  />
                  我已看到绿色 MCP 状态和本次真实回复，工程名称、路径正确。
                </label>
                <label>
                  回复中的 task_id
                  <Input
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
                {secondary("重新生成配置", { type: "connect" }, !project)}
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
          {failure && (
            <div className="onboarding-error" role="alert">
              <p>{failure}</p>
              <AgentErrorDetails diagnostic={state.errorDetails} />
              {dsh && installed && (
                <div className="onboarding-actions">
                  {recovery.key &&
                    secondary("去 dsh 更新 Key", { type: "open-agent" })}
                  {recovery.balance && link("去充值", "balance")}
                </div>
              )}
            </div>
          )}
          <div className="onboarding-support">
            {installed && (
              <details>
                <summary>安装信息</summary>
                <p className="onboarding-url">
                  {installed}
                  {p.version ? ` · ${p.version}` : ""}
                </p>
              </details>
            )}
            {link("官方帮助", dsh ? "help" : "workbuddy")}
          </div>
        </div>
      )}
    </div>
  );
}
