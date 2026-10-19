"""弯矩图、转矩图（Pillow 绘制 PNG，图中只用拉丁字符，避免依赖中文字体）。"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont


def moment_diagram(shaft_result, width: int = 900, row_h: int = 150) -> bytes:
    samples = shaft_result.strength.samples
    lay = shaft_result.layout
    rows = [
        ("Mx (xz plane)", [s.m_x for s in samples], (52, 101, 164)),
        ("My (yz plane)", [s.m_y for s in samples], (196, 98, 16)),
        ("M = sqrt(Mx^2+My^2)", [s.m for s in samples], (60, 130, 60)),
        ("T", [abs(s.torque) for s in samples], (120, 60, 140)),
    ]
    zs = [s.z for s in samples]
    z0, z1 = min(zs), max(zs)
    pad_l, pad_r, pad_t = 150, 20, 18
    img = Image.new("RGB", (width, row_h * len(rows) + 30), "white")
    dr = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=14)

    def X(z):
        return pad_l + (z - z0) / (z1 - z0) * (width - pad_l - pad_r)

    for i, (name, vals, color) in enumerate(rows):
        top = i * row_h + pad_t
        h = row_h - 2 * pad_t
        vmax = max(max(abs(v) for v in vals), 1e-9)
        base = top + h / 2 if min(vals) < -1e-6 * vmax else top + h
        scale = (h / 2 if min(vals) < -1e-6 * vmax else h) / vmax
        pts = [(X(z), base - v * scale) for z, v in zip(zs, vals)]
        dr.polygon([(X(z0), base)] + pts + [(X(z1), base)], fill=tuple(int(c + (255 - c) * 0.75) for c in color))
        dr.line(pts, fill=color, width=2)
        dr.line([(X(z0), base), (X(z1), base)], fill="black", width=1)
        k = max(range(len(vals)), key=lambda j: abs(vals[j]))
        dr.text((pts[k][0] + 4, pts[k][1] - 16 if vals[k] >= 0 else pts[k][1] + 2), f"{vals[k]:.1f} N·m", fill="black", font=font)
        dr.text((8, top + h / 2 - 8), name, fill="black", font=font)
    # 支承位置
    bottom = row_h * len(rows)
    for zb in lay.bearing_z:
        dr.line([(X(zb), 0), (X(zb), bottom)], fill=(160, 160, 160), width=1)
        dr.text((X(zb) - 6, bottom + 6), "A" if zb == lay.bearing_z[0] else "B", fill="black", font=font)
    for p in shaft_result.load_case.loads:
        dr.line([(X(p.z), 0), (X(p.z), bottom)], fill=(200, 120, 120), width=1)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def deflection_diagram(shaft_result, fem=None, curve=None, width: int = 900, row_h: int = 170) -> bytes:
    """合成挠度和偏转角曲线（默认用刚度校核的曲线，可用 curve 换成计入剪切的曲线）；
    给出 fem（BeamResult）时叠加有限元节点结果（圆点）。"""
    import math

    c = curve or shaft_result.stiffness.curve
    lay = shaft_result.layout
    zs = c.z
    rows = [
        ("y (um)", [math.hypot(a, b) * 1e6 for a, b in zip(c.yx, c.yy)],
         None if fem is None else (fem.z, [math.hypot(a, b) * 1e6 for a, b in zip(fem.ux, fem.uy)]), (52, 101, 164)),
        ("theta (mrad)", [math.hypot(a, b) * 1e3 for a, b in zip(c.tx, c.ty)],
         None if fem is None else (fem.z, [math.hypot(a, b) * 1e3 for a, b in zip(fem.rx, fem.ry)]), (196, 98, 16)),
    ]
    z0, z1 = min(zs), max(zs)
    pad_l, pad_r, pad_t = 150, 20, 18
    img = Image.new("RGB", (width, row_h * len(rows) + (54 if fem is not None else 30)), "white")
    dr = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=14)

    def X(z):
        return pad_l + (z - z0) / (z1 - z0) * (width - pad_l - pad_r)

    for i, (name, vals, pts_fem, color) in enumerate(rows):
        top = i * row_h + pad_t
        h = row_h - 2 * pad_t
        vmax = max(max(vals), max(pts_fem[1]) if pts_fem else 0.0, 1e-12)
        base = top + h
        pts = [(X(z), base - v / vmax * h) for z, v in zip(zs, vals)]
        dr.line([(X(z0), base), (X(z1), base)], fill="black", width=1)
        dr.line(pts, fill=color, width=2)
        if pts_fem:
            fz, fv = pts_fem
            step = max(len(fz) // 40, 1)
            for z, v in list(zip(fz, fv))[::step]:
                x, y = X(z), base - v / vmax * h
                dr.ellipse([x - 3, y - 3, x + 3, y + 3], outline=(40, 40, 40))
        k = max(range(len(vals)), key=lambda j: vals[j])
        dr.text((pts[k][0] + 4, pts[k][1] - 16), f"{vals[k]:.3g}", fill="black", font=font)
        dr.text((8, top + h / 2 - 8), name, fill="black", font=font)
    bottom = row_h * len(rows)
    for zb in lay.bearing_z:
        dr.line([(X(zb), 0), (X(zb), bottom)], fill=(160, 160, 160), width=1)
        dr.text((X(zb) - 6, bottom + 6), "A" if zb == lay.bearing_z[0] else "B", fill="black", font=font)
    for p in shaft_result.load_case.loads:
        dr.line([(X(p.z), 0), (X(p.z), bottom)], fill=(200, 120, 120), width=1)
    if fem is not None:
        dr.text((pad_l, bottom + 30), "line: analytic (with shear)   o: FEM (CalculiX)", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
