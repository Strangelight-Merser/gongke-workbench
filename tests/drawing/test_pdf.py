"""DXF → PDF：页面尺寸、线条和文字轮廓都写进内容流，结构符合 PDF 1.4（交叉引用表偏移正确）。"""

import re
import zlib

import ezdxf

from gongke_core.drawing import pdf


def test_single_page_pdf(tmp_path):
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (297, 0), (297, 210), (0, 210)], close=True)
    msp.add_line((10, 10), (100, 50))
    msp.add_text("A", height=5).set_placement((50, 100))
    dxf = tmp_path / "t.dxf"
    doc.saveas(dxf)
    out = tmp_path / "t.pdf"
    pdf.to_pdf([(dxf, 297.0, 210.0)], out, "测试")
    data = out.read_bytes()
    assert b"/MediaBox [0 0 841.89 595.28]" in data  # A4 横放，pt
    # 交叉引用表中的偏移量指向各对象
    xref = int(re.search(rb"startxref\n(\d+)", data).group(1))
    table = data[xref:].split(b"\n")
    n = int(table[1].split()[1])
    for i in range(1, n):
        off = int(table[2 + i].split()[0])
        assert data[off:].startswith(f"{i} 0 obj".encode())
    stream = re.search(rb"stream\n(.*?)\nendstream", data, re.S).group(1)
    ops = zlib.decompress(stream).decode().splitlines()
    assert ops.count("S") >= 2  # 图框和直线
    assert ops.count("f*") >= 1  # 文字转成的填充轮廓
