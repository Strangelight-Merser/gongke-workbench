"""新建的默认值不依赖桌面入口，已有计算能力需显式提供条件。"""
import json
import subprocess
import sys
from pathlib import Path
import pytest
from gongke_app.project import Project
from gongke_app.service import Application


def assert_empty(view):
    assert view['task'] is None
    assert view['results'] == []
    assert view['working_copies'] == []
    assert view['delivery'] is None
    assert [f['name'] for f in view['files']] == ['gongke-project.json']


def test_create_is_empty_for_python_and_stdio(tmp_path):
    assert_empty(Project.create(str(tmp_path/'python')).view())
    result = subprocess.run([sys.executable,'-m','gongke_app.service','--state-dir',str(tmp_path/'state')],
        input=json.dumps({'id':1,'method':'project.create','params':{'path':str(tmp_path/'stdio')}})+'\n',
        text=True,capture_output=True,check=True,cwd=Path(__file__).resolve().parents[1])
    assert_empty(json.loads(result.stdout)['result'])


def test_creation_rejects_retired_teaching_parameter(tmp_path):
    app = Application(tmp_path/'state')
    try:
        with pytest.raises(ValueError):
            app.dispatch('project.create', {'path':str(tmp_path/'project'),'teaching':True})
        assert not (tmp_path/'project').exists()
        assert_empty(app.dispatch('project.create',{'path':str(tmp_path/'project')}))
        assert app.dispatch('task.list',{}) == []
        with pytest.raises(ValueError,match='尚无计算条件'):
            app.dispatch('design.calculate',{})
    finally:
        app.close()
