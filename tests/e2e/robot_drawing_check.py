"""机器人图纸独立验收；数值来自本地图纸人工复核，不给 Agent 建模配方。"""
import math


async def check_robot(case, snapshot, document, body, call):
    page = {"robot14":14, "robot13":13, "robot4":4}[case]
    source = f"quadruped-robot-drawings.pdf 原第{page}页，人工复核标注及投影关系"
    conditions = []
    def condition(name, measurement, expected, unit):
        conditions.append({"id": name, "source": source, "measurement": measurement,
                           "expected": expected, "unit": unit, "tolerance": .01})
    bounds = [(b-a)*1000 for a,b in zip(snapshot["bounds"]["min"], snapshot["bounds"]["max"])]
    expected_bounds = {"robot14":[23,18,7], "robot13":[18,20,20], "robot4":[45,27,4]}[case]
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
    elif case == "robot4":
        # 来源：第4页45/36/17/5/4/3与2×45°标注，镜像关系经人工查看原投影确认。
        # 这是审计截面边界，不向 Agent 提供这些坐标或建模顺序。
        outer = [(-16,13.5),(16,13.5),(18,11.5),(18,8.5),(20.5,8.5),(22.5,6.5),
                 (22.5,-6.5),(20.5,-8.5),(18,-8.5),(18,-11.5),(16,-13.5),(-16,-13.5),
                 (-18,-11.5),(-18,-8.5),(-20.5,-8.5),(-22.5,-6.5),(-22.5,6.5),(-20.5,8.5),(-18,8.5),(-18,11.5)]
        arrow = [(13,6.5),(13,3.5),(18,3.5),(18,-3.5),(13,-3.5),(13,-6.5),(4,0)]
        triangle = [(-8.5,8.5),(8.5,8.5),(0,3)]
        loops = [outer, arrow, [(-x,y) for x,y in arrow], triangle, [(x,-y) for x,y in triangle]]
        condition("plate_section", {"kind":"section_area", "plane":{"origin":[0,0,.002],"normal":[0,0,1]}}, 828.5, "mm^2")
        section = await call("host.section", document=document, object_ref=body, plane={"origin":[0,0,.002],"normal":[0,0,1]})
        expected_edges = [(a,b) for loop in loops for a,b in zip(loop,loop[1:]+loop[:1])]
        actual_edges = [(e["start"],e["end"]) for e in section.get("edges",[]) if e["kind"]=="line"]
        def close(a,b):
            return math.dist(a, [b[0]*1000,b[1]*1000]) < .01
        topology = section.get("wire_count")==5 and len(actual_edges)==len(expected_edges) and all(
            sum((close(a,c) and close(b,d)) or (close(a,d) and close(b,c)) for c,d in actual_edges)==1
            for a,b in expected_edges)
        extra.update(volume_expected_mm3=3314, volume_error_mm3=snapshot["volume"]*1e9-3314,
                     outline_source="45×27、中心宽36、厚4、8处2×45°；两箭头与两三角透孔的投影边界", section=section)
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
