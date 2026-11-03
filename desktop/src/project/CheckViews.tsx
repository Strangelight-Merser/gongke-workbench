import { useEffect, useState, ReactNode } from "react";
import { Button } from "../ui/controls";
import { Data } from "../api";
import { CRITICAL } from "./workflow";
const pct = (u: number) => Math.round(u * 100);
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
    <Button className={"ck" + (selected ? " sel" : "")} onClick={onSelect}>
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
    </Button>
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
