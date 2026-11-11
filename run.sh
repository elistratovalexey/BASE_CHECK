#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv venv
fi

source venv/bin/activate

if ! python -c "import PyQt5, pytesseract, PIL, openpyxl, pdf2image, pypdf" 2>/dev/null; then
    echo "Устанавливаю зависимости..."
    pip install --quiet PyQt5 pytesseract Pillow openpyxl pdf2image pypdf
fi

if ! command -v tesseract &> /dev/null; then
    echo "⚠️  Tesseract не найден. Установите: sudo apt install tesseract-ocr tesseract-ocr-rus"
    echo "    (нужен только для сканов/фото; электронные PDF с текстовым слоем работают без него)"
fi

if ! command -v pdftoppm &> /dev/null; then
    echo "⚠️  Poppler не найден. Установите: sudo apt install poppler-utils"
    echo "    (нужен только для сканированных PDF без текстового слоя)"
fi

echo "Запуск программы обработки чеков..."
python main.py