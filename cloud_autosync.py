# cloud_autosync.py
"""Автосинхронизация: периодическая + отложенная после правок (дебаунс)."""
import logging
import threading
import time

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

import cloud_config
import cloud_sync

logger = logging.getLogger(__name__)


class SyncManager(QObject):
    status = pyqtSignal(str)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = cloud_config.load()
        self._busy = threading.Lock()
        self._last_change = 0.0
        self._last_sha = None
        self._periodic = time.time()
        self._timer = QTimer(self)
        self._timer.setInterval(10_000)
        self._timer.timeout.connect(self._tick)

    def reload(self):
        self.cfg = cloud_config.load()
        if self.cfg.get("autosync") and cloud_config.is_configured(self.cfg):
            self._periodic = time.time()
            self._timer.start()
        else:
            self._timer.stop()

    def start(self):
        self.reload()

    def stop(self):
        self._timer.stop()

    def _tick(self):
        if not cloud_config.is_configured(self.cfg):
            return
        try:
            sha = cloud_sync.sha256_bytes(cloud_sync.snapshot_db())
        except Exception:
            return
        if self._last_sha is None:
            self._last_sha = sha
        if sha != self._last_sha:
            self._last_sha = sha
            self._last_change = time.time()
        debounce = int(self.cfg.get("debounce_sec", 120) or 0)
        interval = int(self.cfg.get("interval_min", 15) or 0) * 60
        need_debounce = self._last_change and debounce and (time.time() - self._last_change >= debounce)
        need_periodic = interval and (time.time() - self._periodic >= interval)
        if need_debounce or need_periodic:
            self._last_change = 0.0
            self._periodic = time.time()
            self.run_async("auto")

    def run_async(self, mode="auto"):
        if not cloud_config.is_configured(self.cfg):
            self.failed.emit("Облако не настроено")
            return
        if not self._busy.acquire(blocking=False):
            return

        def work():
            s = None
            try:
                self.status.emit("синхронизация…")
                s = cloud_sync.CloudSync(self.cfg)
                res = s.push() if mode == "push" else s.pull() if mode == "pull" else s.sync()
                self._last_sha = res.get("sha")
                self._last_change = 0.0
                self.done.emit(res)
            except Exception as e:
                logger.warning("Синхронизация не удалась: %s", e)
                self.failed.emit(str(e))
            finally:
                if s:
                    s.close()
                self._busy.release()

        threading.Thread(target=work, daemon=True).start()

    def run_blocking(self, mode="auto", timeout_sec=None):
        """Синхронно — для старта и выхода программы."""
        if not cloud_config.is_configured(self.cfg):
            return {"action": "skip", "reason": "not configured"}
        s = None
        try:
            s = cloud_sync.CloudSync(self.cfg)
            if timeout_sec:
                s.dav.timeout = int(timeout_sec)
            return s.push() if mode == "push" else s.pull() if mode == "pull" else s.sync()
        except Exception as e:
            logger.warning("Синхронизация (%s) не удалась: %s", mode, e)
            return {"action": "error", "error": str(e)}
        finally:
            if s:
                s.close()