import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  safeStorage,
  shell,
} from "electron";
import { join, resolve, relative, isAbsolute } from "node:path";
import { existsSync, readFileSync, writeFileSync, realpathSync } from "node:fs";
import { Service } from "./service.cjs";
import { normalizeProvider, mayReuseKey } from "./credentials.cjs";

let window: BrowserWindow;
let service: Service;
let projectRoot = "";
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
  "agent.run",
]);
function settingsPath() {
  return join(app.getPath("userData"), "provider.json");
}
function readSettings() {
  try {
    return JSON.parse(readFileSync(settingsPath(), "utf8"));
  } catch {
    return {};
  }
}
async function configureSaved() {
  const s = readSettings();
  if (s.encryptedKey && safeStorage.isEncryptionAvailable())
    await service.request("agent.configure", {
      base_url: s.base_url,
      model: s.model,
      api_key: safeStorage.decryptString(Buffer.from(s.encryptedKey, "base64")),
    });
}
function startService() {
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
      backgroundColor: "#131619",
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
    ipcMain.handle("configure-agent", async (event, s) => {
      requireMainFrame(event);
      const base_url = normalizeProvider(s.base_url);
      if (!s.model?.trim()) throw new Error("请输入模型名称");
      const old = readSettings();
      if (
        !s.api_key &&
        old.encryptedKey &&
        !mayReuseKey(old.base_url, base_url)
      )
        throw new Error("服务地址已改变，请为此服务输入新的 API 密钥");
      const key =
        s.api_key ||
        (old.encryptedKey && safeStorage.isEncryptionAvailable()
          ? safeStorage.decryptString(Buffer.from(old.encryptedKey, "base64"))
          : "");
      if (!key) throw new Error("请输入 API 密钥");
      await service.request("agent.configure", {
        base_url,
        model: s.model.trim(),
        api_key: key,
      });
      const secure = safeStorage.isEncryptionAvailable();
      writeFileSync(
        settingsPath(),
        JSON.stringify({
          base_url,
          model: s.model.trim(),
          ...(secure
            ? {
                encryptedKey: safeStorage.encryptString(key).toString("base64"),
              }
            : {}),
        }),
        { mode: 0o600 },
      );
      return { configured: true, persisted: secure };
    });
    ipcMain.handle("agent-settings", (event) => {
      requireMainFrame(event);
      const s = readSettings();
      return {
        base_url: s.base_url || "https://api.openai.com/v1",
        model: s.model || "",
        has_key: !!s.encryptedKey,
      };
    });
    ipcMain.handle("restart-service", async (event) => {
      requireMainFrame(event);
      await service.stop();
      startService();
      await configureSaved();
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
    try {
      await configureSaved();
    } catch {
      window.webContents.send("service-event", {
        event: "agent.unavailable",
        message: "模型连接未恢复，请检查设置",
      });
    }
  });
  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", () => service?.stop());
}
