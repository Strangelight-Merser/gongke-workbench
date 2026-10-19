"""DXF → SVG 预览（ezdxf drawing 插件，白底黑线）。"""

from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, layout, svg
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration, LineweightPolicy
from ezdxf.fonts import fonts

CJK_FALLBACKS = ["simfang.ttf", "SimSun.ttf", "NotoSansCJK-Regular.ttc", "NotoSerifCJK-Regular.ttc",
                 "wqy-zenhei.ttc", "wqy-microhei.ttc", "DroidSansFallbackFull.ttf"]


def _cjk_font() -> str | None:
    for name in CJK_FALLBACKS:
        try:
            ff = fonts.find_font_face(name)
        except Exception:
            continue
        if ff and ff.filename.lower() == name.lower():
            return name
    return None


def to_svg(dxf_path: str | Path, svg_path: str | Path, width_mm: float | None = None, height_mm: float | None = None):
    doc = ezdxf.readfile(str(dxf_path))
    font = _cjk_font()
    if font:
        for st in doc.styles:
            if st.dxf.name.upper() == "GB":
                st.dxf.font = font
    msp = doc.modelspace()
    ctx = RenderContext(doc)
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK,
                        lineweight_policy=LineweightPolicy.ABSOLUTE)
    be = svg.SVGBackend()
    Frontend(ctx, be, config=cfg).draw_layout(msp)
    if width_mm is None:
        ext = ezdxf.bbox.extents(msp)
        width_mm, height_mm = ext.size.x, ext.size.y
    page = layout.Page(width_mm, height_mm, layout.Units.mm, margins=layout.Margins.all(0))
    Path(svg_path).write_text(be.get_string(page), encoding="utf-8")
