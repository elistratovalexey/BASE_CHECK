# main.py
import sys
import logging

import paths
from config import APP_TITLE, APP_VERSION


def _setup_logging():
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    handlers = [logging.FileHandler(paths.log_path(), encoding="utf-8")]
    if sys.stdout is not None:            # в оконном exe stdout отсутствует
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


logger = logging.getLogger(__name__)


def _excepthook(exc_type, exc, tb):
    logging.getLogger("unhandled").critical("Необработанное исключение", exc_info=(exc_type, exc, tb))
    try:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Ошибка",
                             f"{exc_type.__name__}: {exc}\n\nЛог: {paths.log_path()}")
    except Exception:
        pass


def main():
    _setup_logging()
    sys.excepthook = _excepthook
    logger.info("=== Запуск %s v%s ===", APP_TITLE, APP_VERSION)
    logger.info("Каталог данных: %s", paths.user_data_dir())

    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        app = QApplication(sys.argv)
        app.setApplicationName("BASE_CHECK")
        app.setOrganizationName("BASE_CHECK")

        from database import init_db
        init_db()
        logger.info("БД инициализирована: %s", paths.db_path())

        from ui_main_window import MainWindow
        w = MainWindow()
        w.show()
        logger.info("Главное окно открыто")
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
