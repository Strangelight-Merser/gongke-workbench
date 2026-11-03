import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import { join, resolve, relative, isAbsolute } from "node:path";
import { existsSync, realpathSync, mkdirSync } from "node:fs";
import { Service } from "./service.cjs";
import { AgentClient } from "./acp/client.cjs";
import { AgentConfiguration } from "./acp/settings.cjs";

let window: BrowserWindow;
let service: Service;
let projectRoot = "";
let agent: AgentClient;
const allowed = new Set([
  "system.status",
  "project.create",
  "project.open",
  "project.current",
  "project.files",
  "project.read_file",
  "project.set_task",
  "design.example",
  "design.calculate",
  "design.generate",
  "task.list",
  "task.get",
  "task.cancel",
  "freecad.context",
  "freecad.scene",
  "freecad.select",
  "freecad.read",
  "freecad.review",
  "freecad.preview",
  "freecad.apply",
  "freecad.operation",
  "freecad.undo",
  "freecad.save",
  "freecad.update_drawing",
  "freecad.export_drawing",
  "hosts.list",
  "host.command",
  "design.schema",
]);
function startService() {
  mkdirSync(app.getPath("userData"), { recursive: true });
  const root = resolve(__dirname, "../..");
  const binary = join(
    process.resourcesPath,
    "service",
    "gongke-service",
    process.platform === "win32" ? "gongke-service.exe" : "gongke-service",
  );
  const executable = app.isPackaged
    ? binary
    : process.env.GONGKE_PYTHON || "python3";
  const args = app.isPackaged ? [] : ["-m", "gongke_app.service"];
  args.push("--state-dir", join(app.getPath("userData"), "state"));
  service = new Service(
    executable,
    args,
    app.isPackaged ? app.getPath("userData") : root,
    {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      ...(app.isPackaged ? {} : { PYTHONPATH: root }),
    },
  );
  service.on("event", (event) => {
    if (!window?.isDestroyed()) window.webContents.send("service-event", event);
  });
  service.start();
}
function requireMainFrame(event: Electron.IpcMainInvokeEvent) {
  if (event.senderFrame !== window.webContents.mainFrame)
    throw new Error("无效的命令来源");
}
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", () => {
    window?.show();
    window?.focus();
  });
  app.whenReady().then(async () => {
    if (process.env.GONGKE_DESKTOP_USER_DATA)
      app.setPath("userData", process.env.GONGKE_DESKTOP_USER_DATA);
    startService();
    window = new BrowserWindow({
      width: 1440,
      height: 960,
      minWidth: 1080,
      minHeight: 740,
      title: "构想引擎",
      backgroundColor: "#e6ebe3",
      // macOS 内容延伸到标题栏，侧栏顶部与工作区标题行作为拖动区域。
      ...(process.platform === "darwin"
        ? {
            titleBarStyle: "hiddenInset" as const,
            trafficLightPosition: { x: 14, y: 15 },
          }
        : {}),
      webPreferences: {
        preload: join(__dirname, "preload.cjs"),
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: true,
      },
    });
    window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    window.webContents.on("will-navigate", (event) => event.preventDefault());
    ipcMain.handle("command", async (event, method, params = {}) => {
      requireMainFrame(event);
      if (!allowed.has(method)) throw new Error("不支持的工程命令");
      if (method === "project.open" || method === "project.create") {
        if (agent?.busy) throw new Error("请先取消当前 Agent 操作再切换工程");
        await agent?.disconnect();
      }
      const value = await service.request(method, params);
      if (
        (method === "project.open" ||
          method === "project.create" ||
          method === "project.current") &&
        value?.path
      )
        projectRoot = realpathSync(value.path);
      return value;
    });
    ipcMain.handle("choose-project", async (event, create) => {
      requireMainFrame(event);
      const result = await dialog.showOpenDialog(window, {
        title: create ? "选择新工程的存放目录" : "打开工程目录",
        properties: ["openDirectory", "createDirectory"],
      });
      return result.canceled ? null : result.filePaths[0];
    });
    const configuration = new AgentConfiguration(
      app.getPath("userData"),
      resolve(__dirname, "../.."),
    );
    agent = new AgentClient((state) => {
      if (!window.isDestroyed()) window.webContents.send("acp-state", state);
    });
    const handle = (name: string, action: (...args: any[]) => unknown) =>
      ipcMain.handle(`acp-${name}`, (event, ...args) => {
        requireMainFrame(event);
        return action(...args);
      });
    handle("settings", () => configuration.read());
    handle("save-settings", async (settings) => {
      if (agent.busy) throw new Error("请先取消当前 Agent 操作");
      configuration.save(settings);
      await agent.disconnect();
    });
    handle("state", () => agent.snapshot());
    handle("start", async (id) => {
      if (!projectRoot) throw new Error("请先打开工程");
      const { profile, mcp } = configuration.launch(id, projectRoot);
      await agent.start(profile, projectRoot, mcp);
    });
    handle("authenticate", (id) => agent.authenticate(id));
    handle("new-session", () => agent.newSession());
    handle("prompt", (text) => agent.prompt(text));
    handle("cancel", () => agent.cancel());
    handle("disconnect", () => agent.disconnect());
    handle("permission", (id, optionId) => agent.permission(id, optionId));
    ipcMain.handle("restart-service", async (event) => {
      requireMainFrame(event);
      if (agent.busy) throw new Error("请先取消当前 Agent 操作再重启工程服务");
      await agent.disconnect();
      await service.stop();
      startService();
      if (projectRoot)
        await service.request("project.open", { path: projectRoot });
      return service.request("system.status");
    });
    ipcMain.handle("reveal", async (event, path) => {
      requireMainFrame(event);
      if (!projectRoot) throw new Error("尚未打开工程");
      const target = realpathSync(resolve(projectRoot, path));
      const rel = relative(projectRoot, target);
      if (rel.startsWith("..") || isAbsolute(rel) || !existsSync(target))
        throw new Error("文件不属于当前工程");
      shell.showItemInFolder(target);
    });
    await window.loadFile(join(__dirname, "../dist/index.html"));
  });
  app.on("window-all-closed", () => app.quit());
  let quitting = false;
  app.on("before-quit", (event) => {
    if (quitting) return;
    event.preventDefault();
    quitting = true;
    Promise.allSettled([agent?.disconnect(), service?.stop()]).then(() =>
      app.quit(),
    );
  });
}
