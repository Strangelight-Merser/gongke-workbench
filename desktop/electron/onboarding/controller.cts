import { agentError } from "./errors.cjs";
import {
  AgentFailure,
  diagnosticFor,
  failedTools,
  logDiagnostic,
  redact,
} from "../acp/diagnostics.cjs";
import { existsSync, readFileSync, writeFileSync, renameSync } from "node:fs";
import { join } from "node:path";
import type { AgentClient } from "../acp/client.cjs";
import type { AgentConfiguration } from "../acp/settings.cjs";
import { releases } from "./releases.cjs";
import type {
  OnboardingAction,
  OnboardingState,
  Progress,
  Provider,
  Release,
} from "./types.cjs";
export const links = {
  register: "https://platform.deepseek.com/",
  balance: "https://platform.deepseek.com/balance",
  keys: "https://platform.deepseek.com/api_keys",
  help: "https://static.deepseek.com/faq/index.html?lang=zh",
  workbuddy: "https://www.workbuddy.cn/",
};
export const firstPrompt =
  "请只调用 gongke 的 project.current 读取当前工程，告诉我工程名称、路径和当前状态，并在回复末尾原样列出工具返回的 task_id。不要调用文件、终端或其他工具。";
export type Dependencies = {
  directory: string;
  canInstall: boolean;
  agent: Pick<AgentClient, "start" | "prompt" | "snapshot" | "busy">;
  configuration: Pick<AgentConfiguration, "read" | "save" | "launch">;
  project(): string;
  detect(provider: Provider, saved?: string): Promise<Partial<Progress>>;
  locate(provider: Provider): Promise<Partial<Progress> | undefined>;
  openAgent(provider: Provider, progress: Progress): Promise<void>;
  openLink(url: string): Promise<void>;
  install(
    release: Release,
    signal: AbortSignal,
    progress: (phase: string, received: number) => void,
  ): Promise<void>;
  configureWorkbuddy(): Promise<unknown>;
  task(id: string): Promise<any>;
  publish(state: OnboardingState): void;
};
export function validReceipt(record: any, project: string, since: string) {
  return (
    record?.kind === "mcp" &&
    record.status === "complete" &&
    record.project === project &&
    Date.parse(record.created_at) >= Date.parse(since) &&
    record.result?.path === project &&
    record.receipts?.some(
      (r: any) =>
        r.command === "project.current" &&
        r.phase === "finished" &&
        r.result?.path === project,
    )
  );
}
export class Onboarding {
  private data: Pick<OnboardingState, "selected" | "agents"> = {
    selected: "deepseek",
    agents: { deepseek: { step: "detect" }, workbuddy: { step: "detect" } },
  };
  private error?: string;
  private errorDetails?: OnboardingState["errorDetails"];
  private installing?: OnboardingState["installing"];
  private abort?: AbortController;
  private working = false;
  private path: string;
  constructor(private d: Dependencies) {
    this.path = join(d.directory, "agent-onboarding.json");
    if (existsSync(this.path))
      this.data = JSON.parse(readFileSync(this.path, "utf8"));
  }
  snapshot(): OnboardingState {
    const state: OnboardingState = {
      ...structuredClone(this.data),
      error: this.error,
      errorDetails: this.errorDetails,
      installing: this.installing,
      releases,
      canInstall: this.d.canInstall,
      working: this.working,
    };
    for (const progress of Object.values(state.agents)) {
      if (
        ["verify", "complete"].includes(progress.step) &&
        progress.project !== this.d.project()
      )
        progress.step = "connect";
    }
    return state;
  }
  externalFailure(message: string) {
    this.error = message;
    this.publish();
  }
  private publish() {
    this.d.publish(this.snapshot());
  }
  private save() {
    const temp = this.path + ".tmp";
    writeFileSync(temp, JSON.stringify(this.data, null, 2), { mode: 0o600 });
    renameSync(temp, this.path);
    this.publish();
  }
  private progress() {
    return this.data.agents[this.data.selected];
  }
  private async detectOne(provider: Provider) {
    const p = this.data.agents[provider];
    const found = await this.d.detect(
      provider,
      provider === "deepseek" ? p.command : p.application,
    );
    const installed =
      provider === "deepseek" ? found.command : found.application;
    this.data.agents[provider] = {
      ...p,
      command: undefined,
      application: undefined,
      version: undefined,
      ...found,
      step: installed
        ? ["detect", "install"].includes(p.step)
          ? provider === "deepseek"
            ? "account"
            : "connect"
          : p.step
        : "install",
    };
  }
  private requireProject() {
    const project = this.d.project();
    if (!project) throw new Error("请先创建或打开工程，再连接 Agent");
    return project;
  }
  async act(action: OnboardingAction): Promise<OnboardingState> {
    if (action.type === "cancel-install") {
      this.abort?.abort();
      return this.snapshot();
    }
    if (this.working) throw new Error("请等待当前引导操作结束");
    this.working = true;
    this.error = undefined;
    this.errorDetails = undefined;
    this.publish();
    try {
      const provider = this.data.selected;
      const p = this.progress();
      switch (action.type) {
        case "select":
          if (!["deepseek", "workbuddy"].includes(action.provider))
            throw new Error("无效的 Agent");
          this.data.selected = action.provider;
          break;
        case "detect":
          // 一项检测失败仍保留另一项的结果。
          for (const id of ["deepseek", "workbuddy"] as const) {
            try {
              await this.detectOne(id);
            } catch {
              this.error = "部分 Agent 检测失败，请重试或选择安装位置。";
            }
          }
          break;
        case "locate": {
          const found = await this.d.locate(provider);
          if (found)
            Object.assign(p, found, {
              step: provider === "deepseek" ? "account" : "connect",
            });
          break;
        }
        case "install": {
          if (action.consent !== true)
            throw new Error("请先同意下载和运行官方安装器");
          if (!this.d.canInstall)
            throw new Error(
              "自动安装仅支持 Windows x64；请安装官方客户端后选择安装位置",
            );
          const release = releases.find((r) => r.provider === provider)!;
          p.step = "install";
          this.save();
          const abort = new AbortController();
          this.abort = abort;
          try {
            await this.d.install(
              release,
              this.abort.signal,
              (phase, received) => {
                this.installing = {
                  provider,
                  phase,
                  received,
                  total: release.size,
                };
                this.publish();
              },
            );
            await this.detectOne(provider);
            if (this.data.agents[provider].step === "install")
              throw new Error(
                "安装向导已关闭，但没有检测到 Agent。请重试检测或选择安装位置。",
              );
          } catch (error) {
            if (abort.signal.aborted)
              throw new Error("下载已取消，可稍后重试。");
            throw error;
          } finally {
            this.abort = undefined;
            this.installing = undefined;
          }
          break;
        }
        case "link":
          if (!Object.hasOwn(links, action.link))
            throw new Error("无效的官方页面");
          await this.d.openLink(links[action.link]);
          break;
        case "advance":
          if (!["account", "credentials", "connect"].includes(action.step))
            throw new Error("无效的引导步骤");
          p.step = action.step;
          break;
        case "open-agent":
          await this.d.openAgent(provider, p);
          break;
        case "connect": {
          const project = this.requireProject();
          if (this.d.agent.busy) throw new Error("请先结束当前 Agent 操作");
          if (provider === "deepseek") {
            if (!p.command) throw new Error("请先检测或选择 dsh 安装位置");
            const config = this.d.configuration.read();
            const profile = config.agents.find((a) => a.id === "deepseek");
            if (!profile)
              throw new Error(
                "连接设置中缺少 deepseek，请恢复 DeepSeek Harness 配置",
              );
            profile.command = p.command;
            this.d.configuration.save(config);
            const launch = this.d.configuration.launch("deepseek", project);
            try {
              await this.d.agent.start(launch.profile, project, launch.mcp);
            } catch (error) {
              if (error instanceof AgentFailure) throw error;
              throw new AgentFailure(
                agentError(error),
                diagnosticFor(error, "connect"),
              );
            }
          } else {
            if (!p.application)
              throw new Error("请先检测或选择 WorkBuddy 安装位置");
            await this.d.configureWorkbuddy();
          }
          Object.assign(p, {
            step: "verify",
            project,
            configuredAt: new Date().toISOString(),
            verifiedAt: undefined,
            evidence: undefined,
          });
          break;
        }
        case "verify": {
          if (provider !== "deepseek")
            throw new Error("请在 WorkBuddy 中完成首次对话");
          const project = this.requireProject();
          const state = this.d.agent.snapshot();
          if (
            state.phase !== "ready" ||
            state.project !== project ||
            state.agentId !== "deepseek"
          )
            throw new Error("请先连接当前工程的 DeepSeek Harness");
          const since = new Date().toISOString();
          p.step = "verify";
          p.project = project;
          this.save();
          let result;
          try {
            result = await this.d.agent.prompt(firstPrompt);
          } catch (error) {
            if (error instanceof AgentFailure) throw error;
            throw new AgentFailure(
              agentError(error),
              diagnosticFor(error, "session/prompt"),
            );
          }
          if (!result?.completed)
            throw new Error("首次对话未完成或已取消，请重试首次对话");
          const ids = [
            ...new Set(
              JSON.stringify(result.events).match(/\b[a-f0-9]{32}\b/g) || [],
            ),
          ];
          let receipt: string | undefined;
          for (const id of ids) {
            let task;
            try {
              task = await this.d.task(id);
            } catch {
              continue;
            }
            if (validReceipt(task, project, since)) {
              receipt = id;
              break;
            }
          }
          if (project !== this.d.project())
            throw new Error("工程已切换，请重新连接");
          if (!receipt)
            throw new Error(
              "已收到回复，但尚未核实本次工程读取成功。请批准 project.current 后重试首次对话。",
            );
          Object.assign(p, {
            step: "complete",
            verifiedAt: new Date().toISOString(),
            evidence: receipt,
          });
          break;
        }
        case "confirm-workbuddy": {
          const project = this.requireProject();
          if (
            provider !== "workbuddy" ||
            p.project !== project ||
            !p.configuredAt ||
            action.sawReply !== true
          )
            throw new Error("请先配置当前工程，并在 WorkBuddy 中确认真实回复");
          if (!/^[a-f0-9]{32}$/.test(action.taskId))
            throw new Error(
              "请填入 WorkBuddy 回复中的 task_id（32 位），不要填写 API Key",
            );
          const task = await this.d.task(action.taskId);
          if (!validReceipt(task, project, p.configuredAt))
            throw new Error(
              "该任务不是本次配置后成功读取当前工程的记录，请在 WorkBuddy 重试 project.current",
            );
          Object.assign(p, {
            step: "complete",
            verifiedAt: new Date().toISOString(),
            evidence: action.taskId,
          });
          break;
        }
        default:
          throw new Error("不支持的引导操作");
      }
    } catch (error) {
      this.errorDetails = diagnosticFor(error, `onboarding/${action.type}`, {
        project: this.d.project(),
        tools: failedTools(this.d.agent.snapshot().events || []),
      });
      logDiagnostic(
        this.errorDetails,
        join(this.d.directory, "agent-errors.jsonl"),
      );
      this.error = this.abort?.signal.aborted
        ? "下载已取消，可稍后重试。"
        : error instanceof Error
          ? redact(error.message)
          : "操作失败，请重试";
    } finally {
      this.working = false;
      this.save();
    }
    return this.snapshot();
  }
}
