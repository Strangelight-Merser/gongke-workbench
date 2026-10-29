export function normalizeProvider(value: string) {
  const url = new URL(value);
  if (
    !["https:", "http:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw new Error("请输入不含账号、查询参数的 HTTP(S) 服务地址");
  return url.href.replace(/\/$/, "");
}
export function mayReuseKey(previous: string | undefined, next: string) {
  return !!previous && normalizeProvider(previous) === normalizeProvider(next);
}
