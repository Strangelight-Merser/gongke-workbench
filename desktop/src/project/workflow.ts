import type { Data } from "../api";
// 课程设计的阶段顺序与课程设计指导书一致；校核项按名称归入阶段。
export type StageId =
  "task" | "plan" | "gears" | "shafts" | "housing" | "drawings" | "report";
export const STAGES: { id: StageId; name: string; match?: RegExp }[] = [
  { id: "task", name: "任务书" },
  { id: "plan", name: "电动机与传动比", match: /速度误差|V 带|带轮包角|带速/ },
  { id: "gears", name: "传动零件", match: /齿面接触|齿根弯曲|蜗|锥齿/ },
  { id: "shafts", name: "轴系与轴承", match: /轴（|轴承|平键|挠度|偏转角/ },
  { id: "housing", name: "箱体与润滑", match: /间隙|浸油|大带轮尺寸/ },
  { id: "drawings", name: "图纸" },
  { id: "report", name: "说明书" },
];
export const CRITICAL = 0.85;

export function summaryOf(result: Data | null): Data | null {
  return result ? result.summary || result.result?.summary || result : null;
}
export function stageChecks(r: Data | null, id: StageId): Data[] {
  const stage = STAGES.find((s) => s.id === id);
  if (!r?.checks || !stage?.match) return [];
  return r.checks.filter((c: Data) => {
    // 先归入更具体的阶段，避免“轴承”与“齿轮”名称交叉
    const first = STAGES.find((s) => s.match?.test(c.item));
    return first?.id === id;
  });
}
export type StageState = "done" | "warn" | "fail" | "";
export function stageState(
  r: Data | null,
  project: Data | null,
  id: StageId,
): { state: StageState; note: string } {
  if (id === "task")
    return project?.task?.conveyor
      ? { state: "done", note: project.teaching ? "教学示例" : "已填写" }
      : { state: "", note: "待填写" };
  if (id === "drawings" || id === "report") {
    const delivery = project?.delivery;
    if (!delivery)
      return {
        state: "",
        note: project?.generations?.length ? "旧成果已过期" : "待生成",
      };
    if (delivery.status === "running") return { state: "", note: "生成中" };
    if (id === "drawings" && delivery.drawing_check?.total > 0)
      return {
        state: "fail",
        note: `${delivery.drawing_check.total} 处图检问题`,
      };
    const kinds = id === "drawings" ? ["drawings"] : ["markdown", "docx"];
    const artifacts = kinds
      .map((kind) => delivery.artifacts?.[kind])
      .filter(Boolean);
    if (
      artifacts.length &&
      artifacts.every((item) => item.status === "complete" && item.available)
    ) {
      const count = artifacts
        .flatMap((item) => item.files)
        .filter((name: string) => name.endsWith(".svg")).length;
      return {
        state: delivery.calculation_ok ? "done" : "warn",
        note: !delivery.calculation_ok
          ? "已生成 · 校核未通过"
          : id === "drawings"
            ? `${count} 张`
            : "已生成",
      };
    }
    return { state: "fail", note: "产物未完整生成" };
  }

  if (!r) return { state: "", note: "" };
  const checks = stageChecks(r, id);
  const failed = checks.filter((c) => !c.ok).length,
    critical = checks.filter(
      (c) => c.ok && (c.utilization ?? 0) >= CRITICAL,
    ).length;
  if (failed) return { state: "fail", note: `${failed} 项未通过` };
  if (critical) return { state: "warn", note: `${critical} 项临界` };
  if (id === "plan") return { state: "done", note: r.motor?.model || "" };
  if (id === "gears") return { state: "done", note: `${checks.length} 项校核` };
  if (id === "shafts")
    return { state: "done", note: `${r.shafts?.length || 0} 根轴` };
  return { state: checks.length ? "done" : "", note: "" };
}
