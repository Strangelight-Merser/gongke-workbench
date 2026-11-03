import { Button } from "../ui/controls";
import { DataDetails } from "../ui/DataDetails";
import { useModelingProgress } from "./ModelingProgress";
import { modelResult, resultRef, stepInput, stepTitle } from "./modelingSteps";
export function ModelingSteps({ openModel }: { openModel(): void }) {
  const { steps, error, locate } = useModelingProgress();
  if (!steps.length && !error) return null;
  return (
    <section className="modeling-steps" aria-label="建模步骤">
      {error && <p role="status">读取建模步骤失败：{error}</p>}
      {steps.map((step) => {
        const result = modelResult(step),
          input = stepInput(step.command, step.params);
        const failed = !!result.error,
          done = step.phase === "finished";
        return (
          <details
            className="agent-tool"
            key={`${step.task_id}:${step.at}:${step.command}`}
          >
            <summary>
              {stepTitle(step.command, step.params)}
              <span>
                {!done
                  ? "进行中"
                  : failed
                    ? "失败"
                    : result.state && result.state !== "finished"
                      ? "结果待确认"
                      : result.status === "fail"
                        ? "尺寸不符"
                        : result.status === "unknown"
                          ? "待核实"
                          : "完成"}
              </span>
            </summary>
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
            {result.deleted_ref && <p>已删除 {result.deleted_ref}</p>}
            <DataDetails value={input} />
            <DataDetails value={step.result} />
          </details>
        );
      })}
    </section>
  );
}
