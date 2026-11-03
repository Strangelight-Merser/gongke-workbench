import { useEffect, useState } from "react";
import { Field, Input, Select } from "@fluentui/react-components";
import { call, Data, errorText } from "../api";
const groups: Record<string, string> = {
  gears: "齿轮参数",
  high: "高速级",
  low: "低速级",
  worm: "蜗杆传动",
  shaft: "轴",
  vbelt: "V 带",
  overrides: "教材查表系数",
  title: "任务名称",
};
// 字段、范围、默认值来自现有计算服务，不复制一份计算契约。
export function ConditionFields({
  task,
  onChange,
}: {
  task: Data;
  onChange(task: Data): void;
}) {
  const [schema, setSchema] = useState<Data>(),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    call("design.schema")
      .then((s) => {
        if (live) setSchema(s);
      })
      .catch((e) => {
        if (live) setError(errorText(e));
      });
    return () => {
      live = false;
    };
  }, []);
  function fields(
    properties: Data,
    value: Data,
    change: (v: Data) => void,
    prefix = "",
  ) {
    return Object.entries(properties).map(([key, raw]) => {
      if (
        !prefix &&
        ["scheme", "conveyor", "life", "bearing_life_years"].includes(key)
      )
        return null;
      if (
        prefix === "gears" &&
        ((task.scheme === "worm" && key !== "worm") ||
          (task.scheme !== "worm" && key === "worm") ||
          (["single", "worm"].includes(task.scheme) && key === "low"))
      )
        return null;
      if (key === "vbelt" && !["vbelt", "single"].includes(task.scheme))
        return null;
      const spec = raw.anyOf ? raw.anyOf[task.scheme === "bevel" ? 1 : 0] : raw;
      const path = prefix ? prefix + "." + key : key;
      const update = (next: unknown) => {
        const copy = { ...value };
        if (next === undefined) delete copy[key];
        else copy[key] = next;
        change(copy);
      };
      if (spec.type === "object")
        return (
          <details className="condition-group" key={key}>
            <summary>{groups[key] || spec.description || key}</summary>
            <div className="condition-fields">
              {fields(spec.properties, value[key] || {}, update, path)}
            </div>
          </details>
        );
      const label = groups[key] || spec.description || key;
      const hint =
        value[key] === undefined
          ? spec.default === undefined
            ? "未指定，由计算规则确定"
            : `默认：${spec.default}`
          : "本工程指定";
      return (
        <Field key={key} label={label} hint={hint}>
          {spec.enum || spec.type === "boolean" ? (
            <Select
              value={value[key] === undefined ? "" : String(value[key])}
              onChange={(e) =>
                update(
                  e.target.value === ""
                    ? undefined
                    : spec.type === "boolean"
                      ? e.target.value === "true"
                      : typeof spec.enum[0] === "number"
                        ? Number(e.target.value)
                        : e.target.value,
                )
              }
            >
              <option value="">使用默认值</option>
              {(spec.enum || [true, false]).map(
                (v: string | number | boolean) => (
                  <option value={String(v)} key={String(v)}>
                    {typeof v === "boolean" ? (v ? "是" : "否") : String(v)}
                  </option>
                ),
              )}
            </Select>
          ) : (
            <Input
              value={String(value[key] ?? "")}
              type={
                ["number", "integer"].includes(spec.type) ? "number" : "text"
              }
              min={spec.minimum}
              max={spec.maximum}
              step={spec.type === "integer" ? 1 : "any"}
              onChange={(_, d) =>
                update(
                  d.value === ""
                    ? undefined
                    : ["number", "integer"].includes(spec.type)
                      ? Number(d.value)
                      : d.value,
                )
              }
            />
          )}
        </Field>
      );
    });
  }
  return (
    <details className="condition-group">
      <summary>材料与计算参数</summary>
      {error ? (
        <p role="alert">{error}</p>
      ) : schema ? (
        <div className="condition-fields">
          {fields(schema.properties, task, onChange)}
        </div>
      ) : (
        <p>正在读取参数…</p>
      )}
    </details>
  );
}
