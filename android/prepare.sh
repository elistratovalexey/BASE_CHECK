#!/usr/bin/env bash
# Копирует платформенно-независимое ядро из корня репозитория в android/
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DST="$ROOT/android"
CORE="paths.py config.py database.py expense_utils.py date_utils.py filters.py models.py \
ocr_service.py receipt_excel.py cloud_config.py cloud_webdav.py cloud_sync.py"
for f in $CORE; do
  cp "$ROOT/$f" "$DST/$f"
  echo "core: $f"
done
mkdir -p "$DST/tessdata"
if [ ! -f "$DST/tessdata/rus.traineddata" ]; then
  echo "Скачиваю rus.traineddata…"
  curl -L -o "$DST/tessdata/rus.traineddata" \
    https://github.com/tesseract-ocr/tessdata_fast/raw/main/rus.traineddata
fi
echo "Готово. Далее: cd android && buildozer android debug"