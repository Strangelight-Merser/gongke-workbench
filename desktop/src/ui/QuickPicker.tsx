import { useEffect, useState } from "react";
import {
  Dialog,
  DialogSurface,
  DialogBody,
  Input,
} from "@fluentui/react-components";
export type QuickItem = {
  id: string;
  label: string;
  detail?: string;
  shortcut?: string;
  run(): void;
};
export function QuickPicker({
  mode,
  items,
  close,
}: {
  mode: "commands" | "files";
  items: QuickItem[];
  close(): void;
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const filtered = items.filter((i) =>
    `${i.label} ${i.detail || ""}`
      .toLowerCase()
      .includes(query.replace(/^>/, "").toLowerCase()),
  );
  useEffect(() => setSelected(0), [query]);
  function execute(index: number) {
    const item = filtered[index];
    if (item) {
      close();
      item.run();
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(_, d) => {
        if (!d.open) close();
      }}
    >
      <DialogSurface
        className="quick-picker"
        aria-label={mode === "commands" ? "命令面板" : "快速打开"}
      >
        <DialogBody>
          <Input
            autoFocus
            aria-label={mode === "commands" ? "搜索命令" : "搜索工程文件"}
            placeholder={
              mode === "commands" ? "> 输入命令名称" : "按名称搜索工程文件"
            }
            value={query}
            onChange={(_, d) => setQuery(d.value)}
            role="combobox"
            aria-expanded
            aria-controls="quick-results"
            aria-activedescendant={
              filtered[selected] ? `quick-${selected}` : undefined
            }
            onKeyDown={(e) => {
              if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                setSelected((i) =>
                  Math.max(
                    0,
                    Math.min(
                      filtered.length - 1,
                      i + (e.key === "ArrowDown" ? 1 : -1),
                    ),
                  ),
                );
              }
              if (e.key === "Enter") {
                e.preventDefault();
                execute(selected);
              }
            }}
          />
          <div role="listbox" id="quick-results" className="quick-results">
            {filtered.map((item, i) => (
              <div
                role="option"
                id={`quick-${i}`}
                aria-selected={i === selected}
                key={item.id}
                onMouseMove={() => setSelected(i)}
                onClick={() => execute(i)}
                ref={(el) => {
                  if (i === selected) el?.scrollIntoView({ block: "nearest" });
                }}
              >
                <span>
                  {item.label}
                  <small>{item.detail}</small>
                </span>
                <kbd>{item.shortcut}</kbd>
              </div>
            ))}
            {!filtered.length && <p className="pane-empty">没有匹配项</p>}
          </div>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}
