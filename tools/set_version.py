#!/usr/bin/env python3
"""Автоматическая нумерация версий APK.

major.minor берётся из корневого config.py (APP_VERSION = "1.6.0").
Номер сборки: GITHUB_RUN_NUMBER (в CI) или локальный счётчик android/.build_number.
Итог: versionName = major.minor.build
      versionCode = major*10000000 + minor*100000 + build

Запускать ПОСЛЕ android/prepare.sh:
    python tools/set_version.py
"""
import os
import re
import sys
import pathlib
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
ANDROID = ROOT / "android"
COUNTER = ANDROID / ".build_number"
MAX_BUILD = 99999


def read_base():
    txt = (ROOT / "config.py").read_text(encoding="utf-8")
    m = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", txt)
    if not m:
        sys.exit("Не найден APP_VERSION в config.py")
    p = (m.group(1).split(".") + ["0", "0"])[:3]
    major, minor = int(p[0]), int(p[1])
    if not (0 <= major <= 200 and 0 <= minor <= 99):
        sys.exit("major должен быть 0..200, minor 0..99")
    return major, minor


def build_number():
    env = os.environ.get("BUILD_NUMBER") or os.environ.get("GITHUB_RUN_NUMBER")
    if env and env.strip().isdigit():
        n = int(env.strip())
    else:
        n = 0
        if COUNTER.exists():
            try:
                n = int(COUNTER.read_text(encoding="utf-8").strip() or 0)
            except ValueError:
                n = 0
        n += 1
        COUNTER.write_text(str(n), encoding="utf-8")
    return max(1, min(n, MAX_BUILD))


def set_key(path, key, value):
    """Записывает key = value в [app]; без кавычек — как требует buildozer."""
    txt = path.read_text(encoding="utf-8")
    line = f"{key} = {value}"
    pat = re.compile(r"(?m)^" + re.escape(key) + r"\s*=.*$")
    if pat.search(txt):
        txt = pat.sub(line, txt, count=1)
    else:
        txt = txt.replace("[app]", "[app]\n" + line, 1)
    path.write_text(txt, encoding="utf-8")


def main():
    major, minor = read_base()
    build = build_number()
    version = f"{major}.{minor}.{build}"
    code = major * 10000000 + minor * 100000 + build

    cfg = ANDROID / "config.py"
    if not cfg.exists():
        sys.exit("Нет android/config.py — сначала выполните: bash android/prepare.sh")
    txt = cfg.read_text(encoding="utf-8")
    txt = re.sub(r"(?m)^APP_VERSION\s*=.*$", f'APP_VERSION = "{version}"', txt, count=1)
    txt = re.sub(r"(?m)^APP_DATE\s*=.*$",
                 'APP_DATE = "%s"' % date.today().strftime("%d.%m.%Y"), txt, count=1)
    cfg.write_text(txt, encoding="utf-8")

    spec = ANDROID / "buildozer.spec"
    set_key(spec, "version", version)
    set_key(spec, "android.numeric_version", code)
    # убираем конфликтующие ключи, если они остались
    s = spec.read_text(encoding="utf-8")
    s = re.sub(r"(?m)^version\.(regex|filename)\s*=.*$\n?", "", s)
    spec.write_text(s, encoding="utf-8")

    print(f"versionName={version}  versionCode={code}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"version={version}\ncode={code}\n")


if __name__ == "__main__":
    main()