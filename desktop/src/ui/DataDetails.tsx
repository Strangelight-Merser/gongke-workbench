import { ReactNode } from "react";
const labels: Record<string, string> = {
  status: "状态",
  state: "状态",
  outcome: "结果",
  error: "错误",
  message: "说明",
  result: "结果",
  method: "操作",
  command: "命令",
  operation_id: "操作编号",
  session_id: "会话",
  host_id: "宿主",
  revision: "修订",
  expected_revision: "预期修订",
  document_path: "文档",
  path: "路径",
  checks: "检查",
  item: "检查项",
  detail: "依据",
  ok: "通过",
  utilization: "利用率",
  before: "修改前",
  after: "修改后",
  changes: "变化",
  warnings: "提示",
  readback: "读回结果",
  readback_matches: "读回一致",
  rebuilt: "重建完成",
  title: "名称",
  name: "名称",
  value: "值",
  unit: "单位",
  type: "类型",
  params: "参数",
  response: "回执",
  query: "查询结果",
  initial_error: "首次响应",
};
/** 工程回执按字段查看；原始键保留，以免把未知工程量错误翻译。 */
export function DataDetails({ value }: { value: unknown }) {
  if (value == null) return null;
  if (typeof value !== "object")
    return (
      <span>
        {typeof value === "boolean" ? (value ? "是" : "否") : String(value)}
      </span>
    );
  const entries = Array.isArray(value)
    ? value.map((v, i) => [String(i + 1), v])
    : Object.entries(value);
  return (
    <dl className="data-details">
      {entries.map(([key, item]) => (
        <div key={key as string}>
          <dt>{labels[key as string] || (key as ReactNode)}</dt>
          <dd>
            <DataDetails value={item} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
