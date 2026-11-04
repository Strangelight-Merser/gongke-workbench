"""WorkBuddy 启动真实解释器；开发配置由运行中的桌面服务产生。"""
import json
from pathlib import Path
import os
import subprocess
import sys
import venv

from gongke_app.cli import main
from gongke_app.connection import ConnectionServer, write_workbuddy
from gongke_app.project import Project
from gongke_app.service import Application


def test_configured_interpreter_keeps_venv_from_unrelated_directory(tmp_path):
    runtime = tmp_path / "runtime"
    venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(runtime)
    executable = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    project = Project.create(str(tmp_path / "工程"), teaching=False)
    configured = write_workbuddy(project, tmp_path / "state", executable, False,
                                 prefix=("-m", "gongke_app"), env={"PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    server = configured["server"]
    assert server["cwd"] == str(project.path)
    # venv 身份取决于调用入口，不能把 python 符号链接换成基础解释器。
    result = subprocess.run([server["command"], "-c", "import sys; print(sys.prefix)"],
                            cwd=tmp_path, check=True, text=True, capture_output=True)
    assert Path(result.stdout.strip()).resolve() == runtime.resolve()


def test_cli_uses_live_service_runtime_and_rejects_other_project(tmp_path, monkeypatch, capsys):
    app = Application(tmp_path / "state")
    try:
        project = app.dispatch("project.create", {"path": str(tmp_path / "工程")})
        # 不开监听端口；真实 configure 分派与 CLI 通过同一个应用对象核对绑定。
        server = ConnectionServer.__new__(ConnectionServer)
        server.app = app
        monkeypatch.setattr("gongke_app.cli.Connection", lambda _: server)
        monkeypatch.setattr(server, "request", lambda action, **params: server.dispatch({"action": action, "params": params}), raising=False)
        assert main(["workbuddy", "--project", project["path"]]) == 1
        preview = json.loads(capsys.readouterr().out)
        assert preview["status"] == "confirmation_required"
        assert not Path(preview["path"]).exists()
        assert main(["workbuddy", "--project", project["path"], "--allow-writes", "--confirm-user-config"]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["server"]["command"] == str(Path(sys.executable).absolute())
        assert result["server"]["args"][:3] == ["-m", "gongke_app", "mcp"]
        assert result["server"]["args"][-1] == "--allow-writes"
        assert "PYTHONPATH" in result["server"]["env"]
        saved = Path(result["path"]).read_bytes()
        assert main(["workbuddy", "--project", str(tmp_path / "other")]) == 2
        assert "不是桌面当前工程" in capsys.readouterr().err
        assert Path(result["path"]).read_bytes() == saved
        assert not app.bindings
    finally:
        app.close()


# 配置测试使用独立用户目录，不读取开发者真实 WorkBuddy 配置。
import pytest

@pytest.fixture(autouse=True)
def workbuddy_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
