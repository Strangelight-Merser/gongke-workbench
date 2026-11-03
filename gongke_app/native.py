"""FreeCAD 工程初始化；由应用命令执行，计算与宿主进程保持分离。"""
import json
from gongke_core import api, native_client

def create_shaft_project(case="teaching", task=None):
    """初始化在外部 Python 计算，原生文档创建由 FreeCAD 主线程执行。"""
    if case == "teaching":
        if task is not None:
            raise ValueError("教学三段轴不接收减速器任务书")
        from importlib.resources import files
        from uuid import uuid4
        snapshot = json.loads(files("gongke_core").joinpath("resources/native_shaft.json").read_text(encoding="utf-8"))
        snapshot["entity_id"] = str(uuid4())
    elif case == "course_output":
        from gongke_core.course_shaft import from_design
        task = api.example_task("coupling") if task is None else task
        errors = api.validate(task)
        if errors:
            raise ValueError("；".join(errors))
        snapshot = from_design(api._run(task))
        snapshot["initialization"] = {"task": task, "source": "coupling design initialization"}
    else:
        raise ValueError("case 必须为 teaching 或 course_output")
    return native_client.call("create_project", snapshot=snapshot)
