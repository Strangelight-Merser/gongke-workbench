import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { createRoot } from "react-dom/client";
import { DrawingViewer } from "./DrawingViewer";
import { call, Data, errorText, text } from "./api";
import { ModelView } from "./ModelView";
import {
  CommercialView,
  pendingKey,
  savedPending,
  registeredWorkingCopy,
} from "./CommercialView";
import { Collapsible, StreamText, streamFragment } from "./Motion";
import {
  CheckInspector,
  CheckRow,
  CRITICAL,
  Fact,
  Spectrum,
  StageId,
  STAGES,
  stageChecks,
  stageState,
  summaryOf,
} from "./Workflow";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
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
    [tab, setTab] = useState("task");
  const [result, setResult] = useState<Data | null>(null),
    [check, setCheck] = useState<Data | null>(null),
    [filesOpen, setFilesOpen] = useState(false);
  const [hostKind, setHostKind] = useState("freecad");
  const importingDxf = useRef(false);
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
  const [inspector, setInspector] = useState<HTMLDivElement | null>(null),
    [sidebar, setSidebar] = useState(() => {
      try {
        return localStorage.getItem("gongke.sidebar") !== "hidden";
      } catch {
        return true;
      }
    });
  useEffect(() => {
    try {
      localStorage.setItem("gongke.sidebar", sidebar ? "shown" : "hidden");
    } catch {}
  }, [sidebar]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "\\" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setSidebar((v) => !v);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
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
          const index = items.findIndex(
            (x) => x.streaming && x.task_id === event.task_id,
          );
          const prior = items[index];
          const fragment = streamFragment(event.content);
          const message = {
            ...prior,
            id: prior?.id || crypto.randomUUID(),
            role: "assistant",
            task_id: event.task_id,
            streaming: true,
            content: (prior?.content || "") + event.content,
            fragments: [...(prior?.fragments || []), fragment],
          };
          return index < 0
            ? [...items, message]
            : items.map((item, i) => (i === index ? message : item));
        });
      if (event.event === "agent.message")
        setMessages((items) => {
          const index = items.findIndex(
            (x) => x.streaming && x.task_id === event.task_id,
          );
          if (index < 0)
            return [...items, { ...event, id: crypto.randomUUID() }];
          const prior = items[index];
          const content =
            typeof event.content === "string"
              ? event.content
              : text(event.content);
          const tail = content.startsWith(prior.content)
            ? content.slice(prior.content.length)
            : null;
          const fragments =
            tail === null
              ? undefined
              : tail
                ? [...prior.fragments, streamFragment(tail)]
                : prior.fragments;
          return items.map((item, i) =>
            i === index
              ? { ...event, id: prior.id, streaming: false, fragments }
              : item,
          );
        });
      if (event.event === "service.error") setError(event.error.message);
      if (event.event === "service.stopped") {
        setStatus({ online: false });
        setError(event.message);
      }
      if (event.event === "agent.unavailable") setError(event.message);
    });
    return stop;
  }, [refresh]);
  // 打开带条件的工程时做一次只读计算，侧栏阶段状态与校核汇总由它得出。
  const taskKey = project
    ? project.path + JSON.stringify(project.task || {})
    : "";
  useEffect(() => {
    setCheck(null);
    if (!project?.task?.conveyor) {
      setResult(null);
      return;
    }
    let live = true;
    call("design.calculate", { task: project.task })
      .then((value) => live && setResult(value))
      .catch(() => live && setResult(null));
    return () => {
      live = false;
    };
  }, [taskKey]);
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
  async function importDxf() {
    if (importingDxf.current || !file) return;
    importingDxf.current = true;
    const showAutoCad = () => {
      setHostKind("autocad");
      setTab("native");
    };
    try {
      await run("导入 AutoCAD", async () => {
        if (savedPending("autocad")) {
          showAutoCad();
          throw new Error(
            "上一次原生操作尚待确认，请查询原操作；本次未重复导入",
          );
        }
        const host = hosts.find((h) => h.host === "autocad" && h.connected);
        if (!host) throw new Error("AutoCAD 尚未连接");
        const operation_id = crypto.randomUUID();
        const request = {
          host_id: host.host_id,
          method: "drawing.import_dxf",
          operation_id,
          params: {
            source_path: file.path,
            target_path:
              "revisions/dwg-" +
              crypto.randomUUID().slice(0, 12) +
              "/drawing.dwg",
            operation_id,
          },
        };
        const remember = (value: Data) =>
          localStorage.setItem(pendingKey("autocad"), JSON.stringify(value));
        remember({ ...request, state: "submitted" });
        let result: Data;
        try {
          result = await call("host.command", {
            host_id: request.host_id,
            method: request.method,
            params: request.params,
          });
        } catch (error) {
          remember({
            ...request,
            error: { message: errorText(error), outcome: "unknown" },
          });
          showAutoCad();
          throw error;
        }
        if (result.error) {
          if (result.error.outcome === "unknown") {
            remember({ ...request, ...result });
            showAutoCad();
          } else localStorage.removeItem(pendingKey("autocad"));
          throw new Error(result.error.message);
        }
        remember({ ...request, result });
        try {
          if (result.outcome !== "committed")
            throw new Error("导入结果尚未确认，请查询原操作回执");
          const { project: updated, path } = await registeredWorkingCopy(
            "autocad",
            request,
          );
          setProject(updated);
          const opened = await call("host.command", {
            host_id: host.host_id,
            method: "document.open",
            params: { path, operation_id: crypto.randomUUID() },
          });
          if (opened.error) throw new Error(opened.error.message);
          localStorage.removeItem(pendingKey("autocad"));
          showAutoCad();
          await refresh();
        } catch (error) {
          showAutoCad();
          throw error;
        }
      });
    } finally {
      importingDxf.current = false;
    }
  }
  async function send() {
    if (!prompt.trim()) return;
    const message = prompt;
    setMessages((items) => [
      ...items,
      { id: crypto.randomUUID(), role: "user", content: message },
    ]);
    setPrompt("");
    await run("提交任务", async () => {
      await call("agent.run", { message, allow_writes: allowWrites });
      await refresh();
    });
  }
  const r = summaryOf(result);
  const stageIndex = STAGES.findIndex((s) => s.id === tab);
  const allChecks: Data[] = r?.checks || [];
  const failedCount = allChecks.filter((c) => !c.ok).length,
    criticalCount = allChecks.filter(
      (c) => c.ok && (c.utilization ?? 0) >= CRITICAL,
    ).length;
  const running = tasks.filter((t) => t.status === "running").length;
  const title =
    stageIndex >= 0
      ? STAGES[stageIndex].name
      : tab === "checks"
        ? "全部校核"
        : tab === "native"
          ? "原生模型"
          : tab === "tasks"
            ? "任务与回执"
            : file?.name;
  const eyebrow =
    stageIndex >= 0
      ? `第 ${stageIndex + 1} 步 · ${project?.task?.title || "课程设计"}`
      : tab === "checks"
        ? "按利用率排序"
        : tab === "file"
          ? file?.path
          : tab === "native"
            ? "实时连接的 CAD 文档"
            : "工程操作记录";
  const selectCheck = (c: Data) => setCheck(c);
  return (
    <div className="app">
      <div className="body">
        <aside className="tree" hidden={!sidebar}>
          <div className="tree-top drag">
            <span className="brand-mark">G</span>
            <div className="proj" title={project?.path}>
              <b>{project?.name || "构想引擎"}</b>
              <small>
                {project
                  ? project.teaching
                    ? "教学示例 · 条件须核对"
                    : schemes[project.task?.scheme] || "工程"
                  : "未打开工程"}
              </small>
            </div>
            <button
              className="ghost"
              aria-label="刷新工程"
              title="刷新工程"
              onClick={refresh}
            >
              ↻
            </button>
          </div>
          <div className="project-actions">
            <button onClick={() => choose(false)}>打开工程</button>
            <button onClick={() => choose(true)}>新建工程</button>
          </div>
          <div className="side-scroll">
            <div className="section-title">
              设计流程
              <span className="num">
                {
                  STAGES.filter(
                    (s) => stageState(r, project, s.id).state === "done",
                  ).length
                }{" "}
                / {STAGES.length}
              </span>
            </div>
            <nav className="flow">
              {STAGES.map((s) => {
                const st = stageState(r, project, s.id);
                return (
                  <button
                    key={s.id}
                    className={`step ${st.state} ${tab === s.id ? "on" : ""}`}
                    onClick={() => setTab(s.id)}
                  >
                    <span className="mk" />
                    {s.name}
                    <em>{st.note}</em>
                  </button>
                );
              })}
            </nav>
            <div className="section-title">原生模型</div>
            {["freecad", "solidworks", "autocad"].map((name) => {
              const h = hosts.find((h) => h.host === name);
              return (
                <button
                  key={name}
                  className={
                    "host" +
                    (tab === "native" && hostKind === name ? " on" : "")
                  }
                  onClick={() => {
                    setHostKind(name);
                    setTab("native");
                  }}
                >
                  <span className={`led ${h?.connected ? "on" : ""}`} />
                  {
                    (
                      {
                        freecad: "FreeCAD",
                        solidworks: "SOLIDWORKS",
                        autocad: "AutoCAD",
                      } as Data
                    )[name]
                  }
                  <em>
                    {name === "freecad" && native.document
                      ? native.document
                      : h?.connected
                        ? "已连接"
                        : "未连接"}
                  </em>
                </button>
              );
            })}
            <button
              className="section-title files-toggle"
              aria-expanded={filesOpen}
              onClick={() => setFilesOpen(!filesOpen)}
            >
              工程文件{" "}
              <span className="num">
                {project?.files?.length || 0} {filesOpen ? "▾" : "▸"}
              </span>
            </button>
            {filesOpen && (
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
            )}
          </div>
          <button className="settings-link" onClick={() => setSettings(true)}>
            模型服务
            <small>设置</small>
          </button>
        </aside>
        <main>
          <div className="workspace-title drag">
            <button
              className="ghost sidebar-toggle"
              aria-label={sidebar ? "隐藏侧栏" : "显示侧栏"}
              title={(sidebar ? "隐藏侧栏" : "显示侧栏") + "（⌘/Ctrl+\\）"}
              onClick={() => setSidebar(!sidebar)}
            >
              ▤
            </button>
            <div className="titles">
              <div className="eyebrow">{eyebrow}</div>
              <h1>{title}</h1>
            </div>
            <span className="busy">{busy || ""}</span>
            {r && (
              <button
                className={
                  "check-summary" +
                  (failedCount ? " fail" : criticalCount ? " warn" : "")
                }
                onClick={() => setTab("checks")}
                title="查看全部校核"
              >
                <span className="led on" />
                <b className="num">{allChecks.length}</b> 项校核
                {failedCount ? (
                  <span> · {failedCount} 项未通过</span>
                ) : (
                  <span> · {criticalCount} 项临界</span>
                )}
              </button>
            )}
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
                  inspector={inspector}
                  onInspect={() => setCheck(null)}
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
          {(stageIndex >= 0 || tab === "checks") &&
            (project ? (
              <div className="scroll paper">
                {tab === "task" ? (
                  <TaskForm
                    project={project}
                    setProject={setProject}
                    run={run}
                    refresh={refresh}
                    onResult={setResult}
                  />
                ) : tab === "checks" ? (
                  r ? (
                    <>
                      <Spectrum
                        checks={allChecks}
                        selected={check?.item}
                        onSelect={selectCheck}
                      />
                      <div className="checks">
                        {[...allChecks]
                          .sort(
                            (a, b) =>
                              Number(a.ok) - Number(b.ok) ||
                              (b.utilization ?? -1) - (a.utilization ?? -1),
                          )
                          .map((c, i) => (
                            <CheckRow
                              key={c.item + i}
                              check={c}
                              selected={check?.item === c.item}
                              onSelect={() => selectCheck(c)}
                            />
                          ))}
                      </div>
                    </>
                  ) : (
                    <NeedCalc go={() => setTab("task")} />
                  )
                ) : (
                  <StageView
                    id={tab as StageId}
                    r={r}
                    project={project}
                    check={check}
                    onCheck={selectCheck}
                    openFile={readFile}
                    go={setTab}
                  />
                )}
                {stageIndex >= 0 && stageIndex < STAGES.length - 1 && (
                  <div className="nextline">
                    <p>
                      {stageState(r, project, STAGES[stageIndex].id).state ===
                      "warn"
                        ? "本阶段有临界项：通过，但裕度不足 15%，答辩常被追问。可以接受，也可以回到任务书调整条件。"
                        : stageState(r, project, STAGES[stageIndex].id)
                              .state === "fail"
                          ? "本阶段有未通过的校核，需要先调整条件再继续。"
                          : "本阶段的数值和校核如上。"}
                    </p>
                    <button
                      className="primary"
                      onClick={() => setTab(STAGES[stageIndex + 1].id)}
                    >
                      继续：{STAGES[stageIndex + 1].name} →
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <Empty
                title="从一个工程开始"
                body="课程设计按任务书、方案、传动零件、轴系、箱体、图纸、说明书的顺序进行；每一步的数值和校核都保存在工程里。"
                action="开始新工程"
                onAction={() => choose(true)}
              />
            ))}
          {tab === "tasks" && (
            <div className="scroll paper">
              <TaskList tasks={tasks} run={run} />
            </div>
          )}
          {tab === "file" && file && (
            <div className="file-view">
              <div className="toolbar">
                <button
                  onClick={() =>
                    run("定位文件", () => window.gongke.reveal(file.path))
                  }
                >
                  在文件夹中显示
                </button>
                {file.kind === "dxf" &&
                  hosts.some((h) => h.host === "autocad" && h.connected) && (
                    <button disabled={!!busy} onClick={importDxf}>
                      导入 AutoCAD 工作修订
                    </button>
                  )}
              </div>
              {file.kind === "svg" ? (
                <DrawingViewer svg={file.content} />
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
          <section className="inspector-pane">
            <div className="pane-heading">检查器</div>
            <div className="inspector" ref={setInspector}>
              {check && tab !== "native" ? (
                <CheckInspector check={check} />
              ) : tab === "file" && file ? (
                <div className="insp-in">
                  <div className="crumb">文件</div>
                  <h4>{file.name}</h4>
                  <dl className="kv">
                    <dt>类型</dt>
                    <dd>{(file.kind || "file").toUpperCase()}</dd>
                    <dt>位置</dt>
                    <dd className="path">{file.path}</dd>
                  </dl>
                </div>
              ) : tab !== "native" ? (
                <p className="hint">
                  点任意一项校核，这里显示利用率、依据和结论。
                </p>
              ) : null}
            </div>
          </section>
          <section className="agent-pane">
            <div className="pane-heading">
              工程助手
              <span
                className={`led ${status.agent?.connection === "已完成模型请求" ? "on" : ""}`}
              />
            </div>
            <div className="conversation">
              {!messages.length && (
                <div className="agent-welcome">
                  <p>
                    读取当前模型、核对条件、计算和修改。操作结果直接进入工作区。
                  </p>
                  <button
                    className="suggestion"
                    onClick={() =>
                      setPrompt(
                        check
                          ? `解释「${check.item}」的依据，并说明怎样提高它的裕度。先不要修改。`
                          : "读取当前工程，说明已知条件和还缺少什么。先不要修改模型。",
                      )
                    }
                  >
                    {check ? `解释「${check.item}」` : "核对当前工程的条件"}{" "}
                    <span className="inline-icon" aria-hidden="true">
                      ↗
                    </span>
                  </button>
                  {!status.agent?.configured && (
                    <button className="link" onClick={() => setSettings(true)}>
                      连接模型服务
                    </button>
                  )}
                </div>
              )}
              {messages.map((message) => (
                <div key={message.id} className={"message " + message.role}>
                  <small>
                    {message.role === "user"
                      ? "你"
                      : message.role === "tool"
                        ? "工程操作"
                        : "工程助手"}
                  </small>
                  <div>
                    <StreamText
                      content={
                        typeof message.content === "string"
                          ? message.content
                          : text(message.content)
                      }
                      fragments={message.fragments}
                      streaming={message.streaming === true}
                    />
                  </div>
                </div>
              ))}
            </div>
            {check && tab !== "native" && (
              <div className="context-line">
                上下文 <b>{check.item}</b>
              </div>
            )}
            <div className="compose">
              <textarea
                aria-label="工程任务"
                placeholder="问助手，或描述要做的修改…"
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
                  发送 <span className="inline-icon">↑</span>
                </button>
              </div>
            </div>
          </section>
        </aside>
      </div>
      <footer>
        <span>
          <span className={`led ${status.online ? "on" : ""}`} />
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
        <span className="revs">
          {(project?.results || [])
            .slice(-4)
            .map((x: Data, i: number, all: Data[]) => (
              <span
                key={i}
                className={"rev" + (i === all.length - 1 ? " cur" : "")}
                title={x.directory || x.output_dir || x.path || ""}
              >
                <i />r{(project?.results?.length || 0) - all.length + i + 1}
                {x.name && x.name !== x.kind ? " " + x.name : " 出图"}
              </span>
            ))}
        </span>
        <button
          className={"rail-tasks" + (tab === "tasks" ? " on" : "")}
          onClick={() => setTab("tasks")}
        >
          任务{running ? ` · ${running} 个执行中` : ""}
        </button>
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
  const [task, setTask] = useState<Data>(project.task || {}),
    [advanced, setAdvanced] = useState(false),
    [draft, setDraft] = useState("");
  useEffect(() => setTask(project.task || {}), [project.task]);
  const change = (key: string, value: number) =>
    setTask({ ...task, conveyor: { ...task.conveyor, [key]: value } });
  async function calculate() {
    await run("计算中", async () => {
      await call("project.set_task", { task });
      onResult(await call("design.calculate", { task }));
      await refresh();
    });
  }
  return (
    <div className="design">
      <div className="section-bar">
        <p className="lede">
          填写任务书给定的工作条件，单位按工程习惯。计算是确定性的，同样的条件得到同样的结果。
        </p>
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
              aria-expanded={advanced}
              aria-controls="advanced-conditions"
              onClick={() => {
                setDraft(text(task));
                setAdvanced(!advanced);
              }}
            >
              完整条件
            </button>
          </div>
          <div className="disclosure-grid" data-open={advanced}>
            <div
              id="advanced-conditions"
              className="disclosure-content"
              inert={!advanced}
              aria-hidden={!advanced}
            >
              <div className="advanced disclosure-body">
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                />
                <button
                  onClick={() =>
                    run("保存条件", async () => {
                      const next = JSON.parse(draft);
                      setProject(
                        await call("project.set_task", { task: next }),
                      );
                      setTask(next);
                      setAdvanced(false);
                    })
                  }
                >
                  保存条件
                </button>
              </div>
            </div>
          </div>
        </>
      )}
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
    const files = (project.files || []).filter((f: Data) =>
      id === "drawings"
        ? f.kind === "svg" && f.path.includes("/drawings/")
        : /report\.(md|docx)$/.test(f.name),
    );
    return files.length ? (
      <div className="sheet-grid">
        {files.map((f: Data) => (
          <button
            key={f.path}
            className="sheet-card"
            onClick={() => openFile(f)}
          >
            <span className="sheet-thumb">{f.kind.toUpperCase()}</span>
            <b>{f.name}</b>
            <small>{f.path.split("/").slice(0, -1).join("/")}</small>
          </button>
        ))}
      </div>
    ) : (
      <Empty
        title={id === "drawings" ? "还没有图纸" : "还没有说明书"}
        body="在任务书一步选择「生成模型与图纸」，生成的文件会出现在这里。"
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
function Native({
  inspector,
  onInspect,
  project,
  run,
  onContext,
  pendingOperation,
  setPendingOperation,
}: {
  inspector: HTMLElement | null;
  onInspect: () => void;
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
  // 读到原生场景后切到属性，对象列表在那里。
  const hasScene = !!scene;
  useEffect(() => {
    if (hasScene) onInspect();
  }, [hasScene]);
  // 属性面板存在时渲染到右侧检查器，否则保留在视图旁。
  const portal = (node: React.ReactElement) =>
    inspector ? createPortal(node, inspector) : node;
  const select = useCallback(
    (id: string) => {
      setSelected(id);
      onInspect();
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
                  <DrawingViewer
                    svg={
                      scene.pages.find((p: Data) => p.name === page)?.svg || ""
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
            {portal(
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
                  <Collapsible title="校核结果" defaultOpen>
                    <Json value={review} />
                  </Collapsible>
                )}
              </div>,
            )}
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
            <Collapsible title="结果">
              <Json value={task.result} />
            </Collapsible>
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
document.documentElement.dataset.platform = navigator.userAgent.includes("Mac")
  ? "mac"
  : "other";
createRoot(document.getElementById("root")!).render(<App />);
