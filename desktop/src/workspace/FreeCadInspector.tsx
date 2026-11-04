import { useModelingProgress } from "../agent/ModelingProgress";
import {
  commandOf,
  modelResult,
  resultRef,
  sameDocument,
  sameIdentity,
  serialRefresh,
  stepInput,
} from "../agent/modelingSteps";
import { readLiveScene } from "./liveScene";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Input } from "../ui/controls";
import { call, Data, errorText } from "../api";
import { DataDetails } from "../ui/DataDetails";
import { Collapsible } from "../ui/Disclosure";
import { Empty } from "../ui/Empty";
import { DrawingViewer } from "./DrawingViewer";
import { ModelView } from "./ModelView";
export function FreeCadInspector({
  hostInstance,
  project,
  run,
  onContext,
  onProjectChange,
  pendingOperation,
  setPendingOperation,
}: {
  project: Data | null;
  hostInstance: string | undefined;
  run: any;
  onContext: (data: Data) => void;
  onProjectChange: () => Promise<void>;
  pendingOperation: Data | null;
  setPendingOperation: (value: Data | null) => void;
}) {
  const [context, setContext] = useState<Data>({}),
    [scene, setScene] = useState<Data | null>(null),
    [selected, setSelected] = useState(""),
    [object, setObject] = useState<Data | null>(null),
    [preview, setPreview] = useState<Data | null>(null),
    [review, setReview] = useState<Data | null>(null),
    [diameter, setDiameter] = useState(""),
    [segment, setSegment] = useState(""),
    [page, setPage] = useState(""),
    [operation, setOperation] = useState(""),
    [connectionError, setConnectionError] = useState("");
  useEffect(() => {
    onContext({
      ...context,
      modified:
        scene?.revision === context.revision ? scene?.modified : undefined,
      selected_object: selected,
    });
  }, [context, scene, selected, onContext]);
  const [locateRequest, setLocateRequest] = useState(0);
  const select = useCallback(
    (id: string) => {
      setSelected(id);
      setLocateRequest((value) => value + 1);
      setObject(null);
      setPreview(null);
      setReview(null);
      if (context.session_id && !window.cadEmbed?.supported)
        run("选择原生对象", () =>
          call("freecad.select", {
            session_id: context.session_id,
            object_name: id,
            expected_revision: context.revision,
          }),
        );
    },
    [context.session_id, context.revision, run],
  );
  const { steps, target } = useModelingProgress();
  const locatedRequest = useRef<number | undefined>(undefined);
  const [features, setFeatures] = useState<Data[]>([]),
    [detail, setDetail] = useState<Data | null>(null);
  const focus = useRef("");
  const focusDocument = useRef<Data | undefined>(undefined);
  const live = useRef<ReturnType<typeof serialRefresh> | null>(null);
  const newest = [...steps]
    .reverse()
    .find(
      (s) =>
        s.phase === "finished" &&
        !!modelResult(s).document &&
        commandOf(s.command, s.params) !== "host.check" &&
        s.params?.host_id === "freecad",
    );
  useEffect(() => {
    let active = true;
    const queue = serialRefresh(
      async () => {
        const value = await readLiveScene(
          focus.current,
          call,
          focusDocument.current,
        );
        if (!active) return;
        setConnectionError("");
        setContext(value.context);
        setScene(value.scene);
        setFeatures(value.features);
        setDetail(value.detail);
        setSelected(value.selected);
        setPreview(null);
        setReview(null);
        setObject(null);
      },
      (error) => {
        if (active) setConnectionError(errorText(error));
      },
    );
    live.current = queue;
    void queue.request();
    return () => {
      active = false;
      queue.close();
    };
  }, [project?.path, hostInstance]);
  useEffect(() => {
    if (!newest) return;
    focusDocument.current = modelResult(newest).document;
    const p = stepInput(newest.command, newest.params);
    focus.current =
      modelResult(newest).outcome !== "committed" ||
      modelResult(newest).deleted_ref
        ? ""
        : resultRef(modelResult(newest), p);
    // 空 Body 尚无可读取的形体。
    if (
      ["host.model_new", "host.body", "host.model_copy"].includes(
        commandOf(newest.command, newest.params),
      )
    )
      focus.current = "";
    void live.current?.request();
  }, [newest]);
  const refresh = async () => {
    await live.current?.request();
  };
  const check = [...steps]
    .reverse()
    .find(
      (s) =>
        s.result?.checks &&
        (!newest ||
          sameDocument(modelResult(newest).document, scene?.nativeDocument)) &&
        sameDocument(s.result.document, scene?.nativeDocument),
    )?.result;
  useEffect(() => {
    if (
      !target ||
      target.params?.host_id !== "freecad" ||
      !scene?.nativeDocument ||
      locatedRequest.current === target.requestedAt
    )
      return;
    locatedRequest.current = target.requestedAt;
    if (
      !(modelResult(target).checks ? sameDocument : sameIdentity)(
        modelResult(target).document,
        scene?.nativeDocument,
      )
    ) {
      setConnectionError("该步骤属于旧文档或旧修订，请在当前特征树中选择对象");
      return;
    }
    const id = resultRef(
      modelResult(target),
      stepInput(target.command, target.params),
    );
    if (id && features.some((f) => f.native_ref === id)) {
      setSelected(id);
      setPage("");
      setLocateRequest((value) => value + 1);
    } else if (id) setConnectionError("该特征已不在当前模型中");
  }, [target, scene?.nativeDocument]);
  useEffect(() => {
    if (!selected || !scene?.nativeDocument) {
      setDetail(null);
      return;
    }
    if (
      detail?.object_ref === selected &&
      sameDocument(detail.document, scene.nativeDocument)
    )
      return;
    let active = true;
    call("host.inspect", {
      host_id: "freecad",
      document: scene.nativeDocument,
      object_ref: selected,
    })
      .then((value) => {
        if (active) {
          if (value.error) throw new Error(value.error.message);
          setDetail(value);
        }
      })
      .catch((error) => {
        if (active) {
          setDetail(null);
          setConnectionError(errorText(error));
        }
      });
    return () => {
      active = false;
    };
  }, [selected, scene?.nativeDocument]);
  useEffect(() => {
    if (!selected || !context.session_id) return;
    let current = true;
    const item = context.objects?.find(
      (o: Data) => o.name === selected || o.entity_id === selected,
    );
    if (item)
      call("freecad.read", {
        session_id: context.session_id,
        entity_id: item.entity_id,
      })
        .then((result) => {
          if (!current) return;
          setObject(result);
          const editable = result.snapshot?.segments?.find(
            (s: Data) => s.editable,
          );
          if (editable) {
            setSegment(editable.segment_id);
            setDiameter(String(editable.diameter_m * 1000));
          }
        })
        .catch((error) => {
          if (current)
            setObject({ supported: false, reason: errorText(error) });
        });
    return () => {
      current = false;
    };
  }, [selected, context]);
  useEffect(() => {
    if (!window.cadEmbed?.supported || !selected || !scene?.session_id) return;
    void call("freecad.select", {
      session_id: scene.session_id,
      expected_revision: scene.revision,
      object_name: selected,
    }).catch((error) => setConnectionError(errorText(error)));
  }, [selected, scene?.session_id, scene?.revision]);
  const params = {
    session_id: context.session_id,
    entity_id: object?.entity_id,
  };
  return (
    <div className="native">
      <div className="toolbar">
        <Button
          appearance="primary"
          onClick={() => run("读取原生工程", refresh)}
        >
          读取 FreeCAD 工程
        </Button>
        {context.session_id && (
          <>
            <Button
              disabled={!!pendingOperation}
              onClick={() =>
                run("保存原生工程", async () => {
                  await call("freecad.save", {
                    session_id: context.session_id,
                    path:
                      "revisions/native-" +
                      crypto.randomUUID().slice(0, 12) +
                      "/shaft.FCStd",
                  });
                  await refresh();
                  await onProjectChange();
                })
              }
            >
              另存工作修订
            </Button>
            <Button
              disabled={!operation || !!pendingOperation}
              onClick={() =>
                run("撤销", async () => {
                  await call("freecad.undo", {
                    session_id: context.session_id,
                    operation_id: operation,
                  });
                  setOperation("");
                  await refresh();
                })
              }
            >
              撤销本次修改
            </Button>
          </>
        )}
        <span>{context.path || ""}</span>
      </div>
      {pendingOperation && (
        <div className="error">
          <span>修改结果待确认，已暂停继续写入。</span>
          <Button
            onClick={() =>
              run("查询原生回执", async () => {
                const result = await call(
                  "freecad.operation",
                  pendingOperation,
                );
                if (
                  result.state === "committed" ||
                  result.state === "not_found"
                ) {
                  setOperation(
                    result.state === "committed" && !result.undone
                      ? pendingOperation.operation_id
                      : "",
                  );
                  setPendingOperation(null);
                  await refresh();
                }
              })
            }
          >
            查询修改结果
          </Button>
        </div>
      )}
      {connectionError && scene && (
        <div className="error" role="status">
          {connectionError}
        </div>
      )}
      {!scene ? (
        <Empty
          title={connectionError ? "原生连接已中断" : "读取正在编辑的工程"}
          body={
            connectionError ||
            "在 FreeCAD 中启用 GongKe 工作台后，模型和 TechDraw 图纸会显示在这里。SOLIDWORKS 与 AutoCAD 需要 Windows 宿主插件。"
          }
        />
      ) : (
        <>
          <div className="native-tabs">
            <Button
              className={!page ? "active" : ""}
              onClick={() => setPage("")}
            >
              三维模型
            </Button>
            {scene.pages?.map((p: Data) => (
              <Button
                key={p.name}
                className={page === p.name ? "active" : ""}
                onClick={() => setPage(p.name)}
              >
                {p.label}
              </Button>
            ))}
          </div>
          <div className="native-area">
            <div className="page-view" hidden={!page}>
              {scene.pages?.map((p: Data) => (
                <div
                  className="page-view"
                  key={p.name}
                  hidden={page !== p.name}
                >
                  {p.error ? (
                    <Empty title="图纸预览未就绪" body={p.error} />
                  ) : (
                    <DrawingViewer svg={p.svg || ""} />
                  )}
                </div>
              ))}
              <div className="toolbar">
                <Button
                  disabled={!!pendingOperation}
                  onClick={() =>
                    run("更新原生图纸", async () => {
                      await call("freecad.update_drawing", {
                        session_id: context.session_id,
                        page_name: page,
                        expected_revision: context.revision,
                      });
                      await refresh();
                    })
                  }
                >
                  更新图纸
                </Button>
                {project && (
                  <Button
                    disabled={!!pendingOperation}
                    onClick={() =>
                      run("导出原生 DXF", async () => {
                        await call("freecad.export_drawing", {
                          session_id: context.session_id,
                          page_name: page,
                          expected_revision: context.revision,
                        });
                        await onProjectChange();
                      })
                    }
                  >
                    导出 DXF 修订
                  </Button>
                )}
              </div>
            </div>
            <div className="model-document" hidden={!!page}>
              <ModelView
                scene={scene}
                selected={selected}
                onSelect={select}
                detail={detail}
                focusRequest={locateRequest}
                checks={check}
              />
            </div>
            <div className="properties">
              <h3>特征树</h3>
              {features.map((f: Data) => (
                <Button
                  key={f.native_ref}
                  className={
                    selected === f.native_ref ? "object active" : "object"
                  }
                  style={{ paddingLeft: f.parent ? 24 : 8 }}
                  onClick={() => select(f.native_ref)}
                >
                  {f.label}
                  {f.sketch ? " · 草图" : ""}
                </Button>
              ))}
              {check?.checks
                ?.filter((c: Data) => c.status !== "pass")
                .map((c: Data) => (
                  <div className="error" key={c.id}>
                    {c.id} · {c.status === "fail" ? "不符" : "待核实"}
                    {!c.actual?.locations?.length && " · 无可定位实体"}
                  </div>
                ))}
              {!features.length &&
                scene.objects?.map((o: Data) => (
                  <Button
                    className={selected === o.id ? "object active" : "object"}
                    key={o.id}
                    onClick={() => select(o.id)}
                  >
                    {o.label}
                  </Button>
                ))}
              {object?.supported ? (
                <>
                  <h3>原生尺寸</h3>
                  {object.snapshot?.segments?.map((s: Data) => (
                    <div key={s.segment_id} className="property">
                      <span>{s.segment_id}</span>
                      <strong>⌀ {(s.diameter_m * 1000).toFixed(2)} mm</strong>
                    </div>
                  ))}
                  {segment && (
                    <>
                      <label>
                        目标直径 / mm
                        <Input
                          aria-label="目标直径"
                          type="number"
                          value={diameter}
                          onChange={(e) => {
                            setDiameter(e.target.value);
                            setPreview(null);
                          }}
                        />
                      </label>
                      <Button
                        onClick={() =>
                          run("比较修改", async () =>
                            setPreview(
                              await call("freecad.preview", {
                                ...params,
                                segment_id: segment,
                                diameter_m: Number(diameter) / 1000,
                              }),
                            ),
                          )
                        }
                      >
                        计算修改影响
                      </Button>
                    </>
                  )}
                  <Button
                    onClick={() =>
                      run("原生校核", async () =>
                        setReview(await call("freecad.review", params)),
                      )
                    }
                  >
                    校核当前模型
                  </Button>
                </>
              ) : (
                <p className="muted">{object?.reason}</p>
              )}
              {preview && (
                <div className="candidate">
                  <h3>修改比较</h3>
                  <DataDetails value={preview} />
                  <Button
                    appearance="primary"
                    disabled={!preview.change_id || !!pendingOperation}
                    onClick={() =>
                      run("应用原生修改", async () => {
                        const operation_id = crypto.randomUUID();
                        setPendingOperation({
                          session_id: context.session_id,
                          operation_id,
                        });
                        await call("freecad.apply", {
                          session_id: context.session_id,
                          change_id: preview.change_id,
                          operation_id,
                        });
                        setPendingOperation(null);
                        setOperation(operation_id);
                        await refresh();
                      })
                    }
                  >
                    应用修改
                  </Button>
                </div>
              )}
              {review && (
                <Collapsible title="校核结果" defaultOpen>
                  <DataDetails value={review} />
                </Collapsible>
              )}
            </div>
          </div>
          <div className="native-status">
            {scene.modified ? "有未保存修改" : "文档已保存"} · 修订{" "}
            {scene.revision} · {scene.objects?.length || 0} 个对象
            {scene.needs_rebuild ? " · 需要重建" : ""}
          </div>
        </>
      )}
    </div>
  );
}
