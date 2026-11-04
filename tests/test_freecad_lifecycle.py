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


@pytest.mark.parametrize("mode", ["exception", "sigint", "sigterm"])
def test_script_cleanup_on_failure(tmp_path, mode):
    pidfile = tmp_path / "pid"
    code = f'''from scripts.owned_processes import OwnedProcesses
import sys, time, os, signal
from pathlib import Path
owned=OwnedProcesses()
p=owned.spawn([sys.executable, '-c', 'import time; time.sleep(60)'])
Path({str(pidfile)!r}).write_text(str(p.pid))
'''
    code += 'raise RuntimeError("injected")' if mode == "exception" else f'os.kill(os.getpid(), signal.{"SIGINT" if mode == "sigint" else "SIGTERM"})'
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=15)
    assert result.returncode != 0
    assert process_identity(int(pidfile.read_text())) is None


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
