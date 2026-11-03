import { createContext, useContext, useEffect, useState } from "react";
import { call, Data, errorText } from "../api";
import { commandOf, modelingCommands } from "./modelingSteps";
const Context = createContext<{
  steps: Data[];
  error: string;
  target: Data | null;
  locate(step: Data): void;
}>({ steps: [], error: "", target: null, locate() {} });
export const useModelingProgress = () => useContext(Context);
export function ModelingProgress({
  project,
  children,
}: {
  project?: string;
  children: React.ReactNode;
}) {
  const [error, setError] = useState("");
  const [steps, setSteps] = useState<Data[]>([]),
    [target, setTarget] = useState<Data | null>(null);
  useEffect(() => {
    setSteps([]);
    setTarget(null);
    setError("");
    if (!project) return;
    let active = true;
    const add = (step: Data) => {
      if (
        !active ||
        !modelingCommands.has(commandOf(step.command, step.params))
      )
        return;
      setSteps((rows) => {
        const key = (s: Data) => `${s.task_id}:${s.at}:${s.command}`;
        const found = rows.find((s) => key(s) === key(step));
        if (found?.phase === "finished" && step.phase !== "finished")
          return rows;
        return [...rows.filter((s) => key(s) !== key(step)), step]
          .sort((a, b) => a.at.localeCompare(b.at))
          .slice(-200);
      });
    };
    const unsubscribe = window.gongke.onEvent((e) => {
      if (e.event === "task.receipt" && e.project === project)
        add({ ...e.receipt, task_id: e.task_id });
    });
    void call("task.list")
      .then(async (tasks) => {
        for (const task of tasks) {
          if (!active) break;
          if (
            task.project !== project ||
            !["mcp", "command"].includes(task.kind)
          )
            continue;
          const detail = await call("task.get", { task_id: task.task_id });
          for (const receipt of detail.receipts || [])
            add({ ...receipt, task_id: task.task_id });
        }
      })
      .catch((error) => {
        if (active) setError(errorText(error));
      });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [project]);
  return (
    <Context.Provider
      value={{
        steps,
        error,
        target,
        locate: (step) => setTarget({ ...step, requestedAt: Date.now() }),
      }}
    >
      {children}
    </Context.Provider>
  );
}
