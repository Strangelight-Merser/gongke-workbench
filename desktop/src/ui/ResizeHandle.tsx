import { useRef } from "react";
export function ResizeHandle({
  label,
  value,
  min,
  max,
  reverse = false,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  reverse?: boolean;
  onChange(value: number): void;
}) {
  const start = useRef({ x: 0, value: 0 });
  return (
    <div
      className="resize-handle"
      role="separator"
      aria-label={label}
      aria-orientation="vertical"
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onPointerDown={(e) => {
        start.current = { x: e.clientX, value };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (e.currentTarget.hasPointerCapture(e.pointerId))
          onChange(
            Math.max(
              min,
              Math.min(
                max,
                start.current.value +
                  (e.clientX - start.current.x) * (reverse ? -1 : 1),
              ),
            ),
          );
      }}
      onPointerUp={(e) => e.currentTarget.releasePointerCapture(e.pointerId)}
      onKeyDown={(e) => {
        if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
          e.preventDefault();
          onChange(
            e.key === "Home"
              ? min
              : e.key === "End"
                ? max
                : Math.max(
                    min,
                    Math.min(
                      max,
                      value +
                        (e.key === "ArrowRight" ? 16 : -16) *
                          (reverse ? -1 : 1),
                    ),
                  ),
          );
        }
      }}
    />
  );
}
