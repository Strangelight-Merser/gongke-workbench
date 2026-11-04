import { Button, Tab, TabList } from "@fluentui/react-components";
import { DismissRegular } from "@fluentui/react-icons";
import type { Data } from "../api";
import { ResizeHandle } from "../ui/ResizeHandle";
import { Checks } from "./Checks";
import { TaskList } from "./TaskList";
import type { ModelTarget } from "./modelChecks";
export type PanelTab = "checks" | "tasks" | "output";
export function OperationPanel({
  open,
  tab,
  onTab,
  height,
  onHeight,
  close,
  tasks,
  run,
  openCad,
  locate,
  output,
  error,
  problemCount,
}: {
  open: boolean;
  tab: PanelTab;
  onTab(tab: PanelTab): void;
  height: number;
  onHeight(height: number): void;
  close(): void;
  tasks: Data[];
  run: any;
  openCad(): void;
  locate(target: ModelTarget): Promise<void>;
  output: string[];
  error: string;
  problemCount: number;
}) {
  return (
    <>
      {open && (
        <ResizeHandle
          label="底部面板高度"
          value={height}
          min={120}
          max={Math.floor(innerHeight * 0.65)}
          horizontal
          reverse
          onChange={onHeight}
        />
      )}
      <section
        className="bottom-panel"
        aria-label="底部面板"
        hidden={!open}
        style={{ height, maxHeight: "65%" }}
      >
        <div className="panel-tabs">
          <TabList
            size="small"
            selectedValue={tab}
            onTabSelect={(_, d) => onTab(d.value as PanelTab)}
            aria-label="面板视图"
          >
            <Tab
              value="checks"
              id="panel-tab-checks"
              aria-controls="panel-checks"
            >
              问题{problemCount ? ` (${problemCount})` : ""}
            </Tab>
            <Tab value="tasks" id="panel-tab-tasks" aria-controls="panel-tasks">
              操作记录
            </Tab>
            <Tab
              value="output"
              id="panel-tab-output"
              aria-controls="panel-output"
            >
              输出 / 日志
            </Tab>
          </TabList>
          <span className="toolbar-space" />
          <Button
            appearance="subtle"
            size="small"
            aria-label="关闭底部面板"
            icon={<DismissRegular />}
            onClick={close}
          />
        </div>
        <div
          className="panel-content"
          role="tabpanel"
          id="panel-checks"
          aria-labelledby="panel-tab-checks"
          hidden={tab !== "checks"}
        >
          <Checks
            problemsOnly
            tasks={tasks}
            openCad={openCad}
            locate={locate}
          />
        </div>
        <div
          className="panel-content"
          role="tabpanel"
          id="panel-tasks"
          aria-labelledby="panel-tab-tasks"
          hidden={tab !== "tasks"}
        >
          <TaskList tasks={tasks} run={run} />
        </div>
        <div
          className="panel-content"
          role="tabpanel"
          id="panel-output"
          aria-labelledby="panel-tab-output"
          hidden={tab !== "output"}
        >
          <pre className="output-log">
            {output.length ? output.join("\n") : "尚无服务日志"}
            {error ? `\n${error}` : ""}
          </pre>
        </div>
      </section>
    </>
  );
}
