import type { AgentDiagnostic } from "../../electron/acp/diagnostics.cjs";

export function AgentErrorDetails({
  diagnostic,
}: {
  diagnostic?: AgentDiagnostic;
}) {
  if (!diagnostic) return null;
  return (
    <details className="agent-error-details">
      <summary>错误详情</summary>
      <p>
        {diagnostic.operation}
        {diagnostic.code !== undefined ? ` · 错误码 ${diagnostic.code}` : ""}
      </p>
      <pre>{diagnostic.message}</pre>
      {diagnostic.details && (
        <>
          <strong>ACP 详情</strong>
          <pre>{diagnostic.details}</pre>
        </>
      )}
      {diagnostic.tools && (
        <>
          <strong>工程工具失败</strong>
          <pre>{diagnostic.tools}</pre>
        </>
      )}
      {diagnostic.stderr && (
        <>
          <strong>Agent 进程输出（末尾摘要）</strong>
          <pre>{diagnostic.stderr}</pre>
        </>
      )}
      {diagnostic.logPath && <p>日志：{diagnostic.logPath}</p>}
      {diagnostic.logError && <p>日志未能写入：{diagnostic.logError}</p>}
    </details>
  );
}
