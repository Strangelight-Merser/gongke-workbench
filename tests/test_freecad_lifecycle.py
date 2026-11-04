"""进程身份、启动互斥、连接复用与清理的回归测试。"""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
import importlib.util

import pytest

from gongke_app import freecad_lifecycle as lifecycle
from gongke_core.host_session import FileLock, process_identity


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("GONGKE_FREECAD_SESSION", str(tmp_path / "session.json"))
    return lifecycle.FreeCADLifecycle()


def record(manager, **changes):
    value = {"pid": os.getpid(), "process": process_identity(os.getpid()), "instance": "test", "token": "private", "url": "http://127.0.0.1:12345"}
    value.update(changes)
    manager.path.write_text(json.dumps(value))
    return value


def test_reuse_without_spawn(manager, monkeypatch):
    value = record(manager)
    calls = []
    def request(session, method, **params):
        calls.append(method)
        return {"pid": value["pid"], "instance": value["instance"]}
    monkeypatch.setattr(lifecycle, "request", request)
    assert manager.connect()["pid"] == os.getpid()
    assert manager.connect()["pid"] == os.getpid()
    assert manager.process is None
    assert calls.count("lifecycle.acquire") == 2


@pytest.mark.parametrize("reuse_pid", [False, True])
def test_stale_session_removed(manager, monkeypatch, reuse_pid):
    record(manager, process={"pid": os.getpid(), "started": "old", "command": "old"})
    if not reuse_pid:
        monkeypatch.setattr(lifecycle, "process_identity", lambda pid: None)
    assert manager.discover() is None
    assert not manager.path.exists()


def test_unresponsive_live_bridge_never_spawns(manager, monkeypatch):
    record(manager)
    monkeypatch.setattr(lifecycle, "request", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(ValueError, match="未启动重复实例"):
        manager.connect()
    assert manager.path.exists() and manager.process is None


def test_other_live_process_not_claimed(manager):
    record(manager, process=None)
    with pytest.raises(ValueError, match="缺少进程身份"):
        manager.connect()
    assert manager.process is None


def test_cross_process_lock(tmp_path):
    path = tmp_path / "host.lock"
    with FileLock(path):
        code = f"from gongke_core.host_session import FileLock; from pathlib import Path; FileLock(Path({str(path)!r}))"
        result = subprocess.run([sys.executable, "-c", code], capture_output=True)
        assert result.returncode != 0
    with FileLock(path):
        pass


@pytest.fixture
def bridge(monkeypatch):
    documents = []
    scheduled = []
    monkeypatch.setitem(sys.modules, "FreeCAD", SimpleNamespace(listDocuments=lambda: {d.Name: d for d in documents}))
    monkeypatch.setitem(sys.modules, "FreeCADGui", SimpleNamespace(getDocument=lambda name: next(d for d in documents if d.Name == name), getMainWindow=lambda: SimpleNamespace(close=lambda: None)))
    monkeypatch.setitem(sys.modules, "PySide", SimpleNamespace(QtCore=SimpleNamespace(QTimer=SimpleNamespace(singleShot=lambda *args: scheduled.append(args)))))
    spec = importlib.util.spec_from_file_location("lifecycle_bridge_test", Path(__file__).resolve().parents[1] / "freecad/gongke/bridge.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    host = module.Bridge.__new__(module.Bridge)
    host.lifecycle_lock = threading.Lock()
    host.instance = "test"
    host.managed = True
    host.clients = {}
    host.closing = False
    state = module.DocumentState.__new__(module.DocumentState)
    host.main_call = lambda name: getattr(state, name)()
    return host, documents, scheduled


@pytest.mark.parametrize("saved,modified", [(False, False), (True, True), (True, False)])
def test_exit_documents(bridge, saved, modified):
    host, documents, scheduled = bridge
    documents.append(SimpleNamespace(Name="Doc", Label="学生模型", FileName="part.FCStd" if saved else "", Modified=modified))
    host.dispatch("lifecycle.acquire", {"client": "one", "process": process_identity(os.getpid())})
    result = host.dispatch("lifecycle.release", {"client": "one"})
    assert result["closed"] == (saved and not modified)
    assert bool(scheduled) == result["closed"]
    assert bool(result["documents"]) != result["closed"]
    if not result["closed"]:
        assert "one" in host.clients


def test_last_client_only_and_borrowed_host(bridge):
    host, _, scheduled = bridge
    for client in ("one", "two"):
        host.dispatch("lifecycle.acquire", {"client": client, "process": process_identity(os.getpid())})
    assert not host.dispatch("lifecycle.release", {"client": "one"})["closed"]
    host.managed = False
    assert not host.dispatch("lifecycle.release", {"client": "two"})["closed"]
    assert not scheduled


# 按操作系统的真实退出方式取值，不把 Windows TerminateProcess 当作可捕获 SIGTERM。
EXIT_MODES = ["normal", "exception", "keyboard_interrupt", "force"] + (
    ["ctrl_break"] if os.name == "nt" else ["sigint", "sigterm"])


@pytest.mark.parametrize("mode", EXIT_MODES)
def test_script_cleanup_on_failure(tmp_path, mode):
    import signal
    import time

    pidfile = tmp_path / "child.json"
    # 由子进程自身报告就绪，避开 macOS Python 启动器 exec 前的临时身份。
    child_code = f"""import os, time, json
from pathlib import Path
from gongke_core.host_session import process_identity
path = Path({str(pidfile)!r})
path.with_suffix('.tmp').write_text(json.dumps(process_identity(os.getpid())))
path.with_suffix('.tmp').replace(path)
time.sleep(60)
"""
    code = f'''from scripts.owned_processes import OwnedProcesses
import sys, time, subprocess
from pathlib import Path
owned=OwnedProcesses()
# 独立子进程组使 Ctrl+Break 只到达所有者，不能靠广播杀死子进程伪装成清理成功。
p=owned.spawn([sys.executable, '-c', {child_code!r}],
              creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
path=Path({str(pidfile)!r})
deadline=time.monotonic()+10
while not path.exists() and time.monotonic()<deadline and p.poll() is None:
    time.sleep(.02)
assert path.exists(), '子进程未就绪'
'''
    code += {"normal": "owned.close()", "exception": 'raise RuntimeError("injected")',
             "keyboard_interrupt": "raise KeyboardInterrupt"}.get(mode, "while True: time.sleep(.05)")
    console_created = False
    if mode == "ctrl_break":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        if kernel.GetConsoleCP() == 0:
            assert kernel.AllocConsole(), ctypes.get_last_error()
            console_created = True
    child_identity = None
    try:
        # 输出落盘；强制终止的父进程不能让遗留子进程持有测试的 PIPE。
        with (tmp_path / "owner.log").open("wb") as log:
            owner = subprocess.Popen([sys.executable, "-c", code], stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            try:
                deadline = time.monotonic() + 10
                while not pidfile.exists() and time.monotonic() < deadline and owner.poll() is None:
                    time.sleep(.02)
                assert pidfile.exists(), (tmp_path / "owner.log").read_text(errors="replace")
                child_identity = json.loads(pidfile.read_text())
                assert child_identity is not None
                if mode == "ctrl_break":
                    owner.send_signal(signal.CTRL_BREAK_EVENT)
                elif mode in {"sigint", "sigterm"}:
                    owner.send_signal(signal.SIGINT if mode == "sigint" else signal.SIGTERM)
                elif mode == "force":
                    owner.kill()  # Windows TerminateProcess / POSIX SIGKILL，均不运行清理。
                result = owner.wait(timeout=15)
                assert (result == 0) == (mode == "normal")
                actual = process_identity(child_identity["pid"])
                if mode == "force":
                    assert actual == child_identity, "强制结束所有者不应被误报为成功清理"
                else:
                    assert actual is None, "可处理退出必须回收自己的子进程"
            finally:
                if owner.poll() is None:
                    owner.kill()
                    owner.wait(timeout=5)
                if child_identity is None and pidfile.exists():
                    child_identity = json.loads(pidfile.read_text())
                if child_identity and process_identity(child_identity["pid"]) == child_identity:
                    if os.name == "nt":
                        # 持有同一内核对象并等待终止完成，不在销毁映像期间反复查询身份。
                        import ctypes
                        from ctypes import wintypes
                        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                        kernel.OpenProcess.restype = wintypes.HANDLE
                        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
                        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                        handle = kernel.OpenProcess(0x100000 | 0x0001, False, child_identity["pid"])
                        assert handle, ctypes.get_last_error()
                        try:
                            assert kernel.TerminateProcess(handle, 1), ctypes.get_last_error()
                            assert kernel.WaitForSingleObject(handle, 5000) == 0
                        finally:
                            kernel.CloseHandle(handle)
                    else:
                        os.kill(child_identity["pid"], signal.SIGKILL)
                        deadline = time.monotonic() + 5
                        while process_identity(child_identity["pid"]) == child_identity and time.monotonic() < deadline:
                            time.sleep(.02)
                        assert process_identity(child_identity["pid"]) != child_identity
    finally:
        if console_created:
            kernel.FreeConsole()


def test_live_bridge_lock_without_session_blocks_launch(manager):
    with FileLock(manager.path.with_suffix('.bridge.lock')):
        with pytest.raises(ValueError, match="实例锁"):
            manager.connect()
    assert manager.process is None


def test_dirty_release_keeps_client(manager, monkeypatch):
    manager.session = record(manager)
    monkeypatch.setattr(lifecycle, 'request', lambda *a, **k: {'closed': False, 'documents': ['草图']})
    assert manager.close()['documents'] == ['草图']
    assert manager.session is not None


def test_identity_mismatch_on_exit_does_not_send_command(manager, monkeypatch):
    manager.session = record(manager, process={'pid': os.getpid(), 'started': 'old', 'command': 'old'})
    monkeypatch.setattr(lifecycle, 'request', lambda *a, **k: pytest.fail('不能向复用 PID 发送退出命令'))
    assert manager.close()['closed']
