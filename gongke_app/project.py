"""Portable project manifest; generated revisions never replace input files."""
from __future__ import annotations

import json
from pathlib import Path
import threading
from uuid import uuid4

from gongke_core import api

MANIFEST = "gongke-project.json"


class Project:
    def __init__(self, path: Path, manifest: dict):
        self.path = path.resolve()
        self.manifest = manifest
        self.lock = threading.RLock()

    @classmethod
    def create(cls, path: str, name: str | None = None, teaching: bool = True):
        root = Path(path).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        manifest = {"version": 1, "name": name or root.name, "teaching": teaching,
                    "task": api.example_task() if teaching else None, "results": [], "working_copies": []}
        # Exclusive creation keeps an existing project and all original files intact.
        with (root / MANIFEST).open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
        return cls(root, manifest)

    @classmethod
    def open(cls, path: str):
        root = Path(path).expanduser().resolve()
        if root.is_file() and root.name == MANIFEST:
            root = root.parent
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        if manifest.get("version") != 1 or not isinstance(manifest.get("results"), list):
            raise ValueError("不支持的工程清单，请选择包含 gongke-project.json 的工程目录")
        return cls(root, manifest)

    def save(self):
        # Callers hold the project lock; atomic replacement avoids a partial manifest.
        temp = self.path / (".gongke-" + uuid4().hex + ".tmp")
        temp.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temp.replace(self.path / MANIFEST)

    def resolve(self, relative: str, *, exists: bool = False) -> Path:
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise ValueError("文件必须使用工程内的相对路径")
        target = (self.path / relative).resolve()
        if not target.is_relative_to(self.path) or target == self.path:
            raise ValueError("不能访问工程目录以外的文件")
        if exists and not target.is_file():
            raise ValueError("工程文件不存在")
        return target

    def output(self, name: str | None = None) -> Path:
        name = name or uuid4().hex[:12]
        if not isinstance(name, str) or name in (".", "..") or any(c in name for c in "/\\:"):
            raise ValueError("修订名称不能包含路径分隔符")
        target = self.resolve("revisions/" + name)
        if target.exists():
            raise ValueError("该修订已存在，请使用新的名称；已有文件不会覆盖")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def files(self) -> list[dict]:
        rows = []
        for path in sorted(self.path.rglob("*")):
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(self.path):
                continue
            relative = path.relative_to(self.path)
            if any(part.startswith(".") for part in relative.parts):
                continue
            rows.append({"path": relative.as_posix(), "name": path.name,
                         "kind": path.suffix.lower().lstrip("."), "size": path.stat().st_size})
        return rows

    def view(self):
        with self.lock:
            return {**json.loads(json.dumps(self.manifest)), "path": str(self.path), "files": self.files()}

    def task(self, supplied=None):
        with self.lock:
            task = supplied if supplied is not None else self.manifest.get("task")
            if not isinstance(task, dict):
                raise ValueError("工程尚无计算条件，请设置任务书或明确选择教学示例")
            errors = api.validate(task)
            if errors:
                raise ValueError("；".join(errors))
            return json.loads(json.dumps(task, allow_nan=False))

    def set_task(self, task, teaching=None):
        validated = self.task(task)
        with self.lock:
            self.manifest["task"] = validated
            if teaching is not None:
                self.manifest["teaching"] = teaching
            self.save()
        return self.view()

    def add_result(self, result):
        with self.lock:
            self.manifest["results"].append(result)
            self.save()

    def remember_copy_operation(self, operation):
        """Persist the exact request before handing a new copy to a native host."""
        with self.lock:
            operations = self.manifest.setdefault("copy_operations", {})
            operation_id = operation["operation_id"]
            if operation_id in operations:
                raise ValueError("该副本操作 ID 已提交；请查询原操作结果，不要重复写入")
            operations[operation_id] = json.loads(json.dumps(operation, allow_nan=False))
            self.save()

    def copy_operation(self, operation_id):
        with self.lock:
            record = self.manifest.get("copy_operations", {}).get(operation_id)
            return json.loads(json.dumps(record)) if record else None

    def register_copy(self, path, host, receipt, *, operation_id=None):
        self.register_copies([(path, receipt)], host, operation_id=operation_id)

    def register_copies(self, entries, host, *, operation_id=None):
        records = []
        for path, receipt in entries:
            target = Path(path).resolve()
            if not target.is_relative_to(self.path) or not target.is_file():
                raise ValueError("原生保存回执未能验证为工程内的实际文件；未授予该文件修改资格")
            if not receipt.get("path") or Path(receipt["path"]).resolve() != target:
                raise ValueError("原生保存回执路径与请求不一致；未授予该文件修改资格")
            relative = target.relative_to(self.path).as_posix()
            records.append({"path": relative, "host": host, "receipt": receipt,
                            **({"operation_id": operation_id} if operation_id else {})})
        with self.lock:
            operation = self.manifest["copy_operations"][operation_id] if operation_id else None
            if operation and operation["state"] == "registered":
                return
            self.manifest.setdefault("working_copies", []).extend(records)
            if operation:
                operation["state"] = "registered"
            self.save()

    def is_working_copy(self, path, host):
        if not path:
            return False
        target = Path(path).resolve()
        if not target.is_relative_to(self.path) or not target.is_file():
            return False
        relative = target.relative_to(self.path).as_posix()
        with self.lock:
            return any(item["path"] == relative and item["host"] == host for item in self.manifest.get("working_copies", []))

    def read(self, path: str):
        target = self.resolve(path, exists=True)
        if target.suffix.lower() not in {".svg", ".json", ".md", ".txt", ".yaml", ".yml"}:
            raise ValueError("此文件需由原生软件打开；工作台目前预览 SVG、JSON 和文本")
        if target.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("文件超过 4 MiB 预览上限")
        return {"path": path, "kind": target.suffix.lstrip("."), "content": target.read_text(encoding="utf-8")}
