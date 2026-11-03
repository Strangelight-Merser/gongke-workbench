import { existsSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { homedir } from "node:os";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { resolveCommand } from "../acp/settings.cjs";
import { spawnAgent, stopAgent } from "../acp/process.cjs";
import type { Provider, Progress } from "./types.cjs";
const exec = promisify(execFile);
export const powershell = () =>
  join(
    process.env.SystemRoot || "C:\\Windows",
    "System32",
    "WindowsPowerShell",
    "v1.0",
    "powershell.exe",
  );
export async function ps(script: string) {
  return exec(
    powershell(),
    [
      "-NoProfile",
      "-NonInteractive",
      "-EncodedCommand",
      Buffer.from(script, "utf16le").toString("base64"),
    ],
    { windowsHide: true, timeout: 30_000 },
  );
}
export function installation(
  provider: Provider,
  location: string,
): Partial<Progress> | undefined {
  const directory = existsSync(location) && statSync(location).isDirectory();
  if (provider === "workbuddy") {
    const app =
      directory && !location.endsWith(".app")
        ? join(location, "WorkBuddy.exe")
        : location;
    if (existsSync(app) && /(?:WorkBuddy\.exe|WorkBuddy\.app)$/i.test(app))
      return { application: app };
    return;
  }
  const candidates = directory
    ? [
        join(location, "resources/runtime/cli/bin/dsh.cmd"),
        join(location, "Contents/Resources/runtime/cli/bin/dsh"),
        join(location, process.platform === "win32" ? "dsh.cmd" : "dsh"),
      ]
    : [location];
  const command = candidates.find(
    (p) => existsSync(p) && /(?:^|[/\\])dsh(?:\.cmd|\.exe)?$/i.test(p),
  );
  if (!command) return;
  const app = command.includes("/Contents/Resources/")
    ? command.split("/Contents/")[0]
    : /resources[/\\]runtime[/\\]cli[/\\]bin[/\\]dsh.cmd$/i.test(command)
      ? join(dirname(command), "../../../..", "DeepSeek Harness.exe")
      : undefined;
  return { command, application: app && existsSync(app) ? app : undefined };
}
export async function detect(
  provider: Provider,
  saved?: string,
): Promise<Partial<Progress>> {
  const candidates = saved ? [saved] : [];
  if (process.platform === "darwin") {
    const name =
      provider === "deepseek" ? "DeepSeek Harness.app" : "WorkBuddy.app";
    candidates.push(
      join("/Applications", name),
      join(homedir(), "Applications", name),
    );
  }
  if (process.platform === "win32") {
    const name = provider === "deepseek" ? "DeepSeek Harness" : "WorkBuddy";
    for (const base of [
      process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, "Programs"),
      process.env.LOCALAPPDATA,
      process.env.ProgramFiles,
    ])
      if (base) candidates.push(join(base, name));
    // 安装器允许自选目录；读取 Windows 已安装应用登记，不扫描用户数据。
    const { stdout } = await ps(
      `$ErrorActionPreference='Stop'; $OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); @(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*','HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*','HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*' -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like '${name}*' } | ForEach-Object { if ($_.InstallLocation) { $_.InstallLocation }; if ($_.DisplayIcon) { ($_.DisplayIcon -replace ',\\d+$','').Trim('"') } }) | ConvertTo-Json -Compress`,
    );
    if (stdout.trim()) candidates.push(...[].concat(JSON.parse(stdout)));
  }
  if (provider === "deepseek") {
    try {
      candidates.push(resolveCommand("dsh"));
    } catch {
      /* 未安装 CLI */
    }
  }
  for (const path of candidates) {
    let found = installation(provider, path);
    if (!found && /DeepSeek Harness.exe$/i.test(path))
      found = installation(provider, dirname(path));
    if (found) {
      if (found.command) found.version = await cliVersion(found.command);
      return found;
    }
  }
  return {};
}
export async function cliVersion(command: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawnAgent(command, ["--version"], { windowsHide: true });
    let output = "";
    const timer = setTimeout(() => {
      void stopAgent(child).then(
        () => reject(new Error("读取 dsh 版本超时，请重新选择安装位置")),
        reject,
      );
    }, 15_000);
    child.stdout.on("data", (chunk) => {
      if (output.length < 4096) output += chunk;
    });
    child.stderr.resume();
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      const version = output.match(/\b\d+\.\d+\.\d+(?:-[\w.-]+)?\b/)?.[0];
      if (code === 0 && version) resolve(version);
      else reject(new Error("dsh 无法启动，请重新选择安装位置或重新安装"));
    });
  });
}
