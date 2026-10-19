"""计算说明书的内容：按课程设计说明书的惯例组织章节，每个计算都写出公式、代入值和结果。"""

from __future__ import annotations

import math

from gongke_core.design import ReducerDesign, ShaftResult
from gongke_core.calc.gear import GearPair
from gongke_core.report import Doc
from gongke_core.report import diagrams


_NUMERALS = "一二三四五六七八九十"


def _h1(doc: Doc, title: str):
    """章标题，自动编号（一、二、……十一、十二……）。"""
    n = getattr(doc, "_chapter", 0) + 1
    doc._chapter = n
    if n <= 10:
        num = _NUMERALS[n - 1]
    else:
        num = ("" if n < 20 else _NUMERALS[n // 10 - 1]) + "十" + (_NUMERALS[n % 10 - 1] if n % 10 else "")
    doc.h1(f"{num}、{title}")


def f(v: float, nd: int = 2) -> str:
    return f"{v:.{nd}f}"


def mm(v: float, nd: int = 2) -> str:
    return f"{v * 1e3:.{nd}f}"


def mpa(v: float, nd: int = 1) -> str:
    return f"{v / 1e6:.{nd}f}"


def build(d: ReducerDesign, with_diagrams: bool = True) -> Doc:
    doc = Doc(d.task.title + " 设计计算说明书")
    _task(doc, d)
    _motor(doc, d)
    _ratios(doc, d)
    if d.belt:
        _belt(doc, d)
    for p in (d.high, d.low):
        _gear(doc, p)
    for s in d.shafts:
        _shaft(doc, s, with_diagrams)
    _bearings(doc, d)
    _keys(doc, d)
    _couplings(doc, d)
    _housing(doc, d)
    _lubrication(doc, d)
    _summary(doc, d)
    _refs(doc)
    return doc


def _task(doc: Doc, d: ReducerDesign):
    t = d.task.conveyor
    _h1(doc, "设计任务")
    first = "普通 V 带传动" if d.belt else "弹性联轴器"
    doc.p(f"设计带式输送机的传动装置。传动方案为：电动机 → {first} → 展开式二级斜齿圆柱齿轮减速器 → "
          "弹性联轴器 → 卷筒。原始数据如下：")
    doc.table(["参数", "数值"], [
        ["输送带工作拉力 F", f"{t.belt_pull:.0f} N"],
        ["输送带速度 v", f"{t.belt_speed:.2f} m/s"],
        ["卷筒直径 D", f"{mm(t.drum_diameter, 0)} mm"],
        ["设计寿命", f"{t.life_hours:.0f} h"],
        ["轴承预期寿命", f"{d.task.bearing_life_hours:.0f} h"],
    ])
    if d.belt:
        doc.p("V 带传动布置在高速级：带传动平稳、能缓冲吸振，过载时打滑起保护作用，放在转速高、转矩小的一级"
              "可以减小带传动的尺寸。")
    inp = "带轮" if d.belt else "输入联轴器"
    doc.p(f"展开式布置中，高速级齿轮布置在远离{inp}的一侧，低速级齿轮布置在远离输出联轴器的一侧，"
          "使轴的扭转变形部分抵消弯曲变形引起的载荷沿齿宽分布不均。")


def _motor(doc: Doc, d: ReducerDesign):
    k = d.kin
    t = d.task.conveyor
    e = t.efficiencies
    _h1(doc, "电动机的选择")
    doc.eq(f"工作机所需功率 Pw = F·v = {t.belt_pull:.0f} × {t.belt_speed:.2f} = {k.work_power/1e3:.3f} kW")
    if d.belt:
        doc.eq(f"传动装置总效率 η = η带 · η联 · η轴承³ · η齿轮² · η卷筒 = {e.belt} × {e.coupling} × {e.bearing_pair}³ × "
               f"{e.gear_pair}² × {e.drum} = {k.eta_total:.4f}")
    else:
        doc.eq(f"传动装置总效率 η = η联² · η轴承³ · η齿轮² · η卷筒 = {e.coupling}² × {e.bearing_pair}³ × "
               f"{e.gear_pair}² × {e.drum} = {k.eta_total:.4f}")
    doc.eq(f"电动机所需功率 Pd = Pw / η = {k.work_power/1e3:.3f} / {k.eta_total:.4f} = {k.required_power/1e3:.3f} kW")
    m = k.motor
    doc.p(f"按同步转速 {m.sync_speed_rpm:.0f} r/min，选额定功率不小于 Pd 的 Y 系列三相异步电动机 {m.model}："
          f"额定功率 {m.power/1e3:.1f} kW，满载转速 {m.speed_rpm:.0f} r/min，轴伸直径 {mm(m.shaft_d, 0)} mm（JB/T 10391-2008）。")


def _ratios(doc: Doc, d: ReducerDesign):
    k = d.kin
    t = d.task.conveyor
    _h1(doc, "传动比分配与各轴运动、动力参数")
    doc.eq(f"卷筒转速 nw = 60v / (πD) = 60 × {t.belt_speed:.2f} / (π × {t.drum_diameter:.3f}) = {k.drum_speed_rpm:.2f} r/min")
    doc.eq(f"总传动比 i = nm / nw = {k.motor.speed_rpm:.0f} / {k.drum_speed_rpm:.2f} = {k.total_ratio:.3f}")
    if d.belt:
        b = d.belt
        doc.p(f"V 带传动比初取 i带 = {t.belt_ratio:g}（推荐 2～4，宜小于齿轮传动比）。带轮直径圆整后实际传动比 "
              f"i带 = dd2/dd1 = {mm(b.dd2,0)}/{mm(b.dd1,0)} = {b.ratio:.3f}（不计弹性滑动），据此分配减速器传动比：")
        doc.eq(f"减速器传动比 i减 = i / i带 = {k.total_ratio:.3f} / {b.ratio:.3f} = {k.reducer_ratio:.3f}")
        doc.eq(f"高速级 i1 = √({t.ratio_split} i减) = {k.i_high:.3f}，低速级 i2 = i减 / i1 = {k.i_low:.3f}")
        tot = f"i带 i1' i2' = {d.actual_ratio:.3f}"
    else:
        doc.eq(f"高速级 i1 = √({t.ratio_split} i) = {k.i_high:.3f}，低速级 i2 = i / i1 = {k.i_low:.3f}")
        tot = f"{d.actual_ratio:.3f}"
    doc.p(f"齿数圆整后实际传动比 i1' = {d.high.z2}/{d.high.z1} = {d.high.u:.3f}，"
          f"i2' = {d.low.z2}/{d.low.z1} = {d.low.u:.3f}，总传动比 {tot}，"
          f"输送带速度误差 {d.output_speed_error*100:+.2f}%（允许 ±5%）。")
    doc.p("各轴功率按电动机所需功率 Pd 逐级乘以效率计算，转矩 T = 9550 P / n。")
    doc.table(["轴", "功率 P / kW", "转速 n / (r/min)", "转矩 T / (N·m)"],
              [[s.name, f(s.power / 1e3, 3), f(s.speed_rpm, 2), f(s.torque, 2)] for s in k.shafts])


def _gear(doc: Doc, p: GearPair):
    from gongke_core import standards
    i = p.inp
    c = p.check
    m1, m2 = standards.gear_material(i.material1), standards.gear_material(i.material2)
    _h1(doc, f"{i.name}斜齿圆柱齿轮传动设计")
    doc.h2("1. 选择材料、精度和齿数")
    doc.p(f"小齿轮 {m1.name}，{m1.hardness_hb:.0f} HBW；大齿轮 {m2.name}，{m2.hardness_hb:.0f} HBW；软齿面闭式传动。"
          f"精度等级 {i.grade} 级（GB/T 10095）。初选 z1 = {i.z1}，螺旋角 β = {i.beta_deg}°，齿宽系数 φd = {i.phi_d}。")
    doc.h2("2. 许用应力")
    doc.eq(f"应力循环次数 N1 = 60 n1 j Lh = 60 × {i.speed1_rpm:.1f} × 1 × {i.life_hours:.0f} = {p.cycles[0]:.3e}，"
           f"N2 = N1 / u = {p.cycles[1]:.3e}")
    doc.eq(f"接触疲劳寿命系数 KHN1 = {p.k_hn[0]:.3f}，KHN2 = {p.k_hn[1]:.3f}；弯曲疲劳寿命系数 KFN1 = {p.k_fn[0]:.3f}，KFN2 = {p.k_fn[1]:.3f}")
    doc.eq(f"[σH] = min(KHN σHlim / SH) = min({p.k_hn[0]:.3f} × {mpa(m1.sigma_hlim,0)}, {p.k_hn[1]:.3f} × {mpa(m2.sigma_hlim,0)}) / {i.s_h} = {mpa(p.sigma_h_allow)} MPa")
    doc.eq(f"[σF]1 = KFN1 σFE1 / SF = {p.k_fn[0]:.3f} × {mpa(m1.sigma_fe,0)} / {i.s_f} = {mpa(p.sigma_f_allow[0])} MPa；"
           f"[σF]2 = {p.k_fn[1]:.3f} × {mpa(m2.sigma_fe,0)} / {i.s_f} = {mpa(p.sigma_f_allow[1])} MPa")
    doc.h2("3. 按齿面接触疲劳强度设计")
    doc.eq(f"d1t ≥ ∛[ 2 KHt T1 / φd · (u+1)/u · (ZH ZE Zε Zβ / [σH])² ]，取 KHt = 1.3，T1 = {i.torque1*1e3:.0f} N·mm")
    doc.eq(f"试算 d1t = {mm(p.d1_trial)} mm；按实际载荷系数修正后 d1 = d1t ∛(KH / KHt) = {mm(p.d1_design)} mm")
    doc.h2("4. 按齿根弯曲疲劳强度设计")
    doc.eq("mnt ≥ ∛[ 2 KFt T1 Yε Yβ cos²β / (φd z1²) · (YFa YSa / [σF]) ]，取 KFt = 1.3，YFa YSa/[σF] 取两轮中较大者")
    doc.eq(f"试算 mnt = {mm(p.mn_trial, 3)} mm；修正后 mn = {mm(p.mn_design, 3)} mm")
    doc.h2("5. 几何尺寸")
    doc.p(f"取标准模数 mn = {mm(p.mn, 2)} mm（GB/T 1357）。按接触强度所需分度圆直径确定齿数 z1 = {p.z1}，"
          f"z2 = {p.z2}（z1、z2 互质）。中心距 a = (z1 + z2) mn / (2 cos β) 圆整为 {mm(p.a, 0)} mm，反算螺旋角")
    doc.eq(f"β = arccos[(z1 + z2) mn / (2a)] = arccos[({p.z1} + {p.z2}) × {mm(p.mn,2)} / (2 × {mm(p.a,0)})] = {math.degrees(p.beta):.4f}°"
           f"（{_dms(p.beta)}）")
    doc.table(["名称", "小齿轮", "大齿轮"], [
        ["齿数 z", str(p.z1), str(p.z2)],
        ["法向模数 mn / mm", mm(p.mn), mm(p.mn)],
        ["螺旋角 β", _dms(p.beta) + "（右旋）", _dms(p.beta) + "（左旋）"],
        ["分度圆直径 d / mm", mm(p.d1, 3), mm(p.d2, 3)],
        ["齿顶圆直径 da / mm", mm(p.da1, 3), mm(p.da2, 3)],
        ["齿根圆直径 df / mm", mm(p.df1, 3), mm(p.df2, 3)],
        ["齿宽 b / mm", mm(p.b1, 0), mm(p.b2, 0)],
        ["中心距 a / mm", mm(p.a, 0), ""],
    ])
    doc.h2("6. 强度校核")
    doc.eq(f"圆周速度 v = π d1 n1 / 60000 = {p.pitch_velocity:.3f} m/s")
    doc.eq(f"载荷系数 KH = KA Kv KHα KHβ = {i.k_a} × {c.k_v:.3f} × {c.k_alpha:.2f} × {c.k_hbeta:.3f} = {c.k_h:.3f}；"
           f"KF = KA Kv KFα KFβ = {c.k_f:.3f}")
    doc.eq(f"ZH = {c.z_h:.3f}，ZE = 189.8 √MPa，εα = {c.eps_alpha:.3f}，εβ = {c.eps_beta:.3f}，Zε = {c.z_eps:.3f}，Zβ = {c.z_beta:.3f}")
    doc.eq(f"σH = ZH ZE Zε Zβ √[2 KH T1 / (b d1²) · (u+1)/u] = {mpa(c.sigma_h)} MPa ≤ [σH] = {mpa(c.sigma_h_allow)} MPa，"
           + ("满足" if c.sigma_h <= c.sigma_h_allow else "不满足"))
    doc.eq(f"Yε = {c.y_eps:.3f}，Yβ = {c.y_beta:.3f}；YFa = {c.y_fa[0]:.3f} / {c.y_fa[1]:.3f}，YSa = {c.y_sa[0]:.3f} / {c.y_sa[1]:.3f}（按当量齿数插值）")
    for k, nm in enumerate(("小", "大")):
        doc.eq(f"σF{k+1} = 2 KF T1 YFa YSa Yε Yβ / (b mn d1) = {mpa(c.sigma_f[k])} MPa ≤ [σF]{k+1} = {mpa(c.sigma_f_allow[k])} MPa，"
               + ("满足" if c.sigma_f[k] <= c.sigma_f_allow[k] else "不满足"))
    doc.eq(f"啮合力：Ft = 2T1/d1 = {p.tangential_force:.1f} N，Fr = Ft tan αn / cos β = {p.radial_force:.1f} N，"
           f"Fa = Ft tan β = {p.axial_force:.1f} N")


def _belt(doc: Doc, d: ReducerDesign):
    b = d.belt
    sec = b.sec
    k = d.kin
    n1 = b.inp.n1
    _h1(doc, "普通 V 带传动设计")
    doc.p(f"小带轮装在电动机轴上，n1 = {n1:.0f} r/min；大带轮装在Ⅰ轴轴伸上。传递功率取电动机所需功率 "
          f"P = {b.inp.power/1e3:.3f} kW，要求传动比 i = {b.inp.ratio:g}。")
    doc.h2("1. 计算功率和带型")
    doc.eq(f"工况系数 KA = {b.inp.service_factor:g}（载荷变动小，每天工作 {d.task.hours_per_day:g} h），"
           f"Pca = KA P = {b.inp.service_factor:g} × {b.inp.power/1e3:.3f} = {b.p_ca/1e3:.3f} kW")
    doc.p(f"按 Pca 和 n1 选 {sec.name} 型普通 V 带（GB/T 11544）：节宽 bp = {mm(sec.bp,0)} mm，顶宽 b = {mm(sec.b,0)} mm，"
          f"高 h = {mm(sec.h,0)} mm，单位长度质量 q = {sec.q:g} kg/m。")
    doc.h2("2. 带轮基准直径和带速")
    doc.eq(f"小带轮基准直径 dd1 = {mm(b.dd1,0)} mm ≥ ddmin = {mm(sec.dd_min,0)} mm；"
           f"带速 v = π dd1 n1 / 60000 = π × {mm(b.dd1,0)} × {n1:.0f} / 60000 = {b.v:.2f} m/s，在 5～25 m/s 范围内")
    doc.eq(f"大带轮基准直径 dd2 = i dd1 = {b.inp.ratio:g} × {mm(b.dd1,0)} = {mm(b.inp.ratio*b.dd1,1)} mm，"
           f"按基准直径系列取 dd2 = {mm(b.dd2,0)} mm")
    if b.inp.motor_shaft_d:
        doc.p(f"小带轮轮缘内径 dd1 − 2(hf + δ) = {mm(b.dd1 - 2*(sec.hf+sec.delta),1)} mm，不小于电动机轴（d = "
              f"{mm(b.inp.motor_shaft_d,0)} mm）上轮毂的外径 1.8d = {mm(1.8*b.inp.motor_shaft_d,1)} mm。")
    doc.h2("3. 中心距和基准长度")
    doc.eq(f"0.7(dd1 + dd2) ≤ a0 ≤ 2(dd1 + dd2)，初定 a0 = {mm(b.a0,0)} mm")
    doc.eq(f"Ld0 = 2a0 + π(dd1 + dd2)/2 + (dd2 − dd1)²/(4a0) = {mm(b.ld0,1)} mm，取基准长度 Ld = {mm(b.ld,0)} mm")
    doc.eq(f"实际中心距 a ≈ a0 + (Ld − Ld0)/2 = {mm(b.a,1)} mm；安装调整范围 amin = a − 0.015Ld = {mm(b.a_range[0],1)} mm，"
           f"amax = a + 0.03Ld = {mm(b.a_range[1],1)} mm")
    doc.eq(f"小带轮包角 α1 = 180° − (dd2 − dd1) × 57.3°/a = {b.alpha1:.1f}° ≥ 120°")
    doc.h2("4. 带的根数")
    doc.eq(f"单根 V 带基本额定功率 P0 = {b.p0:.3f} kW（dd1 = {mm(b.dd1,0)} mm，n1 = {n1:.0f} r/min，查表插值）")
    doc.eq(f"额定功率增量 ΔP0 = Kb n1 (1 − 1/Ki) = {b.dp0:.3f} kW；包角系数 Kα = 1.25(1 − 5^(−α1/180°)) = {b.k_alpha:.3f}；"
           f"带长修正系数 KL = {b.k_l:.2f}")
    doc.eq(f"z = Pca / [(P0 + ΔP0) Kα KL] = {b.p_ca/1e3:.3f} / [({b.p0:.3f} + {b.dp0:.3f}) × {b.k_alpha:.3f} × {b.k_l:.2f}] "
           f"= {b.z_exact:.2f}，取 z = {b.z} 根")
    doc.h2("5. 初拉力和压轴力")
    doc.eq(f"(F0)min = 500 (2.5 − Kα) Pca / (Kα z v) + q v² = {b.f0:.1f} N（新带安装时取 1.5 倍）")
    doc.eq(f"(Fp)min = 2 z (F0)min sin(α1/2) = {b.fp:.1f} N，作为Ⅰ轴轴伸上的径向载荷")
    doc.h2("6. 带轮结构")
    doc.p(f"带轮材料 HT200。轮槽按 GB/T 10412：ha = {mm(sec.ha,2)} mm，hf = {mm(sec.hf,1)} mm，e = {mm(sec.e,1)} mm，"
          f"f = {mm(sec.f,1)} mm，δ = {mm(sec.delta,1)} mm；小带轮轮槽角 {sec.groove_angle(b.dd1):.0f}°，"
          f"大带轮 {sec.groove_angle(b.dd2):.0f}°。轮缘宽 B = (z − 1)e + 2f = {mm(b.width,0)} mm。"
          f"大带轮轮毂长度 L = {mm(d.shafts[0].layout.coupling_hub,0)} mm（(1.5～2)d，且不小于 B）。")
    doc.note("P0、KL 数据和带型选择为程序按表试算的结果，提交前请对照教材表 8-4、8-2 和图 8-11 核对。")


def _dms(rad: float) -> str:
    deg = math.degrees(rad)
    d = int(deg)
    m = int((deg - d) * 60)
    s = round(((deg - d) * 60 - m) * 60)
    if s == 60:
        m, s = m + 1, 0
    return f"{d}°{m:02d}′{s:02d}″"


def _shaft(doc: Doc, s: ShaftResult, with_diagrams: bool):
    lay = s.layout
    _h1(doc, f"{lay.name}的设计")
    doc.h2("1. 估算最小直径")
    doc.eq(f"材料 45 钢调质，A0 = 112：d ≥ A0 ∛(P/n) = 112 × ∛({s.power/1e3:.3f} / {s.speed_rpm:.2f}) = {mm(lay.d_min)} mm")
    if lay.extension:
        what = "带轮" if lay.index == 1 and s.load_case.loads[-1].label == "带轮压轴力" else "联轴器"
        doc.p(f"轴端有键槽，直径加大 5%，并考虑与{what}孔径相配，取轴端直径 {mm(lay.diameters['端部'],0)} mm。")
    doc.h2("2. 结构设计")
    gear_note = []
    for g in lay.gears:
        nm = f"{'高速级' if g.pair == 'high' else '低速级'}{'小' if g.member == 1 else '大'}齿轮"
        if g.integral:
            gear_note.append(f"{nm}齿根圆到键槽底部的距离小于 2.5mn，做成齿轮轴")
        else:
            gear_note.append(f"{nm}从{'左' if g.mount == 'left' else '右'}端装入，一侧靠轴环、另一侧用套筒定位")
    doc.p("；".join(gear_note) + f"。两端各用一个深沟球轴承 {lay.bearing.designation}，两端固定支承。各轴段尺寸如下（z 自左侧箱体内壁量起）：")
    doc.table(["轴段", "起点 z / mm", "长度 / mm", "直径 / mm", "键槽 b×t1×L / mm"],
              [[seg.role, mm(seg.z0, 1), mm(seg.length, 1), mm(seg.root_d or seg.d, 1),
                "" if not seg.keyway else f"{mm(seg.keyway[0],0)}×{mm(seg.keyway[1],1)}×{mm(seg.keyway[2],0)}"]
               for seg in lay.segments])
    doc.h2("3. 受力分析")
    doc.p(f"轴承中心位置 zA = {mm(lay.bearing_z[0],1)} mm，zB = {mm(lay.bearing_z[1],1)} mm，支承跨距 "
          f"{mm(lay.bearing_z[1]-lay.bearing_z[0],1)} mm。x 为中心连线方向（水平面），y 为铅垂方向。")
    doc.table(["载荷", "z / mm", "Fx / N", "Fy / N", "Fz / N", "力偶 Fa·d/2 / (N·m)"],
              [[p.label, mm(p.z, 1), f(p.fx, 1), f(p.fy, 1), f(p.fz, 1), f(round(p.couple_xz, 2) + 0.0, 2)] for p in s.load_case.loads])
    r = s.strength.reactions
    doc.eq(f"水平面支反力 RAx = {r.ax:.1f} N，RBx = {r.bx:.1f} N；铅垂面支反力 RAy = {r.ay:.1f} N，RBy = {r.by:.1f} N")
    doc.eq(f"合成径向载荷 FrA = {r.radial_a:.1f} N，FrB = {r.radial_b:.1f} N；轴向合力 Fa = {r.axial:.1f} N")
    if with_diagrams:
        doc.img(diagrams.moment_diagram(s), f"{lay.name}弯矩图和转矩图")
    doc.h2("4. 按弯扭合成应力校核")
    cr = s.strength.critical
    doc.eq(f"危险截面位于 z = {mm(cr.z,1)} mm（{cr.role}段，d = {mm(cr.d,1)} mm）：M = √(Mx² + My²) = {cr.m:.2f} N·m，T = {abs(cr.torque):.2f} N·m")
    doc.eq(f"σca = √(M² + (αT)²) / W，α = {s.strength.alpha}：σca = {mpa(cr.sigma_ca)} MPa ≤ [σ−1b] = {mpa(s.strength.sigma_allow,0)} MPa，"
           + ("满足" if s.strength.ok else "不满足"))
    _fatigue(doc, s)


def _fatigue(doc: Doc, s: ShaftResult):
    fc = s.fatigue
    if fc.critical is None:
        return
    m = fc.material
    doc.h2("5. 按疲劳强度精确校核（安全系数法）")
    doc.p(f"材料 {m.name}：σB = {mpa(m.sigma_b,0)} MPa，σ−1 = {mpa(m.sigma_m1,0)} MPa，τ−1 = {mpa(m.tau_m1,0)} MPa，"
          f"ψσ = {m.psi_sigma:g}，ψτ = {m.psi_tau:g}。弯曲应力按对称循环，扭转切应力按脉动循环（τa = τm = T/2WT）。"
          "对每个轴肩和键槽截面计算：")
    doc.eq("Kσ = kσ/εσ + 1/βσ − 1，Sσ = σ−1/(Kσσa)，Sτ = τ−1/(Kττa + ψττm)，Sca = SσSτ/√(Sσ² + Sτ²) ≥ [S]")
    rows = []
    for c in sorted(fc.sections, key=lambda c: c.z):
        inf = lambda v: "—" if v == float("inf") or v > 1e6 else f"{v:.2f}"
        rows.append([c.label, mm(c.d, 0), f"{c.m:.1f}", f"{abs(c.t):.1f}", f"{c.k_sigma:.2f}/{c.k_tau:.2f}",
                     f"{c.eps:.2f}", f"{c.beta:.2f}", mpa(c.sigma_a, 1), mpa(c.tau_a, 1), inf(c.S_sigma), inf(c.S_tau), inf(c.S_ca)])
    doc.table(["截面", "d/mm", "M/(N·m)", "T/(N·m)", "kσ/kτ", "ε", "β", "σa/MPa", "τa/MPa", "Sσ", "Sτ", "Sca"], rows)
    c = fc.critical
    doc.eq(f"最危险截面为{c.label}（d = {mm(c.d,0)} mm）：Sca = {c.S_ca:.2f} {'≥' if fc.ok else '<'} [S] = {fc.S_required:g}，"
           + ("满足" if fc.ok else "不满足"))
    doc.p("说明：kσ、kτ 由轴肩圆角的理论应力集中系数（Peterson 拟合公式）和敏感系数（Kuhn–Hardrath 公式）求得，"
          "εσ、βσ 用解析公式代替查图，均为近似值；齿轮过盈配合处的 kσ/εσ 需查教材附表，"
          "可填入任务书 shaft: k_sigma_fit 后重新计算。")


def _bearings(doc: Doc, d: ReducerDesign):
    _h1(doc, "滚动轴承寿命计算")
    doc.p(f"深沟球轴承，两端固定。当量动载荷 P = fp (X Fr + Y Fa)，fp = {d.task.load_factor_bearing}；"
          f"寿命 L10h = 10⁶/(60n) (C/P)³。预期寿命 {d.task.bearing_life_hours:.0f} h。")
    rows = []
    for s in d.shafts:
        b = s.bearings
        for k, side in enumerate("AB"):
            rows.append([f"{s.layout.name} {side}", b.bearing.designation, f"{b.bearing.Cr/1e3:.1f}",
                         f(b.fr[k], 0), f(b.fa[k], 0), f"{b.x[k]:.2f} / {b.y[k]:.2f}", f(b.p[k], 0),
                         f"{b.life[k]:.0f}", "满足" if b.life[k] >= b.required else "不满足"])
    doc.table(["位置", "代号", "Cr / kN", "Fr / N", "Fa / N", "X / Y", "P / N", "L10h / h", "结论"], rows)


def _keys(doc: Doc, d: ReducerDesign):
    _h1(doc, "键连接的选择与校核")
    doc.p("均采用 A 型普通平键（GB/T 1096），挤压强度 σp = 2T/(k l d)，k = 0.5h，l = L − b。")
    rows = []
    for s in d.shafts:
        for k in s.keys:
            rows.append([k.location, mm(k.d, 0), f"{mm(k.size.b,0)}×{mm(k.size.h,0)}×{mm(k.length,0)}",
                         "双键" if k.count == 2 else "单键", mpa(k.sigma_p), mpa(k.sigma_allow, 0),
                         "满足" if k.ok else "不满足"])
    doc.table(["位置", "轴径 / mm", "b×h×L / mm", "数量", "σp / MPa", "[σp] / MPa", "结论"], rows)


def _couplings(doc: Doc, d: ReducerDesign):
    _h1(doc, "联轴器的选择")
    doc.p(f"选用 LX 型弹性柱销联轴器（GB/T 5014）。计算转矩 Tca = KA T，KA = {d.task.coupling_service_factor}。")
    doc.table(["位置", "Tca / (N·m)", "两侧轴孔直径 / mm", "轴孔长度（估） / mm"],
              [[c.location, f(c.torque, 1), f"{mm(c.bores[0],0)} / {mm(c.bores[1],0)}", mm(c.hub_length, 0)]
               for c in d.couplings])
    doc.note("型号需按 GB/T 5014 核对：公称转矩 Tn ≥ Tca，许用转速 ≥ 工作转速，孔径范围包含两侧轴径。")


def _housing(doc: Doc, d: ReducerDesign):
    h = d.housing
    _h1(doc, "箱体主要结构尺寸")
    doc.table(["名称", "公式", "取值 / mm"], [
        ["箱座壁厚 δ", "0.025a + 3 ≥ 8", mm(h.delta, 1)],
        ["箱盖壁厚 δ1", "0.02a + 3 ≥ 8", mm(h.delta1, 1)],
        ["箱座凸缘厚度 b", "1.5δ", mm(h.flange_base, 1)],
        ["箱盖凸缘厚度 b1", "1.5δ1", mm(h.flange_cover, 1)],
        ["箱座底凸缘厚度 b2", "2.5δ", mm(h.flange_foot, 1)],
        ["地脚螺栓直径 df", "0.036a + 12", f"M{mm(h.bolt_foot,0)}"],
        ["轴承旁连接螺栓 d1", "0.75df", f"M{mm(h.bolt_bearing,0)}"],
        ["箱盖与箱座连接螺栓 d2", "(0.5–0.6)df", f"M{mm(h.bolt_flange,0)}"],
        ["轴承座孔长度 L1", "δ + c1 + c2 + (5–8)", mm(h.bearing_seat_length, 1)],
        ["齿轮端面与内壁距离 Δ2", "≥ δ", mm(h.gap_axial, 0)],
        ["大齿轮齿顶圆与内壁距离 Δ1", "≥ 1.2δ", mm(h.gap_radial, 0)],
        ["轴承端面与内壁距离 Δ3", "油润滑 3–5，脂润滑 8–12", mm(h.gap_bearing, 0)],
        ["箱体内壁宽度", "2Δ2 + b低速小 + c + b高速小", mm(h.inner_width, 1)],
    ])
    doc.p(f"表中 a 取低速级中心距 {mm(d.low.a,0)} mm。")


def _lubrication(doc: Doc, d: ReducerDesign):
    v = max(d.high.pitch_velocity, d.low.pitch_velocity)
    _h1(doc, "润滑与密封")
    doc.p(f"齿轮最大圆周速度 {v:.2f} m/s < 12 m/s，齿轮采用浸油润滑，高速级大齿轮浸入油中约一个齿高。"
          + ("轴承利用齿轮飞溅的油润滑（v ≥ 2 m/s）。" if v >= 2 else "圆周速度小于 2 m/s，轴承采用润滑脂润滑，内侧加挡油环。")
          + "伸出轴处采用毡圈油封或唇形密封圈。")


def _summary(doc: Doc, d: ReducerDesign):
    _h1(doc, "校核结果汇总")
    doc.table(["项目", "结论", "说明"], [[n, "满足" if ok else "不满足", txt] for n, ok, txt in d.checks])
    if d.warnings:
        doc.h2("说明")
        for w in d.warnings:
            doc.note(w)


def _refs(doc: Doc):
    doc.h1("参考资料")
    for r in [
        "濮良贵、纪名刚 主编．机械设计（第八版）．高等教育出版社．",
        "机械设计课程设计指导书（各校通用版本）．",
        "GB/T 3480.1-2019 直齿轮和斜齿轮承载能力计算；ISO 6336-1/2/3．",
        "W. D. Pilkey. Peterson's Stress Concentration Factors（阶梯轴圆角应力集中系数拟合公式）；R. G. Budynas, J. K. Nisbett. Shigley's Mechanical Engineering Design（敏感系数、尺寸系数、表面系数）．",
        "GB/T 13575.1-2008 普通和窄 V 带传动；GB/T 11544-2012 普通 V 带；GB/T 10412-2002 V 带轮．",
        "GB/T 276-2013、GB/T 6391-2010 滚动轴承；GB/T 1095/1096-2003 平键；JB/T 10391-2008 Y 系列电动机．",
    ]:
        doc.p(r)
