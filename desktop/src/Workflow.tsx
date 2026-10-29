import { ReactNode, useEffect, useState } from "react";
import { Data } from "./api";

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
    const files = (project?.files || []).filter((f: Data) =>
      id === "drawings"
        ? f.kind === "svg" && f.path.includes("/drawings/")
        : /report\.(md|docx)$/.test(f.name),
    );
    return files.length
      ? {
          state: "done",
          note: id === "drawings" ? `${files.length} 张` : "已生成",
        }
      : { state: "", note: "" };
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

const pct = (u: number) => Math.round(u * 100);

// 裕度谱：全部校核按利用率排在 0–100% 轴上，临界区打斜线。
export function Spectrum({
  checks,
  selected,
  onSelect,
}: {
  checks: Data[];
  selected?: string;
  onSelect: (c: Data) => void;
}) {
  const rated = checks.filter((c) => c.utilization != null);
  const [grown, setGrown] = useState(false),
    [hover, setHover] = useState<Data | null>(null);
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);
  const failed = checks.filter((c) => !c.ok).length,
    critical = rated.filter((c) => c.ok && c.utilization >= CRITICAL).length,
    max = rated.reduce((m, c) => Math.max(m, c.utilization), 0);
  return (
    <section className="spectrum" aria-label="校核裕度谱">
      <div className="spectrum-top">
        <div className="big num">
          {checks.length}
          <small>
            {failed ? `项校核，${failed} 项未通过` : "项校核全部通过"}
          </small>
        </div>
        <div className="legend">
          <span>
            <i className="swatch warn" />
            临界 {critical} 项（≥ {pct(CRITICAL)}%）
          </span>
          <span>
            <i className="swatch" />
            最高 {pct(max)}%
          </span>
        </div>
      </div>
      <div className="track" onMouseLeave={() => setHover(null)}>
        <div className="zone" style={{ left: `${pct(CRITICAL)}%` }} />
        {rated.map((c, i) => {
          const u = Math.min(c.utilization, 1.08);
          return (
            <button
              key={c.item + i}
              className={
                "tick" +
                (!c.ok ? " fail" : c.utilization >= CRITICAL ? " warn" : "") +
                (selected === c.item ? " hot" : "")
              }
              style={{
                left: `${(u / 1.08) * 100}%`,
                height: grown ? 14 + u * 28 : 0,
                transitionDelay: `${i * 12}ms`,
              }}
              aria-label={`${c.item} ${pct(c.utilization)}%`}
              onMouseEnter={() => setHover(c)}
              onClick={() => onSelect(c)}
            />
          );
        })}
        {hover && (
          <div
            className="tip"
            style={{
              left: `${(Math.min(hover.utilization, 1.08) / 1.08) * 100}%`,
            }}
          >
            {hover.item} · {pct(hover.utilization)}%
          </div>
        )}
      </div>
      <div className="scale">
        {[0, 25, 50, 75, 100].map((v) => (
          <span key={v} style={{ left: `${(v / 108) * 100}%` }}>
            {v}%
          </span>
        ))}
      </div>
    </section>
  );
}

export function CheckRow({
  check,
  selected,
  onSelect,
  prefix = "",
}: {
  check: Data;
  selected: boolean;
  onSelect: () => void;
  prefix?: string;
}) {
  const u = check.utilization,
    tone = !check.ok ? "fail" : u != null && u >= CRITICAL ? "warn" : "";
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return (
    <button className={"ck" + (selected ? " sel" : "")} onClick={onSelect}>
      <span className="ck-n" title={check.item}>
        {prefix && check.item.startsWith(prefix)
          ? check.item.slice(prefix.length)
          : check.item}
      </span>
      {u != null ? (
        <span className="meter">
          <i
            className={tone}
            style={{ width: grown ? `${Math.min(u, 1) * 100}%` : 0 }}
          />
        </span>
      ) : (
        <span className="ck-d">{check.ok ? "满足" : "不满足"}</span>
      )}
      <span className={"ck-p num " + tone}>
        {u != null ? pct(u) + "%" : ""}
      </span>
    </button>
  );
}

export function Fact({
  label,
  value,
  unit,
  source,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  source?: "入" | "标" | "式" | "近";
}) {
  return (
    <div className="fact">
      <dt>
        {label}
        {source && (
          <span className={"src" + (source === "近" ? " near" : "")}>
            {source}
          </span>
        )}
      </dt>
      <dd className="num">
        {value}
        {unit && <span className="unit">{unit}</span>}
      </dd>
    </div>
  );
}

export function CheckInspector({ check }: { check: Data }) {
  const u = check.utilization,
    tone = !check.ok ? "fail" : u != null && u >= CRITICAL ? "warn" : "ok";
  const parts = String(check.detail || "").split(/（|，/);
  return (
    <div className="insp-in" key={check.item}>
      <div className="crumb">校核</div>
      <h4>{check.item}</h4>
      {u != null && (
        <div className={"gauge " + tone}>
          <span className="big num">{pct(u)}%</span>
          <span className="unit">
            利用率
            {tone === "warn" ? " · 临界" : tone === "fail" ? " · 超限" : ""}
          </span>
        </div>
      )}
      <dl className="kv">
        <dt>结论</dt>
        <dd className={tone}>{check.ok ? "满足" : "不满足"}</dd>
        <dt>依据</dt>
        <dd className="num">{parts[0]}</dd>
        {parts.length > 1 && (
          <>
            <dt>备注</dt>
            <dd>
              {check.detail.slice(parts[0].length + 1).replace(/）$/, "")}
            </dd>
          </>
        )}
      </dl>
      <p className="hint">
        利用率：≤ 型为实际 / 许用，≥ 型为要求 / 实际；{pct(CRITICAL)}%
        以上视为临界。
      </p>
    </div>
  );
}
