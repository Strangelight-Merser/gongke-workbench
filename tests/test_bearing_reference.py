"""核对已读原厂 6211 安装表及边界语义；不改变通用标准或原验收数据。"""

import math

import pytest

from gongke_core.bearing_reference import check_abutment, lookup


@pytest.mark.parametrize(("manufacturer", "minimum", "maximum", "housing"), [
    ("SKF", 0.064, None, 0.091),  # SKF 17000/1 EN，2018，印刷页 280–281。
    ("NSK", 0.063, 0.0665, 0.092),  # 官方开式 6211 产品页，Abutment and Fillet Dimensions。
    ("Koyo", 0.063, None, 0.092),  # JTEKT 官方开式 6211 产品页，Mounting dimensions。
])
def test_manufacturer_records(manufacturer, minimum, maximum, housing):
    reference = lookup(manufacturer)
    assert reference["dimensions"] == {"bore_m": 0.055, "outside_m": 0.1, "width_m": 0.021}
    assert reference["abutment"] == {"shaft_diameter_min_m": minimum, "shaft_diameter_max_m": maximum,
                                    "housing_diameter_max_m": housing, "fillet_radius_max_m": 0.0015}
    assert reference["url"].startswith("https://")
    assert reference["source"] and reference["version"]
    assert "load_rating" not in reference


def test_unpublished_maximum_is_not_unlimited_permission():
    result = check_abutment(lookup("SKF"), 0.064, 0.0015)
    assert result["status"] == "unknown"
    assert result["checks"]["lower_bound"]["status"] == "pass"
    assert result["checks"]["upper_bound"]["status"] == "unknown"
    assert result["checks"]["fillet"]["status"] == "pass"
    assert check_abutment(lookup("SKF"), 0.09, 0.001)["status"] == "unknown"


def test_radius_unknown_is_separate_from_dimensions():
    result = check_abutment(lookup("NSK"), 0.064)
    assert result["status"] == "unknown"
    assert result["checks"]["lower_bound"]["status"] == "pass"
    assert result["checks"]["upper_bound"]["status"] == "pass"
    assert result["checks"]["fillet"]["status"] == "unknown"


def test_published_limits_include_endpoints_and_reject_exceedance():
    reference = lookup("NSK")
    assert check_abutment(reference, 0.063, 0.0015)["status"] == "pass"
    assert check_abutment(reference, 0.0665, 0.0015)["status"] == "pass"
    assert check_abutment(reference, math.nextafter(0.063, 0), 0.0015)["checks"]["lower_bound"]["status"] == "fail"
    assert check_abutment(reference, math.nextafter(0.0665, 1), 0.0015)["checks"]["upper_bound"]["status"] == "fail"
    assert check_abutment(reference, 0.064, math.nextafter(0.0015, 1))["checks"]["fillet"]["status"] == "fail"
    assert check_abutment(lookup("SKF"), 0.063, None)["status"] == "fail"


@pytest.mark.parametrize(("manufacturer", "designation"), [("generic", "6211"), ("SKF", "6211-2Z"), (None, "6211")])
def test_no_manufacturer_or_suffix_substitution(manufacturer, designation):
    with pytest.raises(ValueError, match="明确制造商"):
        lookup(manufacturer, designation)


def test_lookup_does_not_expose_mutable_catalog():
    lookup("SKF")["abutment"]["shaft_diameter_min_m"] = 0
    assert lookup("SKF")["abutment"]["shaft_diameter_min_m"] == 0.064


@pytest.mark.parametrize(("diameter", "radius"), [(float("nan"), None), (float("inf"), None),
                                                  (True, None), (-1, None), (0.064, -0.001)])
def test_invalid_measured_dimensions_are_rejected(diameter, radius):
    with pytest.raises(ValueError):
        check_abutment(lookup("SKF"), diameter, radius)
