# -*- mode: python ; coding: utf-8 -*-
import os
import re
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

HERE = os.path.abspath(SPECPATH)

# ---------- версия из config.py ----------
_cfg = open(os.path.join(HERE, "config.py"), encoding="utf-8").read()
APP_VERSION = re.search(r'APP_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]', _cfg).group(1)
_p = (APP_VERSION.split(".") + ["0", "0", "0"])[:3]
VER_TUPLE = tuple(int(re.sub(r"\D", "", x) or 0) for x in _p) + (0,)
VER_FULL = ".".join(str(x) for x in VER_TUPLE)          # 1.6.0.0 — для ресурса
print(f"[spec] APP_VERSION={APP_VERSION} -> {VER_FULL}")

_ver_file = os.path.join(HERE, "version_info.txt")
with open(_ver_file, "w", encoding="utf-8") as f:
    f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={VER_TUPLE},
    prodvers={VER_TUPLE},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('041904B0', [
        StringStruct('CompanyName', 'Alex Elistratov'),
        StringStruct('FileDescription', 'Программа обработки чеков'),
        StringStruct('FileVersion', '{VER_FULL}'),
        StringStruct('InternalName', 'BASE_CHECK'),
        StringStruct('OriginalFilename', 'BASE_CHECK.exe'),
        StringStruct('ProductName', 'Программа обработки чеков'),
        StringStruct('ProductVersion', '{APP_VERSION}'),
        StringStruct('LegalCopyright', 'Alex Elistratov')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1049, 1200])])
  ]
)
""")

# ---------- ресурсы ----------
datas = []
for sub in ("vendor/tesseract", "vendor/poppler"):
    p = os.path.join(HERE, sub)
    if os.path.isdir(p):
        datas.append((p, sub.replace("/", os.sep)))
if os.path.isdir(os.path.join(HERE, "assets")):
    datas.append((os.path.join(HERE, "assets"), "assets"))
datas += collect_data_files("certifi")

hiddenimports = [
    "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets", "PyQt5.sip",
    "sqlite3", "paths", "config", "date_utils", "expense_utils",
    "database", "filters", "models", "ocr_service", "receipt_excel", "excel_service",
    "cloud_config", "cloud_webdav", "cloud_sync", "cloud_autosync",
    "ui_main_window", "ui_scan_dialog", "ui_receipt_dialog", "ui_cloud_dialog",
    "ui_companies_dialog", "ui_items_dialog", "ui_payers_dialog", "ui_calculation_dialog",
    "pytesseract", "pdf2image", "pypdf", "PIL",
    "requests", "certifi", "charset_normalizer", "idna", "urllib3",
] + collect_submodules("openpyxl")

a = Analysis(
    ["main.py"],
    pathex=[HERE],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy",
              "PyQt6", "PySide2", "PySide6", "test_all", "test_cloud", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

_ico = os.path.join(HERE, "assets", "app.ico")

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="BASE_CHECK",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=_ico if os.path.isfile(_ico) else None,
    version=_ver_file,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="BASE_CHECK")
