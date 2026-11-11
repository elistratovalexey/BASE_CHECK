# ocr_service.py
import os
import re
import shutil
import logging
from PIL import Image, ImageEnhance, ImageFilter

try:
    import pytesseract
    # Путь к tesseract можно переопределить переменной окружения TESSERACT_CMD
    pytesseract.pytesseract.tesseract_cmd = (
        os.environ.get("TESSERACT_CMD")
        or shutil.which("tesseract")
        or "/usr/bin/tesseract"
    )
except ImportError:
    pytesseract = None

logger = logging.getLogger(__name__)

# Tesseract не принимает изображения со стороной больше 32767 px
MAX_TESSERACT_SIDE = 32000
# Высота полосы при OCR длинных чековых лент
CHUNK_HEIGHT = 20000


# ============================================================
# Извлечение текста
# ============================================================

def extract_text_from_pdf(pdf_path: str):
    """
    Пытается извлечь текстовый слой из PDF (электронные чеки).
    Возвращает текст или None, если PDF — скан без текстового слоя.
    OCR в этом случае не нужен: текст уже точный, без ошибок распознавания.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            logger.warning("pypdf/PyPDF2 не установлены — текстовый слой PDF недоступен")
            return None
    try:
        reader = PdfReader(pdf_path)
        parts = [(page.extract_text() or "") for page in reader.pages]
        text = "\n".join(parts).strip()
        # Эвристика: текстовый слой считается пригодным,
        # если в нём достаточно символов и цифр
        if len(text) >= 50 and len(re.findall(r"\d", text)) >= 10:
            return text
        return None
    except Exception as e:
        logger.warning(f"Не удалось прочитать текстовый слой PDF: {e}")
        return None


def _ocr_image(img) -> str:
    if pytesseract is None:
        raise RuntimeError(
            "pytesseract не установлен. Установите: pip install pytesseract "
            "и tesseract-ocr + tesseract-ocr-rus"
        )
    custom_config = r"--oem 3 --psm 6 -l rus"
    return pytesseract.image_to_string(img, config=custom_config)


def _find_white_row(img, y_start: int, y_end: int):
    """Ищет полностью белую строку (промежуток между строками текста)."""
    y_start = max(0, y_start)
    y_end = min(img.height - 1, y_end)
    for y in range(y_start, y_end):
        if img.crop((0, y, img.width, y + 1)).getextrema() == (255, 255):
            return y
    return None


def extract_text(image_path: str) -> str:
    """
    Распознаёт текст с улучшенной предобработкой.
    Длинные чековые ленты режутся на полосы по белым промежуткам
    между строками, чтобы не превышать лимит tesseract (32767 px).
    """
    # Длинная лента чека — не "декомпрессионная бомба", снимаем лимит PIL
    Image.MAX_IMAGE_PIXELS = None

    img = Image.open(image_path)
    img = img.convert("L")

    # Увеличиваем только мелкие изображения (фото); 300 dpi уже достаточно
    if img.width < 1200:
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    if img.width > MAX_TESSERACT_SIDE:
        k = MAX_TESSERACT_SIDE / img.width
        img = img.resize((MAX_TESSERACT_SIDE, int(img.height * k)), Image.LANCZOS)

    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.point(lambda x: 0 if x < 128 else 255, "1")

    if img.height <= MAX_TESSERACT_SIDE:
        return _ocr_image(img)

    # Длинная лента: режем на полосы, стараясь резать по пустой строке
    texts = []
    y = 0
    while y < img.height:
        y_end = min(y + CHUNK_HEIGHT, img.height)
        if y_end < img.height:
            white = _find_white_row(img, y_end - 600, y_end + 600)
            if white is not None and white > y:
                y_end = white
        texts.append(_ocr_image(img.crop((0, y, img.width, y_end))))
        y = y_end
    return "\n".join(texts)


# ============================================================
# Вспомогательные функции
# ============================================================

def _clean_number(s):
    """Очистка числа от OCR-мусора. Пробелы-разделители тысяч удаляются."""
    if not s:
        return None
    s = str(s).strip()
    replacements = {
        "'": "7", "`": "7", "´": "7", "l": "1", "I": "1", "|": "1", "i": "1",
        "о": "0", "О": "0", "ш": "4", "Ш": "4", "з": "3", "З": "3",
        "у": "4", "У": "4", "y": "4", "с": "6", "С": "6", "c": "6",
        "г": "7", "Г": "7", "т": "7", "Т": "7", "р": "8", "Р": "8",
        "ь": "6", "Ь": "6", "б": "6", "Б": "6", "н": "4", "Н": "4",
        "к": "4", "К": "4", "м": "4", "М": "4", "х": "4", "Х": "4",
        "q": "0", "Q": "0", "g": "9", "G": "9", "e": "3", "E": "3",
        "a": "4", "A": "4", "S": "5", "s": "5", "B": "8", "b": "8",
        "~": "", "+": "",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)

    s = re.sub(r"[^\d.,]", "", s)
    s = s.replace(",", ".")
    if s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(s)
    except ValueError:
        return None


def _find_company(lines: list) -> str:
    """
    Поиск компании. Приоритет:
    1) строка магазина известных сетей ("Глобус Балашиха" и т.п.);
    2) юрлицо (ООО/ИП/...) в шапке чека;
    3) ресторан/кафе или название в кавычках в шапке.
    Названия товаров в кавычках и карта лояльности не считаются компанией.
    """
    skip = ["ЧЕК", "КАССОВЫЙ", "ОНЛАЙН", "КАССА", "ТО/", "КАРТА",
            "АРТ.", "АКЦИЯ", " ВЕС"]
    chains = (r"^(ГЛОБУС|АШАН|ЛЕНТА|МАГНИТ|ПЯТЁРОЧКА|ПЯТЕРОЧКА|"
              r"ПЕРЕКРЁСТОК|ПЕРЕКРЕСТОК|ДИКСИ|METRO|МЕТРО)\b")
    for line in lines:
        s = line.strip()
        if re.match(chains, s.upper()):
            return s
    for line in lines[:15]:
        up = line.upper().strip()
        if any(kw in up for kw in skip):
            continue
        if re.search(r"\b(ООО|ЗАО|ОАО|АО|ИП)\b", up):
            m = re.search(r'[«"]([^»"]+)[»"]', line)
            return m.group(1).strip() if m else line.strip()
    for line in lines[:15]:
        up = line.upper().strip()
        if any(kw in up for kw in skip):
            continue
        if re.match(r"^(РЕСТОРАН|КАФЕ|БАР|СТОЛОВАЯ)", up):
            return line.strip()
        m = re.search(r'[«"]([^»"]+)[»"]', line)
        if m and len(m.group(1)) > 2:
            return m.group(1).strip()
    return ""


def _find_total(lines: list) -> float:
    """
    Поиск итога. Сумма может содержать пробелы-разделители тысяч:
    "Итого 11 408,46 руб." -> 11408.46
    """
    pat = re.compile(
        r"(?:ИТОГО\s+К\s+ОПЛАТЕ|ИТОГО|ВСЕГО\s+К\s+ОПЛАТЕ|ВСЕГО|TOTAL)"
        r"\s*[:=]?\s*(\d[\d\s\u00a0]*[.,]\d{2})"
    )
    for line in lines:
        up = line.upper()
        if "НДС" in up:  # "Итого НДС" — не итог чека
            continue
        m = pat.search(up)
        if m:
            val = _clean_number(m.group(1))
            if val:
                return val
    return 0.0


# ============================================================
# Парсеры позиций
# ============================================================

def _is_globus_format(lines: list) -> bool:
    has_art = any(l.strip().startswith("Арт.") for l in lines)
    has_qty = any(
        re.match(r"^\d+(?:[.,]\d+)?\s+(кг|шт)\s+[\d\s]+[.,]\d{2}\s*руб", l.strip())
        for l in lines
    )
    return has_art and has_qty


def _parse_globus_style(lines: list):
    """
    Парсинг чека «Глобус». Формат:
        Арт.: 280060
        РЕДИС ВЕС                  <- название, 1-2 строки
        0.658 кг 98,69 руб.
        Акция по карте –24,60 руб. <- необязательно (сумма уже со скидкой)
    Повторяющиеся позиции (творог x10 и т.п.) сохраняются все.
    Возвращает (items, discount_total).
    """
    items = []
    discount_total = 0.0
    qty_sum = re.compile(
        r"^(\d+(?:[.,]\d+)?)\s+(кг|шт|л|г|мл|уп)\s+([\d\s]+[.,]\d{2})\s*руб\.?$"
    )
    disc = re.compile(r"^Акция по карте\s+[–\-−]\s*([\d\s]+[.,]\d{2})", re.IGNORECASE)
    stripped = [l.strip() for l in lines]

    for i, ln in enumerate(stripped):
        d = disc.match(ln)
        if d:
            discount_total += _clean_number(d.group(1)) or 0.0
        if not ln.startswith("Арт."):
            continue
        article = ln.split(":", 1)[1].strip() if ":" in ln else ""
        name_lines = []
        j = i + 1
        while j < len(stripped):
            m = qty_sum.match(stripped[j])
            if m:
                qty = _clean_number(m.group(1))
                total = _clean_number(m.group(3))
                name = re.sub(r"\s+", " ", " ".join(name_lines)).strip()
                if name and qty and total is not None and qty > 0:
                    items.append({
                        "name": name,
                        "qty": round(qty, 3),
                        # фактическая цена за единицу (сумма уже со скидкой)
                        "price": round(total / qty, 2),
                        "sum": round(total, 2),
                        "unit": m.group(2),
                        "article": article,
                    })
                break
            if stripped[j].startswith(("Арт.", "Акция")) or not stripped[j]:
                break
            name_lines.append(stripped[j])
            j += 1
    return items, round(discount_total, 2)


def _parse_restaurant_style(lines: list) -> list:
    """Ресторанный чек: "1.4 НАЗВАНИЕ БЛЮДА 1.00 597.00" """
    items = []
    item_pattern = re.compile(
        r"^\s*(\d+(?:[.\d]*\d+)?)\s+"
        r"([A-ZА-ЯЁ][A-ZА-ЯЁа-яё\s\-\(\)\/\&\.\"\'@]{5,})"
        r"(\d+[.,]\d{0,2})\s+"
        r"(\d+[.,]\d{2,})"
    )
    skip_keywords = ["ВСЕГО", "ИТОГО", "СКИДКА", "БЛЮДО", "КОЛ-ВО", "СУММА",
                     "ЧЕК", "ОТКРЫТ", "ЗАКРЫТ", "КАССИР", "ОФИЦИАНТ", "СТОЛ",
                     "ГОСТЕЙ", "РЕСТОРАН", "ОПЛАТА", "НАЛИЧН", "КАРТ", "НДС", "ЦЕНА"]
    for line in lines:
        line = line.strip()
        if not line:
            continue
        line_up = line.upper()
        if any(kw in line_up for kw in skip_keywords):
            continue
        if re.match(r"^\d{10,}", line):
            continue
        if not re.search(r"[A-ZА-ЯЁ]", line_up):
            continue
        m = item_pattern.match(line)
        if m:
            name_raw = m.group(2).strip()
            qty = _clean_number(m.group(3))
            total = _clean_number(m.group(4))
            if qty and total and qty > 0 and total > 10:
                name = re.sub(r"\s+", " ", name_raw).strip()
                name = re.sub(r"[\s\~\(\)\+\-\!\@\#\$\%\^\&\*\=\[\]\{\}\;\:\'\"\<\>\?\/\|]+$", "", name).strip()
                if len(name) >= 3:
                    items.append({"name": name, "qty": qty,
                                  "price": round(total / qty, 2), "sum": round(total, 2)})
    return items


def _parse_shop_style(lines: list) -> list:
    """
    Магазинный чек: название на нескольких строках, затем "ЦЕНА xКОЛ-ВО =СУММА"
    Пример: "260.00 x1 шт. =260.00"
    """
    items = []
    # ИСПРАВЛЕНО: количество берётся из второй группы (раньше бралось первое
    # число строки, т.е. цена), допускаются "x"/"Ж" и точка после единицы.
    price_pattern = re.compile(
        r"^(\d+[.,]\d{2})\s+"
        r"[xX×Ж]?\s*(\d+(?:[.,]\d+)?)\s*"
        r"(?:шт|кг|л|г|мл|уп)?\.?\s*"
        r"[=@]?\s*"
        r"(\d+[.,]\d{2})"
    )
    simple_pattern = re.compile(r"^(\d+[.,]\d{0,2})\s+(\d+[.,]\d{2})\s*$")
    skip_keywords = ["КАССОВЫЙ", "ЧЕК", "ОНЛАЙН", "КАССА", "МЕСТО РАСЧЕТОВ",
                     "ИТОГО", "ВСЕГО", "НДС", "СУММА", "КОЛ-ВО", "ЦЕНА",
                     "ОПЛАТА", "НАЛИЧНЫМИ", "КАРТОЙ", "СДАЧА", "СПАСИБО",
                     "МАГАЗИН", "ТОРГОВЛЯ", "НЕ ОБЛАГАЕТСЯ"]

    def collect_name(idx):
        name_lines = []
        j = idx - 1
        while j >= 0 and len(name_lines) < 3:
            prev_line = lines[j].strip()
            if (not prev_line or len(prev_line) < 3
                    or re.match(r"^\d+[.,]?\d*\s+\d+[.,]?\d*$", prev_line)):
                break
            if any(kw in prev_line.upper() for kw in skip_keywords):
                break
            name_lines.insert(0, prev_line)
            j -= 1
        name = re.sub(r'["\'@]', "", " ".join(name_lines)).strip()
        return re.sub(r"\s+", " ", name).strip()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if any(kw in line.upper() for kw in skip_keywords):
            i += 1
            continue

        m_price = price_pattern.match(line)
        m_simple = simple_pattern.match(line)

        if m_price:
            price = _clean_number(m_price.group(1))
            qty = _clean_number(m_price.group(2))
            total = _clean_number(m_price.group(3))
            if qty is None or qty <= 0:
                qty = 1.0
            name = collect_name(i)
            if len(name) >= 5 and price and total:
                items.append({"name": name, "qty": round(qty, 3),
                              "price": round(price, 2), "sum": round(total, 2)})
        elif m_simple:
            qty = _clean_number(m_simple.group(1))
            total = _clean_number(m_simple.group(2))
            if qty and total:
                name = collect_name(i)
                if len(name) >= 5:
                    items.append({"name": name, "qty": round(qty, 3),
                                  "price": round(total / qty, 2), "sum": round(total, 2)})
        i += 1
    return items


# ============================================================
# Главный парсер
# ============================================================

def parse_receipt(text: str) -> dict:
    """
    Универсальный парсер чеков: «Глобус» + ресторан + магазин.
    Возвращает date, company, total, items, а также discount_total,
    items_sum и warnings (контроль сходимости суммы позиций с итогом).
    """
    result = {"date": "", "company": "", "total": 0.0, "items": [],
              "discount_total": 0.0, "items_sum": 0.0, "warnings": []}
    lines = text.split("\n")

    # 1. Дата
    for line in lines:
        m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})", line)
        if m:
            day, month, year = m.groups()
            if len(year) == 2:
                year = "20" + year
            result["date"] = f"{day.zfill(2)}.{month.zfill(2)}.{year}"
            break

    # 2. Компания
    result["company"] = _find_company(lines)

    # 3. Итого (с учётом пробелов-разделителей тысяч)
    result["total"] = _find_total(lines)

    # 4. Позиции
    if _is_globus_format(lines):
        items, discount = _parse_globus_style(lines)
        result["items"] = items
        result["discount_total"] = discount
    else:
        items_restaurant = _parse_restaurant_style(lines)
        items_shop = _parse_shop_style(lines)
        # Убираем только полные пересечения двух парсеров (название+кол-во+сумма).
        # Законные повторы одинаковых позиций внутри чека сохраняются.
        seen = {(it["name"].lower(), it["qty"], it["sum"]) for it in items_restaurant}
        result["items"] = items_restaurant + [
            it for it in items_shop
            if (it["name"].lower(), it["qty"], it["sum"]) not in seen
        ]

    # 5. Контроль сходимости
    result["items_sum"] = round(sum(it["sum"] for it in result["items"]), 2)
    if result["total"] == 0 and result["items"]:
        result["total"] = result["items_sum"]
    elif result["items"] and abs(result["total"] - result["items_sum"]) > 0.05:
        result["warnings"].append(
            f"Сумма позиций ({result['items_sum']:.2f}) не сходится "
            f"с итогом чека ({result['total']:.2f})"
        )
    return result