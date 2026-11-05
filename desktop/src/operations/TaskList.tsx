import { useState } from "react";
import { Button } from "../ui/controls";
import { call, Data } from "../api";
import { Empty } from "../ui/Empty";
import { Collapsible } from "../ui/Disclosure";
import { DataDetails } from "../ui/DataDetails";
const statuses: Data = {
  queued: "排队中",
  running: "执行中",
  complete: "已完成",
  failed: "未完成",
  canceled: "已取消",
  interrupted: "已中断",
  partial: "部分完成",
  needs_attention: "需检查",
};
const kinds: Data = {
  "revision.inspect": "检查模型与图纸",
  execution: "工程操作",
};
export function TaskList({ tasks, run }: { tasks: Data[]; run: any }) {
  const [details, setDetails] = useState<Data>({});
  return (
    <div className="task-list">
      {!tasks.length && (
        <Empty
          title="还没有任务"
          body="计算、模型修改和工程助手的执行状态会保存在这里。"
        />
      )}
      {tasks.map((task: Data) => (
        <article className="task" data-kind={task.kind} key={task.task_id}>
          <div>
            <strong>{task.title || kinds[task.kind] || "工程操作"}</strong>
            <span className={"task-status " + task.status}>
              {statuses[task.status] || task.status}
            </span>
          </div>
          <p>{task.message || task.stage || ""}</p>
          {task.error && (
            <div className="error">
              <DataDetails value={task.error} />
            </div>
          )}
          {["running", "queued"].includes(task.status) && (
            <Button
              onClick={() =>
                run("取消任务", () =>
                  call("task.cancel", { task_id: task.task_id }),
                )
              }
            >
              取消待执行操作
            </Button>
          )}
          <Button
            onClick={() =>
              run("读取回执", async () => {
                const detail = await call("task.get", {
                  task_id: task.task_id,
                });
                setDetails((items) => ({ ...items, [task.task_id]: detail }));
              })
            }
          >
            查看操作回执
          </Button>
          {details[task.task_id] && (
            <div>
              {details[task.task_id].receipts.length ? (
                details[task.task_id].receipts.map(
                  (receipt: Data, i: number) => (
                    <Collapsible key={i} title={receipt.command}>
                      <DataDetails value={receipt} />
                    </Collapsible>
                  ),
                )
              ) : (
                <p className="hint">此任务没有工具操作回执。</p>
              )}
            </div>
          )}
          {task.result && (
            <Collapsible title="结果">
              <DataDetails value={task.result} />
            </Collapsible>
          )}
        </article>
      ))}
    </div>
  );
}
