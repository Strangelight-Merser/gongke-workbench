import type { Provider, Step } from "../../electron/onboarding/types.cjs";
export function guideProgress(provider: Provider, step: Step) {
  const labels =
    provider === "deepseek"
      ? ["检测 / 安装", "注册与充值", "在 dsh 填 Key", "连接并首次对话"]
      : ["检测 / 安装", "连接工程", "首次对话"];
  const index =
    provider === "deepseek"
      ? {
          detect: 0,
          install: 0,
          account: 1,
          credentials: 2,
          connect: 3,
          verify: 3,
          complete: 4,
        }[step]
      : {
          detect: 0,
          install: 0,
          account: 1,
          credentials: 1,
          connect: 1,
          verify: 2,
          complete: 3,
        }[step];
  return { labels, index };
}
// 控制器已将上游错误转换成这些明确的提示；一般错误不推断为密钥或余额问题。
export function recoveryFor(error: string) {
  return {
    key: /^(API Key 无效|尚未配置 API Key)/.test(error),
    balance: /^API 余额不足/.test(error),
  };
}
