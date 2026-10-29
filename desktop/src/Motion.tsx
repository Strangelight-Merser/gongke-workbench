import { useId, useState, type ReactNode } from "react";
import type { Data } from "./api";

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
      <button
        className="disclosure-toggle"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        <span className="disclosure-chevron" aria-hidden="true">
          ›
        </span>
        {title}
      </button>
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

export function StreamText({
  content,
  fragments,
  streaming = false,
}: {
  content: string;
  fragments?: Data[];
  streaming?: boolean;
}) {
  if (!fragments) return <>{content}</>;
  return (
    <span className={"stream-text" + (streaming ? "" : " stream-complete")}>
      <span className="sr-only">{content}</span>
      <span aria-hidden="true">
        {fragments.map((fragment) => (
          <span key={fragment.id}>
            {fragment.characters.map((character: string, index: number) => (
              <span
                key={index}
                className="stream-character"
                style={{ animationDelay: Math.min(index, 3) * 30 + "ms" }}
              >
                {character}
              </span>
            ))}
            {fragment.remainder}
          </span>
        ))}
      </span>
    </span>
  );
}

export function streamFragment(content: string) {
  const characters = Array.from(
    new Intl.Segmenter("zh", { granularity: "grapheme" }).segment(content),
    (part) => part.segment,
  );
  return {
    id: crypto.randomUUID(),
    characters: characters.slice(0, 24),
    remainder: characters.slice(24).join(""),
  };
}
