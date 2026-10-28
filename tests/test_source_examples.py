"""独立出版资料的数值例题；不从项目数据表反推期望值。"""
import math

import pytest

from gongke_core.calc.bearing import life_hours
from gongke_core.calc.gear import transverse_contact_ratio, transverse_pressure_angle, virtual_teeth


def test_skf_6205_basic_rating_life_example():
    # SKF Bearings and Mounted Products, 印刷页 18：6205，3600 rpm，
    # C=3330 lbf，P=100 lbf，L10h=170954 h。载荷同乘单位换算因子。
    # https://cdn.skfmediahub.skf.com/api/public/0901d196807026e8/pdf_preview_medium/0901d196807026e8_pdf_preview_medium.pdf
    lbf_to_n = 4.4482216152605
    assert life_hours(3330 * lbf_to_n, 100 * lbf_to_n, 3600) == pytest.approx(170954, abs=1)


@pytest.mark.parametrize("z1,z2,beta_deg", [(34, 179, 14.4922), (34, 137, 18.1949), (24, 96, 20)])
def test_kg_normal_helical_geometry(z1, z2, beta_deg):
    # KG STOCK GEARS Technical Data, 印刷页 108，§9.3，式 13/19/27/31。
    # 用齿顶圆/基圆路径长度式独立核对实现中的齿数-渐开线形式。
    # https://www.kggear.co.jp/en/wp-content/themes/bizvektor-global-edition/pdf/TechnicalData_KGSTOCKGEARS.pdf
    beta, an, mn = math.radians(beta_deg), math.radians(20), 2.5
    mt = mn / math.cos(beta)
    at = math.atan(math.tan(an) / math.cos(beta))
    d1, d2 = mt * z1, mt * z2
    db1, db2 = d1 * math.cos(at), d2 * math.cos(at)
    da1, da2 = d1 + 2 * mn, d2 + 2 * mn
    path = math.sqrt(da1**2-db1**2)/2 + math.sqrt(da2**2-db2**2)/2 - (d1+d2)/2*math.sin(at)
    assert transverse_contact_ratio(z1, z2, an, beta) == pytest.approx(path/(math.pi*mt*math.cos(at)))
    assert transverse_pressure_angle(an, beta) == pytest.approx(at)
    assert virtual_teeth(z1, beta) == pytest.approx(z1/math.cos(beta)**3)
