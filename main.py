# main.py
import sys
import logging
from PyQt5.QtWidgets import QApplication
from database import init_db
from ui_main_window import MainWindow

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),  # файл логов
        logging.StreamHandler(sys.stdout)                   # вывод в консоль
    ]
)
logger = logging.getLogger(__name__)

def main():
    logger.info("=== Запуск программы обработки чеков ===")
    
    try:
        init_db()
        logger.info("База данных инициализирована")
        
        app = QApplication(sys.argv)
        w = MainWindow()
        w.show()
        
        logger.info("Главное окно открыто")
        sys.exit(app.exec_())
        
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()