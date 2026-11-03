const fs = require("node:fs");
const path = require("node:path");

// 每个场景单独收集错误、留图并返回；调用方始终可以继续下一个场景。
async function recordCase({
  page,
  output,
  name,
  size,
  run,
  screenshotOnSuccess = true,
}) {
  const errors = [];
  const onError = (error) => errors.push(String(error));
  page.on("pageerror", onError);
  const record = {
    case: name,
    ...size,
    status: "passed",
    evidence: "production renderer; simulated service and CAD",
  };
  try {
    await run();
    if (errors.length) throw new Error(errors.join("\n"));
  } catch (error) {
    record.status = "failed";
    record.error = String(error);
    record.stack = error.stack;
  }
  if (screenshotOnSuccess || record.status === "failed") {
    const file = `${size.width}x${size.height}-${name}${record.status === "failed" ? "-failure" : ""}.png`;
    try {
      await page.evaluate(() => {
        const footer = document.querySelector(".statusbar");
        if (!footer || footer.querySelector("[data-review-mark]")) return;
        const mark = document.createElement("span");
        mark.dataset.reviewMark = "true";
        mark.textContent = "界面评审样例 · 模拟工程数据";
        mark.style.cssText =
          "flex-shrink:0;color:var(--muted);padding:0 8px;border-left:1px solid var(--line)";
        footer.insertBefore(mark, footer.querySelector("button"));
      });
      await page.screenshot({ path: path.join(output, file) });
      record.file = file;
    } catch (error) {
      record.status = "failed";
      record.captureError = String(error);
    }
  }
  page.off("pageerror", onError);
  if (errors.length && record.status === "passed") {
    record.status = "failed";
    record.error = errors.join("\n");
  }
  record.errors = errors;
  if (record.status === "failed") {
    fs.writeFileSync(
      path.join(output, `${size.width}x${size.height}-${name}-failure.json`),
      JSON.stringify(record, null, 2),
    );
  }
  return record;
}
module.exports = { recordCase };
