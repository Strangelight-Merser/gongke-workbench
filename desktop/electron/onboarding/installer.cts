import { createHash } from "node:crypto";
import { mkdtemp, open, rm, statfs } from "node:fs/promises";
import { join } from "node:path";
import { spawn } from "node:child_process";
import { ps } from "./discovery.cjs";
import type { Release } from "./types.cjs";

export async function verifySignature(
  file: string,
  release: Release,
  run = ps,
) {
  const literal = file.replaceAll("'", "''");
  let result: { status: string; thumbprint: string };
  try {
    const { stdout } = await run(
      `$ErrorActionPreference='Stop'; $s=Get-AuthenticodeSignature -LiteralPath '${literal}'; @{status=$s.Status.ToString(); thumbprint=$s.SignerCertificate.Thumbprint} | ConvertTo-Json -Compress`,
    );
    result = JSON.parse(stdout.trim());
  } catch {
    throw new Error(
      "无法完成 Windows 签名校验，已停止安装。请检查 PowerShell、系统权限和网络后重试。",
    );
  }
  if (
    result.status !== "Valid" ||
    result.thumbprint !== release.signerThumbprint
  )
    throw new Error(
      "Windows 签名或发布者校验失败，已停止安装。请检查系统时间和网络后重试，仍失败请联系支持。",
    );
}
export async function runInstaller(file: string) {
  await new Promise<void>((resolve, reject) => {
    // 原厂交互安装，不传静默参数；安装位置由安装向导选择。
    const child = spawn(file, [], { stdio: "ignore" });
    child.once("error", () =>
      reject(new Error("无法打开安装器；请检查 Windows 权限后重试")),
    );
    child.once("exit", (code) =>
      code === 0
        ? resolve()
        : reject(new Error(`安装未完成（${code}），可重试或选择已安装的位置`)),
    );
  });
}
export type InstallDependencies = {
  fetch: typeof fetch;
  signature: typeof verifySignature;
  launch: typeof runInstaller;
};
export async function installRelease(
  release: Release,
  cache: string,
  signal: AbortSignal,
  progress: (phase: string, received: number) => void,
  dependencies: InstallDependencies = {
    fetch,
    signature: verifySignature,
    launch: runInstaller,
  },
) {
  const disk = await statfs(cache);
  if (disk.bavail * disk.bsize < release.size)
    throw new Error(
      `下载目录空间不足，请至少释放 ${Math.ceil(release.size / 1024 / 1024)} MiB 后重试；安装所需空间由安装器检查`,
    );
  const directory = await mkdtemp(join(cache, "gongke-agent-"));
  const file = join(directory, "setup.exe");
  try {
    progress("正在下载", 0);
    const response = await dependencies
      .fetch(release.url, {
        signal: AbortSignal.any([signal, AbortSignal.timeout(15 * 60_000)]),
        redirect: "error",
      })
      .catch(() => {
        throw new Error("下载失败或超时，请检查网络后重试");
      });
    if (!response.ok || !response.body)
      throw new Error("下载失败，请检查网络后重试");
    const length = response.headers.get("content-length");
    if (length && Number(length) !== release.size)
      throw new Error(
        "安装包大小与版本清单不符，已停止安装；请更新构想引擎后重试",
      );
    const hash = createHash("sha512");
    let size = 0;
    const output = await open(file, "wx", 0o600);
    try {
      for await (const chunk of response.body as any as AsyncIterable<Uint8Array>) {
        signal.throwIfAborted();
        size += chunk.length;
        if (size > release.size) throw new Error("安装包大小不符，已停止安装");
        hash.update(chunk);
        await output.writeFile(chunk);
        progress("正在下载", size);
      }
    } finally {
      await output.close();
    }
    if (size !== release.size || hash.digest("base64") !== release.sha512)
      throw new Error(
        "安装包摘要校验失败，已停止安装；请重试下载，仍失败请更新构想引擎",
      );
    signal.throwIfAborted();
    progress("正在校验 Windows 签名", size);
    await dependencies.signature(file, release);
    signal.throwIfAborted();
    progress("请完成安装向导", size);
    await dependencies.launch(file);
  } catch (error) {
    if ((error as NodeJS.ErrnoException)?.code === "ENOSPC")
      throw new Error("下载目录空间不足，请释放磁盘空间后重试");
    throw error;
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}
