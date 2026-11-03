import { ConditionFields } from "./ConditionFields";
import { useEffect, useState } from "react";
import { Button, Input, Select, Checkbox } from "../ui/controls";
import { call, Data } from "../api";
import { Empty } from "../ui/Empty";
import {
  StageId,
  STAGES,
  stageChecks,
  stageState,
  summaryOf,
} from "./workflow";
import { CheckInspector, CheckRow, Fact } from "./CheckViews";
const statuses: Data = {
  running: "生成中",
  complete: "完成",
  failed: "失败",
  partial: "部分完成",
};
const schemes: Data = {
  coupling: "二级圆柱齿轮 · 联轴器",
  vbelt: "二级圆柱齿轮 · V 带",
  single: "一级圆柱齿轮",
  bevel: "圆锥—圆柱齿轮",
  worm: "蜗杆传动",
};
function TaskForm({
  project,
  setProject,
  run,
  refresh,
  onResult,
}: {
  project: Data;
  setProject: (p: Data) => void;
  run: any;
  refresh: () => Promise<void>;
  onResult: (r: Data) => void;
}) {
  const blank = () => ({
    scheme: "coupling",
    conveyor: {},
    life: { years: 10, days_per_year: 300, shifts: 2 },
    bearing_life_years: 3,
  });
  const draftKey = "gongke.conditions." + project.path;
  const initial = JSON.parse(localStorage.getItem(draftKey) || "null");
  const [base, setBase] = useState(
    initial?.base || JSON.stringify(project.task),
  );
  const [task, setTask] = useState<Data>(
      initial?.task || project.task || blank(),
    ),
    [teaching, setTeaching] = useState(initial?.teaching ?? !!project.teaching);
  useEffect(() => {
    localStorage.setItem(draftKey, JSON.stringify({ task, teaching, base }));
  }, [task, teaching, base, draftKey]);
  const remoteChanged =
    JSON.stringify(project.task) !== base &&
    JSON.stringify(project.task) !== JSON.stringify(task);
  const change = (key: string, value: number) =>
    setTask({ ...task, conveyor: { ...task.conveyor, [key]: value } });
  async function calculate() {
    await run("计算中", async () => {
      const updated = await call("project.set_task", { task, teaching });
      setBase(JSON.stringify(updated.task));
      setProject(updated);
      onResult(await call("design.calculate", { task }));
      await refresh();
    });
  }
  return (
    <div className="design">
      {remoteChanged && (
        <div role="alert" className="condition-conflict">
          <p>
            工程条件已在其他操作中更新。你的草稿仍保留，请先选择采用的版本。
          </p>
          <Button
            onClick={() => {
              setTask(project.task || blank());
              setTeaching(!!project.teaching);
              setBase(JSON.stringify(project.task));
            }}
          >
            载入最新工程条件
          </Button>
          <Button onClick={() => setBase(JSON.stringify(project.task))}>
            使用我的草稿覆盖条件
          </Button>
        </div>
      )}
      <div className="section-bar">
        <p className="lede">工作条件</p>
        <Button
          onClick={() =>
            run("载入教学条件", async () => {
              const data = await call("design.example");
              const t = data.task || data;
              setTask(t);
              setTeaching(true);
              setBase(JSON.stringify(t));
              setProject(
                await call("project.set_task", { task: t, teaching: true }),
              );
            })
          }
        >
          载入教学条件
        </Button>
      </div>
      {
        <>
          <div className="form-grid">
            <label>
              传动方案
              <Select
                value={task.scheme || "coupling"}
                onChange={(e) => setTask({ ...task, scheme: e.target.value })}
              >
                {Object.entries(schemes).map(([k, v]) => (
                  <option key={k} value={k}>
                    {String(v)}
                  </option>
                ))}
              </Select>
            </label>
            <label>
              工作拉力 / N
              <Input
                type="number"
                min="1"
                value={task.conveyor?.belt_pull_N ?? ""}
                onChange={(e) => change("belt_pull_N", +e.target.value)}
              />
            </label>
            <label>
              带速 / m·s⁻¹
              <Input
                type="number"
                step="0.1"
                min="0.01"
                value={task.conveyor?.belt_speed_m_s ?? ""}
                onChange={(e) => change("belt_speed_m_s", +e.target.value)}
              />
            </label>
            <label>
              卷筒直径 / mm
              <Input
                type="number"
                min="1"
                value={task.conveyor?.drum_diameter_mm ?? ""}
                onChange={(e) => change("drum_diameter_mm", +e.target.value)}
              />
            </label>
          </div>
          <div className="form-grid">
            {[
              ["years", "使用年限 / 年"],
              ["days_per_year", "每年工作天数"],
              ["shifts", "每天班数（每班 8 小时）"],
            ].map(([key, label]) => (
              <label key={key}>
                {label}
                <Input
                  type="number"
                  min="1"
                  value={task.life?.[key] ?? ""}
                  onChange={(e) =>
                    setTask({
                      ...task,
                      life: { ...task.life, [key]: +e.target.value },
                    })
                  }
                />
              </label>
            ))}
            <label>
              轴承检修期 / 年
              <Input
                type="number"
                min="1"
                value={task.bearing_life_years ?? ""}
                onChange={(e) =>
                  setTask({ ...task, bearing_life_years: +e.target.value })
                }
              />
            </label>
          </div>
          <ConditionFields task={task} onChange={setTask} />
          <label className="source-choice">
            <Checkbox
              checked={teaching}
              onChange={(_, data) => setTeaching(data.checked === true)}
            />{" "}
            教学示例条件
          </label>
          <p className="hint">
            未指定的材料、精度与系数采用课程计算默认值，完整条件和生成说明书保留取值依据；通过校核不代表专业验收。
          </p>
          <div className="toolbar">
            <Button
              appearance="primary"
              disabled={remoteChanged}
              onClick={calculate}
            >
              计算方案
            </Button>
            <Button
              disabled={remoteChanged}
              onClick={() =>
                run("生成工程", async () => {
                  setProject(
                    await call("project.set_task", { task, teaching }),
                  );
                  setBase(JSON.stringify(task));
                  await call("design.generate", {
                    task,
                    step: true,
                    drawings: true,
                    report_docx: true,
                    full_teeth: false,
                  });
                  await refresh();
                })
              }
            >
              生成模型、图纸与说明书
            </Button>
          </div>
        </>
      }
    </div>
  );
}
function NeedCalc({ go }: { go: () => void }) {
  return (
    <Empty
      title="还没有计算结果"
      body="在任务书里填写条件并计算后，这一步的数值和校核会出现在这里。"
      action="去填写任务书"
      onAction={go}
    />
  );
}
const fixed = (v: any, n = 2) =>
  typeof v === "number" ? +v.toFixed(n) : (v ?? "—");
function StageView({
  id,
  r,
  project,
  check,
  onCheck,
  openFile,
  go,
}: {
  id: StageId;
  r: Data | null;
  project: Data;
  check: Data | null;
  onCheck: (c: Data) => void;
  openFile: (f: Data) => void;
  go: (tab: string) => void;
}) {
  const checks = (list: Data[], prefix = "", heading = "校核 · 利用率") =>
    list.length > 0 && (
      <div className="checks">
        <h3>{heading}</h3>
        {list.map((c, i) => (
          <CheckRow
            key={c.item + i}
            check={c}
            selected={check?.item === c.item}
            onSelect={() => onCheck(c)}
            prefix={prefix}
          />
        ))}
      </div>
    );
  if (id === "drawings" || id === "report") {
    const revisions: Data[] = project.generations || [];
    const groups = revisions.map((revision) => ({
      revision,
      files: (project.files || []).filter(
        (f: Data) =>
          f.path.startsWith(revision.path + "/") &&
          (id === "drawings"
            ? f.kind === "svg" && f.path.includes("/drawings/")
            : /report\.(md|docx)$/.test(f.name)),
      ),
    }));
    return groups.length ? (
      <div>
        {groups.map(({ revision, files }) => (
          <section key={revision.path} className="revision-group">
            <h3>
              {revision.path.split("/").pop()} ·{" "}
              {revision.current ? "当前条件" : "已过期 · 历史条件"}
              {revision.status !== "complete"
                ? " · " + (statuses[revision.status] || revision.status)
                : ""}
            </h3>
            {!files.length && <p className="hint">此修订尚无可查看的产物。</p>}
            <div className="sheet-grid">
              {files.map((f: Data) => (
                <Button
                  key={f.path}
                  className="sheet-card"
                  onClick={() => openFile(f)}
                >
                  <b>{f.name}</b>
                </Button>
              ))}
            </div>
          </section>
        ))}
      </div>
    ) : (
      <Empty
        title={id === "drawings" ? "还没有图纸" : "还没有说明书"}
        body="保存任务书后生成模型、图纸与说明书，说明书会一并生成。"
        action="去任务书"
        onAction={() => go("task")}
      />
    );
  }

  if (!r) return <NeedCalc go={() => go("task")} />;
  const own = stageChecks(r, id);
  if (id === "plan")
    return (
      <>
        <dl className="facts">
          <Fact label="电动机" value={r.motor?.model} source="标" />
          <Fact
            label="额定功率"
            value={r.motor?.power_kw}
            unit="kW"
            source="标"
          />
          <Fact
            label="满载转速"
            value={r.motor?.speed_rpm}
            unit="r/min"
            source="标"
          />
          <Fact
            label="总传动比"
            value={fixed(r.ratios?.total, 3)}
            source="式"
          />
          <Fact label="高速级" value={fixed(r.ratios?.high, 3)} source="式" />
          <Fact
            label={r.ratios?.low ? "低速级" : "带传动"}
            value={fixed(r.ratios?.low ?? r.ratios?.belt, 3)}
            source="式"
          />
        </dl>
        {r.shaft_states && (
          <table>
            <thead>
              <tr>
                <th>轴</th>
                <th>功率 / kW</th>
                <th>转速 / r·min⁻¹</th>
                <th>转矩 / N·m</th>
              </tr>
            </thead>
            <tbody>
              {r.shaft_states.map((s: Data) => (
                <tr key={s.name}>
                  <td>{s.name}</td>
                  <td>{s.power_kw.toFixed(3)}</td>
                  <td>{s.speed_rpm.toFixed(2)}</td>
                  <td>{s.torque_nm.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {checks(own)}
      </>
    );
  if (id === "gears") {
    const pairs = Object.values(r.gears || {}).filter(Boolean) as Data[];
    return (
      <div className="columns">
        {pairs.map((g) => (
          <section key={g.name}>
            <h2>
              {g.name}
              {g.z1 && (
                <span>
                  {g.z1} / {g.z2} 齿
                  {g.beta_deg ? ` · β ${fixed(g.beta_deg)}°` : ""}
                </span>
              )}
            </h2>
            <dl className="facts">
              {g.mn != null && (
                <Fact label="法向模数" value={g.mn} unit="mm" source="标" />
              )}
              {g.a != null && (
                <Fact label="中心距" value={fixed(g.a)} unit="mm" source="式" />
              )}
              {g.beta_deg != null && (
                <Fact
                  label="螺旋角"
                  value={fixed(g.beta_deg)}
                  unit="°"
                  source="式"
                />
              )}
              {g.d1 != null && (
                <Fact
                  label="小齿轮分度圆"
                  value={fixed(g.d1)}
                  unit="mm"
                  source="式"
                />
              )}
              {g.d2 != null && (
                <Fact
                  label="大齿轮分度圆"
                  value={fixed(g.d2)}
                  unit="mm"
                  source="式"
                />
              )}
              {g.b1 != null && (
                <Fact
                  label="齿宽 b₁ / b₂"
                  value={`${fixed(g.b1)} / ${fixed(g.b2)}`}
                  unit="mm"
                  source="式"
                />
              )}
            </dl>
            {checks(
              own.filter((c) => c.item.startsWith(g.name)),
              g.name,
            )}
          </section>
        ))}
        {pairs.length === 0 && checks(own)}
      </div>
    );
  }
  if (id === "shafts")
    return (
      <div className="columns three">
        {(r.shafts || []).map((s: Data) => (
          <section key={s.name}>
            <h2>
              {s.name}
              <span>轴承 {s.bearing}</span>
            </h2>
            <dl className="facts two">
              {Object.entries(s.diameters || {})
                .filter(([, d]) => d != null)
                .map(([k, d]) => (
                  <Fact
                    key={k}
                    label={k + "段直径"}
                    value={fixed(d, 1)}
                    unit="mm"
                    source="式"
                  />
                ))}
            </dl>
            {checks(
              own.filter((c) => c.item.startsWith(s.name)),
              s.name,
            )}
          </section>
        ))}
      </div>
    );
  return checks(own) || <p className="hint">这一步没有单独的校核项。</p>;
}

export function ReducerTask({
  project,
  setProject,
  run,
  refresh,
  result,
  onResult,
  openFile,
}: {
  project: any;
  setProject(value: any): void;
  run: any;
  refresh(): Promise<void>;
  result: Data | null;
  onResult(value: Data): void;
  openFile(file: any): void;
}) {
  const [stage, setStage] = useState<StageId>("task");
  const [check, setCheck] = useState<Data | null>(null);
  const summary = summaryOf(result);
  return (
    <div className="reducer-task">
      <nav className="task-stages" aria-label="减速器专项阶段">
        {STAGES.map((s) => (
          <Button
            key={s.id}
            appearance={stage === s.id ? "primary" : "subtle"}
            onClick={() => setStage(s.id)}
          >
            {s.name}
            <span className="stage-note">
              {stageState(summary, project, s.id).note}
            </span>
          </Button>
        ))}
      </nav>
      <div className="scroll document-content">
        <div hidden={stage !== "task"}>
          <TaskForm
            project={project}
            setProject={setProject}
            run={run}
            refresh={refresh}
            onResult={onResult}
          />
        </div>
        {stage !== "task" && (
          <StageView
            id={stage}
            r={summary}
            project={project}
            check={check}
            onCheck={setCheck}
            openFile={openFile}
            go={(s) => setStage(s as StageId)}
          />
        )}
        {check && stage !== "task" && <CheckInspector check={check} />}
      </div>
    </div>
  );
}
