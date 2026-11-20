# paths.py
"""Пути к ресурсам и данным. Работает и из исходников, и из exe (PyInstaller)."""
import os
import sys
import shutil

APP_DIR_NAME = "BASE_CHECK"


def is_frozen():
    return getattr(sys, "frozen", False)


def resource_dir():
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def app_dir():
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def user_data_dir():
    """Каталог для БД и логов — всегда доступен на запись (не Program Files)."""
    if "ANDROID_PRIVATE" in os.environ:          # <-- Android (python-for-android)
        d = os.path.join(os.environ["ANDROID_PRIVATE"], APP_DIR_NAME)
        os.makedirs(d, exist_ok=True)
        return d
    if sys.platform.startswith("win"):
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        root = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    d = os.path.join(root, APP_DIR_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def db_path():
    return os.path.join(user_data_dir(), "receipts.db")


def log_path():
    return os.path.join(user_data_dir(), "app.log")


def _first_file(*candidates):
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def tesseract_cmd():
    exe = "tesseract.exe" if sys.platform.startswith("win") else "tesseract"
    found = _first_file(
        os.environ.get("TESSERACT_CMD"),
        os.path.join(resource_dir(), "vendor", "tesseract", exe),
        os.path.join(app_dir(), "vendor", "tesseract", exe),
        os.path.join(resource_dir(), exe),
        os.path.join(app_dir(), exe),
    )
    if found:
        return found
    found = shutil.which("tesseract")
    if found:
        return found
    if sys.platform.startswith("win"):
        return _first_file(
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Tesseract-OCR", exe),
            os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Tesseract-OCR", exe),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", exe),
        )
    return _first_file("/usr/bin/tesseract", "/usr/local/bin/tesseract")


def tessdata_dir():
    for d in (os.path.join(resource_dir(), "vendor", "tesseract", "tessdata"),
              os.path.join(app_dir(), "vendor", "tesseract", "tessdata"),
              os.path.join(resource_dir(), "tessdata"),
              os.path.join(app_dir(), "tessdata")):
        if os.path.isdir(d):
            return d
    env = os.environ.get("TESSDATA_PREFIX")
    return env if env and os.path.isdir(env) else None


def poppler_path():
    """Каталог с pdftoppm; None -> pdf2image ищет в PATH (обычный случай Linux)."""
    exe = "pdftoppm.exe" if sys.platform.startswith("win") else "pdftoppm"
    for d in (os.path.join(resource_dir(), "vendor", "poppler", "bin"),
              os.path.join(app_dir(), "vendor", "poppler", "bin"),
              os.path.join(resource_dir(), "poppler", "bin"),
              os.path.join(app_dir(), "poppler", "bin")):
        if os.path.isfile(os.path.join(d, exe)):
            return d
    return None


def migrate_legacy_db():
    """Переносит старую БД из каталога программы в пользовательский каталог."""
    target = db_path()
    if os.path.exists(target):
        return
    for legacy in (os.path.join(app_dir(), "receipts.db"), os.path.join(os.getcwd(), "receipts.db")):
        if os.path.isfile(legacy) and os.path.abspath(legacy) != os.path.abspath(target):
            try:
                shutil.copy2(legacy, target)
            except OSError:
                pass
            return
