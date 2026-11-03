import type { Data } from "../api";

export function commandOf(command: string, params: Data = {}) {
  if (command === "host.write" || command === "host.read") {
    const names: Data = {
      "model.new": "model_new",
      "model.copy": "model_copy",
      "model.save": "model_save",
      "model.operation": "model_operation",
    };
    return `host.${
      names[params.method] ||
      String(params.method)
        .replace(/^model\./, "")
        .replaceAll(".", "_")
    }`;
  }
  return command.replace(/^.*host_/, "host.");
}
export function stepInput(command: string, params: Data = {}) {
  return command === "host.write" || command === "host.read"
    ? params.params || {}
    : params;
}
export const modelingCommands = new Set([
  "host.model_new",
  "host.model_copy",
  "host.body",
  "host.sketch",
  "host.feature",
  "host.feature_edit",
  "host.feature_delete",
  "host.rebuild",
  "host.model_save",
  "host.model_operation",
  "host.check",
]);
export function sameIdentity(a?: Data, b?: Data) {
  return (
    !!a &&
    !!b &&
    ["host_instance", "document_id", "configuration"].every(
      (k) => a[k] === b[k],
    )
  );
}
export function sameDocument(a?: Data, b?: Data) {
  return sameIdentity(a, b) && a?.revision === b?.revision;
}
const mm = (n: number) => `${Number((n * 1000).toFixed(4))} mm`;
export function stepTitle(command: string, params: Data = {}) {
  const c = commandOf(command, params),
    p = stepInput(command, params),
    f = p.feature || {};
  if (c === "host.sketch") {
    const circles = (p.geometry || []).filter((g: Data) => g.kind === "circle");
    const dimensions = circles
      .map((g: Data) => `φ${mm(g.radius * 2)}`)
      .join("、");
    return `${p.sketch_ref ? "修改" : "画"}${p.name || p.sketch_ref || "草图"}${dimensions ? `：圆 ${dimensions}` : ""}`;
  }
  if (c === "host.feature") {
    const names: Data = {
      pad: "拉伸",
      pocket: "切除",
      hole: "切孔",
      revolve: "旋转",
      fillet: "圆角",
      chamfer: "倒角",
      mirror: "镜像",
      linear_pattern: "线性阵列",
      polar_pattern: "圆周阵列",
    };
    return `${f.through_all ? "贯穿" : ""}${names[f.kind] || "创建特征"}${f.diameter != null ? ` φ${mm(f.diameter)}` : f.length != null ? ` ${mm(f.length)}` : f.radius != null ? ` R${mm(f.radius)}` : f.size != null ? ` ${mm(f.size)}` : f.angle != null ? ` ${Number(((f.angle * 180) / Math.PI).toFixed(2))}°` : ""}${f.count ? ` ×${f.count}` : ""}`;
  }
  if (c === "host.feature_edit")
    return `修改 ${p.feature_ref} · ${p.parameter}`;
  if (c === "host.feature_delete") return `删除 ${p.feature_ref}`;
  return (
    (
      {
        "host.model_new": "新建零件",
        "host.model_copy": "另存工作副本",
        "host.body": "创建 Body",
        "host.rebuild": "重建模型",
        "host.model_save": "保存模型",
        "host.model_operation": "查询建模结果",
        "host.check": "核对图纸尺寸",
        "host.context": "读取当前工程",
        "host.inspect": "读取特征与几何",
        "host.measure": "量测模型",
        "host.section": "读取模型截面",
      } as Data
    )[c] || command
  );
}
export function resultRef(result: Data = {}, params: Data = {}) {
  return (
    result.native_ref ||
    result.feature_ref ||
    result.sketch_ref ||
    result.body_ref ||
    params.feature_ref ||
    params.sketch_ref ||
    result.object_ref ||
    ""
  );
}
// 合并执行中的多次回执：只保留一次待刷新请求，不并发读取宿主。
export function serialRefresh(
  read: () => Promise<void>,
  onError: (error: unknown) => void,
) {
  let running = false,
    pending = false,
    closed = false;
  return {
    async request() {
      pending = true;
      if (running || closed) return;
      running = true;
      try {
        while (pending && !closed) {
          pending = false;
          try {
            await read();
          } catch (error) {
            if (!closed) onError(error);
          }
        }
      } finally {
        running = false;
      }
    },
    close() {
      closed = true;
      pending = false;
    },
  };
}

export function modelResult(step: Data): Data {
  const result = step.result || {};
  return commandOf(step.command, step.params) === "host.model_operation" &&
    result.state === "finished"
    ? result.result || {}
    : result;
}
