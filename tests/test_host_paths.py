"""采集机与检查机的路径语义不必一致。"""
import pytest
from gongke_core.revision_mapping import _path


def test_windows_host_path_on_posix_checker():
    assert _path("C:/课程/轴/../中间轴.SLDPRT") == "c:\\课程\\中间轴.sldprt"
    assert _path("\\\\server\\课程\\轴.FCStd") == "\\\\server\\课程\\轴.fcstd"
    assert _path("/home/student/../shaft.FCStd") == "/home/shaft.FCStd"


@pytest.mark.parametrize("path", ["C:shaft.FCStd", "shaft.FCStd", "\\shaft.FCStd"])
def test_relative_host_path_rejected(path):
    with pytest.raises(ValueError):
        _path(path)
