import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

type View = { scale: number; x: number; y: number };
const MIN = 0.05,
  MAX = 16;

// 图纸查看：滚轮以光标为中心缩放，拖动平移，双击适应窗口。
export function DrawingViewer({ svg }: { svg: string }) {
  const box = useRef<HTMLDivElement>(null),
    image = useRef<HTMLImageElement>(null),
    drag = useRef<{ x: number; y: number } | null>(null);
  const [view, setView] = useState<View | null>(null);
  const fit = useCallback(() => {
    const el = box.current,
      img = image.current;
    if (!el || !img?.naturalWidth) return;
    const pad = 24,
      scale = Math.min(
        (el.clientWidth - pad * 2) / img.naturalWidth,
        (el.clientHeight - pad * 2) / img.naturalHeight,
      );
    setView({
      scale,
      x: (el.clientWidth - img.naturalWidth * scale) / 2,
      y: (el.clientHeight - img.naturalHeight * scale) / 2,
    });
  }, []);
  const zoomAt = useCallback((factor: number, cx?: number, cy?: number) => {
    setView((v) => {
      const el = box.current;
      if (!v || !el) return v;
      const scale = Math.min(MAX, Math.max(MIN, v.scale * factor)),
        px = cx ?? el.clientWidth / 2,
        py = cy ?? el.clientHeight / 2,
        k = scale / v.scale;
      return { scale, x: px - (px - v.x) * k, y: py - (py - v.y) * k };
    });
  }, []);
  // 换图后重新适应；数据 URI 可能在挂载前就已解码完成，不能只依赖 onLoad。
  useLayoutEffect(() => {
    setView(null);
    if (image.current?.complete) fit();
  }, [svg, fit]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomAt(
        Math.exp(-e.deltaY * 0.0015),
        e.clientX - rect.left,
        e.clientY - rect.top,
      );
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  }, [zoomAt]);
  const src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  return (
    <div
      ref={box}
      className="drawing-viewer"
      onPointerDown={(e) => {
        if (e.button !== 0 || (e.target as HTMLElement).closest(".zoom-bar"))
          return;
        drag.current = { x: e.clientX, y: e.clientY };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        const start = drag.current;
        if (!start) return;
        drag.current = { x: e.clientX, y: e.clientY };
        setView(
          (v) =>
            v && {
              ...v,
              x: v.x + e.clientX - start.x,
              y: v.y + e.clientY - start.y,
            },
        );
      }}
      onPointerUp={() => (drag.current = null)}
      onPointerCancel={() => (drag.current = null)}
      onDoubleClick={fit}
    >
      <img
        ref={image}
        className="drawing"
        alt="图纸"
        draggable={false}
        src={src}
        onLoad={fit}
        style={
          view
            ? {
                width: image.current!.naturalWidth * view.scale,
                transform: `translate(${view.x}px, ${view.y}px)`,
              }
            : { visibility: "hidden" }
        }
      />
      <div className="zoom-bar">
        <button aria-label="缩小" title="缩小" onClick={() => zoomAt(1 / 1.25)}>
          −
        </button>
        <button
          className="zoom-value"
          title="实际大小"
          onClick={() => zoomAt(1 / (view?.scale || 1))}
        >
          {Math.round((view?.scale || 1) * 100)}%
        </button>
        <button aria-label="放大" title="放大" onClick={() => zoomAt(1.25)}>
          +
        </button>
        <button title="适应窗口（双击图纸）" onClick={fit}>
          适应
        </button>
      </div>
    </div>
  );
}
