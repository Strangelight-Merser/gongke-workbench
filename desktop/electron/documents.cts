import { realpath, readFile, mkdir, copyFile, stat } from "node:fs/promises";
import { constants } from "node:fs";
import {
  resolve,
  relative,
  isAbsolute,
  extname,
  basename,
  join,
} from "node:path";
import { randomUUID } from "node:crypto";
const formats: Record<string, string> = {
  pdf: "application/pdf",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  svg: "image/svg+xml",
  dxf: "application/dxf",
  txt: "text/plain",
  md: "text/plain",
  json: "application/json",
  yaml: "text/plain",
  yml: "text/plain",
};
export async function readDocument(root: string, path: string) {
  if (!root) throw new Error("请先打开工程");
  const target = await realpath(resolve(root, path));
  const rel = relative(await realpath(root), target);
  if (rel.startsWith("..") || isAbsolute(rel))
    throw new Error("文件不属于当前工程");
  const kind = extname(target).slice(1).toLowerCase(),
    mime = formats[kind];
  if (!mime) throw new Error("此格式请在原生软件中打开");
  const content = await readFile(target);
  return { mime, content: content.toString("base64") };
}
/** 图片内容由主进程从当前工程读取，renderer 只提交相对路径。 */
export async function readPromptImages(root: string, paths: string[]) {
  return Promise.all(
    paths.map(async (path) => {
      if (!/\.(png|jpe?g|webp)$/i.test(path))
        throw new Error("Agent 图片附件支持 PNG、JPEG、WebP");
      const image = await readDocument(root, path);
      return { path, mimeType: image.mime, data: image.content };
    }),
  );
}
export async function importDocuments(root: string, sources: string[]) {
  if (!root) throw new Error("请先打开工程");
  const files = [];
  const canonicalRoot = await realpath(root);
  for (const source of sources) {
    const target = await realpath(source),
      kind = extname(target).slice(1).toLowerCase();
    if (!["pdf", "png", "jpg", "jpeg", "webp", "svg", "dxf", "json", "txt"].includes(kind))
      throw new Error("请选择 PDF、图片、DXF 图纸或 JSON/TXT 尺寸说明");
    let rel = relative(canonicalRoot, target);
    if (rel.startsWith("..") || isAbsolute(rel)) {
      // 独立目录保留用户文件名，不覆盖同名图纸或原件。
      const inputs = join(canonicalRoot, "inputs");
      await mkdir(inputs, { recursive: true });
      const canonicalInputs = await realpath(inputs);
      const inside = relative(canonicalRoot, canonicalInputs);
      if (inside.startsWith("..") || isAbsolute(inside))
        throw new Error("图纸目录不属于当前工程");
      const directory = join(canonicalInputs, randomUUID().slice(0, 12));
      await mkdir(directory);
      const dest = join(directory, basename(target));
      await copyFile(target, dest, constants.COPYFILE_EXCL);
      rel = relative(canonicalRoot, dest);
    }
    files.push({
      path: rel.replaceAll("\\", "/"),
      name: basename(target),
      kind,
      size: (await stat(target)).size,
    });
  }
  return files;
}
