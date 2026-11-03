import { contextBridge, ipcRenderer } from "electron";
contextBridge.exposeInMainWorld("gongke", {
  agent: {
    settings: () => ipcRenderer.invoke("acp-settings"),
    saveSettings: (settings: unknown) =>
      ipcRenderer.invoke("acp-save-settings", settings),
    state: () => ipcRenderer.invoke("acp-state"),
    start: (id: string) => ipcRenderer.invoke("acp-start", id),
    authenticate: (id: string) => ipcRenderer.invoke("acp-authenticate", id),
    newSession: () => ipcRenderer.invoke("acp-new-session"),
    prompt: (text: string) => ipcRenderer.invoke("acp-prompt", text),
    cancel: () => ipcRenderer.invoke("acp-cancel"),
    disconnect: () => ipcRenderer.invoke("acp-disconnect"),
    permission: (id: string, optionId: string | null) =>
      ipcRenderer.invoke("acp-permission", id, optionId),
    onState: (callback: (state: unknown) => void) => {
      const listener = (_event: unknown, state: unknown) => callback(state);
      ipcRenderer.on("acp-state", listener);
      return () => ipcRenderer.removeListener("acp-state", listener);
    },
  },
  request: (method: string, params?: Record<string, unknown>) =>
    ipcRenderer.invoke("command", method, params),
  chooseProject: (create: boolean) =>
    ipcRenderer.invoke("choose-project", create),
  restart: () => ipcRenderer.invoke("restart-service"),
  reveal: (path: string) => ipcRenderer.invoke("reveal", path),
  onEvent: (callback: (event: unknown) => void) => {
    const listener = (_event: unknown, value: unknown) => callback(value);
    ipcRenderer.on("service-event", listener);
    return () => ipcRenderer.removeListener("service-event", listener);
  },
});
