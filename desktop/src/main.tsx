import { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { call, Data, errorText, text } from "./api";
import { ModelView } from "./ModelView";
import { CommercialView } from "./CommercialView";
import "./style.css";

const statuses: Data = {
  queued: "排队中",
  running: "执行中",
  complete: "已完成",
  failed: "未完成",
  canceled: "已取消",
  interrupted: "已中断",
  partial: "部分完成",
};
const schemes: Data = {
  coupling: "二级圆柱齿轮 · 联轴器",
  vbelt: "二级圆柱齿轮 · V 带",
  single: "一级圆柱齿轮",
  bevel: "圆锥—圆柱齿轮",
  worm: "蜗杆传动",
};
function Json({ value }: { value: any }) {
  return <pre className="json">{text(value)}</pre>;
}
function App() {
  const [project, setProject] = useState<Data | null>(null),
    [status, setStatus] = useState<Data>({}),
    [tasks, setTasks] = useState<Data[]>([]),
    [tab, setTab] = useState("native");
  const [hostKind, setHostKind] = useState("freecad");
  const [pendingNative, setPendingNative] = useState<Data | null>(() => {
    try {
      return JSON.parse(
        localStorage.getItem("gongke.pending.freecad") || "null",
      );
    } catch {
      return null;
    }
  });
  useEffect(() => {
    if (pendingNative)
      localStorage.setItem(
        "gongke.pending.freecad",
        JSON.stringify(pendingNative),
      );
    else localStorage.removeItem("gongke.pending.freecad");
  }, [pendingNative]);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(""),
    [settings, setSettings] = useState(false),
    [hosts, setHosts] = useState<Data[]>([]);
  const [messages, setMessages] = useState<Data[]>([]),
    [prompt, setPrompt] = useState(""),
    [allowWrites, setAllowWrites] = useState(true),
    [file, setFile] = useState<Data | null>(null),
    [native, setNative] = useState<Data>({});
  const refresh = useCallback(async () => {
    const [s, p, t, h] = await Promise.allSettled([
      call("system.status"),
      call("project.current"),
      call("task.list"),
      call("hosts.list"),
    ]);
    if (s.status === "fulfilled") setStatus({ ...s.value, online: true });
    if (p.status === "fulfilled") setProject(p.value);
    if (t.status === "fulfilled")
      setTasks(Array.isArray(t.value) ? t.value : t.value.tasks || []);
    if (h.status === "fulfilled")
      setHosts(Array.isArray(h.value) ? h.value : h.value.hosts || []);
  }, []);
  const run = useCallback(async (label: string, action: () => Promise<any>) => {
    setBusy(label);
    setError("");
    try {
      return await action();
    } catch (e) {
      setError(errorText(e));
      return null;
    } finally {
      setBusy("");
    }
  }, []);
  useEffect(() => {
    refresh();
    const stop = window.gongke.onEvent((event) => {
      if (event.event === "task.updated") {
        setTasks((items) => [
          event.task,
          ...items.filter((item) => item.task_id !== event.task.task_id),
        ]);
        if (
          ["complete", "partial", "failed", "canceled"].includes(
            event.task.status,
          )
        )
          refresh();
      }
      if (event.event === "agent.delta")
        setMessages((items) => {
          const prior = items.find(
            (x) => x.streaming && x.task_id === event.task_id,
          );
          return [
            ...items.filter(
              (x) => !(x.streaming && x.task_id === event.task_id),
            ),
            {
              role: "assistant",
              task_id: event.task_id,
              streaming: true,
              content: (prior?.content || "") + event.content,
            },
          ];
        });
      if (event.event === "agent.message")
        setMessages((items) => [
          ...items.filter((x) => !(x.streaming && x.task_id === event.task_id)),
          event,
        ]);
      if (event.event === "service.error") setError(event.error.message);
      if (event.event === "service.stopped") {
        setStatus({ online: false });
        setError(event.message);
      }
      if (event.event === "agent.unavailable") setError(event.message);
    });
    return stop;
  }, [refresh]);
  async function choose(create: boolean) {
    await run(create ? "新建工程" : "打开工程", async () => {
      const path = await window.gongke.chooseProject(create);
      if (!path) return;
      const result = await call(create ? "project.create" : "project.open", {
        path,
        ...(create ? { teaching: false } : {}),
      });
      setProject(result);
      setFile(null);
      await refresh();
    });
  }
  async function readFile(item: Data) {
    await run("读取文件", async () => {
      setFile(
        ["svg", "json", "md", "txt", "yaml", "yml"].includes(item.kind)
          ? {
              ...item,
              ...(await call("project.read_file", { path: item.path })),
            }
          : { ...item, content: null },
      );
      setTab("file");
    });
  }
  async function send() {
    if (!prompt.trim()) return;
    const message = prompt;
    setMessages((items) => [...items, { role: "user", content: message }]);
    setPrompt("");
    await run("提交任务", async () => {
      await call("agent.run", { message, allow_writes: allowWrites });
      await refresh();
    });
  }
  return (
    <div className="app">
      <header>
        <div className="brand">
          <span className="brand-mark">G</span>
          <strong>构想引擎</strong>
        </div>
        <span className="project-title">{project?.name || "工程工作台"}</span>
        <div className="header-actions">
          <button onClick={() => choose(false)}>打开工程</button>
          <button onClick={() => choose(true)}>新建工程</button>
          <button className="icon-button" onClick={() => setSettings(true)}>
            模型服务
          </button>
        </div>
      </header>
      <div className="body">
        <aside className="tree">
          <div className="tree-heading">
            {project?.name || "未打开工程"}
            <button onClick={refresh} title="刷新工程">
              ↻
            </button>
          </div>
          <nav>
            <button
              className={tab === "native" ? "active" : ""}
              onClick={() => setTab("native")}
            >
              <span>◇</span>模型与图纸
            </button>
            <button
              className={tab === "design" ? "active" : ""}
              onClick={() => setTab("design")}
            >
              <span>∑</span>设计计算
            </button>
            <button
              className={tab === "tasks" ? "active" : ""}
              onClick={() => setTab("tasks")}
            >
              <span>☷</span>任务
              <span className="count">
                {tasks.filter((t) => t.status === "running").length || ""}
              </span>
            </button>
          </nav>
          <div className="section-title">
            工程文件 <span>{project?.files?.length || 0}</span>
          </div>
          <div className="files">
            {(project?.files || []).map((item: Data) => (
              <button
                key={item.path}
                title={item.path}
                className={file?.path === item.path ? "selected" : ""}
                onClick={() => readFile(item)}
              >
                <span className="file-type">
                  {item.kind?.slice(0, 4) || "FILE"}
                </span>
                <span>{item.name}</span>
              </button>
            ))}
            {project && !project.files?.length && (
              <p className="muted">工程还没有文件</p>
            )}
          </div>
          <div className="connections">
            <div className="section-title">原生连接</div>
            {["freecad", "solidworks", "autocad"].map((name) => {
              const h = hosts.find((h) => h.host === name);
              return (
                <div key={name}>
                  <span className={`dot ${h?.connected ? "green" : ""}`} />
                  {
                    (
                      {
                        freecad: "FreeCAD",
                        solidworks: "SOLIDWORKS",
                        autocad: "AutoCAD",
                      } as Data
                    )[name]
                  }
                  <small>{h?.connected ? "已连接" : "未连接"}</small>
                </div>
              );
            })}
          </div>
        </aside>
        <main>
          <div className="workspace-title">
            <h1>
              {tab === "native"
                ? "模型与图纸"
                : tab === "design"
                  ? "设计计算"
                  : tab === "tasks"
                    ? "任务"
                    : file?.name}
            </h1>
            <span>{busy || ""}</span>
          </div>
          {error && (
            <div role="alert" className="error">
              <span>{error}</span>
              <button onClick={() => setError("")}>×</button>
            </div>
          )}
          {tab === "native" && (
            <>
              <div className="toolbar">
                <select
                  aria-label="原生软件"
                  value={hostKind}
                  onChange={(e) => setHostKind(e.target.value)}
                >
                  <option value="freecad">FreeCAD</option>
                  <option value="solidworks">SOLIDWORKS</option>
                  <option value="autocad">AutoCAD</option>
                </select>
                <button onClick={refresh}>刷新连接</button>
              </div>
              {hostKind === "freecad" ? (
                <Native
                  project={project}
                  run={run}
                  onContext={setNative}
                  pendingOperation={pendingNative}
                  setPendingOperation={setPendingNative}
                />
              ) : (
                <CommercialView
                  key={hostKind}
                  kind={hostKind}
                  host={hosts.find((h) => h.host === hostKind && h.connected)}
                  run={run}
                />
              )}
            </>
          )}
          {tab === "design" &&
            (project ? (
              <Design
                project={project}
                setProject={setProject}
                run={run}
                refresh={refresh}
              />
            ) : (
              <Empty
                title="从一个工程开始"
                body="将原生模型、图纸和计算结果放在同一个工程里。"
                action="新建工程"
                onAction={() => choose(true)}
              />
            ))}
          {tab === "tasks" && (
            <div className="scroll">
              <TaskList tasks={tasks} run={run} />
            </div>
          )}
          {tab === "file" && file && (
            <div className="file-view">
              <div className="toolbar">
                <span>{file.path}</span>
                <button
                  onClick={() =>
                    run("定位文件", () => window.gongke.reveal(file.path))
                  }
                >
                  在文件夹中显示
                </button>
                {file.kind === "dxf" &&
                  hosts.some((h) => h.host === "autocad" && h.connected) && (
                    <button
                      onClick={() =>
                        run("导入 AutoCAD", async () => {
                          const host = hosts.find(
                            (h) => h.host === "autocad" && h.connected,
                          )!;
                          const path =
                            "revisions/dwg-" +
                            crypto.randomUUID().slice(0, 12) +
                            "/drawing.dwg";
                          const r = await call("host.command", {
                            host_id: host.host_id,
                            method: "drawing.import_dxf",
                            params: {
                              source_path: file.path,
                              target_path: path,
                              operation_id: crypto.randomUUID(),
                            },
                          });
                          if (r.error) throw new Error(r.error.message);
                          const opened = await call("host.command", {
                            host_id: host.host_id,
                            method: "document.open",
                            params: { path, operation_id: crypto.randomUUID() },
                          });
                          if (opened.error)
                            throw new Error(opened.error.message);
                          setHostKind("autocad");
                          setTab("native");
                          await refresh();
                        })
                      }
                    >
                      导入 AutoCAD 工作修订
                    </button>
                  )}
              </div>
              {file.kind === "svg" ? (
                <img
                  className="drawing"
                  src={
                    "data:image/svg+xml;charset=utf-8," +
                    encodeURIComponent(file.content)
                  }
                />
              ) : file.content === null ? (
                <Empty
                  title={file.name}
                  body="此文件保留原生格式，可在文件夹中定位后用工程软件打开。"
                  action="在文件夹中显示"
                  onAction={() =>
                    run("定位文件", () => window.gongke.reveal(file.path))
                  }
                />
              ) : (
                <pre>{file.content}</pre>
              )}
            </div>
          )}
        </main>
        <aside className="agent">
          <div className="agent-heading">
            <strong>工程助手</strong>
            <span
              className={`dot ${status.agent?.connection === "已完成模型请求" ? "green" : ""}`}
            />
          </div>
          <div className="conversation">
            {!messages.length && (
              <div className="agent-welcome">
                <span className="agent-symbol">✦</span>
                <h2>一起完成这个工程</h2>
                <p>
                  读取当前模型、核对条件、计算和修改。操作结果直接进入工作区。
                </p>
                <button onClick={() => setSettings(true)}>连接模型服务</button>
                <button
                  className="suggestion"
                  onClick={() =>
                    setPrompt(
                      "读取当前工程，说明已知条件和还缺少什么。先不要修改模型。",
                    )
                  }
                >
                  核对当前工程的条件 ↗
                </button>
              </div>
            )}
            {messages.map((message, index) => (
              <div key={index} className={"message " + message.role}>
                <small>
                  {message.role === "user"
                    ? "你"
                    : message.role === "tool"
                      ? "工程操作"
                      : "工程助手"}
                </small>
                <div>
                  {typeof message.content === "string"
                    ? message.content
                    : text(message.content)}
                </div>
              </div>
            ))}
          </div>
          <div className="compose">
            <textarea
              aria-label="工程任务"
              placeholder="描述你要完成的工程任务…"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <div>
              <label>
                <input
                  type="checkbox"
                  checked={allowWrites}
                  onChange={(e) => setAllowWrites(e.target.checked)}
                />
                执行任务内的修改
              </label>
              <button
                className="primary"
                disabled={!project || !prompt.trim() || !!busy}
                onClick={send}
              >
                发送 ↑
              </button>
            </div>
          </div>
        </aside>
      </div>
      <footer>
        <span>
          <span className={`dot ${status.online ? "green" : ""}`} />
          {status.online ? "工程服务运行中" : "工程服务未运行"}
        </span>
        {!status.online && (
          <button
            onClick={() =>
              run("重启服务", async () => {
                await window.gongke.restart();
                await refresh();
              })
            }
          >
            重新启动
          </button>
        )}
        <span>{native.document || "未读取原生文档"}</span>
        <span className="footer-end">
          {project?.teaching
            ? "教学示例 · 条件须核对"
            : project?.path || "本地工程"}
        </span>
      </footer>
      {settings && (
        <Settings
          onClose={() => setSettings(false)}
          onSave={refresh}
          run={run}
        />
      )}
    </div>
  );
}
function Empty({
  title,
  body,
  action,
  onAction,
}: {
  title: string;
  body: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">◇</div>
      <h2>{title}</h2>
      <p>{body}</p>
      {action && (
        <button className="primary" onClick={onAction}>
          {action}
        </button>
      )}
    </div>
  );
}
function Design({
  project,
  setProject,
  run,
  refresh,
}: {
  project: Data;
  setProject: (p: Data) => void;
  run: any;
  refresh: () => Promise<void>;
}) {
  const [task, setTask] = useState<Data>(project.task || {}),
    [result, setResult] = useState<Data | null>(null),
    [advanced, setAdvanced] = useState(false),
    [draft, setDraft] = useState("");
  useEffect(() => setTask(project.task || {}), [project.task]);
  const change = (key: string, value: number) =>
    setTask({ ...task, conveyor: { ...task.conveyor, [key]: value } });
  async function calculate() {
    await run("计算中", async () => {
      await call("project.set_task", { task });
      setResult(await call("design.calculate", { task }));
      await refresh();
    });
  }
  return (
    <div className="scroll design">
      <div className="section-bar">
        <div>
          <h2>传动装置</h2>
          <p>工程单位输入，确定性计算。</p>
        </div>
        <button
          onClick={() =>
            run("载入教学条件", async () => {
              const data = await call("design.example");
              const t = data.task || data;
              setTask(t);
              setProject(
                await call("project.set_task", { task: t, teaching: true }),
              );
            })
          }
        >
          载入教学条件
        </button>
      </div>
      {!task.conveyor ? (
        <Empty
          title="尚无计算条件"
          body="从教学示例开始，或通过工程助手输入你的任务书。"
        />
      ) : (
        <>
          <div className="form-grid">
            <label>
              传动方案
              <select
                value={task.scheme || "coupling"}
                onChange={(e) => setTask({ ...task, scheme: e.target.value })}
              >
                {Object.entries(schemes).map(([k, v]) => (
                  <option key={k} value={k}>
                    {String(v)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              工作拉力 / N
              <input
                type="number"
                min="1"
                value={task.conveyor.belt_pull_N}
                onChange={(e) => change("belt_pull_N", +e.target.value)}
              />
            </label>
            <label>
              带速 / m·s⁻¹
              <input
                type="number"
                step="0.1"
                min="0.01"
                value={task.conveyor.belt_speed_m_s}
                onChange={(e) => change("belt_speed_m_s", +e.target.value)}
              />
            </label>
            <label>
              卷筒直径 / mm
              <input
                type="number"
                min="1"
                value={task.conveyor.drum_diameter_mm}
                onChange={(e) => change("drum_diameter_mm", +e.target.value)}
              />
            </label>
          </div>
          <div className="toolbar">
            <button className="primary" onClick={calculate}>
              计算方案
            </button>
            <button
              onClick={() =>
                run("生成工程", async () => {
                  await call("project.set_task", { task });
                  await call("design.generate", {
                    task,
                    step: true,
                    drawings: true,
                    report_docx: false,
                    full_teeth: false,
                  });
                  await refresh();
                })
              }
            >
              生成模型与图纸
            </button>
            <button
              onClick={() => {
                setDraft(text(task));
                setAdvanced(!advanced);
              }}
            >
              完整条件
            </button>
          </div>
          {advanced && (
            <div className="advanced">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
              <button
                onClick={() =>
                  run("保存条件", async () => {
                    const next = JSON.parse(draft);
                    setProject(await call("project.set_task", { task: next }));
                    setTask(next);
                    setAdvanced(false);
                  })
                }
              >
                保存条件
              </button>
            </div>
          )}
        </>
      )}
      {result && <Results result={result} />}
      {project.results?.length > 0 && (
        <div className="result-history">
          <h2>工程修订</h2>
          {project.results.map((r: Data, i: number) => (
            <div className="revision" key={i}>
              <strong>{r.name || r.kind || r.path || "修订 " + (i + 1)}</strong>
              <small>{r.created_at || r.directory || r.output_dir || ""}</small>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
function Results({ result }: { result: Data }) {
  const r = result.summary || result.result?.summary || result;
  return (
    <section className="results">
      <h2>计算结果</h2>
      {r.failed?.length > 0 && (
        <p className="error">
          {r.failed.length} 项校核未通过，请查看完整检查项。
        </p>
      )}
      {r.motor && (
        <div className="metrics">
          <div>
            <small>电动机</small>
            <strong>{r.motor.model}</strong>
          </div>
          <div>
            <small>额定功率</small>
            <strong>
              {r.motor.power_kw} <em>kW</em>
            </strong>
          </div>
          <div>
            <small>总传动比</small>
            <strong>{r.ratios?.total?.toFixed(3)}</strong>
          </div>
        </div>
      )}
      {r.shaft_states && (
        <table>
          <thead>
            <tr>
              <th>轴</th>
              <th>功率 / kW</th>
              <th>转速 / rpm</th>
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
      <details>
        <summary>完整结果与检查项</summary>
        <Json value={r} />
      </details>
    </section>
  );
}
function Native({
  project,
  run,
  onContext,
  pendingOperation,
  setPendingOperation,
}: {
  project: Data | null;
  run: any;
  onContext: (data: Data) => void;
  pendingOperation: Data | null;
  setPendingOperation: (value: Data | null) => void;
}) {
  const [context, setContext] = useState<Data>({}),
    [scene, setScene] = useState<Data | null>(null),
    [selected, setSelected] = useState(""),
    [object, setObject] = useState<Data | null>(null),
    [preview, setPreview] = useState<Data | null>(null),
    [review, setReview] = useState<Data | null>(null),
    [diameter, setDiameter] = useState(""),
    [segment, setSegment] = useState(""),
    [page, setPage] = useState(""),
    [operation, setOperation] = useState(""),
    [connectionError, setConnectionError] = useState("");
  const select = useCallback(
    (id: string) => {
      setSelected(id);
      setObject(null);
      setPreview(null);
      setReview(null);
      if (context.session_id)
        run("选择原生对象", () =>
          call("freecad.select", {
            session_id: context.session_id,
            object_name: id,
            expected_revision: context.revision,
          }),
        );
    },
    [context.session_id, context.revision, run],
  );
  const refresh = async () => {
    setConnectionError("");
    const c = await call("freecad.context");
    const s = await call("freecad.scene");
    const current = { ...c, revision: s.revision };
    setContext(current);
    onContext(current);
    setScene(s);
    setPreview(null);
    setReview(null);
    setObject(null);
    if (s.objects?.length && !s.objects.find((x: Data) => x.id === selected))
      setSelected(s.objects[0].id);
  };
  useEffect(() => {
    if (!selected || !context.session_id) return;
    let current = true;
    const item = context.objects?.find(
      (o: Data) => o.name === selected || o.entity_id === selected,
    );
    if (item)
      call("freecad.read", {
        session_id: context.session_id,
        entity_id: item.entity_id,
      })
        .then((result) => {
          if (!current) return;
          setObject(result);
          const editable = result.snapshot?.segments?.find(
            (s: Data) => s.editable,
          );
          if (editable) {
            setSegment(editable.segment_id);
            setDiameter(String(editable.diameter_m * 1000));
          }
        })
        .catch((error) => {
          if (current)
            setObject({ supported: false, reason: errorText(error) });
        });
    return () => {
      current = false;
    };
  }, [selected, context]);
  useEffect(() => {
    if (!context.session_id) return;
    let active = true,
      polling = false;
    const timer = setInterval(() => {
      if (polling) return;
      polling = true;
      call("freecad.context")
        .then((current) => {
          if (
            active &&
            (current.session_id !== context.session_id ||
              current.revision !== context.revision)
          ) {
            setContext(current);
            setPreview(null);
            setReview(null);
            setObject(null);
            setScene(null);
            onContext(current);
          }
        })
        .catch((error) => {
          if (active) {
            setConnectionError(errorText(error));
            setContext({});
            setPreview(null);
            setObject(null);
            setScene(null);
            onContext({});
          }
        })
        .finally(() => {
          polling = false;
        });
    }, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [context.session_id, context.revision, onContext]);
  const params = {
    session_id: context.session_id,
    entity_id: object?.entity_id,
  };
  return (
    <div className="native">
      <div className="toolbar">
        <button
          className="primary"
          onClick={() => run("读取原生工程", refresh)}
        >
          读取 FreeCAD 工程
        </button>
        {context.session_id && (
          <>
            <button
              disabled={!!pendingOperation}
              onClick={() =>
                run("保存原生工程", async () => {
                  await call("freecad.save", {
                    session_id: context.session_id,
                    path:
                      "revisions/native-" +
                      crypto.randomUUID().slice(0, 12) +
                      "/shaft.FCStd",
                  });
                  await refresh();
                })
              }
            >
              另存工作修订
            </button>
            <button
              disabled={!operation || !!pendingOperation}
              onClick={() =>
                run("撤销", async () => {
                  await call("freecad.undo", {
                    session_id: context.session_id,
                    operation_id: operation,
                  });
                  setOperation("");
                  await refresh();
                })
              }
            >
              撤销本次修改
            </button>
          </>
        )}
        <span>{context.path || ""}</span>
      </div>
      {pendingOperation && (
        <div className="error">
          <span>修改结果待确认，已暂停继续写入。</span>
          <button
            onClick={() =>
              run("查询原生回执", async () => {
                const result = await call(
                  "freecad.operation",
                  pendingOperation,
                );
                if (
                  result.state === "committed" ||
                  result.state === "not_found"
                ) {
                  setOperation(
                    result.state === "committed" && !result.undone
                      ? pendingOperation.operation_id
                      : "",
                  );
                  setPendingOperation(null);
                  await refresh();
                }
              })
            }
          >
            查询修改结果
          </button>
        </div>
      )}
      {!scene ? (
        <Empty
          title={connectionError ? "原生连接已中断" : "读取正在编辑的工程"}
          body={
            connectionError ||
            "在 FreeCAD 中启用 GongKe 工作台后，模型和 TechDraw 图纸会显示在这里。SOLIDWORKS 与 AutoCAD 需要 Windows 宿主插件。"
          }
        />
      ) : (
        <>
          <div className="native-tabs">
            <button
              className={!page ? "active" : ""}
              onClick={() => setPage("")}
            >
              三维模型
            </button>
            {scene.pages?.map((p: Data) => (
              <button
                key={p.name}
                className={page === p.name ? "active" : ""}
                onClick={() => setPage(p.name)}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="native-area">
            {page ? (
              <div className="page-view">
                {scene.pages.find((p: Data) => p.name === page)?.error ? (
                  <Empty
                    title="图纸预览未就绪"
                    body={scene.pages.find((p: Data) => p.name === page).error}
                  />
                ) : (
                  <img
                    className="drawing"
                    src={
                      "data:image/svg+xml;charset=utf-8," +
                      encodeURIComponent(
                        scene.pages.find((p: Data) => p.name === page)?.svg ||
                          "",
                      )
                    }
                  />
                )}
                <div className="toolbar">
                  <button
                    disabled={!!pendingOperation}
                    onClick={() =>
                      run("更新原生图纸", async () => {
                        await call("freecad.update_drawing", {
                          session_id: context.session_id,
                          page_name: page,
                          expected_revision: context.revision,
                        });
                        await refresh();
                      })
                    }
                  >
                    更新图纸
                  </button>
                  {project && (
                    <button
                      disabled={!!pendingOperation}
                      onClick={() =>
                        run("导出原生 DXF", async () => {
                          await call("freecad.export_drawing", {
                            session_id: context.session_id,
                            page_name: page,
                            expected_revision: context.revision,
                          });
                        })
                      }
                    >
                      导出 DXF 修订
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <ModelView scene={scene} selected={selected} onSelect={select} />
            )}
            <div className="properties">
              <h3>对象</h3>
              {scene.objects?.map((o: Data) => (
                <button
                  className={selected === o.id ? "object active" : "object"}
                  key={o.id}
                  onClick={() => select(o.id)}
                >
                  {o.label}
                </button>
              ))}
              {object?.supported ? (
                <>
                  <h3>原生尺寸</h3>
                  {object.snapshot?.segments?.map((s: Data) => (
                    <div key={s.segment_id} className="property">
                      <span>{s.segment_id}</span>
                      <strong>⌀ {(s.diameter_m * 1000).toFixed(2)} mm</strong>
                    </div>
                  ))}
                  {segment && (
                    <>
                      <label>
                        目标直径 / mm
                        <input
                          aria-label="目标直径"
                          type="number"
                          value={diameter}
                          onChange={(e) => {
                            setDiameter(e.target.value);
                            setPreview(null);
                          }}
                        />
                      </label>
                      <button
                        onClick={() =>
                          run("比较修改", async () =>
                            setPreview(
                              await call("freecad.preview", {
                                ...params,
                                segment_id: segment,
                                diameter_m: Number(diameter) / 1000,
                              }),
                            ),
                          )
                        }
                      >
                        计算修改影响
                      </button>
                    </>
                  )}
                  <button
                    onClick={() =>
                      run("原生校核", async () =>
                        setReview(await call("freecad.review", params)),
                      )
                    }
                  >
                    校核当前模型
                  </button>
                </>
              ) : (
                <p className="muted">
                  {object?.reason ||
                    "选择已绑定的受支持轴，可读取工程条件并进行尺寸修改。"}
                </p>
              )}
              {preview && (
                <div className="candidate">
                  <h3>修改比较</h3>
                  <Json value={preview} />
                  <button
                    className="primary"
                    disabled={!preview.change_id || !!pendingOperation}
                    onClick={() =>
                      run("应用原生修改", async () => {
                        const operation_id = crypto.randomUUID();
                        setPendingOperation({
                          session_id: context.session_id,
                          operation_id,
                        });
                        await call("freecad.apply", {
                          session_id: context.session_id,
                          change_id: preview.change_id,
                          operation_id,
                        });
                        setPendingOperation(null);
                        setOperation(operation_id);
                        await refresh();
                      })
                    }
                  >
                    应用修改
                  </button>
                </div>
              )}
              {review && (
                <details open>
                  <summary>校核结果</summary>
                  <Json value={review} />
                </details>
              )}
            </div>
          </div>
          <div className="native-status">
            {scene.modified ? "有未保存修改" : "文档已保存"} · 修订{" "}
            {scene.revision} · {scene.objects?.length || 0} 个对象
            {scene.needs_rebuild ? " · 需要重建" : ""}
          </div>
        </>
      )}
    </div>
  );
}
function TaskList({ tasks, run }: { tasks: Data[]; run: any }) {
  return (
    <div className="task-list">
      {!tasks.length && (
        <Empty
          title="还没有任务"
          body="计算、模型修改和工程助手的执行状态会保存在这里。"
        />
      )}
      {tasks.map((task: Data) => (
        <article className="task" key={task.task_id}>
          <div>
            <strong>{task.kind || task.title || "工程任务"}</strong>
            <span className={"task-status " + task.status}>
              {statuses[task.status] || task.status}
            </span>
          </div>
          <p>{task.stage || task.message || task.task_id}</p>
          {task.error && (
            <div className="error">
              {typeof task.error === "string" ? task.error : text(task.error)}
            </div>
          )}
          {["running", "queued"].includes(task.status) && (
            <button
              onClick={() =>
                run("取消任务", () =>
                  call("task.cancel", { task_id: task.task_id }),
                )
              }
            >
              取消待执行操作
            </button>
          )}
          {task.result && (
            <details>
              <summary>结果</summary>
              <Json value={task.result} />
            </details>
          )}
        </article>
      ))}
    </div>
  );
}
function Settings({
  onClose,
  onSave,
  run,
}: {
  onClose: () => void;
  onSave: () => Promise<void>;
  run: any;
}) {
  const [values, setValues] = useState<Data>({
      base_url: "",
      model: "",
      api_key: "",
    }),
    [notice, setNotice] = useState("");
  useEffect(() => {
    window.gongke.settings().then((s) => setValues({ ...s, api_key: "" }));
  }, []);
  return (
    <div className="modal-scrim">
      <div className="modal">
        <div className="section-bar">
          <h2>模型服务</h2>
          <button onClick={onClose}>×</button>
        </div>
        <p>接入支持 Chat Completions 工具调用的模型。</p>
        <label>
          服务地址
          <input
            value={values.base_url}
            onChange={(e) => setValues({ ...values, base_url: e.target.value })}
            placeholder="https://api.openai.com/v1"
          />
        </label>
        <label>
          模型名称
          <input
            value={values.model}
            onChange={(e) => setValues({ ...values, model: e.target.value })}
            placeholder="输入服务商提供的模型 ID"
          />
        </label>
        <label>
          API 密钥
          <input
            type="password"
            autoComplete="off"
            value={values.api_key}
            placeholder={
              values.has_key ? "已安全保存；留空保留" : "仅用于此模型服务"
            }
            onChange={(e) => setValues({ ...values, api_key: e.target.value })}
          />
        </label>
        {notice && <p>{notice}</p>}
        <div className="toolbar">
          <button
            className="primary"
            onClick={() =>
              run("保存模型连接", async () => {
                const result = await window.gongke.configure(values);
                setNotice(
                  result.persisted
                    ? "已通过系统加密保存。连接将在首次任务时验证。"
                    : "已载入本次会话；系统加密不可用，密钥不会保存。",
                );
                setValues({
                  ...values,
                  api_key: "",
                  has_key: result.persisted,
                });
                await onSave();
              })
            }
          >
            保存连接
          </button>
          <button onClick={onClose}>完成</button>
        </div>
      </div>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
