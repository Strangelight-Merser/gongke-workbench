"""把说明书渲染成 Markdown（图片另存为同目录 PNG）。不依赖第三方库。"""

from __future__ import annotations

from pathlib import Path

from gongke_core.report import Doc


def write(doc: Doc, path: str | Path) -> None:
    path = Path(path)
    out = [f"# {doc.title}", ""]
    n_img = 0
    for b in doc.blocks:
        if b.kind == "h1":
            out += [f"## {b.text}", ""]
        elif b.kind == "h2":
            out += [f"### {b.text}", ""]
        elif b.kind == "p":
            out += [b.text, ""]
        elif b.kind == "eq":
            out += [f"> {b.text}", ""]
        elif b.kind == "note":
            out += [f"*注：{b.text}*", ""]
        elif b.kind == "table":
            out.append("| " + " | ".join(b.headers) + " |")
            out.append("|" + "---|" * len(b.headers))
            out += ["| " + " | ".join(r) + " |" for r in b.rows]
            out.append("")
        elif b.kind == "img":
            n_img += 1
            name = f"{path.stem}_fig{n_img}.png"
            (path.parent / name).write_bytes(b.image)
            out += [f"![{b.text}]({name})", "", f"图 {n_img}　{b.text}", ""]
    path.write_text("\n".join(out), encoding="utf-8")
