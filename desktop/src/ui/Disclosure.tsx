import { ChevronRightRegular, ChevronDownRegular } from "@fluentui/react-icons";
import { Button } from "./controls";
import { useId, useState, type ReactNode } from "react";

export function Collapsible({
  title,
  children,
  defaultOpen = false,
  className = "",
}: {
  title: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <section className={"disclosure " + className}>
      <Button
        className="disclosure-toggle"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        <span className="disclosure-chevron" aria-hidden="true">
          {open ? <ChevronDownRegular /> : <ChevronRightRegular />}
        </span>
        {title}
      </Button>
      <div className="disclosure-grid" data-open={open}>
        <div
          id={id}
          className="disclosure-content"
          inert={!open}
          aria-hidden={!open}
        >
          <div className="disclosure-body">{children}</div>
        </div>
      </div>
    </section>
  );
}
