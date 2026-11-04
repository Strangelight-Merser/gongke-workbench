"""一个用户共享一个桥接实例；退出权限由桥接持有，工程副本仍各自隔离。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4
from urllib.request import Request, build_opener, ProxyHandler
from urllib.parse import urlsplit

from gongke_core.host_session import FileLock, endpoint_path, process_identity, remove_session
from gongke_core.native_client import _NoRedirect


def request(session, method, **params):
    url = urlsplit(session["url"])
    if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or url.path or url.query or url.fragment or url.username:
        raise ValueError("无效的宿主回环地址")
    req = Request(session["url"] + "/command", data=json.dumps({"method": method, "params": params}).encode(),
                  headers={"Authorization": "Bearer " + session["token"], "Content-Type": "application/json"})
    with build_opener(ProxyHandler({}), _NoRedirect()).open(req, timeout=30 if method == "lifecycle.release" else 4) as response:
        value = json.load(response)
    if not value["ok"]:
        raise ValueError(value["error"])
    return value["result"]


class FreeCADLifecycle:
    def __init__(self):
        self.path = endpoint_path()
        self.client = uuid4().hex
        self.session = None
        self.process = None

    def discover(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except ValueError:
            raise ValueError("FreeCAD 会话文件损坏，无法确认宿主身份；请检查后再启动") from None
        actual = process_identity(value.get("pid"))
        if actual is None or (value.get("process") and actual != value["process"]):
            remove_session(self.path, value.get("token"))
            return None
        if not value.get("process"):
            raise ValueError("现有 FreeCAD 桥接缺少进程身份，请在该实例退出后重新连接")
        try:
            identity = request(value, "lifecycle.identity")
            if identity != {"pid": value["pid"], "instance": value["instance"]}:
                raise ValueError("桥接身份不符")
        except Exception as exc:
            raise ValueError("FreeCAD 进程仍在运行，但桥接未响应或身份不符；未启动重复实例") from exc
        return value

    def connect(self, executable=None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(self.path.with_suffix(".launch.lock"), blocking=True):
            session = self.discover()
            if session is None:
                try:
                    with FileLock(self.path.with_suffix(".bridge.lock")):
                        pass
                except OSError:
                    raise ValueError("FreeCAD 桥接仍持有实例锁，但会话不可用；未启动重复实例") from None
                executable = executable or os.environ.get("GONGKE_FREECAD_EXE") or shutil.which("FreeCAD")
                if not executable and Path("/Applications/FreeCAD.app/Contents/MacOS/FreeCAD").is_file():
                    executable = "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD"
                if not executable:
                    raise ValueError("未找到 FreeCAD，请选择安装路径")
                root = Path(os.environ.get("GONGKE_FREECAD_MODULE_ROOT", Path(__file__).resolve().parents[1]))
                macro = self.path.parent / "managed_freecad.FCMacro"
                macro.write_text("import sys, freecad\n" + f"sys.path.insert(0, {str(root)!r})\n" +
                                 f"freecad.__path__.insert(0, {str(root / 'freecad')!r})\n" +
                                 "old = sys.modules.get('freecad.gongke.bridge')\n"
                                 "if old and getattr(old, '_bridge', None): old._bridge.close()\n"
                                 "for name in list(sys.modules):\n"
                                 "    if name == 'freecad.gongke' or name.startswith('freecad.gongke.'): del sys.modules[name]\n"
                                 "if hasattr(freecad, 'gongke'): del freecad.gongke\n"
                                 "from freecad.gongke.bridge import start\nstart()\n", encoding="utf-8")
                instance = uuid4().hex
                with (self.path.parent / "freecad.log").open("a") as log:
                    self.process = subprocess.Popen([str(executable), str(macro)], env={**{key: value for key, value in os.environ.items() if key.upper() in {"HOME", "PATH", "TMPDIR", "USER", "LOGNAME", "LANG", "LC_ALL", "DISPLAY", "XAUTHORITY", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE"}},
                        "GONGKE_FREECAD_SESSION": str(self.path), "GONGKE_FREECAD_MANAGED": "1", "GONGKE_FREECAD_INSTANCE": instance}, stdout=log, stderr=log)
                deadline = time.monotonic() + 45
                try:
                    while time.monotonic() < deadline:
                        if self.process.poll() is not None:
                            raise ValueError("FreeCAD 启动失败，请检查 freecad.log")
                        if self.path.exists() and json.loads(self.path.read_text(encoding="utf-8")).get("instance") == instance:
                            session = self.discover()
                            if session:
                                break
                        time.sleep(.1)
                    if session is None:
                        raise TimeoutError("FreeCAD 桥接启动超时")
                except BaseException:
                    # 尚未交给用户的启动失败进程只按本次 Popen 句柄回收。
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()
                    raise
            self.session = session
            request(session, "lifecycle.acquire", client=self.client, process=process_identity(os.getpid()))
            return {"pid": session["pid"], "instance": session["instance"]}

    def close(self):
        if self.process is not None:
            self.process.poll()
        if self.session is None:
            return {"closed": False, "documents": []}
        if process_identity(self.session["pid"]) != self.session["process"]:
            self.session = None
            return {"closed": True, "documents": []}
        try:
            result = request(self.session, "lifecycle.release", client=self.client)
        except Exception:
            # 用户在检查与 HTTP 请求之间关闭了原生窗口。
            if process_identity(self.session["pid"]) == self.session["process"]:
                raise
            result = {"closed": True, "documents": []}
        if not result.get("documents"):
            self.session = None
        return result
