import { useCallback, useRef, useState } from "react";
import { call, Data, text } from "./api";
import { ModelView } from "./ModelView";
import { Collapsible } from "./Motion";

const mutations = new Set([
  "parameter.change",
  "drawing.update",
  "document.save_copy",
  "drawing.export",
  "drawing.edit_text",
  "drawing.move_dimension_text",
]);
const normalPath = (value: string) => value.replace(/\\/g, "/").toLowerCase();
export const pendingKey = (kind: string) => "gongke-native-unresolved-" + kind;
export function savedPending(kind: string): Data | null {
  try {
    return JSON.parse(localStorage.getItem(pendingKey(kind)) || "null");
  } catch {
    return null;
  }
}
export async function registeredWorkingCopy(kind: string, request: Data) {
  const project = await call("project.current");
  const path = request.params.output_path || request.params.target_path;
  const paths = [path, request.params.output_part_path].filter(Boolean);
  if (
    !path ||
    !paths.every((target) =>
      (project?.working_copies || []).some(
        (copy: Data) =>
          copy.host === kind &&
          copy.operation_id === request.operation_id &&
          normalPath(copy.path) === normalPath(target),
      ),
    )
  )
    throw new Error("工作副本尚未完成工程登记；保留原操作，请查询核对后继续");
  return { project, path };
}
function operationResult(value: Data): Data {
  return (
    value.response?.result ||
    (value.response?.error && { error: value.response.error }) ||
    value
  );
}

export function CommercialView({
  host,
  kind,
  run,
}: {
  host: Data | undefined;
  kind: string;
  run: any;
}) {
  const [context, setContext] = useState<Data | null>(null),
    [scene, setScene] = useState<Data | null>(null),
    [parameters, setParameters] = useState<Data[]>([]),
    [snapshot, setSnapshot] = useState<Data | null>(null);
  const [selection, setSelection] = useState(""),
    [draft, setDraft] = useState(""),
    [position, setPosition] = useState<string[]>(["", "", ""]);
  const [receipt, setReceipt] = useState<Data | null>(() => savedPending(kind)),
    [pending, setPending] = useState<Data | null>(() => savedPending(kind)),
    [reviewRequired, setReviewRequired] = useState(false),
    [working, setWorking] = useState(false);
  const inFlight = useRef(false),
    doc = context?.active_document;
  const writeLocked = working || !!pending || reviewRequired;
  const parameter = parameters.find((p) => p.name === selection),
    entity = snapshot?.entities?.find((e: Data) => e.handle === selection);
  function keepPending(value: Data | null) {
    setPending(value);
    if (value) localStorage.setItem(pendingKey(kind), JSON.stringify(value));
    else localStorage.removeItem(pendingKey(kind));
  }
  async function act(label: string, action: () => Promise<unknown>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setWorking(true);
    try {
      return await run(label, action);
    } finally {
      inFlight.current = false;
      setWorking(false);
    }
  }
  function clearSnapshot() {
    setContext(null);
    setScene(null);
    setParameters([]);
    setSnapshot(null);
    setSelection("");
    setDraft("");
    setPosition(["", "", ""]);
  }
  async function invoke(
    method: string,
    params: Data = {},
    targetHost = host?.host_id,
  ) {
    if (!targetHost) throw new Error("未连接原生宿主");
    const write = mutations.has(method);
    if (write && (pending || reviewRequired))
      throw new Error(
        pending
          ? "原操作结果待确认，请查询原操作后再继续修改"
          : "请先读取最新原生状态，核对需要复核的结果",
      );
    const request = {
      host_id: targetHost,
      method,
      params,
      operation_id: params.operation_id,
    };
    let result: any;
    if (write)
      localStorage.setItem(
        pendingKey(kind),
        JSON.stringify({ ...request, state: "submitted" }),
      );
    try {
      result = await call("host.command", {
        host_id: targetHost,
        method,
        params,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (write) {
        const record = { ...request, error: { message, outcome: "unknown" } };
        setReceipt(record);
        keepPending(record);
      }
      throw error;
    }
    if (result?.error) {
      const record = { ...request, ...result };
      setReceipt(record);
      if (write && result.error.outcome === "unknown") keepPending(record);
      else if (write) localStorage.removeItem(pendingKey(kind));
      throw new Error(
        (result.error.outcome === "unknown"
          ? "原操作结果待确认；请勿重复提交。"
          : "") + result.error.message,
      );
    }
    if (write) {
      localStorage.removeItem(pendingKey(kind));
      setReceipt({ ...request, result });
      if (
        result.status === "needs_review" ||
        result.rebuilt === false ||
        result.readback_matches === false
      ) {
        setReviewRequired(true);
        throw new Error(
          "原生操作需要复核；完整读回结果已保留。请读取最新状态后再继续。",
        );
      }
    }
    return result;
  }
  async function refresh(targetHost = host?.host_id) {
    clearSnapshot();
    if (kind === "solidworks") {
      const c = await invoke("document.context", {}, targetHost);
      if (!c.active_document) throw new Error("SOLIDWORKS 中没有活动文档");
      const p = {
        document_path: c.active_document.path,
        configuration: c.active_document.configuration,
      };
      let nextScene: Data | null = null,
        nextParameters: Data[] = [],
        nextSnapshot: Data | null = null;
      if (c.active_document.document_type === 1) {
        const mesh = await invoke("preview.mesh", p, targetHost);
        nextScene = {
          objects: mesh.faces.map((face: Data, index: number) => ({
            id: face.persistent_reference || "unselectable-" + index,
            label: "面 " + (index + 1),
            selectable: !!face.persistent_reference,
            vertices: face.positions.reduce(
              (rows: number[][], value: number, i: number) => {
                if (i % 3 === 0) rows.push([]);
                rows[rows.length - 1].push(value * 1000);
                return rows;
              },
              [],
            ),
            triangles: Array.from(
              { length: face.positions.length / 9 },
              (_, i) => [i * 3, i * 3 + 1, i * 3 + 2],
            ),
          })),
        };
        nextParameters = await invoke("parameters.list", p, targetHost);
      } else if (c.active_document.document_type === 3)
        nextSnapshot = await invoke("drawing.inspect", p, targetHost);
      else throw new Error("当前支持原生零件和工程图，请激活其中一个文档");
      const current = await invoke("document.context", {}, targetHost);
      if (
        !current.active_document ||
        normalPath(current.active_document.path) !==
          normalPath(c.active_document.path) ||
        current.active_document.configuration !==
          c.active_document.configuration ||
        current.active_document.revision !== c.active_document.revision
      )
        throw new Error("读取期间原生文档发生变化，请重新读取");
      setContext(current);
      setScene(nextScene);
      setParameters(nextParameters);
      setSnapshot(nextSnapshot);
    } else {
      const c = await invoke("documents.list", {}, targetHost);
      const active = c.documents.find((item: Data) => item.active);
      if (!active) throw new Error("AutoCAD 中没有活动图纸");
      const next = await invoke(
        "document.snapshot",
        {
          document_id: active.document_id,
        },
        targetHost,
      );
      setSnapshot(next);
      setContext({ active_document: next.document });
    }
    setReviewRequired(false);
  }
  async function readMore() {
    if (snapshot?.next_offset == null) return;
    const next = await invoke("document.snapshot", {
      document_id: doc.document_id,
      offset: snapshot.next_offset,
      expected_revision: snapshot.revision,
    });
    if (
      next.revision !== snapshot.revision ||
      next.document.document_id !== doc.document_id
    ) {
      clearSnapshot();
      throw new Error("图纸在分页读取时发生变化，请重新读取");
    }
    setSnapshot({
      ...next,
      entities: [...snapshot.entities, ...next.entities],
    });
    setContext({ active_document: next.document });
  }
  const bound = () =>
    kind === "solidworks"
      ? {
          document_path: doc.path,
          configuration: doc.configuration,
          session_id: context!.session_id,
          expected_revision: doc.revision,
          operation_id: crypto.randomUUID(),
        }
      : {
          document_id: doc.document_id,
          expected_revision: doc.revision,
          operation_id: crypto.randomUUID(),
        };
  const select = useCallback(
    (id: string) => {
      if (inFlight.current || !context?.active_document) return;
      setSelection(id);
      const selectedEntity = snapshot?.entities?.find(
        (item: Data) => item.handle === id,
      );
      setDraft(selectedEntity?.text ?? "");
      setPosition(selectedEntity?.text_position?.map(String) || ["", "", ""]);
      const document = context.active_document,
        p = parameters.find((item) => item.name === id),
        face = scene?.objects?.find((item: Data) => item.id === id);
      const reference =
        p?.persistent_reference || (face?.selectable ? face.id : null);
      if (kind === "solidworks" && reference)
        act("选择原生对象", () =>
          invoke("selection.set", {
            document_path: document.path,
            configuration: document.configuration,
            session_id: context.session_id,
            operation_id: crypto.randomUUID(),
            expected_revision: document.revision,
            persistent_reference: reference,
          }),
        );
      else if (kind === "autocad")
        act("选择原生对象", () =>
          invoke("document.select", {
            document_id: document.document_id,
            expected_revision: document.revision,
            handle: id,
            operation_id: crypto.randomUUID(),
          }),
        );
    },
    [
      context,
      parameters,
      scene,
      snapshot,
      host,
      kind,
      run,
      pending,
      reviewRequired,
    ],
  );
  async function copy() {
    const suffix = crypto.randomUUID().slice(0, 12),
      directory = "revisions/native-" + suffix;
    const path =
      directory +
      (kind === "solidworks"
        ? doc.document_type === 3
          ? "/drawing-" + suffix + ".slddrw"
          : "/part-" + suffix + ".sldprt"
        : "/drawing.dwg");
    const pair: Data = {};
    if (kind === "solidworks" && doc.document_type === 3) {
      const views = (snapshot?.sheets || [])
        .flatMap((sheet: Data) => sheet.views || [])
        .filter((view: Data) => view.model_path);
      const paths = [
        ...new Set<string>(
          views.map((view: Data) => normalPath(view.model_path)),
        ),
      ];
      if (paths.length !== 1)
        throw new Error("成对工作修订需要所有模型视图引用同一个零件");
      const source = context!.documents.find(
        (item: Data) => normalPath(item.path) === paths[0],
      );
      if (!source || !Number.isInteger(source.revision))
        throw new Error(
          "未读取到关联零件的修订号；请在 SOLIDWORKS 完整加载该零件后重新读取",
        );
      pair.output_part_path = directory + "/part-" + suffix + ".sldprt";
      pair.expected_part_revision = source.revision;
    }
    await invoke("document.save_copy", {
      ...bound(),
      [kind === "solidworks" ? "output_path" : "target_path"]: path,
      ...pair,
    });
    await invoke("document.open", {
      operation_id: crypto.randomUUID(),
      ...(kind === "solidworks"
        ? {
            document_path: path,
            configuration: doc.configuration,
            session_id: context!.session_id,
          }
        : { path }),
    });
    await refresh();
  }
  async function queryPending() {
    if (!pending) return;
    const status = await invoke(
      kind === "solidworks" ? "operation.get" : "operation.status",
      { operation_id: pending.operation_id },
      pending.host_id,
    );
    const result = operationResult(status);
    const { error: initial_error, ...originalRequest } = pending;
    setReceipt({ ...originalRequest, initial_error, query: status, result });
    const terminal =
      kind === "solidworks"
        ? status.state === "finished"
        : ["completed", "failed", "cancelled_before_start"].includes(
            status.status,
          );
    const outcome = result.error?.outcome || result.outcome || status.outcome;
    if (!terminal || outcome === "unknown") return;
    clearSnapshot();
    if (
      result.status === "needs_review" ||
      result.rebuilt === false ||
      result.readback_matches === false
    ) {
      keepPending(null);
      setReviewRequired(true);
      return;
    }
    const saved =
      !result.error &&
      (kind === "solidworks"
        ? result.status === "saved"
        : result.outcome === "committed");
    if (
      saved &&
      ["document.save_copy", "drawing.import_dxf"].includes(pending.method)
    ) {
      const { path } = await registeredWorkingCopy(kind, pending);
      await invoke(
        "document.open",
        {
          operation_id: crypto.randomUUID(),
          ...(kind === "solidworks"
            ? {
                document_path: path,
                configuration: pending.params.configuration,
                session_id: pending.params.session_id,
              }
            : { path }),
        },
        pending.host_id,
      );
      await refresh(pending.host_id);
    }
    keepPending(null);
  }
  async function moveDimension() {
    const coordinates = position.map(Number);
    if (
      position.some((value) => !value.trim()) ||
      coordinates.some((value) => !Number.isFinite(value))
    )
      throw new Error("请输入有限的 WCS X、Y、Z 坐标");
    await invoke("drawing.move_dimension_text", {
      ...bound(),
      handle: entity.handle,
      position: coordinates,
    });
    await refresh();
  }
  const unresolved = pending && (
    <div role="alert" className="error">
      <strong>原操作结果待确认，修改已暂停</strong>
      <p>
        {pending.method} · {pending.operation_id}
      </p>
      <button
        disabled={working}
        onClick={() => act("查询原操作", queryPending)}
      >
        查询原操作结果
      </button>
      <p>查询不会再次执行原操作；确认并登记成功的工作副本会自动打开。</p>
    </div>
  );
  if (!host?.connected)
    return (
      <div className="empty">
        {unresolved}
        <div className="empty-icon">◇</div>
        <h2>{kind === "solidworks" ? "SOLIDWORKS" : "AutoCAD"}</h2>
        <p>
          请在 Windows
          安装对应的原生插件并启动软件，再刷新连接。当前机器没有可用连接。
        </p>
        <small>插件已通过引用编译，原生宿主实测待完成。</small>
        {receipt && <pre>{text(receipt)}</pre>}
      </div>
    );
  return (
    <div className="native">
      {unresolved}
      {reviewRequired && (
        <div role="alert" className="error">
          原生操作需要复核。请检查完整回执，并重新读取当前模型或图纸；修改暂时停用。
        </div>
      )}
      <div className="toolbar">
        <button
          className="primary"
          disabled={working}
          onClick={() => act("读取原生工程", refresh)}
        >
          读取当前工程
        </button>
        {doc && (
          <button
            disabled={writeLocked}
            onClick={() => act("建立工作修订", copy)}
          >
            另存工作修订
          </button>
        )}
        {kind === "solidworks" && doc?.document_type === 3 && (
          <>
            <button
              disabled={writeLocked}
              onClick={() =>
                act("更新原生图纸", async () => {
                  await invoke("drawing.update", bound());
                  await refresh();
                })
              }
            >
              更新图纸
            </button>
            <button
              disabled={writeLocked}
              onClick={() =>
                act("导出原生 DXF", () =>
                  invoke("drawing.export", {
                    ...bound(),
                    sheet: snapshot?.active_sheet,
                    output_path:
                      "revisions/drawing-" +
                      crypto.randomUUID().slice(0, 12) +
                      "/page.dxf",
                  }),
                )
              }
            >
              导出当前页 DXF
            </button>
          </>
        )}
        <span>{doc?.path}</span>
      </div>
      {doc ? (
        <>
          <div className="native-area">
            {scene ? (
              <ModelView scene={scene} selected={selection} onSelect={select} />
            ) : kind === "autocad" && snapshot ? (
              <DwgView
                snapshot={snapshot}
                selected={selection}
                select={select}
              />
            ) : (
              <div className="scroll">
                <pre>{text(snapshot)}</pre>
              </div>
            )}
            <div className="properties">
              <h3>{kind === "solidworks" ? "驱动尺寸" : "图纸对象"}</h3>
              {parameters.map((item) => (
                <button
                  disabled={working}
                  className={
                    selection === item.name ? "object active" : "object"
                  }
                  key={item.name}
                  onClick={() => select(item.name)}
                >
                  {item.name}
                  <br />
                  {item.unit === "m"
                    ? (item.value * 1000).toFixed(3) + " mm"
                    : item.value}
                </button>
              ))}
              {snapshot?.entities
                ?.filter(
                  (item: Data) => item.text !== undefined || item.text_position,
                )
                .map((item: Data) => (
                  <button
                    disabled={working}
                    className={
                      selection === item.handle ? "object active" : "object"
                    }
                    key={item.handle}
                    onClick={() => select(item.handle)}
                  >
                    {item.type} · {item.handle}
                  </button>
                ))}
              {parameter && (
                <>
                  <p className="muted">
                    {parameter.writable
                      ? "参数的工程作用尚未映射；只修改明确指定的尺寸。"
                      : parameter.block_reason}
                  </p>
                  <label>
                    目标尺寸 / mm
                    <input
                      type="number"
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                    />
                  </label>
                  <button
                    disabled={writeLocked || !parameter.writable || !draft}
                    onClick={() =>
                      act("修改并读回", async () => {
                        await invoke("parameter.change", {
                          ...bound(),
                          parameter_name: parameter.name,
                          expected_value: parameter.value,
                          value: Number(draft) / 1000,
                        });
                        await refresh();
                      })
                    }
                  >
                    修改并读回
                  </button>
                </>
              )}
              {entity && (
                <>
                  <pre>{text(entity)}</pre>
                  {entity.editable &&
                    ["TEXT", "MTEXT"].includes(entity.type) && (
                      <>
                        <label>
                          文字
                          <textarea
                            aria-label="文字"
                            value={draft}
                            onChange={(event) => setDraft(event.target.value)}
                          />
                        </label>
                        <button
                          disabled={writeLocked}
                          onClick={() =>
                            act("更新文字", async () => {
                              await invoke("drawing.edit_text", {
                                ...bound(),
                                handle: entity.handle,
                                text: draft,
                              });
                              await refresh();
                            })
                          }
                        >
                          更新文字
                        </button>
                      </>
                    )}
                  {entity.editable && entity.text_position && (
                    <>
                      <p>标注文字位置 · WCS · {doc.units}</p>
                      {["X", "Y", "Z"].map((axis, index) => (
                        <label key={axis}>
                          {axis}
                          <input
                            aria-label={"标注文字 " + axis}
                            type="number"
                            value={position[index]}
                            onChange={(event) =>
                              setPosition((values) =>
                                values.map((value, i) =>
                                  i === index ? event.target.value : value,
                                ),
                              )
                            }
                          />
                        </label>
                      ))}
                      <button
                        disabled={writeLocked}
                        onClick={() => act("移动标注文字", moveDimension)}
                      >
                        移动标注文字并读回
                      </button>
                    </>
                  )}
                </>
              )}
            </div>
          </div>
          <div className="native-status">
            {doc.dirty ? "有未保存修改" : "文档已保存"} · 修订 {doc.revision} ·{" "}
            {kind === "solidworks" ? doc.configuration : doc.units}
            {snapshot?.next_offset != null && (
              <>
                {" "}
                · 已读取 {snapshot.entities.length} / {snapshot.total_entities}{" "}
                个实体{" "}
                <button
                  disabled={working}
                  onClick={() => act("读取下一页实体", readMore)}
                >
                  继续读取
                </button>
              </>
            )}
          </div>
        </>
      ) : (
        <div className="empty">
          <h2>原生软件已连接</h2>
          <p>读取活动文档后显示真实模型与对象。</p>
        </div>
      )}
      {receipt && (
        <Collapsible
          defaultOpen
          className="native-receipt"
          title={
            <>
              原生回执
              {receipt.result?.status === "needs_review" ? " · 需要复核" : ""}
              {receipt.error?.outcome === "unknown" ? " · 结果待确认" : ""}
            </>
          }
        >
          <pre>{text(receipt)}</pre>
        </Collapsible>
      )}
    </div>
  );
}

function DwgView({
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
        <select
          value={current}
          onChange={(event) => setLayout(event.target.value)}
        >
          {layouts.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        <span>
          WCS 平面预览 · {rendered.filter((item: Data) => !item.node).length}{" "}
          个实体需原生视图检查
        </span>
      </div>
      <svg
        className="drawing"
        viewBox={`${minX - pad} ${-maxY - pad} ${maxX - minX + pad * 2} ${maxY - minY + pad * 2}`}
        style={{ color: "#263b39" }}
      >
        {rendered.map(({ entity, node }: Data) => (
          <g
            key={entity.handle}
            onClick={() => select(entity.handle)}
            fill="none"
            stroke={entity.handle === selected ? "#df673c" : "currentColor"}
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
