"""专用 GUI 中的真实 ccx 验收；默认退出，GONGKE_E2E_KEEP_OPEN=1 才保留窗口。"""

import importlib.util
import json
import os
from pathlib import Path
import shlex

import FreeCAD as App
import FreeCADGui as Gui

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("shaft_job_lifecycle_flow", ROOT / "tests/e2e/shaft_job_lifecycle_flow.py")
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)
owned_gui = flow.JobLifecycleSession._ps(os.getpid())
command = shlex.split(owned_gui["command"])
assert len(command) == 2 and Path(command[0]).name == "freecad" and Path(command[1]).resolve() == Path(__file__).resolve(), \
    "必须由本宏启动专用 GUI，不能接管既有实例"
keep_open = os.environ.get("GONGKE_E2E_KEEP_OPEN") == "1"
initial_documents = set(App.listDocuments())
try:
    assert not initial_documents, "专用验收 GUI 不应已有用户文档"
    output = Path(os.environ["GONGKE_NATIVE_OUT"]).resolve()
    endpoint = output / "freecad-session.json"
    os.environ["GONGKE_FREECAD_SESSION"] = str(endpoint)
    from freecad.gongke import bridge, native_shaft

    installed = Path(App.getUserAppDataDir()) / "Mod/GongKeWorkbench"
    assert Path(native_shaft.__file__).is_relative_to(installed)
    assert Path(bridge.__file__).is_relative_to(installed)
    if bridge._bridge is not None:
        assert bridge._bridge.endpoint.resolve() == endpoint, "当前 GUI 的工程桥属于其他端点，不能替换"
    if output.exists():
        assert all(path == endpoint for path in output.iterdir()), "验收目录已有证据，请使用新目录"
    if endpoint.exists():
        # 自动激活可能早于宏，仅允许当前进程的本轮端点。
        owner = json.loads(endpoint.read_text(encoding="utf-8"))
        assert bridge._bridge is not None and owner["pid"] == os.getpid(), "端点不属于本轮 GUI"
        assert owner["token"] == bridge._bridge.token, "端点与本轮工程桥身份不一致"
    output.mkdir(parents=True, exist_ok=True)
    Gui.activateWorkbench("GongKeWorkbench")
    assert bridge._bridge is not None and bridge._bridge.endpoint.resolve() == endpoint
    owner = json.loads(endpoint.read_text(encoding="utf-8"))
    assert owner["pid"] == os.getpid() and owner["token"] == bridge._bridge.token, "激活后的端点身份不一致"
    os.environ.setdefault("GONGKE_MCP_ROOT", str(installed))
    assert Path(os.environ["GONGKE_MCP_ROOT"]).resolve() == installed.resolve(), "MCP 必须使用独立安装副本"
    Gui.runCommand("GongKe_NativeShaft")
    session = flow.start(output, os.environ["GONGKE_EXTERNAL_PYTHON"], owned_gui=owned_gui, keep_open=keep_open)
except BaseException:
    if not keep_open:
        flow.close_owned_gui(owned_gui, set(App.listDocuments()) - initial_documents)
    raise
