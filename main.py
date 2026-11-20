# main.py
import sys
import logging
import ctypes

import paths
from config import APP_TITLE, APP_VERSION

MUTEX_NAME = "BASE_CHECK_RUNNING"


def _setup_logging():
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    handlers = [logging.FileHandler(paths.log_path(), encoding="utf-8")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        handlers=handlers)


logger = logging.getLogger(__name__)
_mutex = None


def _single_instance():
    """Не даёт запустить две копии (важно при синхронизации базы)."""
    global _mutex
    if sys.platform.startswith("win"):
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        return ctypes.windll.kernel32.GetLastError() != 183   # ERROR_ALREADY_EXISTS
    return True


def _excepthook(exc_type, exc, tb):
    logging.getLogger("unhandled").critical("Необработанное исключение", exc_info=(exc_type, exc, tb))
    try:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Ошибка", f"{exc_type.__name__}: {exc}\n\nЛог: {paths.log_path()}")
    except Exception:
        pass


def main():
    _setup_logging()
    sys.excepthook = _excepthook
    logger.info("=== Запуск %s v%s ===", APP_TITLE, APP_VERSION)
    logger.info("Каталог данных: %s", paths.user_data_dir())

    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication, QMessageBox
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        app = QApplication(sys.argv)
        app.setApplicationName("BASE_CHECK")
        app.setOrganizationName("BASE_CHECK")

        if not _single_instance():
            QMessageBox.warning(None, "Программа уже запущена",
                                "Вторая копия программы не запускается — "
                                "иначе база может синхронизироваться некорректно.")
            sys.exit(0)

        from database import init_db
        init_db()
        logger.info("БД инициализирована: %s", paths.db_path())

        import cloud_config
        from cloud_autosync import SyncManager
        mgr = SyncManager()

        # --- синхронизация ПРИ ОТКРЫТИИ ---
        cfg = cloud_config.load()
        if cfg.get("sync_on_start") and cloud_config.is_configured(cfg):
            app.setOverrideCursor(Qt.WaitCursor)
            res = mgr.run_blocking("auto", timeout_sec=60)
            app.restoreOverrideCursor()
            logger.info("Синхронизация при запуске: %s", res)
            if res.get("action") == "conflict":
                QMessageBox.warning(None, "Облако",
                                    "База менялась и здесь, и в облаке.\n"
                                    "Ваша версия сохранена в облако (history/conflict_…db),\n"
                                    "рабочей стала облачная версия.")
            elif res.get("action") == "error":
                logger.warning("Облако недоступно: %s", res.get("error"))

        from ui_main_window import MainWindow
        w = MainWindow()
        w.sync_manager = mgr
        mgr.status.connect(w.set_cloud_status)
        mgr.done.connect(lambda r: w.set_cloud_status(
            f"{r.get('action')} · {r.get('size', 0)} Б"))
        mgr.failed.connect(lambda e: w.set_cloud_status(f"ошибка — {e[:60]}"))
        mgr.start()
        w.set_cloud_status("настроено" if cloud_config.is_configured(cfg) else "не настроено")
        w.show()
        logger.info("Главное окно открыто")

        # --- синхронизация ПРИ ЗАКРЫТИИ ---
        def on_quit():
            mgr.stop()
            c = cloud_config.load()
            if c.get("sync_on_exit") and cloud_config.is_configured(c):
                logger.info("Синхронизация при закрытии…")
                res = mgr.run_blocking("auto", timeout_sec=60)
                logger.info("Синхронизация при закрытии: %s", res)

        app.aboutToQuit.connect(on_quit)
        sys.exit(app.exec_())

    except Exception:
        logger.exception("Критическая ошибка запуска")
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox
            QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "Ошибка запуска",
                                 f"Не удалось запустить программу.\nЛог: {paths.log_path()}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()