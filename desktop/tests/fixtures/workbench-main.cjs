// 后台独立 Electron，避免占用其他验收会话的前台窗口。
const { app, BrowserWindow } = require("electron");
const path = require("node:path");
app.setPath("userData", process.env.GONGKE_VISUAL_USER_DATA);
app.whenReady().then(async () => {
  if (process.platform === "darwin") app.setActivationPolicy("prohibited");
  const win = new BrowserWindow({
    width: 1366,
    height: 768,
    useContentSize: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "visual-preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
    },
  });
  await win.loadFile(path.resolve(__dirname, "../../dist/index.html"));
});
app.on("window-all-closed", () => app.quit());
