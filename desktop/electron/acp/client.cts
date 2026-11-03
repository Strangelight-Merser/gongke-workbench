import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { Readable, Writable } from "node:stream";
import { randomUUID } from "node:crypto";
import type {
  ClientConnection,
  NewSessionRequest,
  RequestPermissionResponse,
} from "@agentclientprotocol/sdk";
import type { AgentProfile, AgentSnapshot, StdioCommand } from "./types.cjs";

/** ACP 只负责会话与授权；不实现文件写入或 terminal 执行。 */
export class AgentClient {
  private child?: ChildProcessWithoutNullStreams;
  private connection?: ClientConnection;
  private pending = new Map<
    string,
    { options: string[]; resolve: (value: RequestPermissionResponse) => void }
  >();
  private state: AgentSnapshot = {
    phase: "disconnected",
    project: "",
    agentId: "",
    authMethods: [],
    events: [],
  };
  private cwd = "";
  private profile?: AgentProfile;
  private launchPending = false;
  private epoch = 0;
  private mcp?: StdioCommand;
  constructor(private publish: (state: AgentSnapshot) => void) {}
  snapshot() {
    return structuredClone(this.state);
  }
  private changed() {
    this.publish(this.snapshot());
  }
  private requireConnection() {
    if (!this.connection || this.connection.signal.aborted)
      throw new Error("Agent 未连接");
    return this.connection.agent;
  }
  get busy() {
    return (
      this.launchPending ||
      ["starting", "authenticating", "prompting", "cancelling"].includes(
        this.state.phase,
      )
    );
  }
  async start(profile: AgentProfile, cwd: string, mcp: StdioCommand) {
    if (this.busy) throw new Error("请先取消当前 Agent 操作");
    this.launchPending = true;
    try {
      await this.disconnect();
      const epoch = this.epoch;
      const sdk = await import("@agentclientprotocol/sdk");
      if (epoch !== this.epoch) throw new Error("连接已取消");
      this.profile = profile;
      this.cwd = cwd;
      this.mcp = mcp;
      this.state = {
        phase: "starting",
        project: cwd,
        agentId: profile.id,
        authMethods: [],
        events: [],
      };
      this.changed();
      const child = spawn(profile.command, profile.args, {
        cwd,
        env: { ...process.env, ...profile.env },
        stdio: "pipe",
        windowsHide: true,
      });
      this.child = child;
      // Agent 的 stderr 可能含账号信息，不广播到 renderer 或持久化。
      child.stderr.resume();
      const connection = sdk
        .client({ name: "gongke-workbench" })
        .onNotification(sdk.methods.client.session.update, ({ params }) => {
          if (this.child !== child) return;
          if (
            this.state.session &&
            params.sessionId !== this.state.session.sessionId
          )
            return;
          this.state.events.push({ type: "update", update: params.update });
          this.changed();
        })
        .onRequest(
          sdk.methods.client.session.requestPermission,
          ({ params, signal }) => {
            if (
              signal.aborted ||
              this.child !== child ||
              this.state.phase !== "prompting" ||
              params.sessionId !== this.state.session?.sessionId
            )
              return { outcome: { outcome: "cancelled" as const } };
            const id = randomUUID();
            return new Promise<RequestPermissionResponse>((resolve) => {
              const finish = (value: RequestPermissionResponse) => {
                signal.removeEventListener("abort", abort);
                this.pending.delete(id);
                this.state.events.push({ type: "permission-resolved", id });
                this.changed();
                resolve(value);
              };
              const abort = () => finish({ outcome: { outcome: "cancelled" } });
              this.pending.set(id, {
                options: params.options.map((o) => o.optionId),
                resolve: finish,
              });
              signal.addEventListener("abort", abort, { once: true });
              this.state.events.push({
                type: "permission",
                id,
                request: params,
              });
              this.changed();
            });
          },
        )
        .connect(
          sdk.ndJsonStream(
            Writable.toWeb(child.stdin),
            Readable.toWeb(child.stdout) as ReadableStream<Uint8Array>,
          ),
        );
      this.connection = connection;
      const ended = (message: string) => {
        connection.close(new Error(message));
        if (this.child !== child) return;
        this.resolvePermissions();
        this.child = undefined;
        this.connection = undefined;
        this.state.phase = "disconnected";
        this.state.error = message;
        this.changed();
      };
      child.once("error", (error) => ended(`Agent 启动失败：${error.message}`));
      child.once("exit", (code, signal) =>
        ended(
          `Agent 已退出（${signal || code}）；未确认的工程操作请先读回状态。`,
        ),
      );
      connection.closed.then(() => {
        if (this.child === child) {
          ended("Agent 协议连接已关闭");
          child.kill();
        }
      });
      try {
        const response = await connection.agent.request(
          sdk.methods.agent.initialize,
          {
            protocolVersion: sdk.PROTOCOL_VERSION,
            clientInfo: {
              name: "gongke-workbench",
              title: "构想引擎",
              version: "0.2.0",
            },
            clientCapabilities: {
              fs: { readTextFile: false, writeTextFile: false },
              terminal: false,
            },
          },
          {
            cancellationSignal: AbortSignal.timeout(30_000),
            stopWaitingOnCancel: true,
          },
        );
        if (response.protocolVersion !== sdk.PROTOCOL_VERSION)
          throw new Error("Agent 不支持 ACP v1");
        this.state.authMethods = response.authMethods || [];
        this.state.phase = "connected";
        this.changed();
        await this.createSession();
      } catch (error) {
        if (this.child === child && this.state.phase === "starting")
          await this.disconnect();
        if (epoch === this.epoch || !this.child) this.fail(error);
        throw error;
      }
    } finally {
      this.launchPending = false;
    }
  }
  private fail(error: unknown) {
    const detail = (error as { data?: { details?: unknown } })?.data?.details;
    this.state.error =
      (error instanceof Error ? error.message : String(error)) +
      (typeof detail === "string" ? `：${detail}` : "");
    this.changed();
  }
  async authenticate(methodId: string) {
    if (this.busy) throw new Error("Agent 正忙");
    const method = this.state.authMethods.find((m) => m.id === methodId);
    if (!method || ("type" in method && method.type === "terminal"))
      throw new Error("该登录方式不支持 ACP authenticate");
    const agent = this.requireConnection();
    const connection = this.connection;
    this.state.phase = "authenticating";
    this.state.error = undefined;
    this.changed();
    try {
      await agent.request("authenticate", { methodId });
      if (connection !== this.connection) return;
      this.state.phase = "connected";
      await this.createSession();
    } catch (error) {
      if (connection === this.connection) {
        this.state.phase = "connected";
        this.fail(error);
      }
      throw error;
    }
  }
  async newSession() {
    if (this.busy) throw new Error("请先结束当前 Agent 操作");
    if (this.state.session)
      return this.start(this.profile!, this.cwd, this.mcp!);
    return this.createSession();
  }
  private async createSession() {
    const agent = this.requireConnection();
    const connection = this.connection;
    const mcp = this.mcp!;
    this.state.phase = "starting";
    this.state.error = undefined;
    this.state.session = undefined;
    this.state.events = [];
    this.changed();
    try {
      const request: NewSessionRequest = {
        cwd: this.cwd,
        mcpServers: [
          {
            name: "gongke",
            command: mcp.command,
            args: mcp.args,
            env: Object.entries(mcp.env).map(([name, value]) => ({
              name,
              value,
            })),
          },
        ],
      };
      const session = await agent.request("session/new", request);
      if (connection !== this.connection) return;
      this.state.session = session;
      this.state.phase = "ready";
      this.changed();
    } catch (error) {
      if (connection === this.connection) {
        this.state.phase = "connected";
        this.fail(error);
      }
      throw error;
    }
  }
  async prompt(text: string) {
    if (this.state.phase !== "ready" || !text.trim())
      throw new Error("请先建立会话并输入任务");
    const agent = this.requireConnection();
    const connection = this.connection;
    this.state.phase = "prompting";
    this.state.error = undefined;
    this.state.events.push({ type: "user", text });
    this.changed();
    try {
      const result = await agent.request("session/prompt", {
        sessionId: this.state.session!.sessionId,
        prompt: [{ type: "text", text }],
      });
      if (connection !== this.connection) return;
      this.state.events.push({
        type: "notice",
        text:
          result.stopReason === "cancelled"
            ? "已取消；已完成的工程操作不会撤销。"
            : {
                end_turn: "本轮完成",
                max_tokens: "已达到输出长度限制",
                max_turn_requests: "已达到本轮调用次数限制",
                refusal: "Agent 拒绝了本次请求",
              }[result.stopReason] || `本轮结束：${result.stopReason}`,
      });
    } catch (error) {
      if (connection === this.connection) this.fail(error);
      throw error;
    } finally {
      if (connection === this.connection) {
        this.resolvePermissions();
        this.state.phase = "ready";
        this.changed();
      }
    }
  }
  permission(id: string, optionId: string | null) {
    const pending = this.pending.get(id);
    if (!pending) throw new Error("此权限请求已结束");
    if (optionId !== null && !pending.options.includes(optionId))
      throw new Error("无效的权限选项");
    pending.resolve({
      outcome:
        optionId === null
          ? { outcome: "cancelled" }
          : { outcome: "selected", optionId },
    });
  }
  private resolvePermissions() {
    for (const pending of [...this.pending.values()])
      pending.resolve({ outcome: { outcome: "cancelled" } });
  }
  async cancel() {
    if (!["prompting", "cancelling"].includes(this.state.phase)) return;
    this.state.phase = "cancelling";
    this.changed();
    this.resolvePermissions();
    await this.requireConnection().notify("session/cancel", {
      sessionId: this.state.session!.sessionId,
    });
    // 等待 session/prompt 结束才重新开放发送，不能把取消通知当作完成。
  }
  async disconnect() {
    this.epoch++;
    const child = this.child;
    this.child = undefined;
    this.resolvePermissions();
    this.connection?.close();
    this.connection = undefined;
    if (child && child.exitCode === null && child.signalCode === null) {
      await new Promise<void>((resolve) => {
        const timer = setTimeout(() => child.kill("SIGKILL"), 2000);
        child.once("close", () => {
          clearTimeout(timer);
          resolve();
        });
        child.kill();
      });
    }
    this.state.phase = "disconnected";
    this.state.session = undefined;
    this.changed();
  }
}
