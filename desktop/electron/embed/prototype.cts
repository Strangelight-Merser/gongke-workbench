import { app, BrowserWindow } from "electron";
import { join } from "node:path";
import { installCadEmbedding } from "./controller.cjs";

// 无 Python 服务/Agent 依赖；和产品共用同一套窗口代码。
app.setName("Gongke Embed Prototype");
app.whenReady().then(async () => {
  if (process.env.GONGKE_EMBED_TEST_DATA) app.setPath("userData", process.env.GONGKE_EMBED_TEST_DATA);
  const window = new BrowserWindow({ width: 1440, height: 960, title: "构想引擎 · CAD 嵌入原型", webPreferences: {
    preload: join(__dirname, "../preload.cjs"), sandbox: true, contextIsolation: true, nodeIntegration: false,
  } });
  installCadEmbedding(window);
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", event => event.preventDefault());
  await window.loadFile(join(__dirname, "../../native/embed/prototype.html"));
});
app.on("window-all-closed", () => app.quit());
