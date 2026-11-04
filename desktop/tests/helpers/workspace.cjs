// 面板可由窄窗口布局自动折叠；通过用户入口展开，不绕过可见性检查。
exports.showProjectTree = async (page) => {
  const explorer = page
    .getByRole("navigation", { name: "活动栏" })
    .getByRole("button", { name: "资源管理器", exact: true });
  if ((await explorer.getAttribute("aria-pressed")) === "false")
    await explorer.click();
  await page
    .getByLabel("工程树", { exact: true })
    .waitFor({ state: "visible" });
};
