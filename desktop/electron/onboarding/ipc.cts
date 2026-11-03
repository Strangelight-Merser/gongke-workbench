import { app, dialog, shell, type BrowserWindow } from "electron";
import { spawn } from "node:child_process";
import { AgentClient } from "../acp/client.cjs";
import { AgentConfiguration } from "../acp/settings.cjs";
import { launchSpec } from "../acp/process.cjs";
import { Onboarding } from "./controller.cjs";
import { detect, installation, cliVersion } from "./discovery.cjs";
import { installRelease } from "./installer.cjs";
import type { OnboardingAction } from "./types.cjs";

export function registerOnboarding(options: {
  window: BrowserWindow;
  agent: AgentClient;
  configuration: AgentConfiguration;
  project(): string;
  request(method: string, params?: any): Promise<any>;
  handle(name: string, action: (...args: any[]) => unknown): void;
}) {
  const { window, agent, configuration, project, request, handle } = options;
  const onboarding = new Onboarding({
    directory: app.getPath("userData"),
    canInstall: process.platform === "win32" && process.arch === "x64",
    agent,
    configuration,
    project,
    detect,
    publish: (state) => {
      if (!window.isDestroyed())
        window.webContents.send("onboarding-state", state);
    },
    openLink: (url) => shell.openExternal(url),
    locate: async (provider) => {
      const result = await dialog.showOpenDialog(window, {
        title:
          provider === "deepseek"
            ? "选择 dsh 安装目录或 dsh 命令"
            : "选择 WorkBuddy 安装目录或应用",
        properties:
          process.platform === "win32"
            ? ["openDirectory"]
            : ["openFile", "openDirectory"],
      });
      if (result.canceled) return;
      const found = installation(provider, result.filePaths[0]);
      if (!found)
        throw new Error(
          "该位置没有找到 Agent。请选择应用安装目录；dsh CLI 可选择所在的 bin 目录。",
        );
      if (found.command) found.version = await cliVersion(found.command);
      return found;
    },
    openAgent: async (provider, progress) => {
      if (progress.application) {
        const error = await shell.openPath(progress.application);
        if (error) throw new Error("无法打开 Agent，请重试检测或选择安装位置");
      } else if (provider === "deepseek" && progress.command) {
        // 官方 web profile 自行打开浏览器并管理登录，工作台不读取其输出中的认证 URL。
        const spec = launchSpec(progress.command, ["web"]);
        await new Promise<void>((resolve, reject) => {
          const child = spawn(spec.command, spec.args, {
            cwd: app.getPath("userData"),
            detached: true,
            stdio: "ignore",
            windowsHide: true,
            windowsVerbatimArguments: spec.windowsVerbatimArguments,
          });
          child.once("error", () =>
            reject(new Error("无法打开 dsh，请重试检测或选择安装位置")),
          );
          child.once("exit", (code) => {
            if (code !== 0)
              onboarding.externalFailure(
                "dsh 配置页面未能启动。请重新检测或选择安装位置，也可在已安装的 dsh 客户端内更新 Key。",
              );
          });
          child.once("spawn", () => {
            child.unref();
            resolve();
          });
        });
      } else throw new Error("请先检测或选择 Agent 安装位置");
    },
    install: (release, signal, progress) =>
      installRelease(release, app.getPath("temp"), signal, progress),
    configureWorkbuddy: () => request("mcp.configure", { allow_writes: false }),
    task: (id) => request("task.get", { task_id: id }),
  });
  handle("onboarding-state", () => onboarding.snapshot());
  handle("onboarding-action", (action: OnboardingAction) =>
    onboarding.act(action),
  );
  void onboarding.act({ type: "detect" });
  return onboarding;
}
