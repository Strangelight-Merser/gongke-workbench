// 仅用于无界面 UI 回归；几何为明确标记的合成样例，不是宿主验收证据。
import React from "react";
import { createRoot } from "react-dom/client";
import { FluentProvider } from "@fluentui/react-components";
import { lightTheme } from "../../src/app/theme";
import { ModelingProgress } from "../../src/agent/ModelingProgress";
import { ModelingSteps } from "../../src/agent/ModelingTimeline";
import { FreeCadInspector } from "../../src/workspace/FreeCadInspector";
import "../../src/styles/tokens.css";
import "../../src/styles/workspace.css";
import "../../src/styles/documents.css";
import "../../src/styles/agent.css";
const listeners = new Set<(e: any) => void>();
let revision = 1,
  height = 8,
  deleted = false;
const calls: string[] = [],
  project = { path: "/fixture/project" };
const doc = () => ({
  host_instance: "fixture",
  document_id: "doc",
  revision,
  configuration: "",
});
const edge = {
  native_ref: "Body.Edge1",
  samples: [
    [0, 0, 0],
    [0.04, 0, 0],
    [0.04, 0.02, 0],
    [0, 0.02, 0],
    [0, 0, 0],
  ],
};
const features = () => [
  { native_ref: "Body", label: "零件", type: "PartDesign::Body" },
  {
    native_ref: "Sketch",
    parent: "Body",
    label: "底板草图",
    type: "Sketcher::SketchObject",
    sketch: {},
  },
  ...(deleted
    ? []
    : [
        {
          native_ref: "Pad",
          parent: "Body",
          label: "底板拉伸",
          type: "PartDesign::Pad",
        },
      ]),
];
const snapshot = (ref: string) => ({
  document: doc(),
  object_ref: ref,
  features: features(),
  edges: [edge],
  faces: [
    {
      native_ref: "Body.Face1",
      kind: "plane",
      point: [0, 0, height / 1000],
      direction: [0, 0, 1],
    },
  ],
});
(window as any).gongke = {
  onEvent: (cb: any) => {
    listeners.add(cb);
    return () => listeners.delete(cb);
  },
  request: async (method: string, p: any = {}) => {
    calls.push(method);
    if (method === "task.list") return [];
    if (method === "freecad.context" || method === "freecad.select")
      return { session_id: "doc", revision, objects: [] };
    if (method === "host.context")
      return {
        active_document: doc(),
        documents: [{ document: doc(), objects: [{ native_ref: "Body" }] }],
      };
    if (method === "host.inspect") return snapshot(p.object_ref);
    if (method === "freecad.scene")
      return {
        session_id: "doc",
        revision,
        objects: [
          {
            id: "Body",
            label: "零件",
            vertices: [
              [0, 0, 0],
              [40, 0, 0],
              [40, 20, 0],
              [0, 20, 0],
              [0, 0, height],
              [40, 0, height],
              [40, 20, height],
              [0, 20, height],
            ],
            triangles: [
              [0, 2, 1],
              [0, 3, 2],
              [4, 5, 6],
              [4, 6, 7],
              [0, 1, 5],
              [0, 5, 4],
              [1, 2, 6],
              [1, 6, 5],
              [2, 3, 7],
              [2, 7, 6],
              [3, 0, 4],
              [3, 4, 7],
            ],
          },
        ],
        pages: [],
      };
    throw Error(method);
  },
};
let index = 0;
(window as any).fixture = {
  calls,
  emit(kind: string) {
    const command =
      kind === "check"
        ? "host.check"
        : kind === "delete"
          ? "host.feature_delete"
          : "host.feature";
    if (kind !== "check") {
      revision++;
      height += 4;
      if (kind === "delete") deleted = true;
    }
    const result =
      kind === "check"
        ? {
            document: doc(),
            object_ref: "Body",
            status: "fail",
            checks: [
              {
                id: "底板厚度",
                status: "fail",
                actual: { locations: [{ native_ref: "Body.Face1" }] },
              },
            ],
          }
        : {
            document: doc(),
            outcome: "committed",
            ...(kind === "delete"
              ? { deleted_ref: "Pad" }
              : { native_ref: "Pad" }),
          };
    for (const cb of listeners)
      cb({
        event: "task.receipt",
        project: project.path,
        task_id: String(++index),
        receipt: {
          command,
          phase: "finished",
          at: new Date().toISOString(),
          params: {
            host_id: "freecad",
            feature: { kind: "pad", length: height / 1000 },
          },
          result,
        },
      });
  },
};
createRoot(document.getElementById("root")!).render(
  <ModelingProgress project={project.path}>
    <FluentProvider theme={lightTheme} className="workbench" data-theme="light">
      <div
        style={{
          height: "100vh",
          display: "grid",
          gridTemplateColumns: "1fr 320px",
          padding: 12,
          gap: 12,
        }}
      >
        <div style={{ minHeight: 0, display: "flex", flexDirection: "column" }}>
          <p>合成样例 · 实时建模 UI 回归</p>
          <FreeCadInspector
            project={project}
            run={(_label: string, fn: any) => fn()}
            onContext={() => {}}
            onProjectChange={async () => {}}
            pendingOperation={null}
            setPendingOperation={() => {}}
          />
        </div>
        <aside style={{ overflow: "auto" }}>
          <ModelingSteps openModel={() => {}} />
        </aside>
      </div>
    </FluentProvider>
  </ModelingProgress>,
);
