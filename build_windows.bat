@echo off
setlocal
cd /d "%~dp0"

echo === 1/5 Python ===
where python >nul 2>nul || (echo Install Python 3.11-3.12 x64 from python.org & exit /b 1)
python -c "import sys;print(sys.version)"

echo === 2/5 venv + deps ===
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip wheel
pip install -r requirements.txt || exit /b 1

echo === 3/5 vendor (Tesseract + Poppler) ===
powershell -NoProfile -ExecutionPolicy Bypass -File get_vendor.ps1

echo === 4/5 PyInstaller ===
if exist build rmdir /s /q build
if exist dist\BASE_CHECK rmdir /s /q dist\BASE_CHECK
pyinstaller --noconfirm BASE_CHECK.spec || exit /b 1

echo === 5/5 Inno Setup ===
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
  "%ISCC%" installer.iss || exit /b 1
  echo Installer: dist\BASE_CHECK-1.4.0-win64-setup.exe
) else (
  echo Inno Setup 6 not found: winget install JRSoftware.InnoSetup
  echo Portable build ready: dist\BASE_CHECK\BASE_CHECK.exe
)
echo Done.
