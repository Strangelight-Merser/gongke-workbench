"""P7/P8 的公开工具调用配方；输入来自原试验 dimensions.json，不导入 STEP 建模。"""
import math


def point(x, y):
    return [x/1000, y/1000]


def line(a, b):
    return {"kind": "line", "start": point(*a), "end": point(*b)}


def arc(a, mid, b):
    return {"kind": "arc", "start": point(*a), "mid": point(*mid), "end": point(*b)}


def circle(x, y, radius):
    return {"kind": "circle", "center": point(x, y), "radius": radius/1000}


def dimension(kind, geometry, value, name):
    return {"kind": kind, "entities": [{"geometry": geometry}], "value": value/1000, "name": name}


def capsule(a, b, r):
    return [line((a, -r), (b, -r)), arc((b, -r), (b+r, 0), (b, r)),
            line((b, r), (a, r)), arc((a, r), (a-r, 0), (a, -r))]


async def build(case, values, sketch_feature):
    """sketch_feature(..., kind, length_mm=None, **feature_options)；贯通切除不传切深。"""
    p = values
    if case == "p7":
        t, c = p["base_thickness"], p["slot_center_distance"]
        x = c+p["slot_to_tube_center"]
        await sketch_feature("Base", "XY", 0, capsule(0, x, p["base_end_radius"]),
                             [dimension("radius", 1, p["base_end_radius"], "EndRadius")], "pad", t)
        await sketch_feature("Boss", "XY", t, capsule(0, c, p["boss_radius"]),
                             [dimension("radius", 1, p["boss_radius"], "BossRadius")], "pad", p["boss_total_height"]-t)
        tube = await sketch_feature("Tube", "XY", t, [circle(x, 0, p["tube_outer_diameter"]/2)],
                                    [dimension("diameter", 0, p["tube_outer_diameter"], "OuterDiameter")], "pad", p["tube_total_height"]-t)
        # 通孔从底面向上贯穿：Tube 加高后仍贯通，不在旧筒顶留下盲孔底面。
        await sketch_feature("Bore", "XY", 0, [circle(x, 0, p["tube_inner_diameter"]/2)],
                             [dimension("diameter", 0, p["tube_inner_diameter"], "BoreDiameter")], "pocket", through_all=True, reversed=True)
        await sketch_feature("Slot", "XY", p["boss_total_height"], capsule(0, c, p["slot_radius"]),
                             [dimension("radius", 1, p["slot_radius"], "SlotRadius")], "pocket", p["boss_total_height"])
        return {"tube_feature": tube["feature_ref"]}
    t, w, r = p["base_thickness"], p["base_width"]/2, p["nose_radius"]
    a = p["nose_to_base_holes"]
    back, front = a+p["base_holes_to_back"], a+p["base_holes_to_wall_front"]
    denom = a*a+w*w
    k = r*math.sqrt(denom-r*r)/denom
    tx, ty = r*r*a/denom-k*w, r*r*w/denom+k*a
    outline = [line((back, -w), (a, -w)), line((a, -w), (tx, -ty)), arc((tx, -ty), (-r, 0), (tx, ty)),
               line((tx, ty), (a, w)), line((a, w), (back, w)), line((back, w), (back, -w))]
    await sketch_feature("Base", "XY", 0, outline, [dimension("radius", 2, r, "NoseRadius")], "pad", t)
    await sketch_feature("BaseHoles", "XY", t,
                         [circle(x, y, p["base_hole_diameter"]/2) for x, y in [(0, 0), (a, -p["base_hole_spacing"]/2), (a, p["base_hole_spacing"]/2)]],
                         [dimension("diameter", i, p["base_hole_diameter"], "HoleDiameter"+str(i)) for i in range(3)], "pocket", t)
    c, h, er, nr = p["wall_hole_spacing"]/2, p["wall_hole_height"], p["ear_radius"], p["notch_radius"]
    notch_z = h+math.sqrt((er+nr)**2-c*c)
    tangent_y, tangent_z = c*nr/(er+nr), h+(notch_z-h)*er/(er+nr)
    left, right = (-tangent_y, tangent_z), (tangent_y, tangent_z)
    wall = [line((-w, t), (-w, h)), arc((-w, h), (-c, h+er), left), arc(left, (0, notch_z-nr), right),
            arc(right, (c, h+er), (w, h)), line((w, h), (w, t)), line((w, t), (-w, t))]
    await sketch_feature("Wall", "YZ", front, wall, [dimension("radius", 1, er, "EarRadius"), dimension("radius", 2, nr, "NotchRadius")], "pad", back-front)
    await sketch_feature("WallHoles", "YZ", back, [circle(y, h, p["wall_hole_diameter"]/2) for y in [-c, c]],
                         [dimension("diameter", i, p["wall_hole_diameter"], "HoleDiameter"+str(i)) for i in range(2)], "pocket", back-front)
    # XZ 法向为 -Y，从 +rib_width/2 向 -Y 拉伸。
    pts = [(front-p["rib_length"], t), (front, t), (front, t+p["rib_height"])]
    await sketch_feature("Rib", "XZ", -p["rib_width"]/2, [line(pts[i], pts[(i+1)%3]) for i in range(3)],
                         [dimension("distance", 0, p["rib_length"], "RibLength")], "pad", p["rib_width"])
    return {}
