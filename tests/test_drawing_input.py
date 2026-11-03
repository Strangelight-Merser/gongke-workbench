"""图纸解析经过真实服务/MCP，样例为解析几何与明确标注，不使用参考模型。"""
import asyncio
import hashlib
import sys

import ezdxf
import pytest
from mcp import Client, StdioServerParameters
from gongke_app.drawing_input import read_drawing
from gongke_app.project import Project
from tests.mcp_helpers import ROOT, ServiceProcess


def drawing(path):
    doc = ezdxf.new("R2010")
    doc.units = 4  # mm；测量值 20，故意用文字 25 覆盖，用于暴露冲突。
    space = doc.modelspace()
    space.add_line((0, 0), (20, 0))
    dim = space.add_linear_dim(base=(0, 10), p1=(0, 0), p2=(20, 0), text="25", override={"dimlfac": 2})
    dim.render()
    block = doc.blocks.new("circle")
    block.add_circle((0, 0), 3)
    space.add_blockref("circle", (10, 20))
    space.add_lwpolyline([(0, 0, 0, 0, 1), (2, 0, 0, 0, 0)], format="xyseb")
    doc.saveas(path)


def test_dxf_units_overrides_blocks_bulges_and_pagination(tmp_path):
    project = Project.create(tmp_path / "project")
    path = project.path / "part.dxf"
    drawing(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    first = read_drawing(project, "part.dxf", limit=1)
    rest = read_drawing(project, "part.dxf", offset=first["next_offset"])
    items = first["items"] + rest["items"]
    dim = next(i for i in items if i["type"] == "DIMENSION")
    assert dim["measurement"] == 20
    assert dim["text_override"] == "25" and dim["rendered_text"] == ["25"]
    assert dim["style"]["dimlfac"] == 2
    assert first["coordinates"]["unit_code"] == 4
    circle = next(i for i in items if i["type"] == "CIRCLE")
    assert circle["attributes"]["center"] == [10, 20, 0]
    poly = next(i for i in items if i["type"] == "LWPOLYLINE")
    assert poly["points_xy_startwidth_endwidth_bulge"][0][-1] == 1
    assert len(items) == first["total_items"] and rest["next_offset"] is None
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()


def pdf_fixture(path, text=True, rotation=False):
    # 最小 PDF 协议样例：200×100 pt 页面，一条20 pt线和文本“20”。不是工程比例。
    stream = b"10 10 m 30 10 l S\n" + (b"BT /F1 12 Tf 10 30 Td (20) Tj ET\n" if text else b"")
    if rotation:
        stream = b"BT /F1 12 Tf 0 1 -1 0 50 30 Tm (17) Tj ET\n"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream"]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(data)
    data += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(f"{n:010} 00000 n \n".encode() for n in offsets[1:])
    data += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    path.write_bytes(data)


def test_pdf_keeps_page_geometry_text_and_unresolved_semantics(tmp_path):
    project = Project.create(tmp_path / "project")
    path = project.path / "part.pdf"
    pdf_fixture(path)
    data = read_drawing(project, "part.pdf")
    assert data["coordinates"]["unit"] == "pt"
    assert data["coordinates"]["engineering_scale"] is None
    line = next(i for i in data["items"] if i["type"] == "lines")
    assert (line["x0"], line["x1"], line["top"]) == (10, 30, 90)
    word = next(i for i in data["items"] if i["type"] == "text")
    assert word["text"] == "20" and word["association"] == "unresolved"
    assert word["dimension_candidate"]
    with pytest.raises(ValueError, match="页码"):
        read_drawing(project, "part.pdf", page=2)
    pdf_fixture(path, text=False)
    assert any("没有可提取文字" in w for w in read_drawing(project, "part.pdf")["warnings"])


def test_drawing_through_bound_service_and_mcp(tmp_path):
    service = ServiceProcess(tmp_path)
    drawing(service.project / "part.dxf")
    outside = tmp_path / "outside.dxf"
    drawing(outside)
    (service.project / "escape.dxf").symlink_to(outside)

    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "gongke_app", "mcp", "--state-dir", str(service.state),
            "--project", str(service.project)], cwd=str(ROOT))
        async with Client(params) as client:
            result = await client.call_tool("project.read_drawing", {"path": "part.dxf", "limit": 2})
            assert not result.is_error
            assert result.structured_content["result"]["next_offset"] == 2
            receipt = service.request("task.get", {"task_id": result.structured_content["task_id"]})["receipts"][0]
            assert receipt["command"] == "project.read_drawing"
            guide = await client.read_resource("gongke://drawing-input")
            assert "页面" in guide.contents[0].text
            for args in ({"path": "escape.dxf"}, {"path": "../outside.dxf"}, {"path": "part.dxf", "limit": 0}):
                assert (await client.call_tool("project.read_drawing", args)).is_error
            service.request("project.create", {"path": str(tmp_path / "other")})
            assert (await client.call_tool("project.read_drawing", {"path": "part.dxf"})).is_error
    try:
        asyncio.run(run())
    finally:
        service.close()


def test_pdf_rotated_dimension_is_not_reversed_or_duplicated(tmp_path):
    project = Project.create(tmp_path / "project")
    pdf_fixture(project.path / "rotated.pdf", rotation=True)
    data = read_drawing(project, "rotated.pdf")
    assert [i["text"] for i in data["items"] if i["type"] == "text"] == ["17"]
    assert not any(i["type"] == "char" for i in data["items"])
    chars = read_drawing(project, "rotated.pdf", detail="characters")
    assert [i["text"] for i in chars["items"] if i["type"] == "char"] == ["1", "7"]
