"""原生建模公共契约；只传受限几何操作，不传脚本或任意属性。"""
from __future__ import annotations

from uuid import UUID
from gongke_app.inspection import obj, TEXT, NUMBER, DOCUMENT

POSITIVE = {"type": "number", "exclusiveMinimum": 0}
ANGLE = {"type": "number", "exclusiveMinimum": 0, "maximum": 6.283185307179586}
BOOL = {"type": "boolean"}
POINT = {"type": "array", "items": NUMBER, "minItems": 2, "maxItems": 2}
INDEX = {"type": "integer", "minimum": 0}
NAME = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_]*$", "maxLength": 80}
OPERATION = {"type": "string", "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"}
BASE = {"host_id": TEXT, "document": DOCUMENT, "operation_id": OPERATION}
BODY = {**BASE, "body_ref": TEXT}


def variant(kind, fields, optional=()):
    return obj({"kind": {"const": kind}, **fields}, ["kind", *(k for k in fields if k not in optional)])


GEOMETRY = {"oneOf": [
    variant("line", {"start": POINT, "end": POINT, "construction": BOOL}, ["construction"]),
    variant("circle", {"center": POINT, "radius": POSITIVE, "construction": BOOL}, ["construction"]),
    variant("arc", {"start": POINT, "mid": POINT, "end": POINT, "construction": BOOL}, ["construction"]),
    variant("rectangle", {"start": POINT, "end": POINT, "construction": BOOL}, ["construction"]),
]}
ENTITY = obj({"geometry": INDEX, "point": {"enum": ["whole", "start", "end", "center"]}}, ["geometry"])
CONSTRAINT = obj({"kind": {"enum": ["horizontal", "vertical", "coincident", "tangent", "parallel", "perpendicular", "equal", "distance", "distance_x", "distance_y", "diameter", "radius", "angle", "fixed"]},
                  "entities": {"type": "array", "items": ENTITY, "minItems": 1, "maxItems": 2},
                  "value": NUMBER, "name": NAME}, ["kind", "entities"])
CONSTRAINT["allOf"] = [
    {"if": {"properties": {"kind": {"enum": ["distance", "distance_x", "distance_y", "diameter", "radius", "angle"]}}},
     "then": {"required": ["value"]}, "else": {"not": {"required": ["value"]}}},
    {"if": {"properties": {"kind": {"enum": ["coincident", "tangent", "parallel", "perpendicular", "equal", "angle"]}}},
     "then": {"properties": {"entities": {"minItems": 2}}}},
]
SUPPORT = {"oneOf": [obj({"plane": {"enum": ["XY", "XZ", "YZ"]}, "offset": NUMBER}, ["plane"]),
                      obj({"face_ref": TEXT})]}
PROFILE = {"sketch_ref": TEXT, "length": POSITIVE, "reversed": BOOL}
FEATURE = {"oneOf": [
    variant("pad", PROFILE, ["reversed"]),
    variant("pocket", PROFILE, ["reversed"]),
    variant("pocket", {"sketch_ref": TEXT, "through_all": {"const": True}, "reversed": BOOL}, ["reversed"]),
    variant("revolve", {"sketch_ref": TEXT, "axis": {"enum": ["horizontal", "vertical"]}, "angle": ANGLE, "reversed": BOOL}, ["reversed"]),
    variant("hole", {**PROFILE, "diameter": POSITIVE}, ["reversed"]),
    variant("fillet", {"edges": {"type": "array", "items": TEXT, "minItems": 1}, "radius": POSITIVE}),
    variant("chamfer", {"edges": {"type": "array", "items": TEXT, "minItems": 1}, "size": POSITIVE}),
    variant("mirror", {"features": {"type": "array", "items": TEXT, "minItems": 1}, "plane": {"enum": ["XY", "XZ", "YZ"]}}),
    variant("linear_pattern", {"features": {"type": "array", "items": TEXT, "minItems": 1}, "axis": {"enum": ["X", "Y", "Z"]}, "spacing": POSITIVE, "count": {"type": "integer", "minimum": 2}}),
    variant("polar_pattern", {"features": {"type": "array", "items": TEXT, "minItems": 1}, "axis": {"enum": ["X", "Y", "Z"]}, "angle": ANGLE, "count": {"type": "integer", "minimum": 2}}),
]}

GUIDE = """先 hosts.list → host.context。按已确认尺寸拆成基体、凸台/筋、孔槽、修饰与重复特征；缺尺寸保留来源和假设。
host.model_new 新建零件并保存到工程内新文件；已有原件先 host.model_copy。只编辑这些副本。
所有长度 m、角度 rad。草图是局部二维 [u,v]；FreeCAD Body 局部基准面：XY=(X,Y,+Z)，XZ=(X,Z,-Y)，YZ=(Y,Z,+X)，offset 沿该基准面法向。SOLIDWORKS 用模板实际草图坐标，先空批创建读取 frame，再追加几何；不猜本地轴向。
面上草图必须使用当前 host.inspect 的面引用，按返回的 frame 定位；不猜面号。每次调用使用上一回执 document。
一次 host.sketch 批量几何和约束；rectangle 展开四边并加重合/水平/竖直约束。geometry 索引从 0 开始，按回执映射；point 为 start/end/center，默认 whole。
先 host.sketch 创建，再用 sketch_ref 追加几何/约束。距离/半径/直径约束填 value(m)，angle 填 rad；保留可编辑命名尺寸。
欠约束会明确返回 solver 状态，但可继续建模；冲突、冗余或无效轮廓必须修正后再生成特征。host.feature_edit 可改命名约束或返回的特征尺寸。
pad 沿草图正法向；pocket/hole 沿负法向，reversed 翻转。孔为直孔，不推断螺纹/公差；SOLIDWORKS 用圆草图+原生切除，圆直径必须等于 diameter。圆角/倒角最后做。
贯通切除用 pocket 的 through_all=true，不传 length；从切入侧沿切除方向贯穿，底面草图向上切须 reversed=true。固定高度草图加固定切深不会随上游加高自动贯通。
阵列 spacing 为相邻间距；polar_pattern angle 为总扫角，2π 为整圆均布。新建 SolidWorks Body 在首个实体特征生成时出现。
每个特征后读回 host.inspect，最终 host.check 逐项对照图纸并修改失败项，再 host.model_save。保存不等于尺寸通过。
错误原样保留；FreeCAD 事务失败回滚仍可能增加 revision，重新 context。SOLIDWORKS 部分失败标 needs_review/unknown，先读回。
结果未知只用同一个 operation_id 调 host.model_operation；not_found 也不代表没执行，禁止换 ID 重做。
"""


def definitions():
    tools = {
        "host.model_new": ("新建原生零件与 Body，保存为工程内新 .FCStd/.sldprt；不覆盖。返回 document/body_ref。" + "长度 m、角度 rad；先读 gongke://modeling。", obj({"host_id": TEXT, "host_instance": TEXT, "operation_id": OPERATION, "path": TEXT, "name": NAME}), True),
        "host.model_copy": ("把当前零件另存并打开新的工作副本，保留原文档；必须传当前 document。返回新 document。", obj({**BASE, "path": TEXT}), True),
        "host.body": ("创建原生 Body；FreeCAD 为显式容器，SOLIDWORKS 在首个 pad/revolve 生成实体。", obj({**BASE, "name": NAME}), True),
        "host.sketch": ("在 body_ref 的基准面/平面面上新建草图，或传 sketch_ref 追加。一批 geometry/constraints 一次求解；m/rad、草图局部二维坐标。返回索引映射、frame 和真实求解状态；欠约束不冒充全约束。rectangle 展开4边，索引见回执。", obj({**BODY, "name": NAME, "support": SUPPORT, "sketch_ref": TEXT, "geometry": {"type": "array", "items": GEOMETRY, "maxItems": 128}, "constraints": {"type": "array", "items": CONSTRAINT, "maxItems": 256}}, [*BODY, "geometry", "constraints"]), True),
        "host.feature": ("创建一个原生特征并重建，保留草图与特征树；全部尺寸 m/rad。pad 正法向、pocket/hole 负法向，reversed 翻转；pocket 二选一：length 定深或 through_all=true 贯通。revolve 轴为草图本地轴。mirror/阵列用实际 feature_ref；孔为直孔。", obj({**BODY, "name": NAME, "feature": FEATURE}), True),
        "host.feature_edit": ("修改一个特征的原生尺寸或命名草图约束后重建；parameter 使用回执 editable_parameters 的 name，value 为 m/rad/计数。不得改任意宿主属性。", obj({**BASE, "feature_ref": TEXT, "parameter": TEXT, "value": NUMBER}), True),
        "host.feature_delete": ("删除指定叶特征并重建；有依赖时返回依赖，不级联删除学生特征。先删下游。", obj({**BASE, "feature_ref": TEXT}), True),
        "host.rebuild": ("重建当前工作副本，返回真实特征错误、草图求解状态和新 document。", obj(BASE), True),
        "host.model_save": ("保存当前文档自身已登记工作副本，不接受覆盖路径；返回新 document。", obj(BASE), True),
        "host.model_operation": ("读取原建模 operation_id 回执；未知不重发。new/copy 结果恢复时登记已验证的新文件。", obj({"host_id": TEXT, "operation_id": OPERATION}), False),
    }
    sketch = tools["host.sketch"][1]
    sketch["oneOf"] = [{"required": ["name", "support"], "not": {"required": ["sketch_ref"]}},
                       {"required": ["sketch_ref"], "not": {"anyOf": [{"required": ["name"]}, {"required": ["support"]}]}}]
    return tools


TO_NATIVE = {key: "model." + key.split(".")[1].removeprefix("model_") for key in definitions()}
FROM_NATIVE = {value: key for key, value in TO_NATIVE.items()}
WRITE_METHODS = set(FROM_NATIVE) - {"model.operation"}
READ_METHODS = {"model.operation"}


def execute(hosts, host_id, method, params, project):
    """公共 typed 工具和 host.write 共用此边界；宿主再次校验身份与副本。"""
    from gongke_app.tools import validate
    from gongke_app.hosts import _fingerprint
    validate({"host_id": host_id, **params}, definitions()[FROM_NATIVE[method]][1])
    if method in WRITE_METHODS and project is None:
        raise ValueError("原生建模需要绑定工程")
    host = "freecad" if host_id == "freecad" else "solidworks"
    config = None
    if host != "freecad":
        config = next((c for c in hosts.discover() if c["host_id"] == host_id and c["host"] == host), None)
        if config is None:
            raise ValueError("未发现 SOLIDWORKS 宿主")
    def request(command, values):
        if host == "freecad":
            from gongke_core import native_client
            return native_client.call("inspect_host", command=command, params=values)
        return hosts._request(config, command, values)

    args = dict(params)
    args["operation_id"] = str(UUID(args["operation_id"]))
    if config and method in WRITE_METHODS:
        args["session_id"] = config["session_id"]
    operation = None
    if method in WRITE_METHODS:
        context = request("model.context", {})
        if "error" in context:
            return context
        if method not in context["capabilities"]:
            raise ValueError("宿主未声明此建模能力")
        if method == "model.new":
            if context["host_instance"] != args["host_instance"]:
                raise ValueError("宿主实例已改变")
        else:
            doc = next((d for d in context["documents"] if d["document"] == args["document"]), None)
            if doc is None:
                raise ValueError("文档身份、修订或配置已改变，请重新读取")
            if method != "model.copy" and not project.is_working_copy(doc["path"], host):
                raise ValueError("只允许修改当前工程登记的原生工作副本；请先 host.model_copy")
        if method in {"model.new", "model.copy"}:
            target = project.resolve(args["path"])
            if target.suffix.lower() != (".fcstd" if host == "freecad" else ".sldprt") or target.exists():
                raise ValueError("需要工程内新的原生零件文件路径")
            target.parent.mkdir(parents=True, exist_ok=True)
            args["path"] = str(target)
            operation = {"operation_id": args["operation_id"], "host_id": host_id, "host": host,
                         "host_session": context["host_instance"], "method": method, "params": args,
                         "fingerprint": _fingerprint(method, args), "state": "unregistered"}
            project.remember_copy_operation(operation)
    result = request(method, args)
    if method == "model.operation" and project:
        operation = project.copy_operation(args["operation_id"])
        if operation and operation["method"] in {"model.new", "model.copy"}:
            # 终态和当前宿主都必须属于原请求；旧日志不能替重启后的会话授予写资格。
            if result.get("state") != "finished":
                return result
            current = request("model.context", {})
            if (operation["host_id"] != host_id or current.get("host_instance") != operation["host_session"]
                    or result.get("host_instance") != operation["host_session"]
                    or result.get("fingerprint") != operation["fingerprint"]):
                return result
            receipt = result.get("result", {})
        else:
            operation = None
    else:
        receipt = result
    if operation and isinstance(receipt, dict) and receipt.get("outcome") == "committed":
        if (receipt.get("operation_id") != operation["operation_id"]
                or receipt.get("document", {}).get("host_instance") != operation["host_session"]
                or receipt.get("path") != operation["params"]["path"]
                or receipt.get("file_exists") is not True):
            raise ValueError("建模副本回执与原请求不一致，未授予写入资格")
        project.register_copy(receipt["path"], host, receipt, operation_id=operation["operation_id"])
    return result
