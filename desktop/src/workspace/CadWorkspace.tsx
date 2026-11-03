import { useState, useCallback, useEffect } from "react";
import { Button, Select } from "@fluentui/react-components";
import { EmbeddedCad } from "./EmbeddedCad";
import { FreeCadInspector } from "./FreeCadInspector";
import { CommercialDocument } from "./CommercialDocument";
import { Data, call } from "../api";
import { Project } from "../project/types";
export function CadWorkspace({
  visible,
  project,
  hosts,
  run,
  refresh,
  onContext,
  kind,
  setKind,
  focusRequest,
}: {
  visible: boolean;
  project: Project;
  hosts: Data[];
  run: any;
  refresh(): Promise<void>;
  onContext(value: Data): void;
  kind: string;
  setKind(kind: string): void;
  focusRequest: number;
}) {
  const [inspect, setInspect] = useState(true);
  useEffect(() => {
    if (focusRequest) setInspect(true);
  }, [focusRequest]);
  const freecadContext = useCallback(
    (value: Data) => {
      if (kind === "freecad") onContext(value);
    },
    [kind, onContext],
  );
  const solidworksContext = useCallback(
    (value: Data) => {
      if (kind === "solidworks") onContext(value);
    },
    [kind, onContext],
  );
  const autocadContext = useCallback(
    (value: Data) => {
      if (kind === "autocad") onContext(value);
    },
    [kind, onContext],
  );
  useEffect(() => {
    if (
      !visible ||
      inspect ||
      !hosts.some((h) => h.host === kind && h.connected)
    )
      return;
    let active = true,
      reading = false;
    const update = async () => {
      if (reading) return;
      reading = true;
      try {
        const h = hosts.find((h) => h.host === kind && h.connected);
        const value =
          kind === "freecad"
            ? await call("freecad.context")
            : await call("host.command", {
                host_id: h?.host_id,
                method: "document.context",
                params: {},
              });
        if (active)
          onContext(
            kind === "freecad"
              ? value
              : {
                  ...value.active_document,
                  document: value.active_document?.path,
                },
          );
      } catch (error) {
        if (active) onContext({ connection_error: String(error) });
      } finally {
        reading = false;
      }
    };
    void update();
    const timer = setInterval(update, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [visible, inspect, kind, hosts, onContext]);
  const [pending, setPending] = useState<Data | null>(() =>
    JSON.parse(localStorage.getItem("gongke.pending.freecad") || "null"),
  );
  function remember(value: Data | null) {
    setPending(value);
    if (value)
      localStorage.setItem("gongke.pending.freecad", JSON.stringify(value));
    else localStorage.removeItem("gongke.pending.freecad");
  }
  return (
    <div className="cad-workspace">
      <EmbeddedCad
        visible={visible && !inspect && kind !== "autocad"}
        kind={kind}
        focusRequest={focusRequest}
        refreshHosts={refresh}
        toolbarStart={
          <>
            <Select
              aria-label="原生软件"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                onContext({});
              }}
            >
              <option value="freecad">FreeCAD</option>
              <option value="solidworks">SOLIDWORKS</option>
              <option value="autocad">AutoCAD</option>
            </Select>
            {window.cadEmbed?.supported && kind !== "autocad" && (
              <Button
                appearance="subtle"
                size="small"
                onClick={() => setInspect(!inspect)}
              >
                {inspect ? "返回 CAD 编辑" : "工程检查"}
              </Button>
            )}
            {!window.cadEmbed?.supported && (
              <span className="muted">原生窗口嵌入需要 Windows</span>
            )}
          </>
        }
      />
      <div
        className="native-inspection"
        hidden={!inspect && kind !== "autocad"}
      >
        <div className="document-surface" hidden={kind !== "freecad"}>
          <FreeCadInspector
            project={project}
            run={run}
            onContext={freecadContext}
            onProjectChange={refresh}
            pendingOperation={pending}
            setPendingOperation={remember}
          />
        </div>
        {["solidworks", "autocad"].map((host) => (
          <div key={host} className="document-surface" hidden={kind !== host}>
            <CommercialDocument
              kind={host}
              host={hosts.find((h) => h.host === host && h.connected)}
              run={run}
              onContext={
                host === "solidworks" ? solidworksContext : autocadContext
              }
            />
          </div>
        ))}
      </div>
    </div>
  );
}
