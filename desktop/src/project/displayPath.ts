/** 文档栏只显示工程相对路径；工程外文档显示文件名。原始路径仍供读写使用。 */
export function displayPath(path: string, root = "") {
  const file = path.replaceAll("\\", "/"),
    base = root.replaceAll("\\", "/").replace(/\/$/, "");
  const windows = /^[A-Za-z]:\//.test(file);
  const compare = (s: string) => (windows ? s.toLowerCase() : s);
  if (base && compare(file).startsWith(compare(base) + "/"))
    return file.slice(base.length + 1);
  return /^(\/|[A-Za-z]:\/)/.test(file) ? file.split("/").at(-1) || "" : file;
}
