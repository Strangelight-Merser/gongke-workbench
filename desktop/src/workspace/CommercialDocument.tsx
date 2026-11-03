import { useEffect } from "react";
import { Button, Input, Textarea } from "../ui/controls";
import { Data } from "../api";
import { DataDetails } from "../ui/DataDetails";
import { ModelView } from "./ModelView";
import { Collapsible } from "../ui/Disclosure";
import { DwgView } from "./DwgView";
import { useCommercialDocument } from "./useCommercialDocument";
export function CommercialDocument({
  host,
  kind,
  run,
  onContext,
}: {
  host: Data | undefined;
  kind: string;
  run: any;
  onContext(value: Data): void;
}) {
  const {
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
  } = useCommercialDocument(host, kind, run);
  useEffect(() => {
    if (doc)
      onContext({
        document: doc.path,
        dirty: doc.dirty,
        revision: doc.revision,
        selected_object: selection,
      });
  }, [doc, selection, onContext]);
  const unresolved = pending && (
    <div role="alert" className="error">
      <strong>原操作结果待确认，修改已暂停</strong>
      <p>
        {pending.method} · {pending.operation_id}
      </p>
      <Button
        disabled={working}
        onClick={() => act("查询原操作", queryPending)}
      >
        查询原操作结果
      </Button>
      <p>查询不会再次执行原操作；确认并登记成功的工作副本会自动打开。</p>
    </div>
  );
  if (!host?.connected)
    return (
      <div className="empty">
        {unresolved}

        <h2>{kind === "solidworks" ? "SOLIDWORKS" : "AutoCAD"}</h2>
        <p>
          请在 Windows
          安装对应的原生插件并启动软件，再刷新连接。当前机器没有可用连接。
        </p>

        {receipt && <DataDetails value={receipt} />}
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
        <Button
          appearance="primary"
          disabled={working}
          onClick={() => act("读取原生工程", refresh)}
        >
          读取当前工程
        </Button>
        {doc && (
          <Button
            disabled={writeLocked}
            onClick={() => act("建立工作修订", copy)}
          >
            另存工作修订
          </Button>
        )}
        {kind === "solidworks" && doc?.document_type === 3 && (
          <>
            <Button
              disabled={writeLocked}
              onClick={() =>
                act("更新原生图纸", async () => {
                  await invoke("drawing.update", bound());
                  await refresh();
                })
              }
            >
              更新图纸
            </Button>
            <Button
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
            </Button>
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
                <DataDetails value={snapshot} />
              </div>
            )}
            <div className="properties">
              <h3>{kind === "solidworks" ? "驱动尺寸" : "图纸对象"}</h3>
              {parameters.map((item) => (
                <Button
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
                </Button>
              ))}
              {snapshot?.entities
                ?.filter(
                  (item: Data) => item.text !== undefined || item.text_position,
                )
                .map((item: Data) => (
                  <Button
                    disabled={working}
                    className={
                      selection === item.handle ? "object active" : "object"
                    }
                    key={item.handle}
                    onClick={() => select(item.handle)}
                  >
                    {item.type} · {item.handle}
                  </Button>
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
                    <Input
                      type="number"
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                    />
                  </label>
                  <Button
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
                  </Button>
                </>
              )}
              {entity && (
                <>
                  <DataDetails value={entity} />
                  {entity.editable &&
                    ["TEXT", "MTEXT"].includes(entity.type) && (
                      <>
                        <label>
                          文字
                          <Textarea
                            aria-label="文字"
                            value={draft}
                            onChange={(event) => setDraft(event.target.value)}
                          />
                        </label>
                        <Button
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
                        </Button>
                      </>
                    )}
                  {entity.editable && entity.text_position && (
                    <>
                      <p>标注文字位置 · WCS · {doc.units}</p>
                      {["X", "Y", "Z"].map((axis, index) => (
                        <label key={axis}>
                          {axis}
                          <Input
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
                      <Button
                        disabled={writeLocked}
                        onClick={() => act("移动标注文字", moveDimension)}
                      >
                        移动标注文字并读回
                      </Button>
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
                <Button
                  disabled={working}
                  onClick={() => act("读取下一页实体", readMore)}
                >
                  继续读取
                </Button>
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
          <DataDetails value={receipt} />
        </Collapsible>
      )}
    </div>
  );
}
