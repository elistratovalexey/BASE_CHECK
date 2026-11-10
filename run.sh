#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "️  Создаю виртуальное окружение..."
    python3 -m venv venv
fi

source venv/bin/activate

if ! python -c "import PyQt5" 2>/dev/null; then
    echo " Устанавливаю зависимости..."
    pip install --quiet PyQt5 pytesseract Pillow openpyxl
fi

if ! command -v tesseract &> /dev/null; then
    echo "  Tesseract не найден. Установите: sudo apt install tesseract-ocr tesseract-ocr-rus"
fi

echo " Запуск программы обработки чеков..."
python main.py
