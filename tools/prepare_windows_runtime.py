"""固定官方 FreeCAD 运行时，保留发行包内全部许可证与第三方材料。"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0.2'
URL = 'https://github.com/FreeCAD/FreeCAD/releases/download/1.0.2/FreeCAD_1.0.2-conda-Windows-x86_64-py311.7z'
SHA256 = 'e89afe0433063c7f2484326b8b9a64e3027dc29d145ddb438a44046c960827a6'


def main():
    work = ROOT / 'out/windows-runtime'
    work.mkdir(parents=True, exist_ok=True)
    archive = work / 'freecad.7z'
    with urlopen(URL, timeout=60) as response, archive.open('wb') as output:
        shutil.copyfileobj(response, output)
    with archive.open('rb') as source:
        assert hashlib.file_digest(source, 'sha256').hexdigest() == SHA256, 'FreeCAD SHA256 mismatch'
    extracted = work / 'extracted'
    subprocess.run(['7z', 'x', str(archive), '-o' + str(extracted), '-y'], check=True, stdout=subprocess.DEVNULL)
    binaries = list(extracted.rglob('bin/FreeCAD.exe'))
    assert len(binaries) == 1, binaries
    destination = ROOT / 'desktop/runtime/freecad'
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(binaries[0].parent.parent, destination)
    licenses = [p for p in destination.rglob('*') if p.is_file() and
                ('license' in p.name.lower() or 'copying' in p.name.lower())]
    assert licenses, 'Official archive must retain license materials'
    (destination / 'gongke-distribution.json').write_text(json.dumps({
        'version': VERSION, 'url': URL, 'sha256': SHA256,
        'source': 'https://github.com/FreeCAD/FreeCAD/releases/download/1.0.2/freecad_source.tar.gz',
        'usage': 'Unmodified distribution, independent process; all upstream licenses retained.',
        'licenses': [p.relative_to(destination).as_posix() for p in licenses],
    }, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
