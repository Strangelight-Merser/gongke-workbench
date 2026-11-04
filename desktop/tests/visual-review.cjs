// npm run build && node tests/visual-review.cjs [输出目录]
// 本脚本隔离 Electron userData；生产界面 + 明确标记的模拟服务/CAD，仅供视觉评审。
const { electron } = require("./helpers/owned-electron.cjs");
const fs = require("node:fs"),
  path = require("node:path"),
  os = require("node:os"),
  assert = require("node:assert/strict");
const output = path.resolve(
  process.argv[2] ||
    path.join(os.tmpdir(), "gongke-visual-review-" + Date.now()),
);
fs.mkdirSync(output, { recursive: true });
const cases = [
  "empty",
  "drawing-pdf",
  "drawing-image",
  "drawing-dxf",
  "modeling",
  "checks",
  "onboarding",
  "dark",
];
const { recordCase } = require("./visual-runner.cjs");
const { inspectContrast } = require("./visual-contrast.cjs");
const contrastRecords = [];
const records = [],
  interactionChecks = [];
(async () => {
  for (const size of [
    { width: 1366, height: 768 },
    { width: 1920, height: 1080 },
  ]) {
    const env = {
      ...process.env,
      GONGKE_VISUAL_USER_DATA: fs.mkdtempSync(
        path.join(os.tmpdir(), "gongke-visual-user-"),
      ),
    };
    delete env.ELECTRON_RUN_AS_NODE;
    let app;
    const errors = [];
    try {
      app = await electron.launch({
        args: [path.join(__dirname, "fixtures/workbench-main.cjs")],
        env,
        timeout: 60000,
      });
      const page = await app.firstWindow();
      page.on("pageerror", (e) => errors.push(String(e)));
      page.setDefaultTimeout(20000);
      await app.evaluate(
        ({ BrowserWindow }, s) =>
          BrowserWindow.getAllWindows()[0].setContentSize(s.width, s.height),
        size,
      );
      for (const name of cases) {
        records.push(
          await recordCase({
            page,
            output,
            name,
            size,
            run: async () => {
              await page.reload();
              await page
                .getByRole("heading", { name: "支架建模练习", exact: true })
                .waitFor();
              await page.evaluate(
                (name) => window.visualReview.setScenario(name),
                name,
              );
              if (name.startsWith("drawing-") || name === "dark") {
                const file =
                  name === "drawing-dxf"
                    ? "支架图纸.dxf"
                    : name === "drawing-image"
                      ? "支架图纸.svg"
                      : "支架图纸.pdf";
                await page
                  .getByRole("treeitem")
                  .filter({ has: page.getByText(file, { exact: true }) })
                  .last()
                  .click();
                if (file.endsWith(".pdf")) {
                  await page.locator(".pdf-pages canvas").waitFor();
                  await page.waitForFunction(() => {
                    const c = document.querySelector(".pdf-pages canvas");
                    return c && c.width > 0;
                  });
                  await page
                    .getByRole("button", { name: "适应宽度", exact: true })
                    .click();
                  await page
                    .locator('.pdf-document[data-render-state="ready"]')
                    .waitFor();
                  await page
                    .locator(".pdf-pages .fui-Spinner")
                    .waitFor({ state: "hidden" });
                } else if (file.endsWith(".dxf")) {
                  await page.locator(".dxf-canvas canvas").waitFor();
                  await page
                    .getByRole("button", { name: "适应宽度", exact: true })
                    .waitFor();
                  await page
                    .locator(".dxf-document[data-ready=true]")
                    .waitFor();
                } else {
                  await page.locator("img.drawing").waitFor();
                  await page.waitForFunction(
                    () =>
                      document.querySelector("img.drawing")?.naturalWidth > 0,
                  );
                }
              }
              if (name === "onboarding") {
                // 已配置 Agent 走真实菜单；切换面板不能伪造引导完成。
                await page
                  .getByRole("button", { name: "Agent 连接设置", exact: true })
                  .click();
                await page
                  .getByRole("menuitem", {
                    name: "使用已配置的 Agent",
                    exact: true,
                  })
                  .click();
                await page
                  .getByRole("button", { name: "连接", exact: true })
                  .waitFor();
                assert.equal(
                  await page.locator(".agent-onboarding:visible").count(),
                  0,
                );
                assert.equal(
                  (await page.evaluate(() => window.gongke.onboarding.state()))
                    .agents.deepseek.step,
                  "credentials",
                );
                await page
                  .getByRole("button", { name: "Agent 连接设置", exact: true })
                  .click();
                await page
                  .getByRole("menuitem", {
                    name: "安装与连接引导",
                    exact: true,
                  })
                  .click();
                await page
                  .getByRole("button", { name: "打开 dsh", exact: true })
                  .waitFor();
                assert.equal(await page.locator(".compose:visible").count(), 0);
              }
              if (name === "modeling") {
                assert.equal(
                  await page
                    .getByText("模型保存状态未同步", { exact: true })
                    .count(),
                  0,
                );
                // prompting 状态会自动打开模型页，开始页按钮已卸载。
                await page
                  .getByRole("tab", { name: "模型", exact: true })
                  .waitFor();
                await page
                  .getByRole("button", { name: "返回 CAD 编辑", exact: true })
                  .click();
                await page.locator(".cad-surface").waitFor();
                await page
                  .getByRole("button", { name: "进入 CAD", exact: true })
                  .waitFor();
                // 原生 HWND 不在 Chromium 截图里；此区域明确使用布局占位，绝不冒充 CAD 实测。
                await page.locator(".cad-surface").evaluate((el) => {
                  el.innerHTML =
                    '<div style="text-align:center;color:#616161"><svg width="360" height="280" viewBox="0 0 360 280"><g fill="#a8b6c4" stroke="#566577" stroke-width="2"><path d="M70 190 L200 240 L300 175 L170 130 Z"/><path d="M70 190 L70 65 L110 40 L110 165 Z"/><path d="M70 65 L200 115 L240 90 L110 40 Z"/><path d="M70 65 L200 115 L200 240 L70 190 Z"/><ellipse cx="130" cy="130" rx="18" ry="24" fill="#eef0f3"/></g></svg><p>CAD 区域占位 · 仅用于布局评审</p></div>';
                });
              }
              if (name === "checks")
                await page
                  .getByRole("navigation", { name: "活动栏" })
                  .getByRole("button", { name: "问题", exact: true })
                  .click();
              if (name === "dark")
                await page
                  .getByRole("button", { name: "切换深色主题", exact: true })
                  .click();
              if (name === "onboarding") {
                await page
                  .locator('.agent-panel[data-onboarding="true"]')
                  .waitFor();
                await page
                  .getByRole("button", { name: "打开 dsh", exact: true })
                  .waitFor();
                assert.equal(
                  await page.locator(".agent-welcome:visible").count(),
                  0,
                );
                assert.equal(await page.locator(".compose:visible").count(), 0);
                assert.equal(
                  await page
                    .locator(".onboarding-primary-action:visible")
                    .count(),
                  1,
                );
                assert.deepEqual(
                  await page.locator(".onboarding-steps li").allTextContents(),
                  [
                    "1检测 / 安装",
                    "2注册与充值",
                    "3在 dsh 填 Key",
                    "4连接并首次对话",
                  ],
                );
                assert.equal(
                  await page
                    .getByRole("button", { name: "去充值", exact: true })
                    .count(),
                  0,
                );
                assert.equal(
                  await page
                    .getByRole("button", {
                      name: "去 dsh 更新 Key",
                      exact: true,
                    })
                    .count(),
                  0,
                );
              }
              if (name === "onboarding") {
                // 已配置 Agent 走真实菜单；切换面板不能伪造引导完成。
                await page
                  .getByRole("button", { name: "Agent 连接设置", exact: true })
                  .click();
                await page
                  .getByRole("menuitem", {
                    name: "使用已配置的 Agent",
                    exact: true,
                  })
                  .click();
                await page
                  .getByRole("button", { name: "连接", exact: true })
                  .waitFor();
                assert.equal(
                  await page.locator(".agent-onboarding:visible").count(),
                  0,
                );
                assert.equal(
                  (await page.evaluate(() => window.gongke.onboarding.state()))
                    .agents.deepseek.step,
                  "credentials",
                );
                await page
                  .getByRole("button", { name: "Agent 连接设置", exact: true })
                  .click();
                await page
                  .getByRole("menuitem", {
                    name: "安装与连接引导",
                    exact: true,
                  })
                  .click();
                await page
                  .getByRole("button", { name: "打开 dsh", exact: true })
                  .waitFor();
                assert.equal(await page.locator(".compose:visible").count(), 0);
              }
              if (name === "modeling") {
                assert.equal(
                  await page
                    .getByText("模型保存状态未同步", { exact: true })
                    .count(),
                  0,
                );
                assert.equal(
                  await page.locator(".cad-workspace > .toolbar").count(),
                  1,
                );
                assert.equal(
                  await page
                    .getByRole("button", { name: "保存诊断", exact: true })
                    .count(),
                  0,
                );
              }
              if (name === "checks") {
                assert.deepEqual(
                  await page.locator(".checks-table th").allTextContents(),
                  ["检查项", "图纸要求", "模型实测", "偏差", "结论", "操作"],
                );
                assert.match(
                  await page
                    .locator(".checks-table tbody tr")
                    .first()
                    .innerText(),
                  /12 mm[\s\S]*10 mm[\s\S]*-2 mm/,
                );
              }
              if (name === "dark") {
                await page.waitForFunction(
                  () =>
                    getComputedStyle(document.querySelector(".workbench"))
                      .getPropertyValue("--colorNeutralForeground1")
                      .trim() === "#ffffff",
                );
                for (const label of [
                  "新建工程",
                  "打开工程",
                  "导入图纸",
                  "新建模型",
                  "Agent 操作",
                  "新会话",
                  "问题",
                  "操作记录",
                ]) {
                  const menuAction = ["新建工程", "打开工程"].includes(label);
                  if (menuAction)
                    await page
                      .getByRole("button", { name: "工程操作", exact: true })
                      .click();
                  const button = menuAction
                    ? page.getByRole("menuitem", { name: label, exact: true })
                    : ["问题", "操作记录"].includes(label)
                      ? page
                          .getByRole("navigation", { name: "活动栏" })
                          .getByRole("button", { name: label, exact: true })
                      : ["新建模型", "导入图纸"].includes(label)
                        ? page
                            .getByLabel("工程树", { exact: true })
                            .getByRole("button", { name: label, exact: true })
                        : page.getByRole("button", {
                            name: label,
                            exact: true,
                          });
                  assert.equal(
                    await button.isEnabled(),
                    true,
                    label + " 应可用",
                  );
                  const colors = await button.evaluate(inspectContrast);
                  contrastRecords.push({ ...size, label, ...colors });
                  assert.ok(
                    colors.ratio >= 4.5,
                    `${label} 对比度 ${colors.ratio.toFixed(2)}:1 不足`,
                  );
                  await button.hover();
                  const hovered = await button.evaluate(inspectContrast);
                  contrastRecords.push({
                    ...size,
                    label: label + " 悬停",
                    ...hovered,
                  });
                  assert.ok(hovered.ratio >= 4.5, `${label} 悬停对比度不足`);
                  const icon = button.locator("svg").first();
                  if (await icon.count()) {
                    const iconColors = await icon.evaluate(inspectContrast);
                    contrastRecords.push({
                      ...size,
                      label: label + " 图标",
                      ...iconColors,
                    });
                    assert.ok(
                      iconColors.ratio >= 4.5,
                      `${label} 图标对比度不足`,
                    );
                  }
                  if (menuAction) await page.keyboard.press("Escape");
                }
                await page.mouse.move(20, 70);
                const enabled = await page
                  .getByRole("button", { name: "新会话", exact: true })
                  .evaluate(inspectContrast);
                const disabled = await page
                  .getByRole("button", { name: "发送", exact: true })
                  .evaluate(inspectContrast);
                assert.equal(disabled.disabled, true);
                assert.notDeepEqual(
                  enabled.foreground,
                  disabled.foreground,
                  "启用与禁用前景必须区分",
                );
              }
              assert.equal(
                await page.locator(".file-document [role=alert]").count(),
                0,
                "预览不能以错误状态通过",
              );
              await page.evaluate(() => document.fonts.ready);
              assert.equal(
                await page
                  .locator("body")
                  .evaluate((el) => el.scrollWidth > el.clientWidth),
                false,
                "页面不得横向溢出",
              );
            },
          }),
        );
      }
      interactionChecks.push(
        await recordCase({
          page,
          output,
          name: "interactions",
          size,
          screenshotOnSuccess: false,
          run: async () => {
            // 交互检查独立初始化，不依赖最后一个截图场景是否成功。
            await page.reload();
            await page
              .getByRole("heading", { name: "支架建模练习", exact: true })
              .waitFor();
            await page.evaluate(() =>
              window.visualReview.setScenario("drawing-pdf"),
            );
            await page
              .getByLabel("工程树", { exact: true })
              .getByText("支架图纸.pdf", { exact: true })
              .dblclick();
            await page
              .locator('.pdf-document[data-render-state="ready"]')
              .waitFor();
            await page
              .getByRole("button", { name: "放大 PDF", exact: true })
              .click();
            await page
              .locator('.pdf-document[data-render-state="ready"]')
              .waitFor();
            assert.equal(
              await page.locator(".pdf-pages .fui-Spinner").count(),
              0,
              "缩放后必须结束渲染状态",
            );
            // 切页及折叠不能丢输入；分隔条支持键盘，布局落盘。
            await page
              .getByLabel("工程任务", { exact: true })
              .fill("检查安装孔，不要改变立板厚度");
            await page
              .getByRole("button", { name: "收起 Agent", exact: true })
              .click();
            await page
              .getByRole("button", { name: "展开 Agent", exact: true })
              .click();
            assert.equal(
              await page.getByLabel("工程任务", { exact: true }).inputValue(),
              "检查安装孔，不要改变立板厚度",
            );
            await page
              .getByLabel("工程树", { exact: true })
              .getByText("支架图纸.svg", { exact: true })
              .dblclick();
            await page.waitForFunction(() => {
              const img = document.querySelector("img.drawing");
              return img?.naturalWidth && img.style.visibility !== "hidden";
            });
            await page
              .getByRole("button", { name: "放大", exact: true })
              .click();
            const imageStyle = await page
              .locator("img.drawing")
              .getAttribute("style");
            await page
              .getByRole("tab", { name: "支架图纸.pdf", exact: true })
              .click();
            await page
              .getByRole("tab", { name: "支架图纸.svg", exact: true })
              .click();
            assert.equal(
              await page.locator("img.drawing").getAttribute("style"),
              imageStyle,
              "切页保持图纸视角",
            );
            await page
              .getByRole("button", { name: "关闭 支架图纸.svg", exact: true })
              .click();
            await page
              .getByLabel("工程树", { exact: true })
              .getByText("支架图纸.svg", { exact: true })
              .dblclick();
            assert.equal(
              await page.locator("img.drawing").getAttribute("style"),
              imageStyle,
              "重新打开保持图纸视角",
            );
            assert.equal(
              await page.getByLabel("工程任务", { exact: true }).inputValue(),
              "检查安装孔，不要改变立板厚度",
            );
            await page.evaluate(() =>
              window.visualReview.setScenario("checks"),
            );
            await page
              .getByRole("navigation", { name: "活动栏" })
              .getByRole("button", { name: "问题", exact: true })
              .click();
            await page
              .getByRole("button", { name: "定位 安装孔直径", exact: true })
              .click();
            await page
              .getByRole("tab", { name: "模型", exact: true })
              .waitFor();
            await page.waitForFunction(
              () => window.visualReview.selections().length === 1,
            );
            const selected = await page.evaluate(
              () => window.visualReview.selections()[0],
            );
            assert.deepEqual(selected, {
              session_id: "fixture-session",
              object_name: "Hole002",
              expected_revision: 4,
            });
            const divider = page.getByRole("separator", {
              name: "Agent 面板宽度",
            });
            await divider.focus();
            await page.keyboard.press("ArrowLeft");
            assert.equal(await divider.getAttribute("aria-valuenow"), "368");
            assert.equal(
              await page.evaluate(
                () => JSON.parse(localStorage.getItem("gongke.layout")).agent,
              ),
              368,
            );
            await page
              .getByRole("button", { name: "收起工程树", exact: true })
              .click();
            const central = await page.locator(".workspace-main").boundingBox();
            assert.ok(central.width > 640, "折叠树后中心文档仍占可用空间");
            await page
              .getByRole("button", { name: "展开工程树", exact: true })
              .click();
          },
        }),
      );
      assert.deepEqual(errors, [], "Electron 页面不能有未处理异常");
    } catch (e) {
      // 窗口级错误也进入汇总；下一尺寸仍会执行。
      interactionChecks.push({
        case: "window",
        ...size,
        status: "failed",
        error: String(e),
        errors,
      });
      for (const name of cases.filter(
        (name) =>
          !records.some((r) => r.width === size.width && r.case === name),
      )) {
        records.push({
          case: name,
          ...size,
          status: "failed",
          error: String(e),
          errors,
        });
      }
    } finally {
      if (app)
        await app.close().catch((e) =>
          interactionChecks.push({
            case: "window-close",
            ...size,
            status: "failed",
            error: String(e),
          }),
        );
    }
  }
  const failures = [...records, ...interactionChecks].filter(
    (r) => r.status === "failed",
  );
  const ok = records.length === 16 && failures.length === 0;
  fs.writeFileSync(
    path.join(output, "failure.json"),
    JSON.stringify(failures, null, 2),
  );
  fs.writeFileSync(
    path.join(output, "review.json"),
    JSON.stringify(
      {
        ok,
        records,
        interactionChecks,
        contrastRecords,
        checks: [
          "no horizontal overflow",
          "composer survives panel collapse",
          "keyboard resizing persists",
          "drawing view survives switching and reopening",
          "composer survives document switching",
        ],
        boundary: "模拟服务和 CAD 不证明宿主建模成功。请人工评审全部截图。",
      },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({
      ok,
      output,
      attempted: records.length,
      screenshots: records.filter((r) => r.file).length,
      failures: failures.length,
    }),
  );
  if (!ok) process.exitCode = 1;
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
