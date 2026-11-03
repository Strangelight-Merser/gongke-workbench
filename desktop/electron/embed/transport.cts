import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface } from "node:readline";
import { EventEmitter } from "node:events";

// stdout 只承载 JSONL；超时后不重发 attach/close 等有副作用的请求。
export class EmbedTransport extends EventEmitter {
  private child: ChildProcessWithoutNullStreams;
  private nextId = 0;
  private failed = false;
  private pending = new Map<number, { resolve: (result: any) => void; reject: (error: Error) => void; timer: NodeJS.Timeout }>();
  constructor(executable: string, args: string[]) {
    super();
    this.child = spawn(executable, args, { windowsHide: true, stdio: "pipe" });
    createInterface({ input: this.child.stdout }).on("line", (line) => {
      try {
        const value = JSON.parse(line);
        if (value.event) { this.emit("event", value); return; }
        const pending = this.pending.get(value.id);
        if (!pending) return;
        clearTimeout(pending.timer); this.pending.delete(value.id);
        if (value.error) pending.reject(new Error(value.error)); else pending.resolve(value.result);
      } catch { this.fail(new Error("窗口辅助进程返回了无效消息")); }
    });
    this.child.stderr.on("data", (data) => this.emit("diagnostic", String(data)));
    this.child.on("error", (error) => this.fail(error));
    this.child.on("exit", (code) => this.fail(new Error(`窗口辅助进程已退出 (${code})；恢复守护进程将尝试释放 CAD 窗口`)));
    this.child.stdin.on("error", (error) => this.fail(error));
  }
  private fail(error: Error) {
    if (this.failed) return;
    this.failed = true;
    for (const item of this.pending.values()) { clearTimeout(item.timer); item.reject(error); }
    this.pending.clear();
    this.emit("event", { event: "failure", message: error.message });
  }
  request<T = any>(method: string, params: object = {}): Promise<T> {
    if (this.failed) return Promise.reject(new Error("窗口辅助进程不可用，请重启构想引擎"));
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`窗口操作 ${method} 未及时返回；请刷新状态，不要重复启动 CAD`));
      }, 10000);
      this.pending.set(id, { resolve, reject, timer });
      this.child.stdin.write(JSON.stringify({ id, method, params }) + "\n");
    });
  }
  async stop() {
    try { if (!this.failed) await this.request("shutdown"); }
    finally { this.child.stdin.end(); }
  }
}
