import { useState, type ReactNode } from "react";
import { Button } from "@fluentui/react-components";
import type { Data } from "../api";
import { stepTitle, stepInput, commandOf } from "./modelingSteps";

// MCP task 完成只表示调用完成；工程检查结论位于 result，必须保留其 unknown/unverified/fail。
function receiptResult(value: Data, isError?: boolean): Data {
  if (value.task_id && value.result && typeof value.result === "object")
    return {
      ...value.result,
      task_id: value.task_id,
      project: value.project,
      isError:
        isError || ["failed", "interrupted", "canceled"].includes(value.status),
    };
  return { ...value, isError: isError || value.isError };
}
// 界面层只挑选信息，不改变宿主回执、单位或操作状态。
export function toolResult(tool: Data): Data {
  const output = tool.rawOutput;
  if (output?.structuredContent)
    return receiptResult(output.structuredContent, output.isError);
  if (
    output != null &&
    typeof output === "object" &&
    !Array.isArray(output.content)
  )
    return receiptResult(output);
  const content = output?.content || tool.content;
  const text =
    typeof output === "string"
      ? output
      : content
          ?.map((c: Data) =>
            c.type === "text"
              ? c.text
              : c.type === "content" && c.content?.type === "text"
                ? c.content.text
                : "",
          )
          .filter(Boolean)
          .join("\n");
  if (!text) return output || {};
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object"
      ? receiptResult(parsed, output?.isError)
      : { message: text, isError: output?.isError };
  } catch {
    return { message: text, isError: output?.isError };
  }
}
export function toolState(status: string, result: Data) {
  if (
    status === "failed" ||
    result?.error ||
    result?.isError ||
    result?.status === "fail" ||
    result?.checks?.some((c: Data) => c.status === "fail" || c.ok === false)
  )
    return "failed";
  if (
    status === "completed" &&
    (result?.status === "unknown" ||
      result?.checks?.some((c: Data) => c.status === "unknown") ||
      (result?.state && result.state !== "finished"))
  )
    return "unknown";
  if (
    status === "completed" &&
    (result?.status === "unverified" ||
      result?.checks?.some((c: Data) => c.status === "unverified"))
  )
    return "unverified";
  return status;
}
export const toolStates: Record<string, string> = {
  completed: "完成",
  failed: "失败",
  pending: "等待授权",
  in_progress: "执行中",
  unknown: "待核实",
  unverified: "未经独立核对",
};
function shortText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "object")
    return shortText(
      (value as Data).message ||
        (value as Data).detail ||
        JSON.stringify(value),
    );
  return String(value);
}
function TextPreview({ text }: { text: string }) {
  const [all, setAll] = useState(false);
  return (
    <>
      <div className="tool-text">
        {all ? text : text.slice(0, 240)}
        {!all && text.length > 240 ? "…" : ""}
      </div>
      {text.length > 240 && (
        <Button size="small" appearance="subtle" onClick={() => setAll(!all)}>
          {all ? "收起" : "显示全部"}
        </Button>
      )}
    </>
  );
}
// 名称来自回执或本次请求；没有可读名称时只描述已提供的类型和尺寸。
export function featureDescription(
  command: string,
  params: Data = {},
  result: Data = {},
) {
  const input = stepInput(command, params);
  const label = [
    result.label,
    result.name,
    input.name,
    input.feature?.name,
  ].find((value) => typeof value === "string" && /[\u3400-\u9fff]/.test(value));
  if (label) return label;
  if (input.feature?.kind)
    return stepTitle("host.feature", { feature: input.feature });
  const kind = commandOf(command, params);
  if (kind === "host.sketch")
    return stepTitle("host.sketch", {
      ...input,
      name: undefined,
      sketch_ref: undefined,
    });
  if (kind === "host.body") return "实体";
  return "未提供特征名称";
}
export function ToolDetails({
  result = {},
  raw,
  children,
  featureLabel,
}: {
  result?: Data;
  featureLabel?: string;
  raw: unknown;
  children?: ReactNode;
}) {
  const message = shortText(
    result?.error ||
      result?.message ||
      result?.detail ||
      (typeof result === "string" ? result : ""),
  );
  const checks: Data[] = Array.isArray(result?.checks) ? result.checks : [];
  return (
    <div className="tool-details">
      {message && <TextPreview text={message} />}
      {result?.native_ref && <p>特征：{featureLabel || "未提供特征名称"}</p>}
      {result?.deleted_ref && (
        <p>已删除特征：{featureLabel || "未提供特征名称"}</p>
      )}
      {!!checks.length && (
        <div className="tool-checks">
          {result.scope && <p>{result.scope}</p>}
          {checks.map((c, i) => (
            <p key={i} data-failed={c.status === "fail" || c.ok === false}>
              {c.item || c.id || c.name} ·{" "}
              {c.status === "fail" || c.ok === false
                ? "不符"
                : c.status === "pass" || c.ok === true
                  ? "通过"
                  : c.status === "unverified"
                    ? "未经独立核对"
                    : "待核实"}
              {c.source_kind && (
                <>
                  {" "}
                  ·{" "}
                  {
                    {
                      drawing_annotation: "图纸标注",
                      drawing_geometry: "图纸几何",
                      agent_defined: "Agent 自定",
                    }[c.source_kind as string]
                  }
                </>
              )}
              {c.evidence?.text && (
                <>
                  {" "}
                  · 标注 {c.evidence.text}（第 {c.evidence.page} 页，
                  {c.evidence.item}）
                </>
              )}
              {c.missing_or_shifted?.length > 0 && (
                <> · 缺少或偏移 {c.missing_or_shifted.length} 条边</>
              )}
              {c.extra_or_shifted?.length > 0 && (
                <> · 多出或偏移 {c.extra_or_shifted.length} 条边</>
              )}
              {c.reason && <span> · {c.reason}</span>}
              {c.expected != null && typeof c.expected !== "object" && (
                <>
                  {" "}
                  · 要求 {shortText(c.expected)} {c.unit}
                </>
              )}
              {c.actual != null && typeof c.actual !== "object" && (
                <>
                  {" "}
                  · 实测 {shortText(c.actual)} {c.unit}
                </>
              )}
              {c.message || c.detail ? (
                <> · {shortText(c.message || c.detail)}</>
              ) : null}
            </p>
          ))}
        </div>
      )}
      {Array.isArray(result.items) &&
        result.items
          .filter(
            (item: Data) =>
              item.type === "text" &&
              item.dimension_candidate &&
              /^\d+(?:\.\d+)?$/.test(item.text),
          )
          .map((item: Data) => (
            <details key={item.source} className="drawing-annotation">
              <summary>标注 {item.text}</summary>
              <p>
                第 {result.page} 页 · 图纸原文 {item.text}
              </p>
            </details>
          ))}
      {children}
      <details className="agent-raw">
        <summary>原始参数与回执</summary>
        <pre tabIndex={0}>{JSON.stringify(raw, null, 2)}</pre>
      </details>
    </div>
  );
}
export function ToolCall({ tool }: { tool: Data }) {
  const result = toolResult(tool),
    state = toolState(tool.status, result);
  const title = stepTitle(tool.title || "工程操作", tool.rawInput || {});
  return (
    <details className="agent-tool" data-state={state}>
      <summary>
        <span className="tool-title" title={title}>
          {title}
        </span>
        <span className="tool-status">
          {state === "failed" &&
          tool.status !== "failed" &&
          !result.error &&
          !result.isError
            ? "尺寸不符"
            : toolStates[state] || "等待中"}
        </span>
      </summary>
      <ToolDetails
        result={result}
        raw={tool}
        featureLabel={featureDescription(
          tool.title || "",
          tool.rawInput || {},
          result,
        )}
      />
    </details>
  );
}
export function CompletedTools({
  count,
  children,
}: {
  count: number;
  children: ReactNode;
}) {
  return (
    <details className="agent-tool-group">
      <summary>已完成 {count} 步</summary>
      {children}
    </details>
  );
}
