import { useCallback, useEffect, useRef, useState } from "react";
import { call, Data, errorText } from "../api";
import { Project } from "../project/types";
export function useProject() {
  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Data[]>([]);
  const [hosts, setHosts] = useState<Data[]>([]);
  const [online, setOnline] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const current = useRef("");
  const refreshVersion = useRef(0);
  const refresh = useCallback(async () => {
    const version = ++refreshVersion.current;
    const [status, p, t, h] = await Promise.allSettled([
      call("system.status"),
      call("project.current"),
      call("task.list"),
      call("hosts.list"),
    ]);
    if (version !== refreshVersion.current) return;
    setOnline(status.status === "fulfilled");
    if (p.status === "fulfilled") {
      current.current = p.value?.path || "";
      setProject(p.value?.path ? p.value : null);
    }
    if (t.status === "fulfilled")
      setTasks(Array.isArray(t.value) ? t.value : t.value.tasks || []);
    if (h.status === "fulfilled")
      setHosts(Array.isArray(h.value) ? h.value : h.value.hosts || []);
    if (status.status === "rejected") setError(errorText(status.reason));
  }, []);
  const run = useCallback(async (label: string, action: () => Promise<any>) => {
    setBusy(label);
    setError("");
    try {
      return await action();
    } catch (e) {
      setError(errorText(e));
      return null;
    } finally {
      setBusy("");
    }
  }, []);
  useEffect(() => {
    void refresh();
    return window.gongke.onEvent((event) => {
      if (event.project && event.project !== current.current) return;
      if (
        event.event === "task.updated" &&
        event.task.project === current.current
      ) {
        setTasks((items) => [
          event.task,
          ...items.filter((t) => t.task_id !== event.task.task_id),
        ]);
        if (!["running", "queued"].includes(event.task.status)) void refresh();
      }
      if (event.event === "service.error") setError(event.error.message);
      if (event.event === "service.stopped") {
        setOnline(false);
        setError(event.message);
      }
    });
  }, [refresh]);
  async function choose(create: boolean) {
    return run(create ? "新建工程" : "打开工程", async () => {
      const path = await window.gongke.chooseProject(create);
      if (!path) return;
      refreshVersion.current++;
      const result = await call(create ? "project.create" : "project.open", {
        path,
      });
      current.current = result.path;
      setProject(result);
      await refresh();
    });
  }
  return {
    project,
    setProject,
    tasks,
    hosts,
    online,
    error,
    setError,
    busy,
    refresh,
    run,
    choose,
  };
}
