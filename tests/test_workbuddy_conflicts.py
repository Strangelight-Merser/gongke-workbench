"""用户级安装只在明确同意后写入，备份、保留其他条目并可撤销。"""
import json
from pathlib import Path
import sys

import pytest

from gongke_app.connection import write_workbuddy, restore_workbuddy
from gongke_app.project import Project


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    user = Path.home() / ".workbuddy/mcp.json"
    user.parent.mkdir(parents=True)
    project = Project.create(str(tmp_path / "project"), teaching=False)
    def configure(**kwargs):
        return write_workbuddy(project, tmp_path / "state", Path(sys.executable), False, **kwargs)
    return project, user, configure


@pytest.mark.parametrize("name,args", [("gongke", ["some-service"]), ("old-cad", "-P -m gongke_core mcp"), ("old-cad", ["-m", "gongke_core", "mcp"])])
def test_consent_backup_preservation_and_restore(setup, name, args):
    project, user, configure = setup
    user.write_text(json.dumps({"extra": 42, "mcpServers": {name: {"command": "python", "args": args}, "unrelated": {"env": {"secret": "keep"}}}}))
    before = user.read_bytes()
    pending = configure()
    assert pending["status"] == "confirmation_required"
    assert pending["conflicts"][0]["name"] == name
    assert "keep" not in json.dumps(pending)
    assert user.read_bytes() == before
    result = configure(confirm_user_config=True)
    assert result["status"] == "configured"
    assert result["service_name"].startswith("gongke-")
    assert Path(result["backup_path"]).read_bytes() == before
    saved = json.loads(user.read_bytes())
    del saved["mcpServers"][result["service_name"]]
    assert saved == json.loads(before)
    assert not (project.path / '.workbuddy/mcp.json').exists()
    assert configure()["service_name"] == result["service_name"]
    assert configure()["status"] == "confirmation_required"
    restore_workbuddy(Path(result["backup_path"]), result["config_sha256"])
    assert user.read_bytes() == before


def test_new_install_also_requires_consent(setup):
    project, user, configure = setup
    pending = configure()
    assert pending["status"] == "confirmation_required"
    assert not user.exists()
    assert not list(user.parent.iterdir())
    result = configure(confirm_user_config=True)
    assert result["service_name"] in json.loads(user.read_text())["mcpServers"]
    restore_workbuddy(Path(result["backup_path"]), result["config_sha256"])
    assert json.loads(user.read_text()) == {"mcpServers": {}}


def test_collision_preserved_and_restore_rejects_later_edits(setup):
    project, user, configure = setup
    name = configure()["service_name"]
    user.write_text(json.dumps({"mcpServers": {name: {"command": "other"}}}))
    result = configure(confirm_user_config=True)
    assert result["service_name"] == name + '-2'
    data = json.loads(user.read_text())
    assert data["mcpServers"][name] == {"command": "other"}
    data["later"] = True
    user.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="配置已变化"):
        restore_workbuddy(Path(result["backup_path"]), result["config_sha256"])
    assert json.loads(user.read_text())["later"]


def test_invalid_json_is_not_overwritten(setup):
    _, user, configure = setup
    user.write_text('{ broken')
    with pytest.raises(ValueError):
        configure(confirm_user_config=True)
    assert user.read_text() == '{ broken'
