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
mkdir -p "$HOME/.local/share/FreeCAD/Mod"
ln -sfn "$REPO" "$HOME/.local/share/FreeCAD/Mod/gongke-workbench"
export GONGKE_E2E_OUT="${GONGKE_E2E_OUT:-/tmp/gongke_e2e}"
# 五种传动方案各跑一遍；第一次先点面板上的按钮，用 FreeCAD 自带的 Python 安装依赖包（与学生首次使用的流程相同）
install=1
for scheme in coupling vbelt bevel worm single; do
  rm -f "$GONGKE_E2E_OUT/ok"
  (cd "$WORK/squashfs-root" && GONGKE_E2E_INSTALL=$install GONGKE_E2E_SCHEME=$scheme xvfb-run -a -s "-screen 0 1600x1000x24" ./usr/bin/freecad "$REPO/tests/e2e/freecad_gui_macro.py" >/dev/null 2>&1 || true)
  cat "$GONGKE_E2E_OUT/log.txt"
  test -f "$GONGKE_E2E_OUT/ok"
  install=
done
