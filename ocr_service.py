# ocr_service.py
import os
import re
import shutil
import logging
import unicodedata
from PIL import Image, ImageEnhance, ImageFilter

try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = (
        os.environ.get("TESSERACT_CMD") or shutil.which("tesseract") or "/usr/bin/tesseract"
    )
except ImportError:
    pytesseract = None

logger = logging.getLogger(__name__)

MAX_TESSERACT_SIDE = 32000
CHUNK_HEIGHT = 20000

# Латинские двойники -> кириллица (для ДЕТЕКЦИИ ключевых слов, не для имён)
LOOK = str.maketrans({
    'A': 'А', 'B': 'В', 'C': 'С', 'E': 'Е', 'H': 'Н', 'K': 'К', 'M': 'М', 'O': 'О',
    'P': 'Р', 'T': 'Т', 'X': 'Х', 'Y': 'У', 'a': 'а', 'b': 'в', 'c': 'с', 'e': 'е',
    'h': 'н', 'k': 'к', 'm': 'м', 'o': 'о', 'p': 'р', 't': 'т', 'x': 'х', 'y': 'у',
    'r': 'г', 'n': 'п', 'u': 'и',
})


def norm(s):
    return unicodedata.normalize("NFKC", s).translate(LOOK)


def lev(a, b):
    if abs(len(a) - len(b)) > 2:
        return 99
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev = dp[0]; dp[0] = i
        for j, cb in enumerate(b, 1):
            cur = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (ca != cb)); prev = cur
    return dp[-1]


# ============================================================
# Извлечение текста
# ============================================================

def _text_layer_quality(text):
    """Оценка пригодности текстового слоя (чтобы не доверять плохому OCR скана)."""
    if len(text) < 50:
        return False
    digits = len(re.findall(r"\d", text))
    cyr = len(re.findall(r"[А-Яа-яЁё]", text))
    lat = len(re.findall(r"[A-Za-z]", text))
    markers = any(k in text for k in ("Итого", "ИТОГО", "руб", "Арт.", "Чек", "ВСЕГО", "Сумма"))
    # хороший слой: есть цифры, кириллица доминирует над латиницей, есть маркеры чека
    return digits >= 10 and cyr >= lat and (markers or cyr > 100)


def extract_text_from_pdf(pdf_path: str):
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            return None
    try:
        reader = PdfReader(pdf_path)
        text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
        if _text_layer_quality(text):
            return text
        return None
    except Exception as e:
        logger.warning(f"Не удалось прочитать текстовый слой PDF: {e}")
        return None


def _ocr_image(img):
    if pytesseract is None:
        raise RuntimeError("pytesseract не установлен. Установите pytesseract и tesseract-ocr-rus")
    return pytesseract.image_to_string(img, config=r"--oem 3 --psm 6 -l rus")


def _find_white_row(img, y_start, y_end):
    y_start = max(0, y_start); y_end = min(img.height - 1, y_end)
    for y in range(y_start, y_end):
        if img.crop((0, y, img.width, y + 1)).getextrema() == (255, 255):
            return y
    return None


def _preprocess(img, gentle=False):
    img = img.convert("L")
    if img.width < 1200:
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    if img.width > MAX_TESSERACT_SIDE:
        k = MAX_TESSERACT_SIDE / img.width
        img = img.resize((MAX_TESSERACT_SIDE, int(img.height * k)), Image.LANCZOS)
    if gentle:
        img = ImageEnhance.Contrast(img).enhance(1.5)
        hist = img.histogram()
        total = sum(hist) or 1
        mean = sum(i * h for i, h in enumerate(hist)) / total
        img = img.point(lambda x: 0 if x < mean else 255, "1")
    else:
        img = ImageEnhance.Contrast(img).enhance(2.5)
        img = img.filter(ImageFilter.SHARPEN)
        img = img.point(lambda x: 0 if x < 128 else 255, "1")
    return img


def _ocr_chunked(img):
    if img.height <= MAX_TESSERACT_SIDE:
        return _ocr_image(img)
    texts = []; y = 0
    while y < img.height:
        y_end = min(y + CHUNK_HEIGHT, img.height)
        if y_end < img.height:
            white = _find_white_row(img, y_end - 600, y_end + 600)
            if white is not None and white > y:
                y_end = white
        texts.append(_ocr_image(img.crop((0, y, img.width, y_end)))); y = y_end
    return "\n".join(texts)


def extract_text(image_path: str) -> str:
    Image.MAX_IMAGE_PIXELS = None
    return _ocr_chunked(_preprocess(Image.open(image_path), gentle=False))


def _extract_gentle(image_path: str) -> str:
    Image.MAX_IMAGE_PIXELS = None
    return _ocr_chunked(_preprocess(Image.open(image_path), gentle=True))


def _score(text):
    r = parse_receipt(text)
    return len(r["items"]) * 2 + (3 if r["total"] > 0 else 0) + (2 if not r["warnings"] else 0)


def extract_text_best(image_path: str) -> str:
    """Два прохода препроцессинга, выбираем лучший по «скору чека»."""
    try:
        a = extract_text(image_path)
        b = _extract_gentle(image_path)
        return b if _score(b) > _score(a) else a
    except Exception:
        return extract_text(image_path)


# ============================================================
# Числа / ключевые слова
# ============================================================

def _clean_number(s):
    if not s:
        return None
    s = str(s).strip()
    replacements = {
        "'": "7", "`": "7", "´": "7", "l": "1", "I": "1", "|": "1", "i": "1",
        "о": "0", "О": "0", "ш": "4", "Ш": "4", "з": "3", "З": "3", "у": "4", "У": "4",
        "y": "4", "с": "6", "С": "6", "c": "6", "г": "7", "Г": "7", "т": "7", "Т": "7",
        "р": "8", "Р": "8", "ь": "6", "Ь": "6", "б": "6", "Б": "6", "н": "4", "Н": "4",
        "к": "4", "К": "4", "м": "4", "М": "4", "х": "4", "Х": "4", "q": "0", "Q": "0",
        "g": "9", "G": "9", "e": "3", "E": "3", "a": "4", "A": "4", "S": "5", "s": "5",
        "B": "8", "b": "8", "~": "", "+": "",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    s = re.sub(r"[^\d.,]", "", s); s = s.replace(",", ".")
    if s.count(".") > 1:
        p = s.split("."); s = "".join(p[:-1]) + "." + p[-1]
    try:
        return float(s)
    except ValueError:
        return None


def _clean_num(s):
    s = re.sub(r"[^\d.,]", "", s).replace(",", ".")
    if s.count(".") > 1:
        p = s.split("."); s = "".join(p[:-1]) + "." + p[-1]
    try:
        return float(s)
    except ValueError:
        return None


def _find_company(det):
    skip = ["ЧЕК", "КАССОВЫЙ", "ОНЛАЙН", "КАССА", "ТО/", "КАРТА", "АРТ.", "АКЦИЯ", " ВЕС"]
    chains = (r"^(ГЛОБУС|АШАН|ЛЕНТА|МАГНИТ|ПЯТЁРОЧКА|ПЯТЕРОЧКА|ПЕРЕКРЁСТОК|ПЕРЕКРЕСТОК|ДИКСИ|METRO|МЕТРО)\b")
    for line in det:
        s = line.strip()
        if re.match(chains, s.upper()):
            return s
    # ресторан/кафе + название в кавычках
    for line in det:
        if re.search(r"ресторан|кафе|бар|столовая", line.lower()):
            m = re.search(r'[«"“]([^»"”]+)[»"”]', line)
            if m:
                return re.sub(r"\s+", " ", m.group(1)).strip(" —-|")
            return line.strip()
    # юрлицо ТОЛЬКО с названием в кавычках (не мусорные "ООО Пи")
    for line in det[:15]:
        up = line.upper().strip()
        if any(kw in up for kw in skip):
            continue
        if re.search(r"\b(ООО|ЗАО|ОАО|АО|ИП)\b", up):
            m = re.search(r'[«"“]([^»"”]+)[»"”]', line)
            if m and len(m.group(1)) > 2:
                return m.group(1).strip()
    for line in det[:15]:
        up = line.upper().strip()
        if any(kw in up for kw in skip):
            continue
        m = re.search(r'[«"“]([^»"”]+)[»"”]', line)
        if m and len(m.group(1)) > 2:
            return m.group(1).strip()
    return ""


def _total_candidates(det):
    cands = []
    for line in det:
        ll = line.lower()
        nums = re.findall(r"\d[\d\s\u00a0]*[.,]\d{1,2}", ll)
        if not nums:
            continue
        words = re.findall(r"[а-яё]+", ll)
        hit = any(lev(w, "итого") <= 2 or lev(w, "всего") <= 2 for w in words) or "оплат" in ll
        if hit and "ндс" not in ll:
            v = _clean_num(nums[-1])
            if v:
                cands.append(v)
    return cands


def _find_discount(det):
    for line in det:
        m = re.search(r"(\d{1,2})\s*%", line)
        words = re.findall(r"[а-яё]+", line.lower())
        if m or any(lev(w, "скидка") <= 2 for w in words):
            nums = re.findall(r"\d[\d\s]*[.,]\d{1,2}", line)
            if nums:
                return _clean_num(nums[-1]) or 0.0
    return 0.0


# ============================================================
# Парсеры позиций
# ============================================================

def _is_globus_format(lines):
    has_art = any(l.strip().startswith("Арт.") for l in lines)
    has_qty = any(re.match(r"^\d+(?:[.,]\d+)?\s+(кг|шт)\s+[\d\s]+[.,]\d{2}\s*руб", l.strip()) for l in lines)
    return has_art and has_qty


def _parse_globus_style(lines):
    items = []; discount = 0.0
    qty_sum = re.compile(r"^(\d+(?:[.,]\d+)?)\s+(кг|шт|л|г|мл|уп)\s+([\d\s]+[.,]\d{2})\s*руб\.?$")
    disc = re.compile(r"^Акция по карте\s+[–\-−]\s*([\d\s]+[.,]\d{2})", re.IGNORECASE)
    st = [l.strip() for l in lines]
    for i, ln in enumerate(st):
        d = disc.match(ln)
        if d:
            discount += _clean_number(d.group(1)) or 0.0
        if not ln.startswith("Арт."):
            continue
        article = ln.split(":", 1)[1].strip() if ":" in ln else ""
        name_lines = []; j = i + 1
        while j < len(st):
            m = qty_sum.match(st[j])
            if m:
                qty = _clean_number(m.group(1)); total = _clean_number(m.group(3))
                name = re.sub(r"\s+", " ", " ".join(name_lines)).strip()
                if name and qty and total is not None and qty > 0:
                    items.append({"name": name, "qty": round(qty, 3), "price": round(total / qty, 2),
                                  "sum": round(total, 2), "unit": m.group(2), "article": article, "confidence": "ok"})
                break
            if st[j].startswith(("Арт.", "Акция")) or not st[j]:
                break
            name_lines.append(st[j]); j += 1
    return items, round(discount, 2)


def _parse_restaurant_style(lines):
    items = []
    pat = re.compile(r"^\s*(\d+(?:[.\d]*\d+)?)\s+([A-ZА-ЯЁ][A-ZА-ЯЁа-яё\s\-\(\)\/\&\.\"\'@]{5,})(\d+[.,]\d{0,2})\s+(\d+[.,]\d{2,})")
    skip = ["ВСЕГО", "ИТОГО", "СКИДКА", "БЛЮДО", "КОЛ-ВО", "СУММА", "ЧЕК", "ОТКРЫТ", "ЗАКРЫТ",
            "КАССИР", "ОФИЦИАНТ", "СТОЛ", "ГОСТЕЙ", "РЕСТОРАН", "ОПЛАТА", "НАЛИЧН", "КАРТ", "НДС", "ЦЕНА"]
    for line in lines:
        line = line.strip()
        if not line:
            continue
        up = line.upper()
        if any(k in up for k in skip) or re.match(r"^\d{10,}", line) or not re.search(r"[A-ZА-ЯЁ]", up):
            continue
        m = pat.match(line)
        if m:
            qty = _clean_number(m.group(3)); total = _clean_number(m.group(4))
            if qty and total and qty > 0 and total > 10:
                name = re.sub(r"\s+", " ", m.group(2)).strip()
                name = re.sub(r"[\s\~\(\)\+\-\!\@\#\$\%\^\&\*\=\[\]\{\}\;\:\'\"\<\>\?\/\|]+$", "", name).strip()
                if len(name) >= 3:
                    items.append({"name": name, "qty": qty, "price": round(total / qty, 2),
                                  "sum": round(total, 2), "confidence": "ok"})
    return items


# Гибкий ресторанный парсер: кол-во в ресторане ~1, ищем пары (1.x | 100) + сумма
RPAIR = re.compile(r"(?<![\d.,])(1(?:[.,]\d{1,3})?|100|10)\s*[—\-–]?\s*(\d{1,7}[.,]\d{1,2})(?![.,]\d)")


def _footer_index(det):
    for i, l in enumerate(det):
        ll = l.lower(); words = re.findall(r"[а-яё]+", ll)
        if any(lev(w, "итого") <= 2 or lev(w, "всего") <= 2 for w in words) or \
           any(k in ll for k in ("оплат", "скид", "карт", "%")):
            return i
    return len(det)


def _parse_restaurant_pairs(det):
    items = []
    flat = "\n".join(det[:_footer_index(det)])
    prev_end = 0
    for m in RPAIR.finditer(flat):
        total = _clean_num(m.group(2))
        if total is None:
            continue
        seg = flat[prev_end:m.start()]; prev_end = m.end()
        seg = seg.split("\n")[-1]
        seg = re.sub(r"^[\s\d.,№#\-—|]+", "", seg)          # номер позиции
        seg = re.sub(r"[^\w\s«»\"'().,%/\-]", " ", seg)
        name = re.sub(r"\s+", " ", seg).strip(" .,-—|")
        if total < 1 and len(name) < 3:
            continue
        conf = "ok" if len(name) >= 4 else "low"
        items.append({"name": name[-60:], "qty": 1.0, "price": round(total, 2),
                      "sum": round(total, 2), "confidence": conf})
    return items


def _parse_shop_style(lines):
    items = []
    price_pattern = re.compile(r"^(\d+[.,]\d{2})\s+[xX×Ж]?\s*(\d+(?:[.,]\d+)?)\s*(?:шт|кг|л|г|мл|уп)?\.?\s*[=@]?\s*(\d+[.,]\d{2})")
    simple_pattern = re.compile(r"^(\d+[.,]\d{0,2})\s+(\d+[.,]\d{2})\s*$")
    skip = ["КАССОВЫЙ", "ЧЕК", "ОНЛАЙН", "КАССА", "МЕСТО РАСЧЕТОВ", "ИТОГО", "ВСЕГО", "НДС",
            "СУММА", "КОЛ-ВО", "ЦЕНА", "ОПЛАТА", "НАЛИЧНЫМИ", "КАРТОЙ", "СДАЧА", "СПАСИБО",
            "МАГАЗИН", "ТОРГОВЛЯ", "НЕ ОБЛАГАЕТСЯ"]

    def collect_name(idx):
        nl = []; j = idx - 1
        while j >= 0 and len(nl) < 3:
            p = lines[j].strip()
            if not p or len(p) < 3 or re.match(r"^\d+[.,]?\d*\s+\d+[.,]?\d*$", p):
                break
            if any(k in p.upper() for k in skip):
                break
            nl.insert(0, p); j -= 1
        return re.sub(r"\s+", " ", re.sub(r'["\'@]', "", " ".join(nl))).strip()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1; continue
        if any(k in line.upper() for k in skip):
            i += 1; continue
        mp = price_pattern.match(line); ms = simple_pattern.match(line)
        if mp:
            price = _clean_number(mp.group(1)); qty = _clean_number(mp.group(2)); total = _clean_number(mp.group(3))
            if qty is None or qty <= 0:
                qty = 1.0
            name = collect_name(i)
            if len(name) >= 5 and price and total:
                items.append({"name": name, "qty": round(qty, 3), "price": round(price, 2),
                              "sum": round(total, 2), "confidence": "ok"})
        elif ms:
            qty = _clean_number(ms.group(1)); total = _clean_number(ms.group(2))
            if qty and total:
                name = collect_name(i)
                if len(name) >= 5:
                    items.append({"name": name, "qty": round(qty, 3), "price": round(total / qty, 2),
                                  "sum": round(total, 2), "confidence": "ok"})
        i += 1
    return items


# ============================================================
# Главный парсер
# ============================================================

def parse_receipt(text: str) -> dict:
    res = {"date": "", "company": "", "total": 0.0, "items": [], "discount_total": 0.0,
           "items_sum": 0.0, "warnings": [], "format": ""}
    lines = text.split("\n")
    det = [norm(l) for l in lines]

    # 1. Дата с валидацией
    for l in det:
        m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})", l)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000
            if 1 <= d <= 31 and 1 <= mo <= 12 and 2000 <= y <= 2035:
                res["date"] = f"{d:02d}.{mo:02d}.{y}"
            else:
                res["warnings"].append(f"Дата распознана сомнительно: {m.group(0)}")
            break

    # 2. Компания
    res["company"] = _find_company(det)

    # 3. Позиции
    if _is_globus_format(lines):
        res["format"] = "globus"
        items, disc = _parse_globus_style(lines)
        res["items"] = items; res["discount_total"] = disc
    else:
        rest = _parse_restaurant_style(lines)
        shop = _parse_shop_style(lines)
        if rest or shop:
            res["format"] = "shop/restaurant"
            seen = {(i["name"].lower(), i["qty"], i["sum"]) for i in rest}
            res["items"] = rest + [i for i in shop if (i["name"].lower(), i["qty"], i["sum"]) not in seen]
        else:
            res["format"] = "restaurant-noisy"
            res["items"] = _parse_restaurant_pairs(det)
        res["discount_total"] = _find_discount(det)

    # 4. Итог: выбираем кандидата, ближайшего к сходимости
    res["items_sum"] = round(sum(i["sum"] for i in res["items"]), 2)
    expect = res["items_sum"] if res["format"] == "globus" else res["items_sum"] - res["discount_total"]
    cands = _total_candidates(det)
    if cands:
        res["total"] = min(cands, key=lambda c: abs(c - expect)) if res["items"] else cands[0]
    elif res["items"]:
        res["total"] = res["items_sum"]

    # 5. Сходимость
    if res["total"] and res["items"]:
        if abs(expect - res["total"]) > max(1.0, res["total"] * 0.01):
            res["warnings"].append(
                f"Сумма позиций {res['items_sum']:.2f} − скидка {res['discount_total']:.2f} = {expect:.2f} "
                f"≠ итог {res['total']:.2f} → вероятны ошибки OCR, нужна ручная проверка")
    return res