import { call, Data } from "../api";
export const mutations = new Set([
  "parameter.change",
  "drawing.update",
  "document.save_copy",
  "drawing.export",
  "drawing.edit_text",
  "drawing.move_dimension_text",
]);
export const normalPath = (value: string) =>
  value.replace(/\\/g, "/").toLowerCase();
export const pendingKey = (kind: string) => "gongke-native-unresolved-" + kind;
export function savedPending(kind: string): Data | null {
  try {
    return JSON.parse(localStorage.getItem(pendingKey(kind)) || "null");
  } catch {
    return null;
  }
}
export async function registeredWorkingCopy(kind: string, request: Data) {
  const project = await call("project.current");
  const path = request.params.output_path || request.params.target_path;
  const paths = [path, request.params.output_part_path].filter(Boolean);
  if (
    !path ||
    !paths.every((target) =>
      (project?.working_copies || []).some(
        (copy: Data) =>
          copy.host === kind &&
          copy.operation_id === request.operation_id &&
          normalPath(copy.path) === normalPath(target),
      ),
    )
  )
    throw new Error("工作副本尚未完成工程登记；保留原操作，请查询核对后继续");
  return { project, path };
}
export function operationResult(value: Data): Data {
  return (
    value.response?.result ||
    (value.response?.error && { error: value.response.error }) ||
    value
  );
}
