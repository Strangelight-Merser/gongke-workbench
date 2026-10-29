import { spawn, ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface } from "node:readline";
import { EventEmitter } from "node:events";

/** 每次重启建立独立请求表；服务退出后不重放任何原生写操作。 */
export class Service extends EventEmitter {
  child?: ChildProcessWithoutNullStreams;
  private seq = 0;
  private pending = new Map<
    number,
    {
      resolve: (value: any) => void;
      reject: (error: Error) => void;
      timer: NodeJS.Timeout;
    }
  >();
  constructor(
    private executable: string,
    private args: string[],
    private cwd: string,
    private env: NodeJS.ProcessEnv,
  ) {
    super();
  }
  start() {
    if (this.child) return;
    const child = spawn(this.executable, this.args, {
      cwd: this.cwd,
      env: this.env,
      stdio: "pipe",
      windowsHide: true,
    });
    this.child = child;
    createInterface({ input: child.stdout }).on("line", (line) => {
      let value: any;
      try {
        value = JSON.parse(line);
      } catch {
        return;
      }
      if (value.id !== undefined) {
        const item = this.pending.get(value.id);
        if (!item) return;
        clearTimeout(item.timer);
        this.pending.delete(value.id);
        value.error
          ? item.reject(new Error(value.error.message || String(value.error)))
          : item.resolve(value.result);
      } else if (value.event) this.emit("event", value);
    });
    // stderr 不进入界面或日志文件，防止第三方异常意外包含凭据。
    child.stderr.resume();
    child.on("error", () => this.end("工程服务未能启动，请检查安装是否完整"));
    child.on("exit", () =>
      this.end("工程服务已退出；未确认的原生操作请先读取状态"),
    );
  }
  private end(message: string) {
    this.child = undefined;
    for (const p of this.pending.values()) {
      clearTimeout(p.timer);
      p.reject(new Error(message));
    }
    this.pending.clear();
    this.emit("event", { event: "service.stopped", message });
  }
  request(method: string, params: Record<string, unknown> = {}) {
    if (!this.child) return Promise.reject(new Error("工程服务未运行"));
    const id = ++this.seq;
    return new Promise<any>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("命令等待超时；请读取任务状态，不要重复提交写操作"));
      }, 120_000);
      this.pending.set(id, { resolve, reject, timer });
      this.child!.stdin.write(
        JSON.stringify({ id, method, params }) + "\n",
        (err) => {
          if (err) {
            clearTimeout(timer);
            this.pending.delete(id);
            reject(err);
          }
        },
      );
    });
  }
  async stop() {
    const child = this.child;
    if (!child) return;
    await new Promise<void>((resolve) => {
      child.once("exit", () => resolve());
      child.kill();
    });
  }
}
