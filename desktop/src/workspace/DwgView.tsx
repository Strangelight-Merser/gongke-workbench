import { useState } from "react";
import { Select } from "../ui/controls";
import { Data } from "../api";
export function DwgView({
  snapshot,
  selected,
  select,
}: {
  snapshot: Data;
  selected: string;
  select: (id: string) => void;
}) {
  const layouts = [
    ...new Set<string>(snapshot.entities.map((entity: Data) => entity.layout)),
  ];
  const [layout, setLayout] = useState("Model");
  const current = layouts.includes(layout) ? layout : layouts[0];
  const entities = snapshot.entities.filter(
      (entity: Data) => entity.layout === current && entity.visible,
    ),
    bounds = entities
      .filter((entity: Data) => entity.bounds)
      .flatMap((entity: Data) => [entity.bounds.min, entity.bounds.max]);
  const minX = Math.min(...bounds.map((point: number[]) => point[0]), 0),
    maxX = Math.max(...bounds.map((point: number[]) => point[0]), 1),
    minY = Math.min(...bounds.map((point: number[]) => point[1]), 0),
    maxY = Math.max(...bounds.map((point: number[]) => point[1]), 1);
  const pad = Math.max(maxX - minX, maxY - minY) * 0.04;
  function shape(entity: Data) {
    const geometry = entity.geometry || {};
    if (geometry.normal && Math.abs(geometry.normal[2] - 1) > 1e-6) return null;
    if (entity.type === "LINE")
      return (
        <line
          x1={geometry.start[0]}
          y1={-geometry.start[1]}
          x2={geometry.end[0]}
          y2={-geometry.end[1]}
        />
      );
    if (entity.type === "CIRCLE")
      return (
        <circle
          cx={geometry.center[0]}
          cy={-geometry.center[1]}
          r={geometry.radius}
        />
      );
    if (entity.type === "ARC") {
      const angle =
        (geometry.end_angle - geometry.start_angle + Math.PI * 2) %
        (Math.PI * 2);
      return (
        <path
          d={`M${geometry.start[0]},${-geometry.start[1]} A${geometry.radius},${geometry.radius} 0 ${angle > Math.PI ? 1 : 0} 0 ${geometry.end[0]},${-geometry.end[1]}`}
        />
      );
    }
    if (
      ["LWPOLYLINE", "POLYLINE"].includes(entity.type) &&
      geometry.vertices?.length
    ) {
      let path = `M${geometry.vertices[0].point[0]},${-geometry.vertices[0].point[1]}`;
      for (
        let i = 0;
        i <
        (geometry.closed
          ? geometry.vertices.length
          : geometry.vertices.length - 1);
        i++
      ) {
        const a = geometry.vertices[i],
          b = geometry.vertices[(i + 1) % geometry.vertices.length],
          chord = Math.hypot(a.point[0] - b.point[0], a.point[1] - b.point[1]);
        path += a.bulge
          ? ` A${(chord * (1 + a.bulge * a.bulge)) / (4 * Math.abs(a.bulge))},${(chord * (1 + a.bulge * a.bulge)) / (4 * Math.abs(a.bulge))} 0 ${Math.abs(a.bulge) > 1 ? 1 : 0} ${a.bulge > 0 ? 0 : 1} ${b.point[0]},${-b.point[1]}`
          : ` L${b.point[0]},${-b.point[1]}`;
      }
      return <path d={path} />;
    }
    if (["TEXT", "MTEXT"].includes(entity.type))
      return (
        <text
          x={geometry.position[0]}
          y={-geometry.position[1]}
          fontSize={geometry.height}
          fill="currentColor"
          stroke="none"
          transform={`rotate(${(-geometry.rotation * 180) / Math.PI},${geometry.position[0]},${-geometry.position[1]})`}
        >
          {entity.text}
        </text>
      );
    return null;
  }
  const rendered = entities.map((entity: Data) => ({
    entity,
    node: shape(entity),
  }));
  return (
    <div className="page-view">
      <div className="toolbar">
        <Select
          value={current}
          onChange={(event) => setLayout(event.target.value)}
        >
          {layouts.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </Select>
        <span>
          WCS 平面预览 · {rendered.filter((item: Data) => !item.node).length}{" "}
          个实体需原生视图检查
        </span>
      </div>
      <svg
        className="drawing"
        viewBox={`${minX - pad} ${-maxY - pad} ${maxX - minX + pad * 2} ${maxY - minY + pad * 2}`}
        style={{ color: "#2a2927" }}
      >
        {rendered.map(({ entity, node }: Data) => (
          <g
            key={entity.handle}
            onClick={() => select(entity.handle)}
            fill="none"
            stroke={entity.handle === selected ? "#e8742a" : "currentColor"}
            strokeWidth={(maxX - minX) / 1000}
            style={{ cursor: "pointer" }}
          >
            {node}
          </g>
        ))}
      </svg>
    </div>
  );
}
