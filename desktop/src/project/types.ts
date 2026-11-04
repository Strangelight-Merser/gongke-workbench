import type { Data } from "../api";
export type ProjectFile = {
  path: string;
  name: string;
  kind: string;
  size?: number;
};
export type Generation = { path: string; current: boolean; status: string };
export type Project = {
  path: string;
  name: string;
  files: ProjectFile[];
  task?: Data;
  teaching?: boolean;
  generations?: Generation[];
  delivery?: Data;
  working_copies?: Data[];
};
export type DocumentRef = {
  id: string;
  title: string;
  type: "home" | "cad" | "file" | "reducer";
  file?: ProjectFile;
  preview?: boolean;
};
export const homeDocument: DocumentRef = {
  id: "home",
  title: "开始",
  type: "home",
};
export const cadDocument: DocumentRef = {
  id: "cad",
  title: "模型",
  type: "cad",
};
export function fileGroup(file: ProjectFile): string {
  if (/^(fcstd|sldprt|sldasm|step|stp|iges|igs|brep)$/i.test(file.kind))
    return "模型";
  if (/report\.(md|docx|pdf)$/i.test(file.name)) return "报告";
  if (
    file.path.startsWith("revisions/") &&
    /^(pdf|svg|dxf|dwg|slddrw)$/i.test(file.kind)
  )
    return "出图";
  if (/^(pdf|png|jpg|jpeg|webp|svg|dxf|dwg|slddrw)$/i.test(file.kind))
    return "图纸";
  return "其他文件";
}
export function revisionOf(project: Project, file: ProjectFile) {
  return project.generations?.find((g) => file.path.startsWith(g.path + "/"));
}
export function openDocument(documents: DocumentRef[], document: DocumentRef) {
  return documents.some((d) => d.id === document.id)
    ? documents
    : [...documents, document];
}
