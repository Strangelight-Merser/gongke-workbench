"""三家制造商开式 6211 的安装尺寸引用，全部采用 SI 单位。

仅记录已核对的外形、轴肩与圆角尺寸，不替换通用标准数据，不提供额定载荷。
SKF 数据来自 2018 年明确版本目录；NSK、Koyo 来自无修订号的官方产品页。
没有公布的尺寸保留 None，不将其解释为无限制。
"""

from __future__ import annotations

from copy import deepcopy
import math


_REFERENCES = {
    "skf": {
        "manufacturer": "SKF", "designation": "6211", "bearing_type": "open",
        "source": "SKF Rolling bearings，PUB BU/P1 17000/1 EN，印刷页 280–281；PDF 第 282–283 页",
        "url": "https://cdn.skfmediahub.skf.com/api/public/0901d196802809de/pdf_preview_medium/0901d196802809de_pdf_preview_medium.pdf",
        "version": "October 2018",
        "dimensions": {"bore_m": 0.055, "outside_m": 0.100, "width_m": 0.021},
        "abutment": {"shaft_diameter_min_m": 0.064, "shaft_diameter_max_m": None,
                     "housing_diameter_max_m": 0.091, "fillet_radius_max_m": 0.0015},
        "notes": "开式 6211 的 da max 栏为横杠；不能借用相邻 6211-2Z/6211-Z 的上限。",
    },
    "nsk": {
        "manufacturer": "NSK", "designation": "6211", "bearing_type": "open",
        "source": "NSK 官方 6211 产品页，Boundary Dimensions / Abutment and Fillet Dimensions",
        "url": "https://www.nsk.com/eu-en/engineering/products/bearings/ball-bearings/deep-groove-ball-bearings/single-row-deep-groove-ball-bearings/6211-apn.html",
        "version": "在线产品页，未标修订号；2026-10-27 核对",
        "dimensions": {"bore_m": 0.055, "outside_m": 0.100, "width_m": 0.021},
        "abutment": {"shaft_diameter_min_m": 0.063, "shaft_diameter_max_m": 0.0665,
                     "housing_diameter_max_m": 0.092, "fillet_radius_max_m": 0.0015},
        "notes": "页面型号 6211，开式、CN、P0；不将安装数据扩展到带后缀型号。",
    },
    "koyo": {
        "manufacturer": "Koyo", "designation": "6211", "bearing_type": "open",
        "source": "JTEKT/Koyo 官方 6211 产品页，Specification data / Mounting dimensions",
        "url": "https://koyo.jtekt.co.jp/en/products/detail/?pno=6211",
        "version": "在线产品页，未标修订号；2026-10-27 核对",
        "dimensions": {"bore_m": 0.055, "outside_m": 0.100, "width_m": 0.021},
        "abutment": {"shaft_diameter_min_m": 0.063, "shaft_diameter_max_m": None,
                     "housing_diameter_max_m": 0.092, "fillet_radius_max_m": 0.0015},
        "notes": "页面型号 6211 Open type，未列 da max；不能借用 6211 2RD 的上限。",
    },
}


def lookup(manufacturer: str, designation: str = "6211") -> dict:
    """按明确制造商和完整型号取引用副本，不把 generic 6211 自动归属某家。"""
    if not isinstance(manufacturer, str) or manufacturer.casefold() not in _REFERENCES or designation != "6211":
        raise ValueError("已核对引用仅支持 SKF、NSK、Koyo 的开式 6211；必须明确制造商和完整型号")
    return deepcopy(_REFERENCES[manufacturer.casefold()])


def _finite(value, *, positive=False):
    return (isinstance(value, (float, int)) and not isinstance(value, bool)
            and math.isfinite(value) and (value > 0 if positive else value >= 0))


def check_abutment(reference: dict, diameter_m: float, fillet_radius_m: float | None = None) -> dict:
    """逐项比较轴肩直径与圆角，未给的上限或未测圆角均返回 unknown。

    pass 只表示这三个安装尺寸比较成立，不包含轴肩接触承载、疲劳或整机验收。
    housing_diameter_max_m 是壳体轴肩限制，不用于替代轴的直径上限。
    """
    if not _finite(diameter_m, positive=True):
        raise ValueError("轴肩直径必须为有限正数，单位 m")
    if fillet_radius_m is not None and not _finite(fillet_radius_m):
        raise ValueError("圆角半径必须为有限非负数，单位 m；未知时传 None")
    limits = reference["abutment"]
    checks = {}
    for name, value, field, relation in (
        ("lower_bound", diameter_m, "shaft_diameter_min_m", ">="),
        ("upper_bound", diameter_m, "shaft_diameter_max_m", "<="),
        ("fillet", fillet_radius_m, "fillet_radius_max_m", "<="),
    ):
        limit = limits[field]
        if limit is not None and not _finite(limit, positive=True):
            raise ValueError(f"引用中的 {field} 必须为有限正数或 None")
        if value is None:
            status, reason = "unknown", "当前工程未提供实际圆角半径"
        elif limit is None:
            status, reason = "unknown", "原厂引用未给出该限制值"
        else:
            passed = value >= limit if relation == ">=" else value <= limit
            status, reason = ("pass", "满足引用尺寸限制") if passed else ("fail", "超出引用尺寸限制")
        checks[name] = {"status": status, "value_m": value, "limit_m": limit,
                        "relation": relation, "reason": reason}
    statuses = [item["status"] for item in checks.values()]
    status = "fail" if "fail" in statuses else "unknown" if "unknown" in statuses else "pass"
    return {"status": status, "checks": checks,
            "reference": {key: reference[key] for key in ("manufacturer", "designation", "source", "url", "version")},
            "limitations": ["只比较轴肩安装直径和圆角，不校核接触承载、疲劳、配合公差或实际装配。",
                            "未公布的最大直径不能解释为允许任意增大轴肩。"]}
