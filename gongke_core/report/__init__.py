"""计算说明书。

``build(design)`` 生成与输出格式无关的文档结构（标题、段落、公式行、表格、图），
``docx.write`` 和 ``markdown.write`` 把它渲染成 Word 或 Markdown 文件。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Block:
    kind: str  # h1 / h2 / p / eq / table / img / note
    text: str = ""
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    image: bytes | None = None


class Doc:
    def __init__(self, title: str):
        self.title = title
        self.blocks: list[Block] = []

    def h1(self, t: str):
        self.blocks.append(Block("h1", t))

    def h2(self, t: str):
        self.blocks.append(Block("h2", t))

    def p(self, t: str):
        self.blocks.append(Block("p", t))

    def eq(self, t: str):
        """一行计算式：公式 = 代入 = 结果。"""
        self.blocks.append(Block("eq", t))

    def note(self, t: str):
        self.blocks.append(Block("note", t))

    def table(self, headers: list[str], rows: list[list[str]]):
        self.blocks.append(Block("table", headers=headers, rows=rows))

    def img(self, png: bytes, caption: str):
        self.blocks.append(Block("img", caption, image=png))
