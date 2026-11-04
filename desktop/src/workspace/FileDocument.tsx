import { useEffect, useState, lazy, Suspense } from "react";
import { FolderOpenRegular, CubeRegular } from "@fluentui/react-icons";
import { Button, Spinner } from "@fluentui/react-components";
import { Project, ProjectFile, revisionOf } from "../project/types";
import { DrawingViewer } from "./DrawingViewer";
import { Empty } from "../ui/Empty";
import { Data } from "../api";
import { useDxfImport } from "../operations/useDxfImport";
import { DataDetails } from "../ui/DataDetails";
const PdfDocument = lazy(() => import("./PdfDocument"));
const DxfDocument = lazy(() => import("./DxfDocument"));
export function FileDocument({
  file,
  project,
  run,
  openCad,
  hosts,
  refresh,
  openAutoCad,
}: {
  file: ProjectFile;
  project: Project;
  run: any;
  openCad(): void;
  hosts: Data[];
  refresh(): Promise<void>;
  openAutoCad(): void;
}) {
  const importDxf = useDxfImport(file, hosts, run, refresh, openAutoCad);
  const [data, setData] = useState<{
    content: string;
    mime: string;
    value?: unknown;
  } | null>(null);
  const [error, setError] = useState("");
  const previewable =
    /^(pdf|png|jpg|jpeg|webp|svg|dxf|txt|md|json|yaml|yml)$/i.test(file.kind);
  useEffect(() => {
    if (!previewable) return;
    let active = true;
    window.gongke.documents
      .read(file.path)
      .then((d) => {
        const value =
          file.kind === "json"
            ? JSON.parse(
                new TextDecoder().decode(
                  Uint8Array.from(atob(d.content), (c) => c.charCodeAt(0)),
                ),
              )
            : undefined;
        if (active) setData({ ...d, value });
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [file.path]);
  const revision = revisionOf(project, file);
  return (
    <div className="file-document">
      <div className="toolbar">
        <span className="file-path" title={file.path}>
          {file.name}
        </span>
        {revision && (
          <span className={!revision.current ? "warn" : "muted"}>
            {revision.current ? "当前成果" : "已过期 · 历史成果"}
          </span>
        )}
        <span className="toolbar-space" />
        <Button
          icon={<FolderOpenRegular />}
          aria-label="在文件夹中显示"
          title="在文件夹中显示"
          onClick={() => run("定位文件", () => window.gongke.reveal(file.path))}
        >
          <span className="file-action-label">在文件夹中显示</span>
        </Button>
        {file.kind === "dxf" &&
          hosts.some((h) => h.host === "autocad" && h.connected) && (
            <Button onClick={importDxf}>导入 AutoCAD 工作修订</Button>
          )}
        <Button
          icon={<CubeRegular />}
          aria-label="进入建模"
          title="进入建模"
          onClick={openCad}
        >
          <span className="file-action-label">进入建模</span>
        </Button>
      </div>
      {error ? (
        <Empty title="无法预览图纸" body={error} />
      ) : !previewable ? (
        <Empty
          title={file.name}
          body="在原生软件中打开此文件，保留其可编辑内容。"
          action="进入 CAD"
          onAction={openCad}
        />
      ) : !data ? (
        <Spinner label="正在读取图纸" />
      ) : (
        <Suspense fallback={<Spinner label="正在打开预览" />}>
          {file.kind === "pdf" ? (
            <PdfDocument content={data.content} />
          ) : file.kind === "dxf" ? (
            <DxfDocument content={data.content} />
          ) : data.mime.startsWith("image/") ? (
            <DrawingViewer src={`data:${data.mime};base64,${data.content}`} />
          ) : file.kind === "json" ? (
            <div className="scroll document-content">
              <DataDetails value={data.value} />
            </div>
          ) : (
            <pre className="text-document">
              {new TextDecoder().decode(
                Uint8Array.from(atob(data.content), (c) => c.charCodeAt(0)),
              )}
            </pre>
          )}
        </Suspense>
      )}
    </div>
  );
}
