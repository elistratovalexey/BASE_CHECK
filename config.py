# config.py
from paths import db_path, migrate_legacy_db

# ЕДИНСТВЕННОЕ место, где меняется версия.
# Отсюда её берут: exe (свойства файла), установщик, APK, заголовок окна.
APP_VERSION = "1.6.0"
APP_DATE = "21.11.2026"
APP_TITLE = "ПРОГРАММА ОБРАБОТКИ ЧЕКОВ"

# БД лежит в пользовательском каталоге (%APPDATA%\BASE_CHECK на Windows),
# чтобы программа работала после установки в Program Files.
migrate_legacy_db()
DB_NAME = db_path()
