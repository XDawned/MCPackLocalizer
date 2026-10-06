# [Module: packaging.desktop] [Status: 已完成] [Brief: Fluent 桌面程序的多目录 EXE 构建]
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).parent
datas = collect_data_files("qfluentwidgets") + collect_data_files("qframelesswindow")
datas += [(str(root / "resources"), "mcpacklocalizer/resources")]
datas += collect_data_files("mcpacklocalizer", includes=["core/mods/data/*.json"])
a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("mcpacklocalizer") + ["tree_sitter_javascript"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["llama_cpp", "numpy", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="MCPackLocalizer",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, icon=str(root / "resources/icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MCPackLocalizer")
