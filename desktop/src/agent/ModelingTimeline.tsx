import { Button } from "../ui/controls";
import { ToolDetails, CompletedTools, toolState, toolStates } from "./ToolCall";
import { groupCompletedTools } from "./events";
import { useModelingProgress } from "./ModelingProgress";
import { modelResult, resultRef, stepInput, stepTitle } from "./modelingSteps";
export function ModelingSteps({ openModel }: { openModel(): void }) {
  const { steps, error, locate } = useModelingProgress();
  if (!steps.length && !error) return null;
  return (
    <section className="modeling-steps" aria-label="建模步骤">
      {error && <p role="status">读取建模步骤失败：{error}</p>}
      {groupCompletedTools(
        steps.map((step) => ({ kind: "tool", tool: step })),
        (step) =>
          step.phase === "finished" &&
          toolState("completed", modelResult(step)) === "completed",
      ).map((row) =>
        row.kind === "tool-group" ? (
          <CompletedTools key={row.tools![0].at} count={row.tools!.length}>
            {row.tools!.map(renderStep)}
          </CompletedTools>
        ) : (
          renderStep(row.tool)
        ),
      )}
    </section>
  );
  function renderStep(step: import("../api").Data) {
    const result = modelResult(step),
      input = stepInput(step.command, step.params);
    const failed = !!result.error,
      done = step.phase === "finished";
    return (
      <details
        className="agent-tool"
        data-state={toolState(done ? "completed" : "in_progress", result)}
        key={`${step.task_id}:${step.at}:${step.command}`}
      >
        <summary>
          <span className="tool-title">
            {stepTitle(step.command, step.params)}
          </span>
          <span className="tool-status">
            {toolState(done ? "completed" : "in_progress", result) ===
              "failed" && !failed
              ? "尺寸不符"
              : toolStates[
                  toolState(done ? "completed" : "in_progress", result)
                ]}
          </span>
        </summary>
        <ToolDetails result={result} raw={step}>
          {done &&
            !failed &&
            result.document &&
            !result.deleted_ref &&
            (resultRef(result, input) || result.checks) && (
              <Button
                onClick={() => {
                  locate(step);
                  openModel();
                }}
              >
                在模型中定位
              </Button>
            )}
        </ToolDetails>
      </details>
    );
  }
}
