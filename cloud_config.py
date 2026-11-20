# cloud_config.py
"""Настройки синхронизации с Облаком Mail.ru.
Файл: %APPDATA%\\BASE_CHECK\\cloud_config.json — доступ только у владельца.
Логин/пароль НИКОГДА не уходят в облако и не пишутся в лог.
"""
import json
import logging
import os
import subprocess
import sys

import paths

logger = logging.getLogger(__name__)
FILE_NAME = "cloud_config.json"

DEFAULTS = {
    "url": "https://webdav.cloud.mail.ru",
    "login": "",
    "password": "",
    "folder": "BASE_CHECK",
    "autosync": True,
    "interval_min": 15,
    "debounce_sec": 120,
    "keep_copies": 10,
    "timeout_sec": 300,
    "retries": 4,
    "copy_every_min": 60,
    "sync_on_start": True,
    "sync_on_exit": True,
}

SHARED_KEYS = ("folder", "autosync", "interval_min", "debounce_sec", "keep_copies",
               "timeout_sec", "retries", "copy_every_min", "sync_on_start", "sync_on_exit")


def config_path():
    return os.path.join(paths.user_data_dir(), FILE_NAME)


def _harden(path):
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if sys.platform.startswith("win"):
        try:
            user = os.environ.get("USERNAME") or ""
            if user:
                subprocess.run(["icacls", path, "/inheritance:r", "/grant:r", f"{user}:F"],
                               capture_output=True, timeout=15, creationflags=0x08000000)
        except Exception:
            pass


def load():
    cfg = dict(DEFAULTS)
    p = config_path()
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
        except Exception as e:
            logger.warning("Не удалось прочитать настройки облака: %s", e)
    return cfg


def save(cfg):
    p = config_path()
    clean = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
    _harden(p)
    return p


def is_configured(cfg=None):
    cfg = cfg or load()
    return bool(cfg.get("url") and cfg.get("login") and cfg.get("password") and cfg.get("folder"))


def shared_part(cfg):
    return {k: cfg.get(k, DEFAULTS[k]) for k in SHARED_KEYS}


def merge_shared(cfg, remote):
    """Применяет облачные настройки, не трогая url/login/password."""
    out = dict(cfg)
    if isinstance(remote, dict):
        for k in SHARED_KEYS:
            if k in remote:
                out[k] = remote[k]
    return out