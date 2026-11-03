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
export async function importDocuments(root: string, sources: string[]) {
  if (!root) throw new Error("请先打开工程");
  const files = [];
  const canonicalRoot = await realpath(root);
  for (const source of sources) {
    const target = await realpath(source),
      kind = extname(target).slice(1).toLowerCase();
    if (!["pdf", "png", "jpg", "jpeg", "webp", "svg", "dxf"].includes(kind))
      throw new Error("请选择 PDF、图片或 DXF 图纸");
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
