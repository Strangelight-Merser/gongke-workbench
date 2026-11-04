import React, { useState, useEffect, useLayoutEffect, useRef } from "react";
import * as THREE from "three";
import {
  AbsoluteFill,
  Composition,
  registerRoot,
  useCurrentFrame,
  interpolate,
  Easing,
  Img,
  OffthreadVideo,
  staticFile,
  delayRender,
  continueRender,
  Sequence,
} from "remotion";
const C = {
  ink: "#101918",
  paper: "#f3f5f4",
  accent: "#24b69c",
  muted: "#98aaa5",
};
const ease = Easing.bezier(0.22, 1, 0.36, 1);
const mix = (f: number, a: number, b: number, x = 0, y = 1) =>
  interpolate(f, [a, b], [x, y], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });
function Fonts() {
  const [h] = useState(() => delayRender("思源黑体"));
  useEffect(() => {
    Promise.all(
      ["Regular", "Bold"].map(async (w) => {
        const f = new FontFace(
          "Source Han",
          `url(${staticFile(`SourceHanSansSC-${w}.otf`)})`,
          { weight: w === "Bold" ? "700" : "400" },
        );
        await f.load();
        document.fonts.add(f);
      }),
    ).then(() => continueRender(h));
  }, []);
  return null;
}
const base: React.CSSProperties = {
  fontFamily: "Source Han",
  color: C.paper,
  background: C.ink,
};
function Frame({ children }: any) {
  return (
    <AbsoluteFill style={base}>
      <Fonts />
      {children}
    </AbsoluteFill>
  );
}
function Solid({ vertices, triangles, opacity }: any) {
  const canvas = useRef<HTMLCanvasElement>(null),
    state = useRef<any>(null);
  useLayoutEffect(() => {
    const renderer = new THREE.WebGLRenderer({
      canvas: canvas.current!,
      alpha: true,
      antialias: true,
    });
    renderer.setSize(1920, 1080);
    renderer.setClearColor(0, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    const scene = new THREE.Scene(),
      camera = new THREE.OrthographicCamera(0, 1920, 1080, 0, 0.1, 5000);
    camera.position.set(0, 0, 2000);
    camera.lookAt(0, 0, 0);
    scene.add(new THREE.AmbientLight("#d1e7df", 1.6));
    const key = new THREE.DirectionalLight("#ffffff", 3.2);
    key.position.set(-400, 1000, 1700);
    scene.add(key);
    const rim = new THREE.DirectionalLight("#91e2cb", 1.1);
    rim.position.set(1800, -500, 1000);
    scene.add(rim);
    const geometry = new THREE.BufferGeometry();
    geometry.setIndex(triangles.flat());
    const material = new THREE.MeshPhysicalMaterial({
      color: "#99b4ac",
      metalness: 0.3,
      roughness: 0.33,
      clearcoat: 0.25,
      flatShading: true,
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);
    state.current = { renderer, scene, camera, geometry, material };
    return () => {
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      state.current = null;
    };
  }, []);
  useLayoutEffect(() => {
    const s = state.current;
    if (!s) return;
    s.geometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(
        vertices.flatMap((p: number[]) => [p[0], 1080 - p[1], p[2]]),
        3,
      ),
    );
    s.geometry.computeVertexNormals();
    s.geometry.computeBoundingSphere();
    s.renderer.render(s.scene, s.camera);
  }, [vertices]);
  return (
    <canvas
      ref={canvas}
      style={{
        position: "absolute",
        inset: 0,
        width: 1920,
        height: 1080,
        opacity,
      }}
    />
  );
}
function Model({ geometry, frame, board = false }: any) {
  const turn = board ? 1 : mix(frame, 185, 290),
    extrusion = board ? 1 : mix(frame, 230, 345),
    exit = board ? 0 : mix(frame, 410, 465);
  const az = turn * -0.44,
    ax = turn * 0.94;
  const project = (p: number[]) => {
    const [x, y, z0] = p,
      z = z0 * extrusion;
    const u = x * Math.cos(az) - y * Math.sin(az),
      v = x * Math.sin(az) + y * Math.cos(az);
    return [
      u,
      v * Math.cos(ax) - z * Math.sin(ax),
      v * Math.sin(ax) + z * Math.cos(ax),
    ];
  };
  const scale = board ? 18 : mix(frame, 180, 290, 16, 22) * (1 - 0.12 * exit),
    cx = board ? 1350 : 960 + 370 * exit,
    cy = board ? 655 : 535 - 15 * exit;
  const point = (p: number[]) => {
    const q = project(p);
    return [cx + q[0] * scale, cy - q[1] * scale, q[2]];
  };
  const verts = geometry.mesh.vertices.map(point);

  const box = geometry.box,
    s = geometry.scale;
  const toNative = (p: number[]) => [
    (p[0] - (box[0] + box[2]) / 2) / s,
    ((box[1] + box[3]) / 2 - p[1]) / s,
    0,
  ];
  return (
    <>
      <svg
        width="1920"
        height="1080"
        style={{ position: "absolute", inset: 0 }}
      >
        <defs>
          <radialGradient id="glow">
            <stop offset="0" stopColor={C.accent} stopOpacity=".13" />
            <stop offset="1" stopColor={C.accent} stopOpacity="0" />
          </radialGradient>
          <filter id="shadow">
            <feGaussianBlur stdDeviation="24" />
          </filter>
        </defs>
        <ellipse cx={cx} cy={cy + 120} rx="680" ry="440" fill="url(#glow)" />
        <ellipse
          cx={cx}
          cy={cy + 205}
          rx={350 * turn}
          ry={22 * turn}
          opacity={0.25 * extrusion}
          fill="#000"
          filter="url(#shadow)"
        />
        <g opacity={board ? 0 : 1 - mix(frame, 260, 330)}>
          {geometry.outline.map((r: any, i: number) => {
            const pts = r.pts.map((p: number[]) => point(toNative(p)));
            return (
              <path
                key={r.source}
                d={`M${pts[0][0]},${pts[0][1]} L${pts[1][0]},${pts[1][1]}`}
                pathLength="1"
                stroke={i < 20 ? C.paper : C.accent}
                strokeWidth="2.4"
                fill="none"
                strokeLinecap="round"
                strokeDasharray="1"
                strokeDashoffset={1 - mix(frame, 8 + i * 1.8, 36 + i * 1.8)}
              />
            );
          })}
        </g>
        <g
          opacity={board ? 0 : (1 - mix(frame, 160, 195)) * mix(frame, 70, 100)}
        >
          {geometry.dimensionLines.map((r: any) => {
            const p = r.pts.map((p: number[]) => point(toNative(p)));
            return (
              <path
                key={r.source}
                d={`M${p[0][0]},${p[0][1]} L${p[1][0]},${p[1][1]}`}
                stroke={C.muted}
                opacity=".6"
                strokeWidth="1"
                fill="none"
              />
            );
          })}
        </g>
        <g opacity={board ? 0 : 1 - mix(frame, 160, 195)}>
          {geometry.dimensions.map((d: any, i: number) => {
            const p = point(
              toNative([
                (d.bbox[0] + d.bbox[2]) / 2,
                (d.bbox[1] + d.bbox[3]) / 2,
              ]),
            );
            return (
              <text
                key={i}
                x={p[0]}
                y={p[1]}
                fill={C.accent}
                fontSize="30"
                textAnchor="middle"
                dominantBaseline="middle"
                opacity={mix(frame, 78 + i * 10, 98 + i * 10)}
              >
                {d.text}
              </text>
            );
          })}
        </g>
      </svg>
      <Solid
        vertices={verts.map((p: number[]) => [p[0], p[1], p[2] * scale])}
        triangles={geometry.mesh.triangles}
        opacity={board ? 1 : mix(frame, 225, 280)}
      />
    </>
  );
}
function Opening({ geometry }: any) {
  const f = useCurrentFrame(),
    appear = mix(f, 415, 460);
  return (
    <Frame>
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(ellipse at 55% 45%,#1c2d29 0%,#101918 68%)",
        }}
      />
      <svg
        width="1920"
        height="1080"
        style={{ position: "absolute", opacity: (1 - mix(f, 180, 300)) * 0.12 }}
      >
        <defs>
          <pattern
            id="grid"
            width="64"
            height="64"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M64 0H0V64"
              fill="none"
              stroke="#83988f"
              strokeWidth=".5"
            />
          </pattern>
        </defs>
        <rect width="1920" height="1080" fill="url(#grid)" />
      </svg>
      <Model geometry={geometry} frame={f} />
      <div
        style={{
          position: "absolute",
          left: 120,
          top: 310,
          opacity: appear,
          transform: `translateY(${(1 - appear) * 28}px)`,
        }}
      >
        <Img
          src={staticFile("logo.svg")}
          style={{ width: 104, height: 104, marginLeft: -9, marginBottom: 24 }}
        />
        <div
          style={{
            fontSize: 88,
            fontWeight: 700,
            letterSpacing: 3,
            lineHeight: 1.3,
          }}
        >
          构想引擎
        </div>
        <div
          style={{
            height: 4,
            width: 64,
            background: C.accent,
            margin: "28px 0",
          }}
        />
        <div style={{ fontSize: 30, color: "#b9c7c2" }}>
          面向工科学生的 AI 工程工作台
        </div>
      </div>
    </Frame>
  );
}
const Label = ({ children }: any) => (
  <div
    style={{
      position: "absolute",
      bottom: 38,
      left: 44,
      fontSize: 30,
      padding: "10px 18px",
      background: "rgba(16,25,24,.88)",
      borderLeft: `3px solid ${C.accent}`,
      borderRadius: 4,
      color: "#fff",
    }}
  >
    {children}
  </div>
);
const Subtitle = ({ children }: any) => (
  <div
    style={{
      position: "absolute",
      bottom: 45,
      left: 550,
      right: 250,
      textAlign: "center",
      fontSize: 30,
      color: "white",
      textShadow: "0 2px 5px #000,0 0 12px #000",
    }}
  >
    {children}
  </div>
);
function Growth({ recording }: any) {
  const f = useCurrentFrame();
  // 连续原片：从新建零件完成后开始，保留草图与拉伸两次真实调用。
  const marks = Object.fromEntries(
    recording.inputs
      .filter((r: any) => r.kind === "mark")
      .map((r: any) => [r.name, r.at / 1000 - recording.frames[0].timestamp]),
  );
  const start = marks["start-5"] - 0.8,
    second = marks["start-6"] - 0.6;
  // 同一取景，先看生长，再缓动推近特征树及完成卡片；全程铺满。
  const push = mix(f, 600, 642),
    scale = 1.16 + push * 0.18;
  const x = 1920 - 1920 * scale,
    y = -180 - push * 25;
  const time = f < 300 ? start + f / 60 : second + (f - 300) / 60;
  const cursor = recording.inputs
    .filter(
      (r: any) =>
        r.kind === "pointermove" &&
        r.at / 1000 - recording.frames[0].timestamp <= time,
    )
    .at(-1);
  return (
    <Frame>
      <AbsoluteFill style={{ overflow: "hidden", background: "#f3f5f4" }}>
        <div
          style={{
            position: "absolute",
            width: 1920,
            height: 1080,
            transformOrigin: "0 0",
            transform: `translate(${x}px,${y}px) scale(${scale})`,
          }}
        >
          <Sequence durationInFrames={300}>
            <OffthreadVideo
              src={staticFile("growth.mp4")}
              startFrom={Math.round(start * 60)}
              style={{ width: 1920, height: 1080 }}
              muted
            />
          </Sequence>
          <Sequence from={300}>
            <OffthreadVideo
              src={staticFile("growth.mp4")}
              startFrom={Math.round(second * 60)}
              style={{ width: 1920, height: 1080 }}
              muted
            />
          </Sequence>
          {cursor && (
            <div
              style={{
                position: "absolute",
                left: cursor.x - 17,
                top: cursor.y - 17,
                width: 34,
                height: 34,
                borderRadius: "50%",
                border: "2px solid rgba(36,182,156,.7)",
                background: "rgba(36,182,156,.14)",
                pointerEvents: "none",
              }}
            />
          )}
        </div>
        <Label>按真实会话重放</Label>
        {f > 155 && f < 290 && <Subtitle>草图先建立起来</Subtitle>}
        {f > 520 && f < 760 && <Subtitle>再拉伸，成为可编辑的零件</Subtitle>}
      </AbsoluteFill>
    </Frame>
  );
}
function Styleboard({ geometry }: any) {
  return (
    <Frame>
      <div
        style={{
          position: "absolute",
          left: 88,
          top: 65,
          display: "flex",
          alignItems: "center",
          gap: 22,
        }}
      >
        <Img src={staticFile("logo.svg")} style={{ width: 88, height: 88 }} />
        <span style={{ fontSize: 48, fontWeight: 700 }}>
          构想引擎 · 视觉样板
        </span>
      </div>
      <div
        style={{
          position: "absolute",
          left: 96,
          top: 230,
          fontSize: 88,
          fontWeight: 700,
        }}
      >
        从图纸，到模型。
      </div>
      <div style={{ position: "absolute", left: 100, top: 365, fontSize: 48 }}>
        思源黑体 · 三级字号
      </div>
      <div
        style={{
          position: "absolute",
          left: 102,
          top: 453,
          fontSize: 30,
          color: "#a9bbb4",
        }}
      >
        标题 88　段落 48　字幕与标注 30
      </div>
      <div
        style={{
          position: "absolute",
          left: 102,
          top: 570,
          display: "flex",
          gap: 22,
        }}
      >
        {[
          [C.accent, "青绿"],
          [C.ink, "墨黑"],
          [C.paper, "雾白"],
        ].map(([color, name]) => (
          <div key={color}>
            <div
              style={{
                width: 170,
                height: 100,
                background: color,
                border: "1px solid #52615b",
                borderRadius: 12,
              }}
            />
            <div style={{ fontSize: 30, marginTop: 16 }}>{name}</div>
            <div style={{ fontSize: 30, color: "#8daba0" }}>{color}</div>
          </div>
        ))}
      </div>
      <Model geometry={geometry} frame={500} board />
      <div
        style={{
          position: "absolute",
          left: 104,
          top: 850,
          fontSize: 30,
          color: "#9fb1a9",
        }}
      >
        0.7 秒缓动推近 · 全幅画面 · 单行字幕
      </div>
      <Label>按真实会话重放</Label>
      <Subtitle>模型留给你，继续改</Subtitle>
    </Frame>
  );
}
registerRoot(() => (
  <>
    <Composition
      id="Opening"
      component={Opening}
      width={1920}
      height={1080}
      fps={60}
      durationInFrames={720}
      defaultProps={{ geometry: null }}
    />
    <Composition
      id="Growth"
      component={Growth}
      width={1920}
      height={1080}
      fps={60}
      durationInFrames={780}
      defaultProps={{ recording: null }}
    />
    <Composition
      id="Styleboard"
      component={Styleboard}
      width={1920}
      height={1080}
      fps={60}
      durationInFrames={1}
      defaultProps={{ geometry: null }}
    />
  </>
));
