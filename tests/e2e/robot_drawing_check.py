"""机器人图纸独立验收；数值来自本地图纸人工复核，不给 Agent 建模配方。"""
import math


async def check_robot(case, snapshot, document, body, call):
    page = 14 if case == "robot14" else 13
    source = f"quadruped-robot-drawings.pdf 原第{page}页，人工复核标注及投影关系"
    conditions = []
    def condition(name, measurement, expected, unit):
        conditions.append({"id": name, "source": source, "measurement": measurement,
                           "expected": expected, "unit": unit, "tolerance": .01})
    bounds = [(b-a)*1000 for a,b in zip(snapshot["bounds"]["min"], snapshot["bounds"]["max"])]
    expected_bounds = [23,18,7] if case == "robot14" else [18,20,20]
    extra = {}
    cylinders = [f for f in snapshot["faces"] if f["kind"] == "cylinder"]
    if case == "robot14":
        for z, area in [(1.5, 23*18-4*3*3/2), (5, math.pi*3**2)]:
            condition("section_"+str(z), {"kind": "section_area", "plane": {"origin": [0,0,z/1000], "normal":[0,0,1]}}, area, "mm^2")
        for f in cylinders:
            condition("boss_diameter", {"kind":"diameter", "selectors":[{"native_ref":f["native_ref"]}]}, 6, "mm")
            for axis, expected in [(0,17),(1,9)]:
                condition("boss_axis_"+str(axis), {"kind":"coordinate", "axis":axis, "selectors":[{"native_ref":f["native_ref"]}]}, expected, "mm")
        volume = (23*18-18)*3 + math.pi*9*4
        extra = {"volume_expected_mm3":volume,"volume_error_mm3":snapshot["volume"]*1e9-volume}
        topology = len(cylinders)==1 and not cylinders[0].get("inward")
    else:
        holes = [f for f in cylinders if f.get("inward")]
        crowns = [f for f in cylinders if not f.get("inward")]
        for i,f in enumerate(holes+crowns):
            condition("diameter_"+str(i), {"kind":"diameter","selectors":[{"native_ref":f["native_ref"]}]}, 5 if f.get("inward") else 10, "mm")
            condition("axis_height_"+str(i), {"kind":"coordinate","axis":2,"selectors":[{"native_ref":f["native_ref"]}]},15,"mm")
        topology = len(holes)==2 and len(crowns)==2
        for z, area in [(.75,18*(20-14)), (2,18*20)]:
            condition("base_section_"+str(z), {"kind":"section_area", "plane":{"origin":[0,0,z/1000], "normal":[0,0,1]}}, area, "mm^2")
        extra["requires_drawing_review"] = True
        extra["scope_note"] = "检查外包络、双耳R5、两孔Ø5中心高15、底部凹口截面；凹口沿Y的1mm端距和切线连接仍需复核"
    checked = await call("host.check", document=document, object_ref=body, conditions=conditions)
    passed = (checked["status"]=="pass" and topology and max(abs(a-b) for a,b in zip(bounds,expected_bounds))<.01
              and abs(extra.get("volume_error_mm3",0))<.1)
    return {"reference_pass":passed,"reference_source":source,"independent_check":checked,
            "bbox_expected_mm":expected_bounds,"bbox_error_mm":[a-b for a,b in zip(bounds,expected_bounds)],
            "topology_check":topology, **extra}
