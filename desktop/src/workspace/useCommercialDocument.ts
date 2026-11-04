import { useCallback, useEffect, useRef, useState } from "react";
import { call, Data } from "../api";
import {
  mutations,
  normalPath,
  pendingKey,
  savedPending,
  registeredWorkingCopy,
  operationResult,
} from "../operations/nativeOperations";
export function useCommercialDocument(
  host: Data | undefined,
  kind: string,
  run: any,
) {
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
  useEffect(() => {
    const update = () => {
      const value = savedPending(kind);
      setPending(value);
      setReceipt(value);
    };
    window.addEventListener("gongke-native-pending", update);
    return () => window.removeEventListener("gongke-native-pending", update);
  }, [kind]);
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
      if (!c.active_document.path)
        throw new Error("当前文档尚未保存；请先在 SOLIDWORKS 中另存为原生文档");
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
  return {
    context,
    scene,
    parameters,
    snapshot,
    selection,
    draft,
    setDraft,
    position,
    setPosition,
    receipt,
    pending,
    reviewRequired,
    working,
    doc,
    writeLocked,
    parameter,
    entity,
    act,
    invoke,
    refresh,
    readMore,
    bound,
    select,
    copy,
    queryPending,
    moveDimension,
  };
}
