import {
  execFile,
  spawn,
  type ChildProcess,
  type SpawnOptionsWithoutStdio,
} from "node:child_process";
import { win32 } from "node:path";

// .cmd 需要 cmd.exe；禁用 AutoRun 和延迟扩展，参数逐个引用。
// % 会被 cmd 在引号内展开，内嵌引号会打断边界；明确拒绝这些输入。
export function launchSpec(
  command: string,
  args: string[],
  platform = process.platform,
) {
  if (platform !== "win32" || !/\.(cmd|bat)$/i.test(command))
    return { command, args, windowsVerbatimArguments: false };
  const quote = (value: string) => {
    if (/["%\r\n\0]/.test(value))
      throw new Error(
        "Windows 命令路径或参数不能包含双引号、百分号或换行；请选择其他安装目录",
      );
    return `"${value.replace(/(\\+)$/, "$1$1")}"`;
  };
  return {
    command: win32.join(
      process.env.SystemRoot || "C:\\Windows",
      "System32",
      "cmd.exe",
    ),
    args: [
      "/d",
      "/s",
      "/v:off",
      "/c",
      `"${[command, ...args].map(quote).join(" ")}"`,
    ],
    windowsVerbatimArguments: true,
  };
}
export function spawnAgent(
  command: string,
  args: string[],
  options: SpawnOptionsWithoutStdio,
) {
  const spec = launchSpec(command, args);
  return spawn(spec.command, spec.args, {
    ...options,
    windowsVerbatimArguments: spec.windowsVerbatimArguments,
    stdio: "pipe",
  });
}

// Windows 的 .cmd 有包装进程，必须一并结束它的 dsh/MCP 子进程。
export async function stopAgent(
  child: ChildProcess,
  signal: NodeJS.Signals = "SIGTERM",
) {
  if (process.platform === "win32" && child.pid) {
    await new Promise<void>((resolve, reject) => {
      execFile(
        win32.join(
          process.env.SystemRoot || "C:\\Windows",
          "System32",
          "taskkill.exe",
        ),
        ["/pid", String(child.pid), "/T", "/F"],
        { windowsHide: true },
        (error) => {
          if (error && child.exitCode === null && child.signalCode === null)
            reject(
              new Error(
                "无法结束 Agent 进程树，请在任务管理器确认 dsh 已退出后重连",
              ),
            );
          else resolve();
        },
      );
    });
  } else child.kill(signal);
}
