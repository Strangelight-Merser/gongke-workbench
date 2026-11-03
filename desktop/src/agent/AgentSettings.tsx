import { useState } from "react";
import {
  Dialog,
  DialogSurface,
  DialogBody,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Field,
  Input,
  Textarea,
  Select,
} from "@fluentui/react-components";
import { DismissRegular, AddRegular } from "@fluentui/react-icons";
import {
  AgentSettings as Settings,
  StdioCommand,
} from "../../electron/acp/types.cjs";
export function AgentSettings({
  value,
  close,
  save,
}: {
  value: Settings;
  close(): void;
  save(value: Settings): Promise<void>;
}) {
  const [settings, setSettings] = useState<Settings>(structuredClone(value));
  const [id, setId] = useState(value.agents[0].id);
  const [error, setError] = useState("");
  const target =
    id === "$mcp" ? settings.mcp : settings.agents.find((a) => a.id === id)!;
  function update(change: Partial<StdioCommand>) {
    setSettings((s) =>
      id === "$mcp"
        ? { ...s, mcp: { ...s.mcp, ...change } }
        : {
            ...s,
            agents: s.agents.map((a) =>
              a.id === id ? { ...a, ...change } : a,
            ),
          },
    );
  }
  return (
    <Dialog
      open
      onOpenChange={(_, d) => {
        if (!d.open) close();
      }}
    >
      <DialogSurface className="agent-settings">
        <DialogBody>
          <DialogTitle
            action={
              <Button
                appearance="subtle"
                icon={<DismissRegular />}
                aria-label="关闭连接设置"
                onClick={close}
              />
            }
          >
            Agent 连接设置
          </DialogTitle>
          <DialogContent>
            <Field label="配置对象">
              <Select value={id} onChange={(e) => setId(e.target.value)}>
                {settings.agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
                <option value="$mcp">工程工具服务</option>
              </Select>
            </Field>
            <Field label="程序路径">
              <Input
                value={target.command}
                onChange={(_, d) => update({ command: d.value })}
              />
            </Field>
            <Field
              label="启动参数"
              hint="每行一个参数；${project} 表示当前工程目录。"
            >
              <Textarea
                value={target.args.join("\n")}
                onChange={(_, d) => update({ args: d.value.split("\n") })}
                resize="vertical"
              />
            </Field>
            <h3>环境变量</h3>
            {Object.entries(target.env).map(([key, val], i) => (
              <div className="env-row" key={i}>
                <Input
                  aria-label={`变量名 ${i + 1}`}
                  value={key}
                  onChange={(_, d) =>
                    update({
                      env: Object.fromEntries(
                        Object.entries(target.env).map((row, j) =>
                          j === i ? [d.value, row[1]] : row,
                        ),
                      ),
                    })
                  }
                />
                <Input
                  aria-label={`变量值 ${i + 1}`}
                  value={val}
                  onChange={(_, d) =>
                    update({ env: { ...target.env, [key]: d.value } })
                  }
                />
                <Button
                  icon={<DismissRegular />}
                  aria-label={`删除变量 ${key}`}
                  onClick={() =>
                    update({
                      env: Object.fromEntries(
                        Object.entries(target.env).filter(([k]) => k !== key),
                      ),
                    })
                  }
                />
              </div>
            ))}
            <Button
              size="small"
              icon={<AddRegular />}
              onClick={() =>
                update({
                  env: {
                    ...target.env,
                    ["VARIABLE_" + (Object.keys(target.env).length + 1)]: "",
                  },
                })
              }
            >
              添加变量
            </Button>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={close}>取消</Button>
            <Button
              appearance="primary"
              onClick={async () => {
                try {
                  await save(settings);
                  close();
                } catch (e) {
                  setError(String(e));
                }
              }}
            >
              保存
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}
