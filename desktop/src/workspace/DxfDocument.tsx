import { useEffect, useRef, useState } from "react";
import { Button, Spinner } from "@fluentui/react-components";
import { DxfViewer } from "dxf-viewer";
import fontUrl from "../assets/preview-font.ttf?url";
export default function DxfDocument({ content }: { content: string }) {
  const area = useRef<HTMLDivElement>(null),
    viewer = useRef<DxfViewer | null>(null);
  const [error, setError] = useState(""),
    [ready, setReady] = useState(false);
  useEffect(() => {
    if (!area.current) return;
    const url = URL.createObjectURL(
      new Blob([Uint8Array.from(atob(content), (c) => c.charCodeAt(0))], {
        type: "application/dxf",
      }),
    );
    const cad = new DxfViewer(area.current, { autoResize: true });
    cad.SetClearColor(0xffffff);
    viewer.current = cad;
    let active = true;
    cad
      .Load({
        url,
        fonts: [new URL(fontUrl, document.baseURI).href],
        workerFactory: () =>
          new Worker(new URL("./dxfWorker.ts", import.meta.url), {
            type: "module",
          }),
      })
      .then(() => {
        if (active) setReady(true);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
      cad.Destroy();
      URL.revokeObjectURL(url);
      viewer.current = null;
    };
  }, [content]);
  return (
    <div className="dxf-document" data-ready={ready}>
      <div className="toolbar">
        <span className="muted">DXF 平面预览</span>
        <span className="toolbar-space" />
        <Button
          disabled={!ready}
          onClick={() => {
            const v = viewer.current;
            const b = v?.GetBounds();
            const o = v?.GetOrigin();
            if (v && b && o)
              v.FitView(b.minX - o.x, b.maxX - o.x, b.minY - o.y, b.maxY - o.y);
          }}
        >
          适应窗口
        </Button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!ready && !error && <Spinner size="small" label="正在读取 DXF" />}
      <div className="dxf-canvas" ref={area} />
    </div>
  );
}
