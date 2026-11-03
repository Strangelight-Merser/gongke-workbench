import { useCallback, useEffect, useState } from "react";
import {
  FluentProvider,
  Button,
  Toolbar,
  ToolbarButton,
  Tooltip,
  MessageBar,
  MessageBarBody,
  MessageBarActions,
} from "@fluentui/react-components";
import {
  AddRegular,
  FolderOpenRegular,
  DocumentAddRegular,
  PanelLeftRegular,
  PanelRightRegular,
  WeatherMoonRegular,
  WeatherSunnyRegular,
  DismissRegular,
  ArrowSyncRegular,
} from "@fluentui/react-icons";
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
} from "../project/types";
import { DocumentTabs } from "../workspace/DocumentTabs";
import { StartPage } from "../workspace/StartPage";
import { CadWorkspace } from "../workspace/CadWorkspace";
import { FileDocument } from "../workspace/FileDocument";
import { ReducerTask } from "../project/ReducerTask";
import { TaskList } from "../operations/TaskList";
import { locateModelTarget, ModelTarget } from "../operations/modelChecks";
import { Checks } from "../operations/Checks";
import { AgentPanel } from "../agent/AgentPanel";
import { ResizeHandle } from "../ui/ResizeHandle";
import { call, Data } from "../api";

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
  const [documents, setDocuments] = useState<DocumentRef[]>([homeDocument]);
  const [visited, setVisited] = useState<DocumentRef[]>([homeDocument]);
  const [active, setActive] = useState("home");
  const [hostKind, setHostKind] = useState("freecad");
  const [native, setNative] = useState<Data>({});
  const [cadFocus, setCadFocus] = useState(0);
  const [result, setResult] = useState<Data | null>(null);
  const [context, setContext] = useState("");
  const [mode, setMode] = useState<"model" | "practice">("model");
  const open = useCallback((doc: DocumentRef) => {
    setDocuments((d) => openDocument(d, doc));
    setVisited((d) => openDocument(d, doc));
    setActive(doc.id);
  }, []);
  const openFile = useCallback(
    (file: ProjectFile) =>
      open({ id: file.path, title: file.name, type: "file", file }),
    [open],
  );
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
    setNative({});
    setContext("");
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
  const current = visited.find((d) => d.id === active);
  const selection =
    current?.type === "file"
      ? current.file!.path
      : current?.type === "cad" && native.document
        ? `${native.document} · 修订 ${native.revision ?? "—"}${native.selected_object ? " · " + native.selected_object : ""}`
        : context;
  const [excluded, setExcluded] = useState("");
  useEffect(() => setExcluded(""), [selection]);
  async function importFiles() {
    if (!project) return;
    await run("打开图纸", async () => {
      const files = await window.gongke.documents.import();
      await refresh();
      files.forEach(openFile);
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
    <FluentProvider
      theme={layout.dark ? darkTheme : lightTheme}
      className="workbench"
      data-theme={layout.dark ? "dark" : "light"}
    >
      {window.gongke.platform === "darwin" && (
        <header className="app-title">
          <strong>构想引擎</strong>
          <span>{project?.name || "未打开工程"}</span>
        </header>
      )}
      <Toolbar className="app-toolbar" aria-label="工程命令">
        <div className="toolbar-project" title={project?.path}>
          <strong>{project?.name || "构想引擎"}</strong>
          <span role="status">
            {busy ||
              (native.document
                ? native.modified === true || native.dirty === true
                  ? "模型有未保存修改"
                  : native.modified === false || native.dirty === false
                    ? "模型已保存"
                    : "模型保存状态未同步"
                : project
                  ? "工程已打开"
                  : "未打开工程")}
          </span>
        </div>
        <span className="toolbar-divider" />
        <ToolbarButton
          icon={<AddRegular />}
          disabled={!!busy}
          onClick={() => choose(true)}
        >
          新建工程
        </ToolbarButton>
        <ToolbarButton
          icon={<FolderOpenRegular />}
          disabled={!!busy}
          onClick={() => choose(false)}
        >
          打开工程
        </ToolbarButton>
        <span className="toolbar-divider" />
        <ToolbarButton
          icon={<DocumentAddRegular />}
          disabled={!project || !!busy}
          onClick={importFiles}
        >
          打开图纸
        </ToolbarButton>
        <span className="toolbar-space" />
        {iconButton(
          layout.treeOpen ? "收起工程树" : "展开工程树",
          <PanelLeftRegular />,
          () => setLayout((l) => ({ ...l, treeOpen: !l.treeOpen })),
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
          <DocumentTabs
            documents={documents}
            active={active}
            select={setActive}
            close={close}
          />
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
                {doc.type === "checks" && (
                  <Checks
                    tasks={tasks}
                    openCad={() => open(cadDocument)}
                    locate={locateCheck}
                  />
                )}
                {doc.type === "tasks" && (
                  <div className="scroll document-content">
                    <TaskList tasks={tasks} run={run} />
                  </div>
                )}
              </section>
            ))}
          </div>
        </main>
        {layout.agentOpen ? (
          <ResizeHandle
            label="Agent 面板宽度"
            value={layout.agent}
            min={300}
            max={520}
            reverse
            onChange={(agent) =>
              setLayout((l) => ({ ...l, agent: panelWidth(agent, "agent") }))
            }
          />
        ) : (
          <div />
        )}
        <aside className="side-slot agent-slot" hidden={!layout.agentOpen}>
          <AgentPanel
            project={project?.path}
            context={excluded !== selection ? selection : undefined}
            removeContext={() => setExcluded(selection)}
            mode={mode}
            onMode={setMode}
            onTurnEnd={refresh}
            openModel={() => open(cadDocument)}
          />
        </aside>
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
        <span className="status-project" title={project?.path}>
          {busy || project?.path || "本地工程"}
        </span>
        <Button
          size="small"
          appearance="transparent"
          onClick={() =>
            open({ id: "checks", title: "检查结果", type: "checks" })
          }
        >
          检查结果
        </Button>
        <Button
          size="small"
          appearance="transparent"
          onClick={() =>
            open({ id: "tasks", title: "操作记录", type: "tasks" })
          }
        >
          {running ? `${running} 项执行中` : "操作记录"}
        </Button>
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
      </footer>
    </FluentProvider>
  );
}
