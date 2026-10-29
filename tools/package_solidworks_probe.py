"""生成借机使用的 SOLIDWORKS 只读源码包；不包含 CAD 或运行环境。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


FILES = ("README.md", "CollectCurrentPart.bas", "read_capture.py", "field-checklist.txt")


def package(output: Path) -> dict:
    source = Path(__file__).resolve().parent / "solidworks"
    contents = {name: (source / name).read_bytes() for name in FILES}
    manifest = {
        "package": "gongke-solidworks-readonly-probe", "schema_version": 2,
        "prototype_validation": "unverified", "windows_requirements": "已安装且可运行 SOLIDWORKS，VBA 宏编辑器",
        "files": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                  for name, data in contents.items()},
    }
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            archive.writestr("gongke-solidworks-probe/" + name, data)
        archive.writestr("gongke-solidworks-probe/manifest.json",
                         json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("生成的 ZIP 校验失败")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="尚不存在的 ZIP 路径，父目录须存在")
    args = parser.parse_args()
    try:
        manifest = package(args.out)
    except (OSError, ValueError) as error:
        parser.exit(1, f"打包失败：{error}\n")
    print(json.dumps({"path": str(args.out.resolve()), "files": len(manifest["files"]),
                      "prototype_validation": manifest["prototype_validation"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
