import {
  AgentFailure,
  diagnosticFor,
  failedTools,
  logDiagnostic,
  redact,
  redactRecord,
  secretValues,
} from "./diagnostics.cjs";
import { agentError } from "../onboarding/errors.cjs";
import { spawnAgent, stopAgent } from "./process.cjs";
import { type ChildProcessWithoutNullStreams } from "node:child_process";
import { Readable, Writable } from "node:stream";
import { randomUUID, createHash } from "node:crypto";
import { appendFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type {
  ClientConnection,
  SetSessionConfigOptionRequest,
  NewSessionRequest,
  RequestPermissionResponse,
  PromptRequest,
  RequestPermissionRequest,
} from "@agentclientprotocol/sdk";
import type {
  AgentEvent,
  AgentProfile,
  AgentSnapshot,
  StdioCommand,
} from "./types.cjs";

/** ACP 授权只需带 toolCallId；显示信息从同一次调用的增量事件取得。 */
export function permissionTool(
  events: AgentEvent[],
  request: RequestPermissionRequest,
) {
  let tool: RequestPermissionRequest["toolCall"] = {
    toolCallId: request.toolCall.toolCallId,
  };
  for (const event of events) {
    if (event.type !== "update") continue;
    const update = event.update;
    if (
      (update.sessionUpdate === "tool_call" ||
        update.sessionUpdate === "tool_call_update") &&
      update.toolCallId === tool.toolCallId
    ) {
      const { sessionUpdate, ...fields } = update;
      tool = {
        ...tool,
        ...Object.fromEntries(
          Object.entries(fields).filter(
            ([, value]) => value !== undefined && value !== null,
          ),
        ),
      };
    }
  }
  return {
    ...tool,
    ...Object.fromEntries(
      Object.entries(request.toolCall).filter(
        ([, value]) => value !== undefined && value !== null,
      ),
    ),
  };
}

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
  private stderr = "";
  private secrets: string[] = [];
  constructor(
    private publish: (state: AgentSnapshot) => void,
    private logPath?: string,
    private tracePath?: string,
  ) {}
  private tracedEvents = 0;
  snapshot() {
    return structuredClone({ ...this.state,
      stderr: redact(this.stderr, this.secrets),
      stderrLogPath: this.logPath ? join(dirname(this.logPath), "agent-stderr.log") : undefined,
    });
  }
  private changed() {
    if (this.tracePath) {
      const events = this.state.events.slice(this.tracedEvents);
      appendFileSync(
        this.tracePath,
        events
          .map(
            (event) =>
              JSON.stringify(
                redactRecord(
                  {
                    at: new Date().toISOString(),
                    sessionId: this.state.session?.sessionId,
                    event,
                  },
                  this.secrets,
                ),
              ) + "\n",
          )
          .join(""),
        { mode: 0o600 },
      );
    }
    this.tracedEvents = this.state.events.length;
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
      this.stderr = "";
      this.secrets = secretValues({
        ...process.env,
        ...profile.env,
        ...mcp.env,
      });
      this.cwd = cwd;
      this.mcp = mcp;
      this.state = {
        phase: "starting",
        project: cwd,
        agentId: profile.id,
        authMethods: [],
        events: [],
      };
      this.tracedEvents = 0;
      this.changed();
      const child = spawnAgent(profile.command, profile.args, {
        cwd,
        env: { ...process.env, ...profile.env },
        windowsHide: true,
      });
      this.child = child;
      // 保留有界尾部，在生成诊断时整体脱敏，避免跨 chunk 的凭据漏出。
      child.stderr.setEncoding("utf8");
      const stderrPath = this.snapshot().stderrLogPath;
      const stderrSecrets = [...this.secrets];
      let pendingStderr = "";
      const flushStderr = (finished = false) => {
        const end = finished ? pendingStderr.length : pendingStderr.lastIndexOf("\n") + 1;
        if (end && stderrPath) appendFileSync(stderrPath, redact(pendingStderr.slice(0, end), stderrSecrets), { mode: 0o600 });
        pendingStderr = pendingStderr.slice(end);
      };
      child.stderr.on("data", (chunk: string) => {
        if (this.child === child)
          this.stderr = (this.stderr + chunk).slice(-24000);
        pendingStderr += chunk;
        flushStderr();
      });
      child.stderr.on("end", () => flushStderr(true));
      const connection = sdk
        .client({ name: "gongke-workbench" })
        .onNotification(sdk.methods.client.session.update, ({ params }) => {
          if (this.child !== child) return;
          if (
            this.state.session &&
            params.sessionId !== this.state.session.sessionId
          )
            return;
          if (this.state.session && params.update.sessionUpdate === "config_option_update")
            this.state.session.configOptions = params.update.configOptions;
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
                this.state.events.push({
                  type: "permission-resolved",
                  id,
                  outcome: value.outcome,
                });
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
                request: {
                  ...params,
                  toolCall: permissionTool(this.state.events, params),
                },
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
        this.fail(new Error(message), "process");
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
          void stopAgent(child).catch((error) => this.fail(error, "process"));
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
        this.state.initialization = response;
        this.state.phase = "connected";
        this.changed();
        await this.createSession();
      } catch (error) {
        if (this.child === child && this.state.phase === "starting")
          await this.disconnect();
        if (epoch === this.epoch || !this.child)
          throw this.fail(error, "initialize");
        throw error;
      }
    } catch (error) {
      // spawn 可同步拒绝非法命令参数；不能把此失败留成永久 starting。
      if (!this.child && this.state.phase === "starting") {
        this.state.phase = "disconnected";
      }
      throw this.fail(error, "start");
    } finally {
      this.launchPending = false;
    }
  }
  private fail(error: unknown, operation: string) {
    const diagnostic = diagnosticFor(
      error,
      operation,
      {
        stderr: this.stderr,
        tools: failedTools(this.state.events),
        project: this.state.project,
        sessionId: this.state.session?.sessionId,
      },
      this.secrets,
    );
    logDiagnostic(diagnostic, this.logPath);
    const failure =
      error instanceof AgentFailure
        ? error
        : new AgentFailure(
            this.profile?.id === "deepseek"
              ? agentError(error)
              : redact(
                  error instanceof Error ? error.message : String(error),
                  this.secrets,
                ),
            diagnostic,
          );
    this.state.error = failure.message;
    this.state.errorDetails = diagnostic;
    this.changed();
    return failure;
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
    this.state.errorDetails = undefined;
    this.changed();
    try {
      await agent.request("authenticate", { methodId });
      if (connection !== this.connection) return;
      this.state.phase = "connected";
      await this.createSession();
    } catch (error) {
      if (connection === this.connection) {
        this.state.phase = "connected";
        throw this.fail(error, "authenticate");
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
    this.state.errorDetails = undefined;
    this.state.session = undefined;
    this.state.events = [];
    this.tracedEvents = 0;
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
      const session = await agent.request("session/new", request, {
        cancellationSignal: AbortSignal.timeout(60_000),
        stopWaitingOnCancel: true,
      });
      if (connection !== this.connection) return;
      this.state.session = session;
      this.state.phase = "ready";
      this.changed();
    } catch (error) {
      if (connection === this.connection) {
        this.state.phase = "connected";
        throw this.fail(error, "session/new");
      }
      throw error;
    }
  }
  async setConfigOption(configId: string, value: string) {
    if (this.state.phase !== "ready" || !this.state.session)
      throw new Error("请在会话就绪后切换模型");
    const connection = this.connection;
    const params: SetSessionConfigOptionRequest = { sessionId: this.state.session.sessionId, configId, value };
    this.state.events.push({ type: "request", method: "session/set_config_option", params });
    this.changed();
    try {
      const result = await this.requireConnection().request("session/set_config_option", params);
      if (connection !== this.connection || !this.state.session) return;
      this.state.session.configOptions = result.configOptions;
      this.state.events.push({ type: "config-result", configOptions: result.configOptions });
      this.state.error = undefined;
      this.state.errorDetails = undefined;
      this.changed();
    } catch (error) {
      throw this.fail(error, "session/set_config_option");
    }
  }
  async prompt(
    text: string,
    images: { path: string; mimeType: string; data: string }[] = [],
  ) {
    if (this.state.phase !== "ready" || !text.trim())
      throw new Error("请先建立会话并输入任务");
    const agent = this.requireConnection();
    const connection = this.connection;
    this.state.phase = "prompting";
    this.state.error = undefined;
    this.state.errorDetails = undefined;
    const firstEvent = this.state.events.length;
    this.state.events.push({
      type: "user",
      text,
      ...(images.length
        ? {
            images: images.map(({ path, mimeType, data }) => ({
              path,
              mimeType,
              sha256: createHash("sha256")
                .update(Buffer.from(data, "base64"))
                .digest("hex"),
            })),
          }
        : {}),
    });
    this.changed();
    try {
      const request: PromptRequest = {
        sessionId: this.state.session!.sessionId,
        prompt: [
          { type: "text" as const, text },
          ...images.map(({ mimeType, data }) => ({
            type: "image" as const,
            mimeType,
            data,
          })),
        ],
      };
      // 在实际 request 前记录内容块类型、字节数和哈希；不复制 base64 到日志。
      this.state.events.push({ type: "request", method: "session/prompt", params: {
        sessionId: request.sessionId,
        advertisedImage: this.state.initialization?.agentCapabilities?.promptCapabilities?.image ?? false,
        configOptions: this.state.session?.configOptions,
        prompt: request.prompt.map((block) => block.type === "image" ? {
          type: "image", mimeType: block.mimeType,
          bytes: Buffer.from(block.data, "base64").length,
          sha256: createHash("sha256").update(Buffer.from(block.data, "base64")).digest("hex"),
        } : block),
      } });
      this.changed();
      const result = await agent.request("session/prompt", request);
      if (connection !== this.connection) return;
      this.state.events.push({ type: "turn-result", result });
      const completed =
        result.stopReason === "end_turn" &&
        this.state.events
          .slice(firstEvent)
          .some(
            (event) =>
              event.type === "update" &&
              event.update.sessionUpdate === "agent_message_chunk" &&
              event.update.content.type === "text" &&
              event.update.content.text.trim(),
          );
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
      return {
        completed,
        events: this.state.events.slice(firstEvent),
        sessionId: this.state.session!.sessionId,
      };
    } catch (error) {
      if (connection === this.connection)
        throw this.fail(error, "session/prompt");
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
    this.resolvePermissions();
    if (this.connection && this.state.session && this.state.phase !== "starting" &&
        this.state.initialization?.agentCapabilities?.sessionCapabilities?.close) {
      const params = { sessionId: this.state.session.sessionId };
      this.state.events.push({ type: "request", method: "session/close", params });
      this.changed();
      try {
        await this.requireConnection().request("session/close", params, {
          cancellationSignal: AbortSignal.timeout(10_000), stopWaitingOnCancel: true,
        });
      } catch (error) {
        this.fail(error, "session/close");
      }
    }
    this.epoch++;
    const child = this.child;
    this.child = undefined;
    this.resolvePermissions();
    this.connection?.close();
    this.connection = undefined;
    if (child && child.exitCode === null && child.signalCode === null) {
      await new Promise<void>((resolve, reject) => {
        const finish = (error?: unknown) => {
          clearTimeout(timer);
          child.removeListener("close", closed);
          if (error) reject(error);
          else resolve();
        };
        const closed = () => finish();
        const timer = setTimeout(() => {
          void stopAgent(child, "SIGKILL").catch(finish);
        }, 2000);
        child.once("close", closed);
        void stopAgent(child).catch(finish);
      });
    }
    this.state.phase = "disconnected";
    this.state.session = undefined;
    this.changed();
  }
}
