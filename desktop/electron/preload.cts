import { contextBridge, ipcRenderer } from "electron";
contextBridge.exposeInMainWorld("gongke", {
  request: (method: string, params?: Record<string, unknown>) =>
    ipcRenderer.invoke("command", method, params),
  chooseProject: (create: boolean) =>
    ipcRenderer.invoke("choose-project", create),
  configure: (settings: Record<string, string>) =>
    ipcRenderer.invoke("configure-agent", settings),
  settings: () => ipcRenderer.invoke("agent-settings"),
  restart: () => ipcRenderer.invoke("restart-service"),
  reveal: (path: string) => ipcRenderer.invoke("reveal", path),
  onEvent: (callback: (event: unknown) => void) => {
    const listener = (_event: unknown, value: unknown) => callback(value);
    ipcRenderer.on("service-event", listener);
    return () => ipcRenderer.removeListener("service-event", listener);
  },
});

// 窗口托管与工程命令分别暴露；renderer 无法提交可执行路径或任意 Win32 消息。
contextBridge.exposeInMainWorld("cadEmbed", {
  supported: process.platform === "win32",
  status: () => ipcRenderer.invoke("cad-embed", "status"),
  discover: () => ipcRenderer.invoke("cad-embed", "discover"),
  chooseInstallation: () => ipcRenderer.invoke("cad-embed", "chooseInstallation"),
  launch: (id: string) => ipcRenderer.invoke("cad-embed", "launch", { id }),
  attach: (hwnd: string, pid: number, mode: string) => ipcRenderer.invoke("cad-embed", "attach", { hwnd, pid, mode }),
  layout: (bounds: unknown) => ipcRenderer.invoke("cad-embed", "layout", bounds),
  focus: () => ipcRenderer.invoke("cad-embed", "focus"),
  detach: () => ipcRenderer.invoke("cad-embed", "detach"),
  closeCad: () => ipcRenderer.invoke("cad-embed", "closeCad"),
  diagnose: () => ipcRenderer.invoke("cad-embed", "diagnose"),
  cancelClose: () => ipcRenderer.send("cad-embed-cancel-close"),
  onEvent: (callback: (event: unknown) => void) => {
    const listener = (_event: unknown, value: unknown) => callback(value);
    ipcRenderer.on("cad-embed-event", listener);
    return () => ipcRenderer.removeListener("cad-embed-event", listener);
  },
});
