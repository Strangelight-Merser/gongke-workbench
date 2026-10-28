"""当前轴的受限梁求解任务；输入快照不随 CAD 后续编辑变化。

计算完成只表示求解任务成功。调用方必须比较 source_context 与当前工程，
才能决定结果适用性；此模块不回写或修改任何 CAD 文档。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from uuid import UUID, uuid4

from gongke_core.calc import shaft_stiffness
from gongke_core.fem import ccx, shaft_beam
from gongke_core.shaft_review import _inputs, validate_snapshot


TIMEOUT_SECONDS = 300
METHOD_VERSION = "shaft-beam-u1-v1"
H_MAX_M = 0.002
POISSON_RATIO = 0.3
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}
LIMITATIONS = [
    "当前三段轴的抽象梁刚度复核，不是实际 CAD 局部应力或疲劳验证。",
    "只施加横向载荷；输入中的 torque_points 不进入该梁仿真，不提供扭转结论。",
    "支承采用简支约束，材料为线弹性，泊松比假定为 0.3。",
    "解析对照采用相同的 Timoshenko 剪切变形假设；数值接近不证明实际零件安全。",
    "任务保存原始工程上下文；是否仍适用于当前编辑版本由调用方核对。",
]

COURSE_LIMITATIONS = [
    "七段课程轴的圆截面梁刚度复核，不计键槽对截面惯性矩的局部削弱，不验证圆角应力或疲劳。",
    "施加完整集中力和轴向力偏心力偶；torque_points 不进入梁仿真，不提供扭转结论。",
    "支承采用简支约束，材料为线弹性，泊松比假定为 0.3。",
    "刚度限值沿用当前工程声明，来源状态随结果保留；数值通过不代表这些条件已获专业确认。",
    "解析对照采用相同的 Timoshenko 剪切变形假设，二者接近不能证明实际零件安全。",
]


def _beam_inputs(snapshot):
    if snapshot.get("scope") == "course_shaft_review":
        from gongke_core.course_shaft import _current_inputs
        state = snapshot.get("cad_geometry_state", {})
        if (state.get("parameters_current") is not True or state.get("load_binding_current") is not True
                or state.get("unsupported_features")):
            raise ValueError("课程轴当前 CAD 尺寸或载荷位置未绑定，不能提交梁仿真")
        segments, case = _current_inputs(snapshot)
        limits = snapshot["stiffness_limits"]
        for item in limits:
            if (item["kind"] not in ("y", "θ") or item.get("unit") != ("m" if item["kind"] == "y" else "rad")
                    or isinstance(item["limit"], bool) or not math.isfinite(item["limit"]) or item["limit"] <= 0
                    or not segments[0].z0 <= item["z_m"] <= segments[-1].z1):
                raise ValueError("课程轴刚度控制位置或限值无效")
        if not limits:
            raise ValueError("课程轴缺少刚度控制位置及限值")
        young = snapshot["material"]["young_modulus_pa"]
        if isinstance(young, bool) or not math.isfinite(young) or young <= 0:
            raise ValueError("弹性模量必须为有限正数")
        return segments, case, COURSE_LIMITATIONS
    errors = validate_snapshot(snapshot)
    if errors:
        raise ValueError("；".join(errors))
    segments, case = _inputs(snapshot)
    return segments, case, LIMITATIONS


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2)


def _write(path, value):
    """先写完整临时文件，再发布引用和状态。"""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(_json(value), encoding="utf-8")
    temporary.replace(path)


def _stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def _process_identity(pid):
    """只在 macOS 读取完整 OS 身份；查询失败不能视作进程已退出。"""
    if sys.platform != "darwin":
        raise RuntimeError("当前平台未实现孤儿求解器身份核对及自动清理")
    if type(pid) is not int or pid <= 1:
        raise ValueError("无效的进程 PID")
    result = subprocess.run(
        ["/bin/ps", "-ww", "-p", str(pid), "-o", "pid=", "-o", "ppid=",
         "-o", "stat=", "-o", "lstart=", "-o", "command="],
        capture_output=True, text=True, timeout=2, env=dict(os.environ, LC_ALL="C"),
    )
    if result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip():
        return None
    if result.returncode != 0:
        raise RuntimeError(f"无法核对进程 {pid}：ps 返回 {result.returncode}")
    fields = result.stdout.strip().split(None, 8)
    if len(fields) != 9 or not fields[0].isdigit() or int(fields[0]) != pid or not fields[1].isdigit():
        raise RuntimeError(f"无法解析进程 {pid} 的完整身份")
    return {"pid": pid, "ppid": int(fields[1]), "state": fields[2],
            "started": " ".join(fields[3:8]), "command": fields[8]}


def _valid_identity(value):
    return (isinstance(value, dict) and type(value.get("pid")) is int and value["pid"] > 1
            and isinstance(value.get("started"), str) and bool(value["started"])
            and isinstance(value.get("command"), str) and bool(value["command"]))


def _same_process(current, recorded):
    # GUI 崩溃后子进程会重归属；当前 PPID 不能再作为原 solver 的身份证明。
    return current is not None and all(current[k] == recorded[k] for k in ("pid", "started", "command"))


def _owner_exited(record):
    owner = record.get("owner_process")
    if not _valid_identity(owner):
        return False, "缺少原任务管理进程的完整身份，未自动清理"
    try:
        current = _process_identity(owner["pid"])
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if _same_process(current, owner) and "Z" not in current["state"]:
        raise RuntimeError(f"任务管理进程 {owner['pid']} 仍在运行，不能接管同一任务目录")
    return True, None


def _wait_process_exit(identity, timeout):
    deadline = time.monotonic() + timeout
    while True:
        current = _process_identity(identity["pid"])
        if current is None or (_same_process(current, identity) and "Z" in current["state"]):
            return True
        if not _same_process(current, identity):
            raise RuntimeError("求解器身份变化，未继续发送信号，无法确认原进程退出")
        if time.monotonic() >= deadline:
            return False
        time.sleep(.05)


def _recover_solver(record, owner_exited, owner_error):
    """只清理完整身份仍一致的原子进程；每个信号前重新核对。"""
    cleanup = {"status": "unverified", "signals": []}
    if not owner_exited:
        return dict(cleanup, reason=owner_error)
    solver = record.get("solver_process")
    owner = record["owner_process"]
    stem = f"shaft-{record['job_id']}"
    if (not _valid_identity(solver) or solver.get("ppid") != owner["pid"]
            or solver["pid"] != record.get("pid") or solver["pid"] == owner["pid"]
            or record.get("input_stem") != stem or not solver["command"].endswith(" -i " + stem)):
        return dict(cleanup, reason="缺少匹配本任务 UUID 的原始求解器身份或父子关系，未自动清理")
    try:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            current = _process_identity(solver["pid"])
            if current is None or (_same_process(current, solver) and "Z" in current["state"]):
                return dict(cleanup, status="terminated" if cleanup["signals"] else "already_exited")
            if not _same_process(current, solver):
                return dict(cleanup, reason="当前 PID 的启动时间或完整命令不匹配，未发送信号")
            try:
                os.kill(solver["pid"], sig)
                cleanup["signals"].append(signal.Signals(sig).name)
            except ProcessLookupError:
                pass
            if _wait_process_exit(solver, 2):
                return dict(cleanup, status="terminated")
        return dict(cleanup, reason="已发送终止信号，但未能确认求解器退出")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        return dict(cleanup, reason=str(exc))


class JobManager:
    """一个根目录由一个进程中的管理器拥有；重启后旧任务标记为中断。"""

    def __init__(self, root_dir):
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._jobs = {}
        self._events = {}
        self._processes = {}
        pending = []
        for path in self.root.glob("*/status.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            job_id = record["job_id"]
            if path.parent.name != str(UUID(job_id)):
                raise ValueError(f"任务目录与身份不一致：{path}")
            if record["status"] not in TERMINAL:
                pending.append((path, record, *_owner_exited(record)))
            self._jobs[job_id] = record
        # 先排除仍活跃的 owner，再改变任何旧记录，避免部分接管活任务。
        for path, record, exited, error in pending:
            cleanup = _recover_solver(record, exited, error)
            record.update(status="interrupted", finished_at=_now(),
                          error="任务管理进程中断，未恢复求解。" if exited else "旧任务未恢复，原管理进程是否退出及资源清理未核实。",
                          recovery_cleanup=cleanup)
            _write(path, record)
        self._owner = None
        self._owner_error = None
        try:
            self._owner = _process_identity(os.getpid())
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            self._owner_error = str(exc)

    def start(self, snapshot, source_context):
        """提交独立快照。无效输入抛出 ValueError；环境问题记为任务失败。"""
        _, _, limitations = _beam_inputs(snapshot)
        if not isinstance(source_context, dict):
            raise ValueError("source_context 必须是当前工程上下文对象")
        # JSON 往返同时固定输入及上下文，不保存对调用方可变对象的引用。
        data = json.loads(_json(snapshot))
        context = json.loads(_json(source_context))
        job_id = str(uuid4())
        directory = self.root / job_id
        directory.mkdir()
        _write(directory / "snapshot.json", data)
        _write(directory / "source_context.json", context)
        (directory / "stdout.log").touch()
        record = {
            "job_id": job_id, "status": "queued", "created_at": _now(),
            "source_context": context,
            "input_hash": hashlib.sha256(_json(data).encode()).hexdigest(),
            "method_version": METHOD_VERSION, "directory": str(directory),
            "input_stem": f"shaft-{job_id}", "owner_process": self._owner,
            "limitations": list(limitations),
        }
        if self._owner_error:
            record["owner_identity_error"] = self._owner_error
        with self._lock:
            self._jobs[job_id] = record
            self._events[job_id] = threading.Event()
            _write(directory / "status.json", record)
        threading.Thread(target=self._run, args=(job_id, data), daemon=True,
                         name=f"shaft-{job_id[:8]}").start()
        return {"job_id": job_id, "status": "queued"}

    def get(self, job_id):
        with self._lock:
            if not isinstance(job_id, str) or job_id not in self._jobs:
                raise ValueError("任务不存在")
            return deepcopy(self._jobs[job_id])

    def _update(self, job_id, **changes):
        with self._lock:
            record = self._jobs[job_id]
            if record["status"] in TERMINAL:
                return
            record.update(changes)
            _write(self.root / job_id / "status.json", record)

    def cancel(self, job_id):
        with self._lock:
            record = self.get(job_id)
            if record["status"] in TERMINAL:
                return record
            self._events[job_id].set()
            process = self._processes.get(job_id)
        # 先终止并回收已启动的求解器，再公布取消；不留下假取消的计算进程。
        if process is not None:
            _stop(process)
        self._update(job_id, status="cancelled", finished_at=_now(), error="用户取消求解。")
        return self.get(job_id)

    def _run(self, job_id, snapshot):
        directory = self.root / job_id
        event = self._events[job_id]
        process = None
        try:
            self._update(job_id, status="running", started_at=_now())
            if event.is_set():
                return
            executable = ccx.find()
            ccx.check_version(executable)
            if event.is_set():
                return
            segments, case, limitations = _beam_inputs(snapshot)
            young = snapshot["material"]["young_modulus_pa"]
            inp = directory / f"shaft-{job_id}.inp"
            nodes = shaft_beam.write_inp(inp, segments, case, E=young, nu=POISSON_RATIO, h_max=H_MAX_M)
            self._update(job_id, solver=str(executable), mesh_size_m=H_MAX_M,
                         poisson_ratio=POISSON_RATIO, node_count=len(nodes))
            with (directory / "stdout.log").open("w", encoding="utf-8") as log:
                with self._lock:
                    if event.is_set():
                        return
                    process = subprocess.Popen(
                        [str(executable), "-i", inp.stem], cwd=directory,
                        stdout=log, stderr=subprocess.STDOUT,
                        env=dict(os.environ, OMP_NUM_THREADS="1"),
                    )
                    self._processes[job_id] = process
                    identity, identity_error = None, None
                    try:
                        identity = _process_identity(process.pid)
                        if identity is None:
                            identity_error = "求解器已在身份捕获前退出；无可用于重启清理的身份"
                        elif (self._owner is None or identity["ppid"] != self._owner["pid"]
                              or not identity["command"].endswith(" -i " + inp.stem)):
                            identity = None
                            identity_error = "求解器初始父子关系或任务 UUID 命令未核实"
                    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                        identity_error = str(exc)
                    self._update(job_id, pid=process.pid, solver_process=identity,
                                 solver_identity_error=identity_error)
                try:
                    code = process.wait(timeout=TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    _stop(process)
                    if event.is_set():
                        return
                    raise RuntimeError(f"求解超过 {TIMEOUT_SECONDS} 秒，已终止进程。")
            if event.is_set():
                return
            output = (directory / "stdout.log").read_text(encoding="utf-8", errors="replace")
            dat = inp.with_suffix(".dat")
            if code != 0 or "*ERROR" in output or not dat.is_file():
                raise RuntimeError(f"ccx 计算失败（返回码 {code}）：\n" + "\n".join(output.splitlines()[-15:]))
            displacements = shaft_beam.read_displacements(dat)
            if any(i not in displacements or len(displacements[i]) != 6
                   or not all(math.isfinite(v) for v in displacements[i])
                   for i in range(1, len(nodes) + 1)):
                raise RuntimeError("梁位移结果缺少节点、转角或存在非有限数。")
            fem = [math.hypot(displacements[i][0], displacements[i][1]) * shaft_beam.MM
                   for i in range(1, len(nodes) + 1)]
            analytic = shaft_stiffness.solve(segments, case, E=young, shear=True, nu=POISSON_RATIO)
            reference = [analytic.deflection(z) for z in nodes]
            peak = max(range(len(nodes)), key=lambda i: fem[i])
            reference_max = max(reference)
            deviation = max(abs(a - b) for a, b in zip(fem, reference))
            result = {
                "scope": "shaft_beam_stiffness", "max_deflection_m": fem[peak],
                "peak_z_m": nodes[peak], "timoshenko_max_deflection_m": reference_max,
                "max_absolute_difference_m": deviation,
                "normalized_max_difference": deviation / reference_max if reference_max else None,
                "limitations": list(limitations),
            }
            if snapshot["scope"] == "course_shaft_review":
                curve = shaft_beam.BeamResult(nodes,
                    [displacements[i][0] * shaft_beam.MM for i in range(1, len(nodes) + 1)],
                    [displacements[i][1] * shaft_beam.MM for i in range(1, len(nodes) + 1)],
                    [displacements[i][3] for i in range(1, len(nodes) + 1)],
                    [displacements[i][4] for i in range(1, len(nodes) + 1)])
                checks = []
                for item in snapshot["stiffness_limits"]:
                    value = curve.deflection(item["z_m"]) if item["kind"] == "y" else curve.slope(item["z_m"])
                    checks.append({**item, "value": value, "status": "pass" if value <= item["limit"] else "fail"})
                result.update(checks=checks, conclusion="pass" if all(c["status"] == "pass" for c in checks) else "fail",
                              engineering_conclusion="not_established", source_scope=snapshot["scope"])
            else:
                result.update(limit_m=snapshot["constraints"]["max_deflection_m"],
                              conclusion="pass" if fem[peak] <= snapshot["constraints"]["max_deflection_m"] else "fail")
            _write(directory / "displacements.json", {
                "z_m": nodes, "deflection_m": fem, "timoshenko_deflection_m": reference,
                "node_values_mm_rad": displacements,
            })
            _write(directory / "result.json", result)
            if not event.is_set():
                self._update(job_id, status="succeeded", finished_at=_now(), result=result)
        except Exception as exc:
            if not event.is_set():
                self._update(job_id, status="failed", finished_at=_now(), error=str(exc))
        finally:
            if process is not None and process.poll() is None:
                _stop(process)
            with self._lock:
                self._processes.pop(job_id, None)
