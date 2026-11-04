"""Agent 引导复用配置生成器，保留项目其他 MCP 服务。"""
import json
from pathlib import Path
import sys

from gongke_app.service import Application
from gongke_app.connection import write_workbuddy


def test_development_workbuddy_configuration_and_other_servers(tmp_path):
    app = Application(tmp_path / "state")
    try:
        project = tmp_path / "工程"
        app.dispatch("project.create", {"path": str(project)})
        path = Path.home() / ".workbuddy/mcp.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"mcpServers": {"other": {"command": "existing"}}}))
        result = app.dispatch("mcp.configure", {"allow_writes": False, "confirm_user_config": True})
        saved = json.loads(path.read_text())
        assert saved["mcpServers"]["other"] == {"command": "existing"}
        server = result["server"]
        assert server["command"] == str(Path(sys.executable).absolute())
        assert server["args"][:3] == ["-m", "gongke_app", "mcp"]
        assert server["args"][-1] == str(project)
        assert "--allow-writes" not in server["args"]
        assert Path(server["env"]["PYTHONPATH"]).joinpath("gongke_app").is_dir()
        packaged = write_workbuddy(app.current(), app.state_dir, Path(sys.executable), False)
        assert packaged["server"]["args"][0] == "mcp"
        assert "env" not in packaged["server"]
    finally:
        app.tasks.close()


# 配置测试使用独立用户目录，不读取开发者真实 WorkBuddy 配置。
import pytest

@pytest.fixture(autouse=True)
def workbuddy_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
