"""生成真实 DXF 重现旧版本头与 UTF-8 内容冲突，独立读取检查符号。"""
import io
import ezdxf
from ezdxf.lldxf.encoding import decode_dxf_unicode
from freecad.gongke.native_export import normalize_dxf_unicode


def test_native_old_dxf_keeps_entities_and_unicode(tmp_path):
    doc = ezdxf.new("R2000")
    model = doc.modelspace()
    model.add_circle((0, 0), 19)
    model.add_text("⌀38 中间轴", dxfattribs={"height": 3})
    output = io.StringIO()
    doc.write(output)
    target = tmp_path / "native.dxf"
    target.write_bytes(output.getvalue().encode("utf-8"))
    assert normalize_dxf_unicode(target) == "dxf_unicode_escape"
    assert b"\\U+2300" in target.read_bytes()
    loaded = ezdxf.readfile(target)
    assert not loaded.audit().has_errors
    assert loaded.modelspace().query("CIRCLE")[0].dxf.radius == 19
    assert decode_dxf_unicode(loaded.modelspace().query("TEXT")[0].dxf.text) == "⌀38 中间轴"
