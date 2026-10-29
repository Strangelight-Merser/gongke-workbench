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
