# Build with tools/build_app_service.py on the target operating system.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

root = Path(SPECPATH).parent
datas = [(str(root / "data"), "data"), (str(root / "examples"), "examples")]
datas += collect_data_files("gongke_core", include_py_files=True)
datas += collect_data_files("ezdxf")
datas += collect_data_files("docx")
hiddenimports = collect_submodules("gongke_core") + collect_submodules("gongke_app")
a = Analysis([str(root / "packaging/service_entry.py")], pathex=[str(root)],
             binaries=collect_dynamic_libs("lib3mf"), datas=datas, hiddenimports=hiddenimports,
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=["tkinter", "pytest", "jupyter", "mcp"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="gongke-service",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="gongke-service")
