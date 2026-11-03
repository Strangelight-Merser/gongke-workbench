import type { Bounds } from "./types.js";

// 不信任 renderer 提交的屏幕坐标；只接受其客户区内 CSS 矩形。
export function contentRect(value: Bounds, width: number, height: number, zoom: number): Bounds {
  if (!value || typeof value.visible !== "boolean" ||
      ![value.x, value.y, value.width, value.height, zoom].every(Number.isFinite) ||
      value.width < 0 || value.height < 0 || zoom <= 0)
    throw new Error("无效的编辑区边界");
  const x = Math.min(width, Math.max(0, value.x * zoom));
  const y = Math.min(height, Math.max(0, value.y * zoom));
  const right = Math.max(x, Math.min(width, (value.x + value.width) * zoom));
  const bottom = Math.max(y, Math.min(height, (value.y + value.height) * zoom));
  return { x: Math.round(x), y: Math.round(y), width: Math.round(right - x), height: Math.round(bottom - y), visible: value.visible };
}
