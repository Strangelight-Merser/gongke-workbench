import { appendFileSync } from "node:fs";
import type { AgentEvent } from "./types.cjs";

export type AgentDiagnostic = {
  at: string;
  operation: string;
  message: string;
  code?: number | string;
  details?: string;
  stderr?: string;
  tools?: string;
  sessionId?: string;
  project?: string;
  logPath?: string;
  logError?: string;
};
const credentialName =
  /authorization|cookie|api[_-]?key|token|secret|password/i;
export function secretValues(env: Record<string, string | undefined>) {
  return Object.entries(env)
    .filter(([name, value]) => credentialName.test(name) && value)
    .map(([, value]) => value!);
}
/** 先脱敏再截断；不把启动环境、请求头或完整对话作为诊断输出。 */
export function redact(text: string, secrets: string[] = []) {
  for (const secret of secrets) text = text.replaceAll(secret, "[REDACTED]");
  return text
    .replace(/\x1b\[[0-9;]*m/g, "")
    .replace(/\b(?:Bearer|Basic)\s+[^\s"'\\,}]+/gi, "Bearer [REDACTED]")
    .replace(/\bsk-[a-zA-Z0-9_-]+/g, "[REDACTED]")
    .replace(
      /((?:[\w-]*(?:api[_-]?key|token|secret|password|authorization|cookie)[\w-]*)["']?\s*[:=]\s*)("(?:\\.|[^"\\])*"|'[^']*'|[^\s,;&}]+)/gi,
      "$1[REDACTED]",
    )
    .replace(/(https?:\/\/)[^\s/@]+:[^\s/@]+@/gi, "$1[REDACTED]@");
}
export function failedTools(events: AgentEvent[]) {
  const failed = events.filter(
    (e) =>
      e.type === "update" &&
      (e.update.sessionUpdate === "tool_call" ||
        e.update.sessionUpdate === "tool_call_update") &&
      e.update.status === "failed",
  );
  return failed.length ? JSON.stringify(failed.slice(-4)) : undefined;
}
export class AgentFailure extends Error {
  constructor(
    message: string,
    readonly diagnostic: AgentDiagnostic,
  ) {
    super(message);
    this.name = "AgentFailure";
  }
}
export function diagnosticFor(
  error: unknown,
  operation: string,
  context: Partial<AgentDiagnostic> = {},
  secrets: string[] = [],
): AgentDiagnostic {
  if (error instanceof AgentFailure) return error.diagnostic;
  const value = error as {
    message?: string;
    code?: number | string;
    data?: unknown;
    cause?: unknown;
  };
  const clean = (text: string) => redact(text, secrets).slice(-12000);
  return {
    ...context,
    at: new Date().toISOString(),
    operation,
    message: clean(String(value?.message || error)),
    code: value?.code,
    details:
      value?.data === undefined && value?.cause === undefined
        ? undefined
        : clean(
            JSON.stringify({
              data: value?.data,
              cause:
                value?.cause instanceof Error
                  ? value.cause.message
                  : value?.cause,
            }),
          ),
    stderr: context.stderr ? clean(context.stderr) : undefined,
    tools: context.tools ? clean(context.tools) : undefined,
  };
}
export function logDiagnostic(diagnostic: AgentDiagnostic, path?: string) {
  if (!path || diagnostic.logPath) return;
  try {
    diagnostic.logPath = path;
    appendFileSync(path, JSON.stringify(diagnostic) + "\n", { mode: 0o600 });
  } catch (error) {
    diagnostic.logPath = undefined;
    diagnostic.logError = redact(String(error));
  }
}
