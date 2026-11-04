import { useCallback, useEffect, useState } from "react";
import {
  FluentProvider,
  Button,
  Toolbar,
  Dialog,
  DialogSurface,
  DialogBody,
  DialogTitle,
  DialogContent,
  DialogActions,
  ToolbarButton,
  Tooltip,
  MessageBar,
  MessageBarBody,
  MessageBarActions,
} from "@fluentui/react-components";
import {
  SearchRegular,
  DocumentRegular,
  HistoryRegular,
  SplitHorizontalRegular,
  PanelBottomRegular,
  WarningRegular,
  PanelLeftRegular,
  PanelRightRegular,
  WeatherMoonRegular,
  WeatherSunnyRegular,
  DismissRegular,
  ArrowSyncRegular,
} from "@fluentui/react-icons";
import { QuickPicker, QuickItem } from "../ui/QuickPicker";
import type { AgentSnapshot } from "../../electron/acp/types.cjs";
import { darkTheme, lightTheme } from "./theme";
import { useProject } from "./useProject";
import { Layout, defaultLayout, fitLayout, panelWidth } from "./layout";
import { ProjectTree } from "../project/ProjectTree";
import {
  DocumentRef,
  ProjectFile,
  homeDocument,
  cadDocument,
  openDocument,
  revisionOf,
} from "../project/types";
import { DocumentTabs } from "../workspace/DocumentTabs";
import { StartPage } from "../workspace/StartPage";
import { CadWorkspace } from "../workspace/CadWorkspace";
import { FileDocument } from "../workspace/FileDocument";
import { ReducerTask } from "../project/ReducerTask";
import { OperationPanel, PanelTab } from "../operations/OperationPanel";
import { locateModelTarget, ModelTarget } from "../operations/modelChecks";
import { AgentPanel } from "../agent/AgentPanel";
import { ResizeHandle } from "../ui/ResizeHandle";
import { call, Data } from "../api";

import { ModelingProgress } from "../agent/ModelingProgress";

export function AppShell() {
  const state = useProject();
  const {
    project,
    tasks,
    hosts,
    online,
    error,
    setError,
    busy,
    refresh,
    run,
    choose,
  } = state;
  const [layout, setLayout] = useState<Layout>(() =>
    fitLayout(
      {
        ...defaultLayout,
        ...JSON.parse(localStorage.getItem("gongke.layout") || "{}"),
      },
      innerWidth,
    ),
  );
  const [picker, setPicker] = useState<"commands" | "files" | null>(null);
  const [panel, setPanel] = useState<PanelTab>("checks");
  const [panelOpen, setPanelOpen] = useState(false);
  const [panelHeight, setPanelHeight] = useState(240);
  const [split, setSplit] = useState<DocumentRef[]>([]);
  const [splitActive, setSplitActive] = useState("");
  const [focusedGroup, setFocusedGroup] = useState(1);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [agentState, setAgentState] = useState<AgentSnapshot>();
  const [output, setOutput] = useState<string[]>([]);
  const [documents, setDocuments] = useState<DocumentRef[]>([homeDocument]);
  const [visited, setVisited] = useState<DocumentRef[]>([homeDocument]);
  const [active, setActive] = useState("home");
  const [hostKind, setHostKind] = useState("freecad");
  const [native, setNative] = useState<Data>({});
  const [cadFocus, setCadFocus] = useState(0);
  const [result, setResult] = useState<Data | null>(null);
  const [mode, setMode] = useState<"model" | "practice">("model");
  const open = useCallback((doc: DocumentRef) => {
    setDocuments((d) => {
      const existing = d.find((x) => x.id === doc.id);
      if (existing)
        return d.map((x) =>
          x.id === doc.id && !doc.preview ? { ...x, preview: false } : x,
        );
      return [...d.filter((x) => !doc.preview || !x.preview), doc];
    });
    setVisited((d) => openDocument(d, doc));
    setActive(doc.id);
    setFocusedGroup(1);
  }, []);
  const openFile = useCallback(
    (file: ProjectFile, preview = false) => {
      const doc: DocumentRef = {
        id: file.path,
        title: file.name,
        type: "file",
        file,
        preview,
      };
      if (focusedGroup === 2) {
        setSplit((d) =>
          d.some((x) => x.id === doc.id)
            ? d.map((x) =>
                x.id === doc.id && !preview ? { ...x, preview: false } : x,
              )
            : [...d.filter((x) => !preview || !x.preview), doc],
        );
        setSplitActive(doc.id);
      } else open(doc);
    },
    [open, focusedGroup],
  );
  function pin(id: string) {
    setDocuments((d) =>
      d.map((x) => (x.id === id ? { ...x, preview: false } : x)),
    );
  }
  function splitFile(file?: ProjectFile) {
    if (!file) {
      setPicker("files");
      return;
    }
    const doc: DocumentRef = {
      id: file.path,
      title: file.name,
      type: "file",
      file,
    };
    setSplit((d) => openDocument(d, doc));
    setSplitActive(doc.id);
    setFocusedGroup(2);
  }
  function showPanel(value: "checks" | "tasks" | "output") {
    setPanel(value);
    setPanelOpen(true);
  }
  function close(id: string) {
    const next = documents.filter((d) => d.id !== id);
    if (!next.length) next.push(homeDocument);
    setDocuments(next);
    if (active === id) setActive(next.at(-1)!.id);
    requestAnimationFrame(() =>
      document
        .querySelector<HTMLButtonElement>(
          '.document-tabs [role="tab"][aria-selected="true"]',
        )
        ?.focus(),
    );
  }
  useEffect(() => {
    localStorage.setItem("gongke.layout", JSON.stringify(layout));
  }, [layout]);
  useEffect(() => {
    const fit = () => setLayout((l) => fitLayout(l, innerWidth));
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);
  useEffect(() => {
    setDocuments([homeDocument]);
    setVisited([homeDocument]);
    setActive("home");
    setSplit([]);
    setSplitActive("");
    setFocusedGroup(1);
    setNative({});
    setResult(null);
  }, [project?.path]);
  useEffect(() => {
    document.title = project ? `${project.name} — 构想引擎` : "构想引擎";
  }, [project?.name]);
  const taskKey = JSON.stringify([
    project?.path,
    project?.task,
    project?.teaching,
  ]);
  useEffect(() => {
    setResult(null);
    if (!project?.task?.conveyor) return;
    let live = true;
    call("design.calculate", { task: project.task })
      .then((r) => {
        if (live) setResult(r);
      })
      .catch((e) => {
        if (live) setError(String(e));
      });
    return () => {
      live = false;
    };
  }, [taskKey]);
  const current =
    focusedGroup === 2
      ? split.find((d) => d.id === splitActive)
      : visited.find((d) => d.id === active);
  const selection =
    current?.type === "file"
      ? current.file!.path
      : current?.type === "cad" && native.document
        ? `${native.document} · 修订 ${native.revision ?? "—"}${native.selected_object ? " · " + native.selected_object : ""}`
        : "";
  const [excluded, setExcluded] = useState("");
  useEffect(() => setExcluded(""), [selection]);
  async function importFiles() {
    if (!project) return;
    await run("打开图纸", async () => {
      const files = await window.gongke.documents.import();
      await refresh();
      files.forEach((file) => openFile(file));
    });
  }
  async function locateCheck(target: ModelTarget) {
    await run("定位检查对象", async () => {
      const context = await locateModelTarget(target, call);
      setHostKind(target.host);
      setNative(context);
      open(cadDocument);
      setCadFocus((n) => n + 1);
    });
  }
  const running = tasks.filter((t) =>
    ["running", "queued"].includes(t.status),
  ).length;
  const problemCount = tasks
    .flatMap((t) => t.result?.checks || [])
    .filter((c) => c.ok !== true).length;
  useEffect(() => {
    void window.gongke.agent
      .state()
      .then(setAgentState)
      .catch((e) => setError(String(e)));
    return window.gongke.agent.onState(setAgentState);
  }, []);
  useEffect(
    () =>
      window.gongke.onEvent((event) => {
        if (event.event?.startsWith("service."))
          setOutput((lines) => [
            ...lines.slice(-199),
            `${new Date().toLocaleTimeString()} ${event.event}: ${event.message || event.error?.message || ""}`,
          ]);
      }),
    [],
  );
  const commands: QuickItem[] = [
    ...(!busy
      ? [
          { id: "new", label: "工程: 新建工程", run: () => choose(true) },
          { id: "open", label: "工程: 打开工程", run: () => choose(false) },
          ...(project
            ? [
                { id: "import", label: "工程: 导入图纸", run: importFiles },
                {
                  id: "model",
                  label: "模型: 新建模型",
                  run: () => open(cadDocument),
                },
              ]
            : []),
        ]
      : []),
    { id: "refresh", label: "工程: 刷新", run: () => void refresh() },
    {
      id: "files",
      label: "文件: 快速打开",
      shortcut: "⌘/Ctrl+P",
      run: () => setPicker("files"),
    },
    { id: "home", label: "帮助: 欢迎页", run: () => open(homeDocument) },
    {
      id: "tree",
      label: "视图: 切换资源管理器",
      shortcut: "⌘/Ctrl+B",
      run: () => setLayout((l) => ({ ...l, treeOpen: !l.treeOpen })),
    },
    {
      id: "panel",
      label: "视图: 切换底部面板",
      shortcut: "⌘/Ctrl+J",
      run: () => setPanelOpen((v) => !v),
    },
    {
      id: "agent",
      label: "视图: 切换 Agent",
      shortcut: "⌘/Ctrl+Alt+B",
      run: () => setLayout((l) => ({ ...l, agentOpen: !l.agentOpen })),
    },
    {
      id: "checks",
      label: "视图: 问题",
      shortcut: "⌘/Ctrl+Shift+M",
      run: () => showPanel("checks"),
    },
    { id: "tasks", label: "视图: 操作记录", run: () => showPanel("tasks") },
    {
      id: "output",
      label: "视图: 输出 / 日志",
      run: () => showPanel("output"),
    },
    {
      id: "split",
      label: "视图: 向右拆分文件",
      shortcut: "⌘/Ctrl+\\",
      run: () => splitFile(current?.file),
    },
    {
      id: "theme",
      label: "首选项: 切换颜色主题",
      run: () => setLayout((l) => ({ ...l, dark: !l.dark })),
    },
  ];
  useEffect(() => {
    const keydown = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.defaultPrevented) return;
      const key = e.key.toLowerCase();
      if (key === "p") {
        e.preventDefault();
        setPicker(e.shiftKey ? "commands" : "files");
      } else if (!picker && key === "b") {
        e.preventDefault();
        setLayout((l) =>
          e.altKey
            ? { ...l, agentOpen: !l.agentOpen }
            : { ...l, treeOpen: !l.treeOpen },
        );
      } else if (!picker && key === "i") {
        e.preventDefault();
        setLayout((l) => ({ ...l, agentOpen: true }));
        requestAnimationFrame(() =>
          document
            .querySelector<HTMLTextAreaElement>(".agent-panel textarea")
            ?.focus(),
        );
      } else if (!picker && key === "e" && e.shiftKey) {
        e.preventDefault();
        setLayout((l) => ({ ...l, treeOpen: true }));
        requestAnimationFrame(() =>
          document
            .querySelector<HTMLElement>('.project-pane [role="treeitem"]')
            ?.focus(),
        );
      } else if (!picker && key === "tab") {
        e.preventDefault();
        const list = focusedGroup === 2 ? split : documents;
        const index = list.findIndex(
          (d) => d.id === (focusedGroup === 2 ? splitActive : active),
        );
        const next =
          list[(index + (e.shiftKey ? -1 : 1) + list.length) % list.length];
        if (next) (focusedGroup === 2 ? setSplitActive : setActive)(next.id);
      } else if (!picker && key === "j") {
        e.preventDefault();
        setPanelOpen((v) => !v);
      } else if (!picker && key === "m" && e.shiftKey) {
        e.preventDefault();
        showPanel("checks");
      } else if (!picker && key === "\\") {
        e.preventDefault();
        splitFile(current?.file);
      } else if (!picker && key === "w") {
        e.preventDefault();
        if (focusedGroup === 2) {
          const next = split.filter((d) => d.id !== splitActive);
          setSplit(next);
          setSplitActive(next.at(-1)?.id || "");
          if (!next.length) setFocusedGroup(1);
        } else close(active);
      } else if (!picker && (key === "1" || key === "2")) {
        e.preventDefault();
        const group = key === "2" && split.length ? 2 : 1;
        setFocusedGroup(group);
        document
          .querySelector<HTMLElement>(`[data-editor-group="${group}"]`)
          ?.focus();
      }
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  });
  const iconButton = (
    label: string,
    icon: React.ReactElement,
    action: () => void,
  ) => (
    <Tooltip content={label} relationship="label">
      <ToolbarButton aria-label={label} icon={icon} onClick={action} />
    </Tooltip>
  );
  return (
    <ModelingProgress project={project?.path}>
      <FluentProvider
        applyStylesToPortals={false}
        theme={layout.dark ? darkTheme : lightTheme}
        className="workbench"
        data-theme={layout.dark ? "dark" : "light"}
      >
        <header
          className={
            "workbench-titlebar " +
            (window.gongke.platform === "darwin" ? "mac-titlebar" : "")
          }
        >
          <span className="app-brand">构想引擎</span>
          <Button
            className="command-center"
            size="small"
            appearance="subtle"
            icon={<SearchRegular />}
            onClick={() => setPicker("commands")}
            title="命令面板 (Ctrl/Cmd+Shift+P)"
          >
            {project?.name || "搜索命令"}
          </Button>
          <Toolbar aria-label="布局">
            {iconButton(
              layout.treeOpen ? "收起工程树" : "展开工程树",
              <PanelLeftRegular />,
              () => setLayout((l) => ({ ...l, treeOpen: !l.treeOpen })),
            )}
            {iconButton(
              panelOpen ? "收起底部面板" : "展开底部面板",
              <PanelBottomRegular />,
              () => setPanelOpen((v) => !v),
            )}
            {iconButton(
              layout.agentOpen ? "收起 Agent" : "展开 Agent",
              <PanelRightRegular />,
              () => setLayout((l) => ({ ...l, agentOpen: !l.agentOpen })),
            )}
            {iconButton(
              layout.dark ? "切换浅色主题" : "切换深色主题",
              layout.dark ? <WeatherSunnyRegular /> : <WeatherMoonRegular />,
              () => setLayout((l) => ({ ...l, dark: !l.dark })),
            )}
          </Toolbar>
        </header>
        {error && (
          <MessageBar intent="error">
            <MessageBarBody>{error}</MessageBarBody>
            <MessageBarActions
              containerAction={
                <Button
                  appearance="transparent"
                  icon={<DismissRegular />}
                  aria-label="关闭错误提示"
                  onClick={() => setError("")}
                />
              }
            />
          </MessageBar>
        )}
        <div className="workbench-body">
          <nav className="activity-bar" aria-label="活动栏">
            <Button
              appearance="subtle"
              icon={<DocumentRegular />}
              aria-label="资源管理器"
              aria-pressed={layout.treeOpen}
              onClick={() =>
                setLayout((l) => ({ ...l, treeOpen: !l.treeOpen }))
              }
            />
            <Button
              appearance="subtle"
              icon={<SearchRegular />}
              aria-label="快速打开"
              onClick={() => setPicker("files")}
            />
            <Button
              appearance="subtle"
              icon={<WarningRegular />}
              aria-label="问题"
              onClick={() => showPanel("checks")}
            />
            <span className="toolbar-space" />
            <Button
              appearance="subtle"
              icon={<HistoryRegular />}
              aria-label="操作记录"
              onClick={() => showPanel("tasks")}
            />
          </nav>
          <div
            className="workspace-grid"
            style={{
              gridTemplateColumns: `${layout.treeOpen ? layout.tree : 0}px ${layout.treeOpen ? 5 : 0}px minmax(0,1fr) ${layout.agentOpen ? 5 : 0}px ${layout.agentOpen ? layout.agent : 0}px`,
            }}
          >
            <div className="side-slot" hidden={!layout.treeOpen}>
              <ProjectTree
                project={project}
                active={active}
                open={open}
                openFile={openFile}
                importFiles={importFiles}
                choose={choose}
                refresh={refresh}
                busy={!!busy}
                splitFile={splitFile}
              />
            </div>
            {layout.treeOpen ? (
              <ResizeHandle
                label="工程树宽度"
                value={layout.tree}
                min={180}
                max={360}
                onChange={(tree) =>
                  setLayout((l) => ({ ...l, tree: panelWidth(tree, "tree") }))
                }
              />
            ) : (
              <div />
            )}
            <main className="workspace-main">
              <div
                className={"editor-groups" + (split.length ? " is-split" : "")}
              >
                <div
                  className="editor-group"
                  data-editor-group="1"
                  tabIndex={-1}
                  onFocusCapture={() => setFocusedGroup(1)}
                  onPointerDown={() => setFocusedGroup(1)}
                >
                  <div className="editor-heading">
                    <DocumentTabs
                      documents={documents}
                      active={active}
                      select={setActive}
                      close={close}
                      pin={pin}
                    />
                    <Button
                      size="small"
                      appearance="subtle"
                      icon={<SplitHorizontalRegular />}
                      aria-label="向右拆分文件"
                      onClick={() =>
                        splitFile(visited.find((d) => d.id === active)?.file)
                      }
                    />
                  </div>
                  <nav className="breadcrumbs" aria-label="面包屑">
                    <span>{project?.name || "欢迎"}</span>
                    <span>›</span>
                    <span>
                      {visited
                        .find((d) => d.id === active)
                        ?.file?.path.split("/")
                        .join(" › ") ||
                        visited.find((d) => d.id === active)?.title}
                    </span>
                    {active === "cad" && native.document && (
                      <>
                        <span>›</span>
                        <span>
                          {String(native.document).split(/[\\/]/).at(-1)}
                        </span>
                        {native.selected_object && (
                          <>
                            <span>›</span>
                            <span>
                              {native.object_path?.join(" › ") ||
                                native.selected_object}
                            </span>
                          </>
                        )}
                      </>
                    )}
                  </nav>
                  <div className="documents">
                    {visited.map((doc) => (
                      <section
                        key={`${project?.path || ""}:${doc.id}`}
                        className="document-surface"
                        hidden={active !== doc.id}
                        role="tabpanel"
                        aria-label={doc.title}
                      >
                        {doc.type === "home" && (
                          <StartPage
                            project={project}
                            choose={choose}
                            importFiles={importFiles}
                            model={() => open(cadDocument)}
                          />
                        )}
                        {doc.type === "cad" && project && (
                          <CadWorkspace
                            visible={active === "cad"}
                            project={project}
                            hosts={hosts}
                            run={run}
                            refresh={refresh}
                            onContext={setNative}
                            focusRequest={cadFocus}
                            kind={hostKind}
                            setKind={setHostKind}
                          />
                        )}
                        {doc.type === "file" && project && (
                          <FileDocument
                            file={doc.file!}
                            project={project}
                            run={run}
                            hosts={hosts}
                            refresh={refresh}
                            openAutoCad={() => {
                              setHostKind("autocad");
                              open(cadDocument);
                            }}
                            openCad={() => open(cadDocument)}
                          />
                        )}
                        {doc.type === "reducer" && project && (
                          <ReducerTask
                            project={project}
                            setProject={state.setProject}
                            run={run}
                            refresh={refresh}
                            result={result}
                            onResult={setResult}
                            openFile={openFile}
                          />
                        )}
                      </section>
                    ))}
                  </div>
                </div>
                {!!split.length && (
                  <div
                    className="editor-group"
                    data-editor-group="2"
                    tabIndex={-1}
                    onFocusCapture={() => setFocusedGroup(2)}
                    onPointerDown={() => setFocusedGroup(2)}
                  >
                    <DocumentTabs
                      documents={split}
                      active={splitActive}
                      select={setSplitActive}
                      pin={(id) =>
                        setSplit((d) =>
                          d.map((x) =>
                            x.id === id ? { ...x, preview: false } : x,
                          ),
                        )
                      }
                      close={(id) => {
                        const next = split.filter((d) => d.id !== id);
                        setSplit(next);
                        setSplitActive(next.at(-1)?.id || "");
                        if (!next.length) setFocusedGroup(1);
                      }}
                    />
                    <nav className="breadcrumbs" aria-label="分屏面包屑">
                      {project?.name} ›{" "}
                      {split
                        .find((d) => d.id === splitActive)
                        ?.file?.path.split("/")
                        .join(" › ")}
                    </nav>
                    <div className="documents">
                      {split.map((doc) => (
                        <section
                          className="document-surface"
                          key={doc.id}
                          hidden={doc.id !== splitActive}
                        >
                          {project && (
                            <FileDocument
                              file={doc.file!}
                              project={project}
                              run={run}
                              hosts={hosts}
                              refresh={refresh}
                              openCad={() => open(cadDocument)}
                              openAutoCad={() => {
                                setHostKind("autocad");
                                open(cadDocument);
                              }}
                            />
                          )}
                        </section>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <OperationPanel
                open={panelOpen}
                tab={panel}
                onTab={setPanel}
                height={panelHeight}
                onHeight={setPanelHeight}
                close={() => setPanelOpen(false)}
                tasks={tasks}
                run={run}
                openCad={() => open(cadDocument)}
                locate={locateCheck}
                output={output}
                error={error}
                problemCount={problemCount}
              />
            </main>
            {layout.agentOpen ? (
              <ResizeHandle
                label="Agent 面板宽度"
                value={layout.agent}
                min={300}
                max={520}
                reverse
                onChange={(agent) =>
                  setLayout((l) => ({
                    ...l,
                    agent: panelWidth(agent, "agent"),
                  }))
                }
              />
            ) : (
              <div />
            )}
            <aside
              className="side-slot agent-slot"
              aria-label="辅助侧栏"
              hidden={!layout.agentOpen}
            >
              <Button
                className="agent-history-action"
                appearance="subtle"
                size="small"
                icon={<HistoryRegular />}
                aria-label="对话历史"
                title="对话历史"
                onClick={() => setHistoryOpen(true)}
              />
              <AgentPanel
                project={project?.path}
                context={excluded !== selection ? selection : undefined}
                referencePath={
                  excluded !== selection &&
                  current?.type === "file" &&
                  /^(png|jpe?g|webp|pdf|dxf|svg|txt|json|md|yaml|yml)$/i.test(
                    current.file!.kind,
                  )
                    ? current.file!.path
                    : undefined
                }
                removeContext={() => setExcluded(selection)}
                mode={mode}
                onMode={setMode}
                onTurnEnd={refresh}
                openModel={() => open(cadDocument)}
              />
            </aside>
          </div>
        </div>
        <footer className="statusbar" aria-busy={!!busy}>
          <span className={"status-dot " + (online ? "online" : "")} />
          <span>{online ? "就绪" : "工程服务未连接"}</span>
          {!online && (
            <Button
              size="small"
              appearance="transparent"
              icon={<ArrowSyncRegular />}
              onClick={() =>
                run("重连", async () => {
                  await window.gongke.restart();
                  await refresh();
                })
              }
            >
              重连
            </Button>
          )}
          <span title={project?.path}>{project?.name || "未打开工程"}</span>
          <span>
            {hosts
              .filter((h) => h.connected)
              .map(
                (h) =>
                  ({
                    freecad: "FreeCAD",
                    solidworks: "SOLIDWORKS",
                    autocad: "AutoCAD",
                  })[h.host as string] || h.host,
              )
              .join(" / ") || "CAD 未连接"}
          </span>
          <Button
            size="small"
            appearance="transparent"
            onClick={() => showPanel("checks")}
          >
            问题 {problemCount}
          </Button>
          <span className="status-project">
            {busy || (running ? `${running} 项执行中` : "")}
          </span>
          <span title="计算使用 SI；图纸单位取自文档标注">
            {current?.type === "cad"
              ? native.unit || "单位：宿主"
              : current?.type === "file"
                ? "单位：文档标注"
                : "SI · r/min"}
          </span>
          <span>
            修订{" "}
            {current?.type === "cad"
              ? (native.revision ?? "—")
              : project && current?.file
                ? revisionOf(project, current.file)?.path.split("/").at(-1) ||
                  "—"
                : "—"}
            {current?.type === "cad" &&
            (native.modified === true || native.dirty === true)
              ? " · 未保存"
              : ""}
          </span>
          <button
            className="status-agent"
            onClick={() =>
              setLayout((l) => ({ ...l, agentOpen: !l.agentOpen }))
            }
          >
            Agent ·{" "}
            {
              {
                disconnected: "未连接",
                starting: "连接中",
                connected: "待登录",
                authenticating: "登录中",
                ready: "已连接",
                prompting: "执行中",
                cancelling: "取消中",
              }[agentState?.phase || "disconnected"]
            }
          </button>
        </footer>
        {picker && (
          <QuickPicker
            key={picker}
            mode={picker}
            close={() => setPicker(null)}
            items={
              picker === "commands"
                ? commands
                : (project?.files || []).map((file) => ({
                    id: file.path,
                    label: file.name,
                    detail: file.path,
                    run: () => openFile(file, true),
                  }))
            }
          />
        )}
        <Dialog
          open={historyOpen}
          onOpenChange={(_, d) => setHistoryOpen(d.open)}
        >
          <DialogSurface>
            <DialogBody>
              <DialogTitle>对话历史</DialogTitle>
              <DialogContent>
                当前 Agent 接口尚不支持列出和恢复历史会话。已保存的对话请在对应
                Agent 中查看；本窗口的操作回执可在底部“操作记录”查看。
              </DialogContent>
              <DialogActions>
                <Button
                  onClick={() => {
                    setHistoryOpen(false);
                    showPanel("tasks");
                  }}
                >
                  操作记录
                </Button>
                <Button
                  appearance="primary"
                  onClick={() => setHistoryOpen(false)}
                >
                  关闭
                </Button>
              </DialogActions>
            </DialogBody>
          </DialogSurface>
        </Dialog>
      </FluentProvider>
    </ModelingProgress>
  );
}
