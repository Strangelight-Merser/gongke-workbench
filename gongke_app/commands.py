"""工程命令的唯一执行路径。"""
from __future__ import annotations

import threading
import json
from contextlib import nullcontext
from uuid import uuid4
from gongke_core import api, native_client
from gongke_app.tools import definitions, validate, NATIVE
from gongke_app.native import create_shaft_project


class Commands:
    def __init__(self, hosts=None):
        self.hosts = hosts
        self.native_lock = threading.RLock()
        self.definitions = definitions()

    def submission(self, method, params, project, *, allow_writes=True):
        """提交时固定生成输入；排队期间用户仍可编辑下一版任务书。"""
        inputs = None
        if method == "design.generate":
            validate(params, self.definitions[method][1])
            with project.lock:
                if "task" in params and params["task"] != project.manifest.get("task"):
                    raise ValueError("请先用 project.set_task 保存已确认的条件及教学标记，再计算或生成")
                inputs = (project.task(params.get("task")), project.manifest["teaching"])
        return lambda ctx: self.call(method, params, project, ctx, allow_writes=allow_writes, inputs=inputs)

    def call(self, method, params, project, ctx=None, *, allow_writes=True, inputs=None):
        receipt_id = None
        try:
            if method not in self.definitions:
                raise ValueError("未知应用命令：" + method)
            validate(params, self.definitions[method][1])
            write = self.definitions[method][2]
            if write and not allow_writes:
                raise ValueError("本次任务未授权写入；需要在工作台启用本次工程修改")
            if project is None and (write or method.startswith("project.")):
                raise ValueError("请先创建或打开工程")
            if ctx:
                ctx.check()
            if method in {"design.calculate", "design.generate"} and inputs is None and "task" in params and params["task"] != project.manifest.get("task"):
                raise ValueError("请先用 project.set_task 保存已确认的条件及教学标记，再计算或生成，避免工作区与工具使用不同任务书")
            if method == "design.generate" and inputs is None:
                with project.lock:
                    inputs = (project.task(), project.manifest["teaching"])
            with self.native_lock if method.startswith("freecad.") else nullcontext():
                prepared = self._prepare_native(method, params, project) if method.startswith("freecad.") else params
                if ctx:
                    recorded = {**prepared, "task": inputs[0], "teaching": inputs[1]} if inputs is not None else prepared
                    receipt_id = ctx.begin(method, recorded)
                result = self._execute(method, prepared, project, ctx, inputs=inputs)
                if ctx:
                    ctx.finish(receipt_id, result)
                return result
        except Exception as exc:
            if ctx:
                if receipt_id is None:
                    ctx.receipt(method, params, {"error": str(exc)})
                else:
                    ctx.finish(receipt_id, {"error": str(exc)})
            raise

    def _prepare_native(self, method, params, project):
        short = method.split(".")[1]
        args = dict(params)
        if short == "create" and args.get("case") == "course_output":
            with project.lock:
                if "task" in args and args["task"] != project.manifest.get("task"):
                    raise ValueError("请先用 project.set_task 保存已确认条件，再创建原生课程轴")
                args["task"] = project.task()
        if short == "export_drawing" and "path" not in args:
            args["path"] = "revisions/native-drawing-" + uuid4().hex[:12] + "/page.dxf"
        if short in {"save", "export_drawing"}:
            target = project.resolve(args["path"])
            if target.exists() and not (short == "save" and project.is_working_copy(target, "freecad")):
                raise ValueError("目标已存在；请保存为新的工作副本，不能覆盖原件")
            if short == "save" and target.suffix.lower() != ".fcstd":
                raise ValueError("FreeCAD 工作副本需使用 .FCStd 后缀")
            args["path"] = str(target)
            if short == "save":
                context = native_client.call("get_project_context")
                if context.get("session_id") != args["session_id"]:
                    raise ValueError("原生文档会话已改变，请重新读取")
                if target.exists() and context.get("path") != str(target):
                    raise ValueError("只能保存当前文档自身的已登记工作副本，不能覆盖其他文件")
        if short in {"apply", "bind", "undo", "update_drawing"}:
            context = native_client.call("get_project_context")
            if (context.get("session_id") != args.get("session_id")
                    or not project.is_working_copy(context.get("path"), "freecad")):
                raise ValueError("请先通过工作台将当前原生工程保存为新工作副本，再修改；放在工程目录中的原件也不会被直接修改")
            if "expected_revision" in args and context.get("revision") != args["expected_revision"]:
                raise ValueError("原生文档修订已过期，请重新读取")
        return args

    def _execute(self, method, params, project, ctx=None, *, inputs=None):
        if method == "project.set_task":
            return project.set_task(**params)
        if method == "project.current":
            return project.view()
        if method == "project.files":
            return project.files()
        if method == "project.read_file":
            return project.read(**params)
        if method == "design.schema":
            return api.task_schema()
        if method == "design.example":
            return {"teaching": True, "task": api.example_task(params.get("scheme", "coupling"))}
        if method == "design.calculate":
            result = api.design(project.task(params.get("task")))
            result["teaching"] = project.manifest["teaching"]
            return result
        if method == "design.generate":
            return self._generate(params, project, ctx, inputs=inputs)
        if method == "design.validate":
            return {"errors": api.validate(params["task"])}
        if method == "design.explore":
            return api.explore(project.task(), **params)
        if method == "design.report":
            return api.report(project.task(), **params)
        if method == "standards.lookup":
            return api.lookup(params["kind"], **params.get("params", {}))
        if method == "drawing.check":
            return api.check_drawings(str(project.resolve(params["path"])))
        if method == "revision.inspect":
            from gongke_core.revision_case import inspect_revision
            return inspect_revision(**params)
        if method == "revision.export":
            from gongke_core.revision_case import inspect_revision, format_summary
            output = project.resolve(params["path"])
            if output.exists():
                raise ValueError("输出目录已存在，请指定新目录，保留原来的检查记录")
            result = inspect_revision(**{key: value for key, value in params.items() if key != "path"})
            output.mkdir(parents=True, exist_ok=False)
            (output / "revision.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            return {"review": result, "summary": format_summary(result), "path": str(output / "revision.json")}
        if method == "hosts.list":
            return self.hosts.list()
        if method in {"host.context", "host.inspect", "host.section", "host.measure", "host.check"}:
            return self.hosts.inspect(method, **params, project=project)
        from gongke_app.modeling import TO_NATIVE
        if method in TO_NATIVE:
            args = dict(params)
            host_id = args.pop("host_id")
            return self.hosts.command(host_id, TO_NATIVE[method], args, project)
        if method in {"host.read", "host.write"}:
            return self.hosts.command(**params, project=project)
        if method.startswith("freecad."):
            return self._execute_native(method, params, project, ctx)
        raise ValueError("命令尚未实现")

    def _execute_native(self, method, params, project, ctx):
        if ctx:
            ctx.check()
        short = method.split(".")[1]
        args = dict(params)
        if short in {"save", "export_drawing"}:
            from pathlib import Path
            target = Path(args["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
        if short in NATIVE:
            if short == "create":
                return create_shaft_project(**args)
            try:
                result = native_client.call(NATIVE[short], **args)
            except native_client.NativeBridgeError as exc:
                # 只回读，不把历史回执当成本次请求成功（宿主也可能明确拒绝了 ID 复用）。
                if short == "save":
                    readback = native_client.call("get_project_context")
                elif short in {"apply", "bind", "undo"}:
                    readback = native_client.call("get_operation_status", session_id=args["session_id"], operation_id=args["operation_id"])
                else:
                    raise
                return {"error": str(exc), "readback": readback}
            if short == "save" and result.get("saved"):
                project.register_copy(args["path"], "freecad", result)
            return result
        return native_client.call({"scene": "get_display_scene", "select": "select_display_object", "operation": "get_operation_status",
                                   "update_drawing": "update_drawing", "export_drawing": "export_drawing"}[short], **args)

    def _generate(self, params, project, ctx=None, *, inputs=None):
        with project.lock:
            task, teaching = inputs if inputs is not None else (project.task(params.get("task")), project.manifest["teaching"])
            output = project.output(params.get("name"))
            output.mkdir()
            relative = output.relative_to(project.path).as_posix()
            project.add_result({"kind": "generation", "path": relative, "status": "running",
                                "input_hash": project.input_hash(task, teaching),
                                "teaching": teaching, "calculation_ok": False, "exports_complete": False})
        if ctx:
            ctx.stage("计算并导出文件；当前导出将安全结束后响应取消")
        options = {key: params[key] for key in ("step", "drawings", "report_docx", "full_teeth") if key in params}
        try:
            result = api.generate(task, str(output), **options)
            result["teaching"] = teaching
            project.update_result(relative, {key: result[key] for key in
                ("status", "calculation_ok", "exports_complete", "run_id", "artifacts", "drawing_check") if key in result})
            return result
        except Exception as exc:
            project.update_result(relative, {"status": "failed", "error": str(exc)})
            raise
