"""修正 TechDraw 1.1.4 新导出 DXF 的字符串编码，不改原生工程或实体。"""
from pathlib import Path
import re


def normalize_dxf_unicode(path):
    """该导出器把 UTF-8 写进 R14；旧版 DXF 要用 ASCII Unicode 转义。

    格式依据 Autodesk DXF Group Code Value Types / Storage of String Values。
    不改 DXF 版本、实体、句柄、尺寸测量值和关联；只处理本次新导出的文本。
    """
    target = Path(path)
    content = target.read_bytes().decode("utf-8")
    version = re.search(r"\$ACADVER\s+1\s+(AC\d{4})", content)
    if version is None:
        raise ValueError("原生导出缺少 DXF 版本，不能确认文字编码")
    if version[1] >= "AC1021":
        return "utf-8"
    escaped = "".join(char if ord(char) < 128 else
                      "\\U+" + format(ord(char), "04X" if ord(char) <= 65535 else "08X")
                      for char in content)
    target.write_bytes(escaped.encode("ascii"))
    return "dxf_unicode_escape"
