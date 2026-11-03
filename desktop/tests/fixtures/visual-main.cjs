// 确定性界面审查宿主：只加载生产 renderer，不启动 Python、Agent 或 CAD。
const { app, BrowserWindow } = require("electron");
const path = require("node:path");
app.setPath("userData", process.env.GONGKE_VISUAL_USER_DATA);
app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1366,
    height: 768,
    useContentSize: true,
    show: true,
    title: "界面评审样例",
    webPreferences: {
      preload: path.join(__dirname, "visual-preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  await win.loadFile(path.resolve(__dirname, "../../dist/index.html"));
});
app.on("window-all-closed", () => app.quit());
