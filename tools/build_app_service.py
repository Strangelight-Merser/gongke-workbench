"""Build the self-contained service consumed by the desktop installer.

Run with the build environment containing ``.[desktop]``. PyInstaller targets
the build machine's OS and architecture; Windows must be built on Windows.
"""
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(root / "desktop/service"),
                    "--workpath", str(root / "out/service-build"),
                    str(root / "packaging/gongke-service.spec")], cwd=root, check=True)


if __name__ == "__main__":
    main()
