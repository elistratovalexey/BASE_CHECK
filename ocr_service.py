# ocr_service.py
import re
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

def extract_text(image_path: str) -> str:
    img = Image.open(image_path)
    img = img.convert('L')
    img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.point(lambda x: 0 if x < 128 else 255, '1')
    
    custom_config = r'--oem 3 --psm 6 -l rus'
    return pytesseract.image_to_string(img, config=custom_config)

def _clean_number(s):
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
    
    s = re.sub(r'[^\d.,]', '', s)
    s = s.replace(',', '.')
    if s.count('.') > 1:
        parts = s.split('.')
        s = ''.join(parts[:-1]) + '.' + parts[-1]
    try:
        return float(s)
    except:
        return None

def parse_receipt(text: str) -> dict:
    result = {"date": "", "company": "", "total": 0.0, "items": []}
    lines = text.split('\n')
    
    # 1. Поиск даты (ИСПРАВЛЕНО)
    for line in lines:
        m = re.search(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})', line)
        if m:
            day, month, year = m.groups()
            if len(year) == 2:
                year = '20' + year
            result["date"] = f"{day.zfill(2)}.{month.zfill(2)}.{year}"
            break
    
    # 2. Поиск компании (ИСПРАВЛЕНО)
    skip_keywords_company = ['ЧЕК', 'КАССОВЫЙ', 'ОНЛАЙН', 'КАССА', 'ТО/']
    for line in lines:
        line_up = line.upper().strip()
        if any(kw in line_up for kw in skip_keywords_company):
            continue
        if re.match(r'^(РЕСТОРАН|КАФЕ|БАР|СТОЛОВАЯ)', line_up):
            result["company"] = line.strip()
            break
        m = re.search(r'[""«"]([^""»"]+)[""»"]', line)
        if m and len(m.group(1)) > 2:
            result["company"] = m.group(1).strip()
            break
    
    # 3. Поиск ИТОГО
    for line in lines:
        line_up = line.upper()
        m = re.search(r'(?:ИТОГО|ВСЕГО|TOTAL|ИТОГО К ОПЛАТЕ)[:\s]*(\d+[.,]?\d*)', line_up)
        if m:
            val = _clean_number(m.group(1))
            if val:
                result["total"] = val
                break
    
    # 4. Поиск позиций
    items_restaurant = _parse_restaurant_style(lines)
    items_shop = _parse_shop_style(lines)
    
    seen_names = set()
    for item in items_restaurant + items_shop:
        name_key = item["name"].lower().strip()[:20]
        if name_key not in seen_names and item["sum"] > 0:
            result["items"].append(item)
            seen_names.add(name_key)
    
    if result["total"] == 0 and result["items"]:
        result["total"] = sum(it["sum"] for it in result["items"])
    
    return result

def _parse_restaurant_style(lines: list) -> list:
    items = []
    item_pattern = re.compile(
        r'^\s*(\d+(?:[.\d]*\d+)?)\s+'
        r'([A-ZА-ЯЁ][A-ZА-ЯЁа-яё\s\-\(\)\/\&\.\"\'@]{5,})'
        r'(\d+[.,]\d{0,2})\s+'
        r'(\d+[.,]\d{2,})'
    )
    skip_keywords = ['ВСЕГО', 'ИТОГО', 'СКИДКА', 'БЛЮДО', 'КОЛ-ВО', 'СУММА', 'ЧЕК', 'ОТКРЫТ', 'ЗАКРЫТ', 'КАССИР', 'ОФИЦИАНТ', 'СТОЛ', 'ГОСТЕЙ', 'РЕСТОРАН', 'ОПЛАТА', 'НАЛИЧН', 'КАРТ', 'НДС', 'ЦЕНА']
    
    for line in lines:
        line = line.strip()
        if not line: continue
        line_up = line.upper()
        if any(kw in line_up for kw in skip_keywords): continue
        if re.match(r'^\d{10,}', line): continue
        if not re.search(r'[A-ZА-ЯЁ]', line_up): continue
        
        m = item_pattern.match(line)
        if m:
            name_raw = m.group(2).strip()
            qty = _clean_number(m.group(3))
            total = _clean_number(m.group(4))
            
            if qty and total and qty > 0 and total > 10:
                name = re.sub(r'\s+', ' ', name_raw).strip()
                name = re.sub(r'[\s\~\(\)\+\-\!\@\#\$\%\^\&\*\=\[\]\{\}\;\:\'\"\<\>\?\/\|]+$', '', name).strip()
                if len(name) >= 3:
                    items.append({"name": name, "qty": qty, "price": round(total / qty, 2), "sum": round(total, 2)})
    return items

def _parse_shop_style(lines: list) -> list:
    items = []
    price_pattern = re.compile(r'^(\d+[.,]\d{2})\s+(?:Ж?\d+[.,]?\d*)\s*(?:шт|кг|л|г|мл|уп)?\s*(?:=|@)?\s*(\d+[.,]\d{2})')
    simple_pattern = re.compile(r'^(\d+[.,]\d{0,2})\s+(\d+[.,]\d{2})\s*$')
    skip_keywords = ['КАССОВЫЙ', 'ЧЕК', 'ОНЛАЙН', 'КАССА', 'МЕСТО РАСЧЕТОВ', 'ИТОГО', 'ВСЕГО', 'НДС', 'СУММА', 'КОЛ-ВО', 'ЦЕНА', 'ОПЛАТА', 'НАЛИЧНЫМИ', 'КАРТОЙ', 'СДАЧА', 'СПАСИБО', 'МАГАЗИН', 'ТОРГОВЛЯ', 'НЕ ОБЛАГАЕТСЯ']
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        line_up = line.upper()
        if any(kw in line_up for kw in skip_keywords):
            i += 1
            continue
        
        m_price = price_pattern.match(line)
        m_simple = simple_pattern.match(line)
        
        if m_price:
            price = _clean_number(m_price.group(1))
            total = _clean_number(m_price.group(2))
            qty_match = re.search(r'Ж?(\d+[.,]?\d*)', line)
            qty = _clean_number(qty_match.group(1)) if qty_match else 1.0
            if qty is None or qty <= 0: qty = 1.0
            
            name_lines = []
            j = i - 1
            while j >= 0 and len(name_lines) < 3:
                prev_line = lines[j].strip()
                if not prev_line or len(prev_line) < 3 or re.match(r'^\d+[.,]?\d*\s+\d+[.,]?\d*$', prev_line):
                    break
                if any(kw in prev_line.upper() for kw in skip_keywords):
                    break
                name_lines.insert(0, prev_line)
                j -= 1
            
            if name_lines:
                name = re.sub(r'["\'@]', '', ' '.join(name_lines)).strip()
                if len(name) >= 5 and price and total:
                    items.append({"name": name, "qty": round(qty, 2), "price": round(price, 2), "sum": round(total, 2)})
        elif m_simple:
            qty = _clean_number(m_simple.group(1))
            total = _clean_number(m_simple.group(2))
            if qty and total:
                name_lines = []
                j = i - 1
                while j >= 0 and len(name_lines) < 3:
                    prev_line = lines[j].strip()
                    if not prev_line or len(prev_line) < 3 or re.match(r'^\d+[.,]?\d*\s+\d+[.,]?\d*$', prev_line):
                        break
                    if any(kw in prev_line.upper() for kw in skip_keywords):
                        break
                    name_lines.insert(0, prev_line)
                    j -= 1
                if name_lines:
                    name = re.sub(r'["\'@]', '', ' '.join(name_lines)).strip()
                    if len(name) >= 5:
                        items.append({"name": name, "qty": round(qty, 2), "price": round(total / qty, 2), "sum": round(total, 2)})
        i += 1
    return items