# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

HERE = os.path.abspath(SPECPATH)

# Портативные Tesseract и Poppler (кладутся скриптом get_vendor.ps1).
datas = []
for sub in ("vendor/tesseract", "vendor/poppler"):
    p = os.path.join(HERE, sub)
    if os.path.isdir(p):
        datas.append((p, sub.replace("/", os.sep)))
if os.path.isdir(os.path.join(HERE, "assets")):
    datas.append((os.path.join(HERE, "assets"), "assets"))

hiddenimports = [
    "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets", "PyQt5.sip",
    "sqlite3", "paths", "config", "date_utils", "expense_utils",
    "database", "filters", "models", "ocr_service", "receipt_excel", "excel_service",
    "ui_main_window", "ui_scan_dialog", "ui_receipt_dialog",
    "ui_companies_dialog", "ui_items_dialog", "ui_payers_dialog", "ui_calculation_dialog",
    "pytesseract", "pdf2image", "pypdf", "PIL",
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
              "PyQt6", "PySide2", "PySide6", "test_all", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

_ico = os.path.join(HERE, "assets", "app.ico")
_ver = os.path.join(HERE, "version_info.txt")

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="BASE_CHECK",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                      # оконное приложение без консоли
    disable_windowed_traceback=False,
    icon=_ico if os.path.isfile(_ico) else None,
    version=_ver if os.path.isfile(_ver) else None,
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="BASE_CHECK",
)
