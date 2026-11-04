import { useState } from "react";
import { Button } from "@fluentui/react-components";
import { CheckmarkCircleRegular, WarningRegular } from "@fluentui/react-icons";
import { Data } from "../api";
import { Empty } from "../ui/Empty";
import { DataDetails } from "../ui/DataDetails";
import {
  ModelCheck,
  ModelTarget,
  canLocate,
  measurement,
  deviation,
} from "./modelChecks";
export function Checks({
  tasks,
  openCad,
  locate,
  problemsOnly = false,
}: {
  tasks: Data[];
  problemsOnly?: boolean;
  openCad(): void;
  locate(target: ModelTarget): Promise<void>;
}) {
  const [selected, setSelected] = useState<ModelCheck | null>(null);
  const [locating, setLocating] = useState(false);
  const reviews = tasks.filter(
    (t) => t.result && /review|inspect|check/.test(t.kind || t.title || ""),
  );
  const allChecks: ModelCheck[] = reviews.flatMap((t) => t.result.checks || []);
  const checks = problemsOnly
    ? allChecks.filter((c) => c.ok !== true)
    : allChecks;
  if (problemsOnly && allChecks.length && !checks.length)
    return (
      <p className="pane-empty">没有检查不符项 · {allChecks.length} 项已通过</p>
    );
  if (!checks.length && !reviews.length)
    return (
      <Empty
        title="还没有检查结果"
        body="在 Agent 面板发起对照图纸检查，或打开减速器专项查看计算校核。"
        action="返回模型"
        onAction={openCad}
      />
    );
  const failed = checks.filter((c) => c.ok === false).length;
  const unknown = checks.filter((c) => typeof c.ok !== "boolean").length;
  return (
    <div className="checks-page scroll">
      <div className="section-bar">
        <h2>检查结果</h2>
        <Button onClick={openCad}>返回模型继续编辑</Button>
      </div>
      {!!checks.length && (
        <>
          <p className={failed ? "fail" : unknown ? "warn" : "ok"}>
            {checks.length} 项检查 ·{" "}
            {failed
              ? `${failed} 项未通过`
              : unknown
                ? "尚有未确认项"
                : "全部通过"}
            {unknown && failed ? ` · ${unknown} 项待确认` : ""}
          </p>
          <table className="checks-table">
            <thead>
              <tr>
                <th>检查项</th>
                <th>图纸要求</th>
                <th>模型实测</th>
                <th>偏差</th>
                <th>结论</th>
                <th>
                  <span className="visually-hidden">操作</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {[...checks]
                .sort((a, b) => Number(a.ok === true) - Number(b.ok === true))
                .map((c, i) => (
                  <tr key={c.item + i} aria-selected={selected === c}>
                    <td>
                      <Button
                        appearance="transparent"
                        onClick={() => setSelected(c)}
                      >
                        {c.item}
                      </Button>
                    </td>
                    <td>{measurement(c.expected, c.unit)}</td>
                    <td>{measurement(c.actual, c.unit)}</td>
                    <td>{deviation(c)}</td>
                    <td
                      className={
                        c.ok === false ? "fail" : c.ok === true ? "ok" : "warn"
                      }
                    >
                      {c.ok === true ? (
                        <CheckmarkCircleRegular />
                      ) : (
                        <WarningRegular />
                      )}
                      {c.ok === false
                        ? "未通过"
                        : c.ok === true
                          ? "通过"
                          : "待确认"}
                    </td>
                    <td>
                      <Button
                        size="small"
                        aria-label={`定位 ${c.item}`}
                        disabled={locating || !canLocate(c.target)}
                        title={
                          canLocate(c.target)
                            ? `定位 ${c.item}`
                            : "记录缺少对象身份或修订，请重新检查"
                        }
                        onClick={async () => {
                          if (!canLocate(c.target)) return;
                          setSelected(c);
                          setLocating(true);
                          try {
                            await locate(c.target);
                          } finally {
                            setLocating(false);
                          }
                        }}
                      >
                        定位
                      </Button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
          {selected?.detail && (
            <section className="check-detail">
              <h3>{selected.item}</h3>
              <p>{selected.detail}</p>
            </section>
          )}
        </>
      )}
      {reviews
        .filter((t) => !t.result.checks)
        .map((t) => (
          <section key={t.task_id}>
            <h3>{t.title || t.kind}</h3>
            <DataDetails value={t.result} />
          </section>
        ))}
    </div>
  );
}
