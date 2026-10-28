#!/bin/bash
# 单个临时桌面；宿主机仅发布 127.0.0.1 的 noVNC 端口。
set -euo pipefail
mkdir -p /workspace/logs /tmp/runtime-engineer
chmod 700 /tmp/runtime-engineer
export XDG_RUNTIME_DIR=/tmp/runtime-engineer
children=()
cleanup() {
    trap - EXIT INT TERM
    for pid in "${children[@]}"; do kill "$pid" 2>/dev/null || true; done
    wait || true
}
trap cleanup EXIT INT TERM
Xvnc :1 -geometry 1440x1000 -depth 24 -rfbport 5901 -localhost \
    -SecurityTypes None -AlwaysShared > /workspace/logs/vnc.log 2>&1 &
children+=("$!")
for attempt in {1..50}; do
    test -S /tmp/.X11-unix/X1 && break
    kill -0 "${children[0]}"
    sleep 0.1
done
test -S /tmp/.X11-unix/X1
openbox > /workspace/logs/window-manager.log 2>&1 &
children+=("$!")
websockify --web=/usr/share/novnc 6080 127.0.0.1:5901 > /workspace/logs/novnc.log 2>&1 &
children+=("$!")
dbus-run-session -- /opt/squashfs-root/AppRun /opt/gongke/bootstrap.FCMacro \
    > /workspace/logs/freecad.log 2>&1 &
children+=("$!")
wait "${children[-1]}"
