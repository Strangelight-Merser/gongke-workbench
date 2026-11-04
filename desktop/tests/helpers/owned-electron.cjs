// 验收仅持有自己启动的 Electron；正常、异常、信号和超时共用收尾。
const { _electron } = require("playwright");
const children = new Set();
function terminate(child) {
  if (child.exitCode === null && child.signalCode === null) child.kill("SIGTERM");
}
for (const signal of ["SIGINT", "SIGTERM"]) process.once(signal, async () => {
  await Promise.allSettled([...children].map(app => app.close()));
  process.exit(signal === "SIGINT" ? 130 : 143);
});
process.on("exit", () => { for (const app of children) terminate(app.process()); });
exports.electron = {
  async launch(options) {
    const app = await _electron.launch(options);
    children.add(app);
    const child = app.process();
    const originalClose = app.close.bind(app);
    let closing;
    app.close = () => closing ||= (async () => {
      let timer;
      try {
        await Promise.race([originalClose(), new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error("Electron 验收关闭超时")), 8000);
        })]);
      } finally {
        clearTimeout(timer);
        if (child.exitCode === null && child.signalCode === null) {
          terminate(child);
          await new Promise(resolve => {
            const kill = setTimeout(() => child.kill("SIGKILL"), 3000);
            child.once("exit", () => { clearTimeout(kill); resolve(); });
          });
        }
        children.delete(app);
      }
    })();
    try {
      if (process.env.GONGKE_TEST_WINDOW_WIDTH) {
        const width = Number(process.env.GONGKE_TEST_WINDOW_WIDTH);
        const page = await app.firstWindow();
        await app.evaluate(({ BrowserWindow }, width) => {
          BrowserWindow.getAllWindows()[0].setContentSize(width, 768);
        }, width);
        await page.waitForFunction(width => innerWidth === width, width);
      }
      return app;
    } catch (error) {
      await app.close();
      throw error;
    }
  }
};
