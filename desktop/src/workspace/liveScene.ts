import { call, Data } from "../api";
import { sameDocument } from "../agent/modelingSteps";

// 网格只读一次；公共检查负责特征与边。读取期间换文档/修订时不拼接快照。
export async function readLiveScene(
  focus = "",
  request = call,
  expected?: Data,
) {
  const context = await request("freecad.context");
  const host = await request("host.context", { host_id: "freecad" });
  const document = host.active_document;
  const scene = await request("freecad.scene");
  if (expected && !sameDocument(expected, document)) focus = "";
  if (!document)
    return { context, scene, features: [], detail: null, selected: "" };
  if (
    context.session_id !== document.document_id ||
    context.revision !== document.revision ||
    scene.session_id !== document.document_id ||
    scene.revision !== document.revision
  )
    throw new Error("模型正在变化，等待下一次完成回执刷新");
  const current = host.documents.find((d: Data) =>
    sameDocument(d.document, document),
  );
  const snapshots: Data[] = [];
  for (const object of current?.objects || []) {
    const snapshot = await request("host.inspect", {
      host_id: "freecad",
      document,
      object_ref: object.native_ref,
    });
    if (snapshot.error)
      throw new Error(snapshot.error.message || String(snapshot.error));
    snapshots.push(snapshot);
  }
  let detail = snapshots.find((s) => s.object_ref === focus) || null;
  const features = [
    ...new Map(
      snapshots
        .flatMap((s) => s.features || [])
        .filter((f: Data) => !f.type?.startsWith("App::"))
        .map((f: Data) => [f.native_ref, f]),
    ).values(),
  ] as Data[];
  if (focus && !detail && features.some((f) => f.native_ref === focus)) {
    detail = await request("host.inspect", {
      host_id: "freecad",
      document,
      object_ref: focus,
    });
    if (detail?.error)
      throw new Error(detail.error.message || String(detail.error));
  }
  // 第一个实体形成之前，宿主 context 不列出空 Body；草图仍可按回执引用读取。
  if (focus && !detail && !features.length) {
    detail = await request("host.inspect", {
      host_id: "freecad",
      document,
      object_ref: focus,
    });
    if (detail?.error)
      throw new Error(detail.error.message || String(detail.error));
    features.push(...(detail?.features || []));
  }
  const after = await request("host.context", { host_id: "freecad" });
  if (!sameDocument(document, after.active_document))
    throw new Error("模型正在变化，等待下一次完成回执刷新");
  return {
    context,
    scene: { ...scene, nativeDocument: document, snapshots },
    features,
    detail,
    selected: focus,
  };
}
