import { useEffect, useRef, useState } from "react";
import { Button, Spinner } from "@fluentui/react-components";
import {
  ChevronLeftRegular,
  ChevronRightRegular,
  SubtractRegular,
  AddRegular,
} from "@fluentui/react-icons";
import {
  getDocument,
  GlobalWorkerOptions,
  PDFDocumentProxy,
  RenderTask,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
GlobalWorkerOptions.workerSrc = workerUrl;
export default function PdfDocument({ content }: { content: string }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy>();
  const [page, setPage] = useState(1);
  const [scale, setScale] = useState(1);
  const [error, setError] = useState("");
  const [rendered, setRendered] = useState<{
    pdf: PDFDocumentProxy;
    page: number;
    scale: number;
  }>();
  const [fitWidth, setFitWidth] = useState(true);
  const rendering =
    !error &&
    (!pdf ||
      rendered?.pdf !== pdf ||
      rendered?.page !== page ||
      rendered?.scale !== scale);
  const canvas = useRef<HTMLCanvasElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setPdf(undefined);
    setPage(1);
    setFitWidth(true);
    setError("");

    const task = getDocument({
      data: Uint8Array.from(atob(content), (c) => c.charCodeAt(0)),
      useSystemFonts: true,
    });
    let active = true;
    task.promise
      .then((p) => {
        if (active) setPdf(p);
      })
      .catch((e) => {
        if (active) {
          setError(String(e));
        }
      });
    return () => {
      active = false;
      void task.destroy();
    };
  }, [content]);
  useEffect(() => {
    if (!pdf || !viewport.current || !fitWidth) return;
    const container = viewport.current;
    let active = true;
    const fit = async () => {
      const width = container.clientWidth - 48;
      if (width <= 0) return;
      const p = await pdf.getPage(page);
      if (active) {
        setScale(width / p.getViewport({ scale: 1 }).width);
        container.scrollLeft = 0;
      }
    };
    const observer = new ResizeObserver(() => {
      void fit();
    });
    observer.observe(container);
    void fit();
    return () => {
      active = false;
      observer.disconnect();
    };
  }, [pdf, page, fitWidth]);
  useEffect(() => {
    if (!pdf || !canvas.current) return;
    let active = true,
      task: RenderTask | undefined;

    setError("");
    pdf
      .getPage(page)
      .then((p) => {
        if (!active) return;
        const v = p.getViewport({ scale });
        const el = canvas.current!;
        const ratio = devicePixelRatio || 1;
        el.width = Math.floor(v.width * ratio);
        el.height = Math.floor(v.height * ratio);
        el.style.width = `${v.width}px`;
        el.style.height = `${v.height}px`;
        task = p.render({
          canvas: el,
          viewport: v,
          transform: [ratio, 0, 0, ratio, 0, 0],
        });
        return task.promise;
      })
      .then(() => {
        if (active) setRendered({ pdf, page, scale });
      })
      .catch((e) => {
        if (active) {
          setError(String(e));
        }
      });
    return () => {
      active = false;
      task?.cancel();
    };
  }, [pdf, page, scale]);
  return (
    <div
      className="pdf-document"
      aria-busy={rendering}
      data-render-state={error ? "error" : rendering ? "rendering" : "ready"}
    >
      <div
        className="toolbar pdf-toolbar"
        role="group"
        aria-label="PDF 导航与缩放"
      >
        <Button
          size="small"
          appearance="subtle"
          icon={<ChevronLeftRegular />}
          aria-label="上一页"
          title="上一页"
          disabled={!pdf || page === 1}
          onClick={() => setPage((p) => p - 1)}
        />
        <span>
          {page} / {pdf?.numPages || "—"}
        </span>
        <Button
          size="small"
          appearance="subtle"
          icon={<ChevronRightRegular />}
          aria-label="下一页"
          title="下一页"
          disabled={!pdf || page === pdf.numPages}
          onClick={() => setPage((p) => p + 1)}
        />
        <span className="toolbar-space" />
        <Button
          size="small"
          appearance="subtle"
          icon={<SubtractRegular />}
          title="缩小 PDF"
          disabled={!pdf}
          aria-label="缩小 PDF"
          onClick={() => {
            setFitWidth(false);
            setScale((s) => Math.max(0.25, s - 0.25));
          }}
        />
        <span>{Math.round(scale * 100)}%</span>
        <Button
          size="small"
          appearance="subtle"
          icon={<AddRegular />}
          title="放大 PDF"
          disabled={!pdf}
          aria-label="放大 PDF"
          onClick={() => {
            setFitWidth(false);
            setScale((s) => Math.min(4, s + 0.25));
          }}
        />
        <Button size="small" disabled={!pdf} onClick={() => setFitWidth(true)}>
          适应宽度
        </Button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="pdf-pages" ref={viewport} aria-label="PDF 图纸">
        {rendering && <Spinner size="small" label="正在渲染" />}
        <canvas ref={canvas} />
      </div>
    </div>
  );
}
