import type { Data } from "../api";

// 检查回执的展示数据；数值必须由检查方提供，不能从 detail 文案猜测。
export type ModelTarget = {
  host: "freecad" | "solidworks" | "autocad";
  session_id: string;
  document_path: string;
  expected_revision: number;
  object_name?: string;
  host_id?: string;
  configuration?: string;
  persistent_reference?: string;
  document_id?: string;
  handle?: string;
};
export type ModelCheck = {
  item: string;
  expected?: number | string;
  actual?: number | string;
  unit?: string;
  ok?: boolean;
  detail?: string;
  target?: ModelTarget;
};
export function measurement(value: ModelCheck["actual"], unit = "") {
  if (value == null || (typeof value === "number" && !Number.isFinite(value)))
    return "未提供";
  return `${typeof value === "number" ? Number(value.toFixed(6)) : value}${unit ? " " + unit : ""}`;
}
export function deviation(check: ModelCheck) {
  if (
    typeof check.expected !== "number" ||
    typeof check.actual !== "number" ||
    !Number.isFinite(check.expected) ||
    !Number.isFinite(check.actual)
  )
    return "无法比较";
  const delta = Number((check.actual - check.expected).toFixed(6));
  return `${delta > 0 ? "+" : ""}${measurement(delta, check.unit)}`;
}
export function canLocate(target?: ModelTarget): target is ModelTarget {
  return (
    !!target &&
    !!target.session_id &&
    !!target.document_path &&
    Number.isInteger(target.expected_revision) &&
    (target.host === "freecad"
      ? !!target.object_name
      : target.host === "solidworks"
        ? !!target.host_id &&
          !!target.persistent_reference &&
          typeof target.configuration === "string"
        : target.host === "autocad" &&
          !!target.host_id &&
          !!target.document_id &&
          !!target.handle)
  );
}
export async function locateModelTarget(
  target: ModelTarget,
  request: (method: string, params?: Data) => Promise<Data>,
) {
  if (!canLocate(target))
    throw new Error("该检查记录缺少原生对象定位信息，请重新检查。");
  if (target.host === "freecad") {
    const current = await request("freecad.context");
    if (
      current.session_id !== target.session_id ||
      current.path !== target.document_path ||
      current.revision !== target.expected_revision
    )
      throw new Error("模型文档或修订已变化，请重新检查后定位。");
    return request("freecad.select", {
      session_id: target.session_id,
      object_name: target.object_name,
      expected_revision: target.expected_revision,
    });
  }
  const invoke = (method: string, params: Data) =>
    request("host.command", { host_id: target.host_id, method, params });
  const current = await invoke("document.context", {});
  const doc = current.active_document;
  if (
    current.session_id !== target.session_id ||
    !doc ||
    doc.path !== target.document_path ||
    doc.revision !== target.expected_revision ||
    (target.host === "solidworks"
      ? doc.configuration !== target.configuration
      : doc.document_id !== target.document_id)
  )
    throw new Error("模型文档或修订已变化，请重新检查后定位。");
  if (target.host === "solidworks")
    await invoke("selection.set", {
      document_path: target.document_path,
      configuration: target.configuration,
      session_id: target.session_id,
      expected_revision: target.expected_revision,
      persistent_reference: target.persistent_reference,
      operation_id: crypto.randomUUID(),
    });
  else
    await invoke("document.select", {
      document_id: target.document_id,
      expected_revision: target.expected_revision,
      handle: target.handle,
      operation_id: crypto.randomUUID(),
    });
  return { ...doc, document: doc.path };
}
