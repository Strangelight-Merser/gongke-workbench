"""隔离验收的 FreeCAD 启动范围；不接管用户已有桥接。"""
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]


def start_host(owned, directory, executable):
    directory.mkdir(parents=True, exist_ok=False)
    endpoint = directory / "session.json"
    system = {"HOME", "PATH", "TMPDIR", "USER", "LOGNAME", "LANG", "LC_ALL", "DISPLAY", "XAUTHORITY", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE"}
    env = {key: value for key, value in os.environ.items() if key.upper() in system}
    env.update(GONGKE_MODELING_ROOT=str(ROOT), GONGKE_FREECAD_SESSION=str(endpoint))
    with (directory / "freecad.log").open("w") as log:
        child = owned.spawn([str(executable), str(ROOT / "tests/e2e/native_modeling_host.FCMacro")], cwd=ROOT, env=env, stdout=log, stderr=log)
    (directory / "process.json").write_text(json.dumps({"pid": child.pid}))
    deadline = time.monotonic() + 45
    while not (directory / "bootstrap.json").exists():
        if child.poll() is not None:
            raise RuntimeError(f"验收宿主提前退出：{directory / 'freecad.log'}")
        if time.monotonic() >= deadline:
            raise TimeoutError("验收宿主启动超时")
        time.sleep(.1)
    boot = json.loads((directory / "bootstrap.json").read_text())
    if boot["pid"] != child.pid:
        raise RuntimeError("启动器未提供真实 FreeCAD PID，请使用直接运行的可执行文件")
    return endpoint
