"""Archive the tested Windows x64 application with recipient instructions."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile

from install_freecad_workbench import install

ROOT = Path(__file__).resolve().parents[1]


def require_windows_x64(path: Path):
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError(f"Not a Windows executable: {path}")
        stream.seek(0x3C)
        stream.seek(struct.unpack("<I", stream.read(4))[0])
        if stream.read(4) != b"PE\0\0" or stream.read(2) != b"\x64\x86":
            raise ValueError(f"Not a Windows x64 PE executable: {path}")


def main():
    release = ROOT / "desktop/release"
    source = release / "win-unpacked"
    for name in ("构想引擎.exe", "resources/service/gongke-service/gongke-service.exe"):
        require_windows_x64(source / name)
    evidence = {}
    for folder in ("desktop-validation", "workflow-validation"):
        results = sorted((ROOT / "out" / folder).glob("*/result.json"),
                         key=lambda path: path.stat().st_mtime)
        if not results:
            raise ValueError(f"Missing packaged acceptance: {folder}")
        result = json.loads(results[-1].read_text(encoding="utf-8"))
        if not result.get("ok") or not result.get("packaged"):
            raise ValueError(f"Packaged acceptance did not pass: {folder}")
        evidence[folder] = {"passed": True, "sha256": hashlib.sha256(results[-1].read_bytes()).hexdigest()}
    archive = release / "gongke-windows-x64.zip"
    with tempfile.TemporaryDirectory(prefix="gongke-delivery-") as temp:
        package = Path(temp) / "构想引擎-Windows-x64"
        package.mkdir()
        shutil.copy2(ROOT / "packaging/windows-使用说明.txt", package / "先读我.txt")
        shutil.copy2(ROOT / "LICENSE", package / "LICENSE.txt")
        install(package / "可选插件/FreeCAD")
        info = {"platform": "Windows x64", "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "workflow_run": os.environ.get("GITHUB_RUN_ID"), "acceptance": evidence,
            "model": "local SSE fixture", "commercial_cad_host_tested": False,
            "signed": False}
        (package / "build-info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            for base, prefix in ((package, package.name), (source, package.name + "/应用")):
                for file in sorted(base.rglob("*")):
                    if file.is_file():
                        output.write(file, prefix + "/" + file.relative_to(base).as_posix())
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    archive.with_suffix(".sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Windows delivery: {archive} ({archive.stat().st_size} bytes), SHA256 {digest}")


if __name__ == "__main__":
    main()
