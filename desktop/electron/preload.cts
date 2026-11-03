import { contextBridge, ipcRenderer } from "electron";
contextBridge.exposeInMainWorld("gongke", {
  platform: process.platform,
  documents: {
    import: () => ipcRenderer.invoke("documents-import"),
    read: (path: string) => ipcRenderer.invoke("documents-read", path),
  },
  getAgentMode: () => ipcRenderer.invoke("agent-mode-current"),
  setAgentMode: (mode: string) => ipcRenderer.invoke("agent-mode", mode),
  onboarding: {
    state: () => ipcRenderer.invoke("acp-onboarding-state"),
    act: (action: unknown) =>
      ipcRenderer.invoke("acp-onboarding-action", action),
    onState: (callback: (state: unknown) => void) => {
      const listener = (_event: unknown, state: unknown) => callback(state);
      ipcRenderer.on("onboarding-state", listener);
      return () => ipcRenderer.removeListener("onboarding-state", listener);
    },
  },
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

// 窗口托管与工程命令分别暴露；renderer 无法提交可执行路径或任意 Win32 消息。
contextBridge.exposeInMainWorld("cadEmbed", {
  supported: process.platform === "win32",
  status: () => ipcRenderer.invoke("cad-embed", "status"),
  discover: () => ipcRenderer.invoke("cad-embed", "discover"),
  chooseInstallation: () =>
    ipcRenderer.invoke("cad-embed", "chooseInstallation"),
  launch: (id: string) => ipcRenderer.invoke("cad-embed", "launch", { id }),
  attach: (hwnd: string, pid: number, mode: string) =>
    ipcRenderer.invoke("cad-embed", "attach", { hwnd, pid, mode }),
  layout: (bounds: unknown) =>
    ipcRenderer.invoke("cad-embed", "layout", bounds),
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
