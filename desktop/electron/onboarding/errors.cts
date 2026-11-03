export function agentError(error: unknown): string {
  const value = error as { message?: string; data?: { details?: string } };
  const text = `${value?.message || error} ${value?.data?.details || ""}`;
  if (
    /\b401\b|Key 无效|invalid.?api.?key|authentication.?fail|unauthorized/i.test(
      text,
    )
  )
    return "API Key 无效。打开 dsh → Settings → Models → DeepSeek 更新 Key，再重新连接。";
  if (/\b402\b|余额不足|insufficient.?balance|insufficient.?quota/i.test(text))
    return "API 余额不足。前往 DeepSeek 充值，到账后重试首次对话。";
  if (/\b429\b|请求过于频繁|rate.?limit/i.test(text))
    return "请求过于频繁，请稍后重试首次对话。";
  if (/\b50[0234]\b|暂时不可用|overloaded/i.test(text))
    return "模型服务暂时不可用，请稍后重试。";
  if (
    /尚未配置 API Key|api.?key.*(?:missing|required|not.*(?:set|found|configured))|no.*api.?key|未.*密钥/i.test(
      text,
    )
  )
    return "尚未配置 API Key。打开 dsh → Settings → Models → DeepSeek 填写并保存，再重新连接。";
  if (/网络连接失败|timeout|fetch failed|network|ECONN|ENOTFOUND/i.test(text))
    return "网络连接失败或超时。请检查网络，重新连接后重试。";
  // 协议错误可能带上游请求头/凭据；不把原始异常放进状态、磁盘或 renderer。
  return "Agent 启动或对话失败。请检查安装位置、在 dsh 确认模型与 Key 已配置，再重新连接；工程工具失败请确认当前工程仍然打开。";
}
