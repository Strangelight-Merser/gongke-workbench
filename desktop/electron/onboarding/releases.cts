import type { Release } from "./types.cjs";
// 2026-11-03 从官方源下载完整文件后固定。来源与复核方式见 desktop/ACP.md。
// 不在运行时读取 latest/feed；更新清单须重新下载、验收并提交。
export const releases: Release[] = [
  {
    provider: "deepseek",
    version: "0.2.1-rc.5",
    url: "https://download.deepseek.com/dsh-desk/bin/win-x64/deepseek-harness-0.2.1-rc.5-win-x64.exe",
    size: 289408544,
    sha512:
      "gu2dH+aTr678c0P8DGAH/h4B1GaWfQIjpsPrLjl/ukLrQIh6DLVq/MhX4FZvJ8o1GCMocOhix6XbLa6KmtjXXg==",
    signerThumbprint: "84032578657219876E273E0D1BD303CFE1B82E6F",
  },
  {
    provider: "workbuddy",
    version: "5.9.3",
    url: "https://acc-1258344699.cos.ap-guangzhou.myqcloud.com/workbuddy/saas/win32-x64-user/WorkBuddy-win32-x64-user-5.9.3.42398134-d4692421.exe",
    size: 450174440,
    sha512:
      "xFkEczgJjx5F5yyF9bUgHKbydwbeshaULAKWbPeJ6dNnD8g+/LWuxb3KQyktnIIaBmN2ud/AEXJUu8o7JLKY4A==",
    signerThumbprint: "2BC94A2110F6F412AB416D53EB755664D320590C",
  },
];
