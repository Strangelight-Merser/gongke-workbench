#!/usr/bin/env python3
"""Build with actual Autodesk NuGet references and stage two runtime bundles."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dotnet', default='dotnet')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts')
    args = parser.parse_args()
    project = ROOT / 'Gongke.AutoCAD.Addin' / 'Gongke.AutoCAD.Addin.csproj'
    subprocess.run([args.dotnet, 'restore', str(project), '--locked-mode'], check=True)
    subprocess.run([args.dotnet, 'build', str(project), '-c', 'Release', '--no-restore', '--nologo'], check=True)
    args.output.mkdir(parents=True, exist_ok=True)
    packages = []
    for runtime in ('net8.0-windows', 'net10.0-windows'):
        bundle = args.output / runtime / 'Gongke.AutoCAD.bundle'
        binary_dir = bundle / 'Contents' / 'Windows'
        binary_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'Gongke.AutoCAD.bundle' / 'PackageContents.xml', bundle)
        dll = ROOT / 'Gongke.AutoCAD.Addin' / 'bin' / 'Release' / runtime / 'Gongke.AutoCAD.Addin.dll'
        shutil.copy2(dll, binary_dir)
        # Only our plug-in is delivered; Autodesk assemblies are supplied by licensed AutoCAD.
        files = sorted(p.relative_to(bundle).as_posix() for p in bundle.rglob('*') if p.is_file())
        assert files == ['Contents/Windows/Gongke.AutoCAD.Addin.dll', 'PackageContents.xml'], files
        xml = ET.parse(bundle / 'PackageContents.xml').getroot()
        entry = xml.find('./Components/ComponentEntry')
        assert entry is not None and (bundle / entry.attrib['ModuleName']).is_file()
        packages.append({'runtime': runtime, 'bundle': str(bundle.resolve()),
                         'sha256': hashlib.sha256(dll.read_bytes()).hexdigest(), 'files': files})
    for script in ('Install.ps1', 'Uninstall.ps1', 'Test-Host.ps1'):
        shutil.copy2(ROOT / 'scripts' / script, args.output)
    result = {'sdk_compiled': True, 'host_tested': False, 'packages': packages}
    (args.output / 'build-manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
