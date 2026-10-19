#!/usr/bin/env bash
# 下载 FreeCAD AppImage，把仓库链接为 FreeCAD 插件，在 Xvfb 下运行界面端到端测试。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
FC_VER="${FC_VER:-1.0.2}"
WORK="${WORK:-$HOME/.cache/gongke-freecad}"
mkdir -p "$WORK"
if [ ! -x "$WORK/squashfs-root/usr/bin/freecad" ]; then
  curl -sSL -o "$WORK/fc.AppImage" "https://github.com/FreeCAD/FreeCAD/releases/download/${FC_VER}/FreeCAD_${FC_VER}-conda-Linux-x86_64-py311.AppImage"
  chmod +x "$WORK/fc.AppImage"
  (cd "$WORK" && ./fc.AppImage --appimage-extract >/dev/null)
fi
FC="$WORK/squashfs-root/usr/bin"
"$FC/python" -m pip install --quiet build123d python-docx pyyaml ezdxf
mkdir -p "$HOME/.local/share/FreeCAD/Mod"
ln -sfn "$REPO" "$HOME/.local/share/FreeCAD/Mod/gongke-workbench"
export GONGKE_PYTHON="$FC/python" GONGKE_E2E_OUT="${GONGKE_E2E_OUT:-/tmp/gongke_e2e}"
# 三种传动方案各跑一遍
for scheme in coupling vbelt bevel; do
  rm -f "$GONGKE_E2E_OUT/ok"
  (cd "$WORK/squashfs-root" && GONGKE_E2E_SCHEME=$scheme xvfb-run -a -s "-screen 0 1600x1000x24" ./usr/bin/freecad "$REPO/tests/e2e/freecad_gui_macro.py" >/dev/null 2>&1 || true)
  cat "$GONGKE_E2E_OUT/log.txt"
  test -f "$GONGKE_E2E_OUT/ok"
done
