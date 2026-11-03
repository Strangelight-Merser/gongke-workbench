import { useRef } from "react";
import { call, Data, errorText } from "../api";
import {
  pendingKey,
  savedPending,
  registeredWorkingCopy,
} from "./nativeOperations";
export function useDxfImport(
  file: Data,
  hosts: Data[],
  run: any,
  refresh: () => Promise<void>,
  showAutoCadDocument: () => void,
) {
  const importingDxf = useRef(false);
  function forget() {
    localStorage.removeItem(pendingKey("autocad"));
    window.dispatchEvent(new Event("gongke-native-pending"));
  }
  async function importDxf() {
    if (importingDxf.current || !file) return;
    importingDxf.current = true;
    const showAutoCad = () => {
      showAutoCadDocument();
    };
    try {
      await run("导入 AutoCAD", async () => {
        if (savedPending("autocad")) {
          showAutoCad();
          throw new Error(
            "上一次原生操作尚待确认，请查询原操作；本次未重复导入",
          );
        }
        const host = hosts.find((h) => h.host === "autocad" && h.connected);
        if (!host) throw new Error("AutoCAD 尚未连接");
        const operation_id = crypto.randomUUID();
        const request = {
          host_id: host.host_id,
          method: "drawing.import_dxf",
          operation_id,
          params: {
            source_path: file.path,
            target_path:
              "revisions/dwg-" +
              crypto.randomUUID().slice(0, 12) +
              "/drawing.dwg",
            operation_id,
          },
        };
        const remember = (value: Data) => {
          localStorage.setItem(pendingKey("autocad"), JSON.stringify(value));
          window.dispatchEvent(new Event("gongke-native-pending"));
        };
        remember({ ...request, state: "submitted" });
        let result: Data;
        try {
          result = await call("host.command", {
            host_id: request.host_id,
            method: request.method,
            params: request.params,
          });
        } catch (error) {
          remember({
            ...request,
            error: { message: errorText(error), outcome: "unknown" },
          });
          showAutoCad();
          throw error;
        }
        if (result.error) {
          if (result.error.outcome === "unknown") {
            remember({ ...request, ...result });
            showAutoCad();
          } else forget();
          throw new Error(result.error.message);
        }
        remember({ ...request, result });
        try {
          if (result.outcome !== "committed")
            throw new Error("导入结果尚未确认，请查询原操作回执");
          const { path } = await registeredWorkingCopy("autocad", request);
          const opened = await call("host.command", {
            host_id: host.host_id,
            method: "document.open",
            params: { path, operation_id: crypto.randomUUID() },
          });
          if (opened.error) throw new Error(opened.error.message);
          forget();
          showAutoCad();
          await refresh();
        } catch (error) {
          showAutoCad();
          throw error;
        }
      });
    } finally {
      importingDxf.current = false;
    }
  }
  return importDxf;
}
