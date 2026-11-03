import { app, BrowserWindow, dialog, ipcMain, screen } from "electron";
import { existsSync, appendFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { EmbedTransport } from "./transport.cjs";
import { contentRect } from "./geometry.cjs";
import type { Bounds, EmbedState } from "./types.js";

const empty: EmbedState = { supported: false, attached: null, pendingPids: [] };
export function installCadEmbedding(window: BrowserWindow) {
  let transport: EmbedTransport | undefined;
  let bounds: Bounds = { x: 0, y: 0, width: 0, height: 0, visible: false };
  let failed = false, allowClose = false, preparingClose = false, closing = false;
  let syncing = false, dirty = false;
  let nativeDialog = false;
  const logDirectory = join(app.getPath("userData"), "embed");
  function send(event: object) { if (!window.isDestroyed()) window.webContents.send("cad-embed-event", event); }
  function helper() {
    if (process.platform !== "win32") throw new Error("CAD 嵌入编辑区需要 Windows");
    if (failed) throw new Error("窗口辅助进程不可用，请重启构想引擎");
    if (!transport) {
      const executable = app.isPackaged
        ? join(process.resourcesPath, "embed", "Gongke.Embed.exe")
        : join(__dirname, "../../native/embed/publish/Gongke.Embed.exe");
      if (!existsSync(executable)) throw new Error("缺少 Windows 窗口组件，请先运行 native/embed/build.ps1");
      mkdirSync(logDirectory, { recursive: true });
      const hwnd = window.getNativeWindowHandle().readBigUInt64LE().toString();
      const bundled = app.isPackaged ? join(process.resourcesPath, "freecad", "bin", "FreeCAD.exe") : process.env.GONGKE_FREECAD_EXE || "";
      transport = new EmbedTransport(executable, [hwnd, String(process.pid), logDirectory, bundled]);
      transport.on("event", (event) => {
        if (event.event === "failure") failed = true;
        if (event.event === "returnFocus") { window.focus(); window.webContents.focus(); }
        send(event);
      });
      transport.on("diagnostic", (text) => appendFileSync(join(logDirectory, "helper-stderr.log"), text));
    }
    return transport;
  }
  async function sync() {
    if (!transport || failed || window.isDestroyed()) return;
    dirty = true;
    if (syncing) return;
    syncing = true;
    try {
      while (dirty && !window.isDestroyed()) {
        dirty = false;
        const content = window.getContentBounds();
        const area = contentRect(bounds, content.width, content.height, window.webContents.getZoomFactor());
        const pixels = screen.dipToScreenRect(window, { x: content.x + area.x, y: content.y + area.y, width: area.width, height: area.height });
        await transport.request("layout", { ...pixels, visible: area.visible && !nativeDialog && window.isVisible() && !window.isMinimized() });
      }
    } catch (error) { send({ event: "failure", message: String(error) }); }
    finally { syncing = false; }
  }
  ipcMain.handle("cad-embed", async (event, method: string, params: any = {}) => {
    if (event.senderFrame !== window.webContents.mainFrame) throw new Error("无效的窗口命令来源");
    if (method === "status" && process.platform !== "win32") return empty;
    if (method === "layout") {
      const content = window.getContentBounds();
      contentRect(params, content.width, content.height, window.webContents.getZoomFactor());
      bounds = params; await sync(); return;
    }
    if (method === "chooseInstallation") {
      nativeDialog = true; await sync();
      try {
        const result = await dialog.showOpenDialog(window, { title: "选择 CAD 程序", properties: ["openFile"], filters: [{ name: "CAD 程序", extensions: ["exe"] }] });
        return result.canceled ? null : await helper().request("addInstallation", { path: result.filePaths[0] });
      } finally { nativeDialog = false; await sync(); }
    }
    if (!["status", "discover", "launch", "attach", "focus", "detach", "closeCad", "diagnose"].includes(method)) throw new Error("不支持的窗口操作");
    const value = await helper().request(method, params);
    if (method === "attach") await sync();
    return value;
  });
  window.on("move", sync); window.on("resize", sync);
  window.on("minimize", sync); window.on("restore", sync);
  window.on("show", sync); window.on("hide", sync);
  const displayChanged = () => void sync();
  screen.on("display-metrics-changed", displayChanged);
  window.webContents.on("did-start-loading", () => { bounds.visible = false; void sync(); });
  window.webContents.on("render-process-gone", () => {
    bounds.visible = false;
    transport?.request("detach").catch((e) => send({ event: "failure", message: String(e) }));
  });
  // 关闭期间保持主窗口与消息循环存活，让原生保存/取消对话框完成。
  window.on("close", (event) => {
    if (allowClose || !transport) return;
    event.preventDefault();
    if (preparingClose) return;
    preparingClose = true;
    void (async () => {
      try {
        const state = await transport!.request<EmbedState>("prepareClose");
        closing = true;
        if (!state.pendingPids.length) { await transport!.stop(); allowClose = true; window.close(); }
        else send({ event: "closing", message: "请在 CAD 中保存或放弃修改并关闭窗口；取消退出可继续工作。" });
      } catch (error) {
        const result = await dialog.showMessageBox(window, { type: "warning", message: "窗口组件未响应，请先确认 CAD 已恢复为独立窗口。", detail: String(error), buttons: ["返回工作台", "CAD 已恢复，退出工作台"], defaultId: 0, cancelId: 0 });
        if (result.response === 1) { allowClose = true; window.close(); }
      } finally { preparingClose = false; }
    })();
  });
  const closeTimer = setInterval(async () => {
    if (!closing || !transport || preparingClose || window.isDestroyed()) return;
    preparingClose = true;
    try {
      const state = await transport.request<EmbedState>("status");
      if (closing && !state.pendingPids.length) { await transport.stop(); allowClose = true; window.close(); }
    } catch { closing = false; }
    finally { preparingClose = false; }
  }, 500);
  // 用户在原生保存提示选择取消后，任何新的托管动作取消应用退出意图。
  const cancelClosing = (_event: Electron.IpcMainEvent) => {
    if (_event.senderFrame === window.webContents.mainFrame) {
      closing = false;
      transport?.request("cancelClose").catch(error => send({ event: "failure", message: String(error) }));
    }
  };
  ipcMain.on("cad-embed-cancel-close", cancelClosing);
  window.on("closed", () => {
    clearInterval(closeTimer); screen.removeListener("display-metrics-changed", displayChanged);
    ipcMain.removeHandler("cad-embed"); ipcMain.removeListener("cad-embed-cancel-close", cancelClosing);
    // 正常路径在销毁 HWND 前已 detach；主进程崩溃由独立守护进程恢复。
    void transport?.stop().catch(() => {});
  });
}
