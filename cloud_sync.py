# cloud_sync.py
"""Синхронизация базы и настроек с Облаком Mail.ru.

Облако:  <folder>/receipts.db, settings.json (без пароля), manifest.json, history/*.db
Локально: cloud_state.json (sha последней синхронизации), backups/*.db
"""
import hashlib
import json
import logging
import os
import shutil
import socket
import sqlite3
import tempfile
import time
import uuid
from datetime import datetime, timezone

import paths
import cloud_config
from cloud_webdav import WebDav, WebDavError

logger = logging.getLogger(__name__)

DB_FILE = "receipts.db"
SETTINGS_FILE = "settings.json"
MANIFEST_FILE = "manifest.json"
HISTORY_DIR = "history"
STATE_FILE = "cloud_state.json"
BACKUP_DIR = "backups"
REQUIRED_TABLES = {"receipts", "receipt_items", "payers", "companies", "item_names"}


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def device_name():
    return socket.gethostname() or "unknown"


def sha256_bytes(data):
    return hashlib.sha256(data or b"").hexdigest()


def state_path():
    return os.path.join(paths.user_data_dir(), STATE_FILE)


def load_state():
    try:
        with open(state_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    p = state_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def snapshot_db(db_path=None):
    """Согласованный снимок базы (SQLite backup API) -> bytes."""
    src_path = db_path or paths.db_path()
    if not os.path.isfile(src_path):
        return None
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        src, dst = sqlite3.connect(src_path), sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def validate_db(data):
    if not data or len(data) < 100:
        return False
    fd, tmp = tempfile.mkstemp(suffix=".db")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        con = sqlite3.connect(tmp)
        try:
            ok = con.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()
        return ok == "ok" and REQUIRED_TABLES <= tables
    except Exception:
        return False
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

def _ensure_private_dir(path):
    os.makedirs(path, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def backup_local_db():
    """Создаёт локальную резервную копию перед заменой базы."""
    src = paths.db_path()
    if not os.path.isfile(src):
        return None

    d = os.path.join(paths.user_data_dir(), BACKUP_DIR)
    _ensure_private_dir(d)

    dst = os.path.join(d, f"receipts_{_stamp()}.db")

    # Копируем через SQLite backup API, а не shutil.copy2:
    # так снимок согласованный и без проблем с правами/атрибутами.
    s = sqlite3.connect(src)
    t = sqlite3.connect(dst)
    try:
        s.backup(t)
    finally:
        t.close()
        s.close()

    try:
        os.chmod(dst, 0o600)
    except OSError:
        pass

    files = sorted(f for f in os.listdir(d) if f.endswith(".db"))
    for f in files[:-20]:
        try:
            os.unlink(os.path.join(d, f))
        except OSError:
            pass

    return dst


def replace_db(data):
    """Заменяет локальную базу данными из облака."""
    if not validate_db(data):
        raise WebDavError("Файл базы в облаке повреждён или не является базой программы")

    backup_local_db()

    dst = paths.db_path()
    dst_dir = os.path.dirname(dst)
    _ensure_private_dir(dst_dir)

    fd, tmp = tempfile.mkstemp(suffix=".db", dir=dst_dir)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass

        os.replace(tmp, dst)

        try:
            os.chmod(dst, 0o600)
        except OSError:
            pass

    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass

    return True


class CloudSync:
    def __init__(self, cfg=None):
        self.cfg = cfg or cloud_config.load()
        self.folder = (self.cfg.get("folder") or "BASE_CHECK").strip("/")
        self.dav = WebDav(self.cfg.get("url"), self.cfg.get("login"), self.cfg.get("password"),
                          timeout=self.cfg.get("timeout_sec", 300),
                          retries=self.cfg.get("retries", 4))

    def close(self):
        self.dav.close()

    def p(self, name):
        return f"{self.folder}/{name}"

    def prepare(self):
        self.dav.ensure_folder(self.folder)
        self.dav.ensure_folder(f"{self.folder}/{HISTORY_DIR}")

    def read_manifest(self):
        raw = self.dav.get(self.p(MANIFEST_FILE))
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _rotate(self):
        keep = int(self.cfg.get("keep_copies", 10) or 0)
        if keep <= 0:
            return
        items = [x for x in self.dav.list(f"{self.folder}/{HISTORY_DIR}")
                 if not x["dir"] and x["name"].endswith(".db")]
        items.sort(key=lambda x: x["name"])
        for x in items[:-keep]:
            self.dav.delete(f"{self.folder}/{HISTORY_DIR}/{x['name']}")

    def make_copy(self, data, prefix="receipts"):
        name = f"{prefix}_{_stamp()}_{device_name()}.db"
        self.dav.put(f"{self.folder}/{HISTORY_DIR}/{name}", data)
        self._rotate()
        return name

    # ---------- операции ----------
    def push(self, make_copy=None):
        self.prepare()
        data = snapshot_db()
        if data is None:
            raise WebDavError("Локальная база не найдена")
        sha = sha256_bytes(data)
        self.dav.put(self.p(DB_FILE), data)
        self.dav.put(self.p(SETTINGS_FILE), json.dumps(
            cloud_config.shared_part(self.cfg), ensure_ascii=False, indent=2).encode("utf-8"))
        st = load_state()
        if make_copy is None:
            every = int(self.cfg.get("copy_every_min", 60) or 0)
            last = float(st.get("last_copy_ts") or 0)
            make_copy = (every == 0) or (time.time() - last >= every * 60)
        copy_name = None
        if make_copy:
            copy_name = self.make_copy(data)
            st["last_copy_ts"] = time.time()
        rev = uuid.uuid4().hex
        self.dav.put(self.p(MANIFEST_FILE), json.dumps(
            {"rev": rev, "db_sha256": sha, "size": len(data), "updated_at": _now_iso(),
             "device": device_name(), "copy": copy_name}, ensure_ascii=False, indent=2).encode("utf-8"))
        st.update({"base_sha": sha, "rev": rev, "last_sync": _now_iso()})
        save_state(st)
        return {"action": "push", "sha": sha, "size": len(data), "copy": copy_name}

    def pull(self):
        self.prepare()
        man = self.read_manifest()
        data = self.dav.get(self.p(DB_FILE))
        if data is None:
            raise WebDavError("В облаке нет файла базы")
        replace_db(data)
        sha = sha256_bytes(data)
        remote_cfg = self.dav.get(self.p(SETTINGS_FILE))
        if remote_cfg:
            try:
                merged = cloud_config.merge_shared(self.cfg, json.loads(remote_cfg.decode("utf-8")))
                cloud_config.save(merged)
                self.cfg = merged
            except Exception as e:
                logger.warning("Настройки из облака не применены: %s", e)
        st = load_state()
        st.update({"base_sha": sha, "rev": (man or {}).get("rev"), "last_sync": _now_iso()})
        save_state(st)
        return {"action": "pull", "sha": sha, "size": len(data)}

    def sync(self):
        self.prepare()
        local = snapshot_db()
        if local is None:
            raise WebDavError("Локальная база не найдена")
        local_sha = sha256_bytes(local)
        man = self.read_manifest()
        st = load_state()
        base = st.get("base_sha")

        if not man:
            return self.push(make_copy=True)
        remote_sha = man.get("db_sha256")
        if remote_sha == local_sha:
            st.update({"base_sha": local_sha, "rev": man.get("rev"), "last_sync": _now_iso()})
            save_state(st)
            return {"action": "noop", "sha": local_sha}
        if remote_sha == base:
            return self.push()
        if local_sha == base:
            return self.pull()
        if base is None:
            self.make_copy(local, prefix="local-before-first-sync")
            return self.pull()
        self.make_copy(local, prefix="conflict")
        res = self.pull()
        res["action"] = "conflict"
        return res

    def diagnostics(self):
        lines = []
        t0 = time.time()
        self.dav.ping()
        lines.append(f"Связь: OK ({time.time() - t0:.1f} c)")
        self.prepare()
        lines.append(f"Папка «{self.folder}»: доступна")
        man = self.read_manifest()
        lines.append(f"Манифест: {'есть' if man else 'нет'}")
        if man:
            lines.append(f"  ревизия {str(man.get('rev'))[:8]}, обновлено {man.get('updated_at')}, "
                         f"устройство {man.get('device')}")
        data = snapshot_db()
        lines.append(f"Локальная база: {len(data or b'')} байт, sha {sha256_bytes(data)[:12]}")
        copies = [x for x in self.dav.list(f"{self.folder}/{HISTORY_DIR}") if x["name"].endswith(".db")]
        lines.append(f"Копий в облаке: {len(copies)}")
        lines.append(f"Файл настроек: {cloud_config.config_path()}")
        return "\n".join(lines)
