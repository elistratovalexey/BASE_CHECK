# ocr_service.py
import re
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract

# Путь к tesseract (для Linux)
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"


def extract_text(image_path: str) -> str:
    """Распознаёт текст с улучшенной предобработкой."""
    img = Image.open(image_path)
    
    # Конвертация в grayscale
    img = img.convert('L')
    
    # Увеличение размера для лучшего распознавания
    img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    
    # Увеличение контрастности
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.5)
    
    # Увеличение резкости
    img = img.filter(ImageFilter.SHARPEN)
    
    # Бинаризация
    img = img.point(lambda x: 0 if x < 128 else 255, '1')
    
    # Распознавание с русским языком
    custom_config = r'--oem 3 --psm 6 -l rus'
    text = pytesseract.image_to_string(img, config=custom_config)
    
    return text


def _clean_number(s):
    """Очистка числа от OCR-мусора."""
    if not s:
        return None
    s = str(s).strip()
    
    # Типичные замены OCR-ошибок
    replacements = {
        "'": "7", "`": "7", "´": "7",
        "l": "1", "I": "1", "|": "1", "i": "1",
        "о": "0", "О": "0",
        "ш": "4", "Ш": "4",
        "з": "3", "З": "3",
        "у": "4", "У": "4", "y": "4",
        "с": "6", "С": "6", "c": "6",
        "г": "7", "Г": "7",
        "т": "7", "Т": "7",
        "р": "8", "Р": "8",
        "ь": "6", "Ь": "6",
        "б": "6", "Б": "6",
        "н": "4", "Н": "4",
        "к": "4", "К": "4",
        "м": "4", "М": "4",
        "х": "4", "Х": "4",
        "q": "0", "Q": "0",
        "g": "9", "G": "9",
        "e": "3", "E": "3",
        "a": "4", "A": "4",
        "S": "5", "s": "5",
        "B": "8", "b": "8",
        "~": "", "+": "",
    }
    
    for old, new in replacements.items():
        s = s.replace(old, new)
    
    # Удаляем всё кроме цифр, точек и запятых
    s = re.sub(r'[^\d.,]', '', s)
    s = s.replace(',', '.')
    
    # Если несколько точек, оставляем только последнюю
    if s.count('.') > 1:
        parts = s.split('.')
        s = ''.join(parts[:-1]) + '.' + parts[-1]
    
    try:
        return float(s)
    except:
        return None


def parse_receipt(text: str) -> dict:
    """
    Универсальный парсер чеков (ресторан + магазин).
    """
    result = {"date": "", "company": "", "total": 0.0, "items": []}
    lines = text.split('\n')
    
    # 1. Поиск даты
    for line in lines:
        m = re.search(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})', line)
        if m:
            day, month, year = m.groups()
            if len(year) == 2:
                year = '20' + year
            result["date"] = f"{day.zfill(2)}.{month.zfill(2)}.{year}"
            break
    
    # 2. Поиск компании/ресторана
    skip_keywords_company = ['ЧЕК', 'КАССОВЫЙ', 'ОНЛАЙН', 'КАССА', 'ТО/', 'ТО/']
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
    
    # 4. Поиск позиций - используем несколько методов
    items_restaurant = _parse_restaurant_style(lines)
    items_shop = _parse_shop_style(lines)
    
    # Объединяем результаты, убирая дубликаты
    seen_names = set()
    for item in items_restaurant + items_shop:
        name_key = item["name"].lower().strip()[:20]
        if name_key not in seen_names and item["sum"] > 0:
            result["items"].append(item)
            seen_names.add(name_key)
    
    # Если итого не найдено - считаем сумму
    if result["total"] == 0 and result["items"]:
        result["total"] = sum(it["sum"] for it in result["items"])
    
    return result


def _parse_restaurant_style(lines: list) -> list:
    """
    Парсинг ресторанного чека.
    Формат: "1.4 НАЗВАНИЕ БЛЮДА 1.00 597.00"
    """
    items = []
    
    # Паттерн для ресторанного чека
    item_pattern = re.compile(
        r'^\s*(\d+(?:[.\d]*\d+)?)\s+'  # номер позиции
        r'([A-ZА-ЯЁ][A-ZА-ЯЁа-яё\s\-\(\)\/\&\.\"\'@]{5,})'  # название
        r'(\d+[.,]\d{0,2})\s+'  # кол-во
        r'(\d+[.,]\d{2,})'  # сумма
    )
    
    skip_keywords = [
        'ВСЕГО', 'ИТОГО', 'СКИДКА', 'БЛЮДО', 'КОЛ-ВО', 'СУММА',
        'ЧЕК', 'ОТКРЫТ', 'ЗАКРЫТ', 'КАССИР', 'ОФИЦИАНТ',
        'СТОЛ', 'ГОСТЕЙ', 'РЕСТОРАН', 'ОПЛАТА', 'НАЛИЧН', 'КАРТ',
        'НДС', 'СУММА', 'ЦЕНА'
    ]
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        line_up = line.upper()
        
        # Пропускаем служебные строки
        if any(kw in line_up for kw in skip_keywords):
            continue
        if re.match(r'^\d{10,}', line):
            continue
        if not re.search(r'[A-ZА-ЯЁ]', line_up):
            continue
        
        m = item_pattern.match(line)
        if m:
            item_num = m.group(1)
            name_raw = m.group(2).strip()
            qty_raw = m.group(3).strip()
            sum_raw = m.group(4).strip()
            
            qty = _clean_number(qty_raw)
            total = _clean_number(sum_raw)
            
            if qty is not None and total is not None and qty > 0 and total > 10:
                # Очищаем название
                name = re.sub(r'\s+', ' ', name_raw).strip()
                name = re.sub(r'[\s\~\(\)\+\-\!\@\#\$\%\^\&\*\=\[\]\{\}\;\:\'\"\<\>\?\/\\\|]+$', '', name).strip()
                
                if len(name) >= 3:
                    price = total / qty
                    items.append({
                        "name": name,
                        "qty": qty,
                        "price": round(price, 2),
                        "sum": round(total, 2),
                    })
    
    return items


def _parse_shop_style(lines: list) -> list:
    """
    Парсинг магазинного чека.
    Формат: название на нескольких строках, затем "ЦЕНА КОЛ-ВО =СУММА"
    Пример:
    Зефир "ЗеФИРНОе куРа6ье_С0 Вкус
    Ом ВАНИЛИ С КОНФИТЮРОМ ВКУС "Абр С.
    ИКОС" 0,45 кг
    260.00 Ж1 шт. =260.00
    """
    items = []
    
    # Паттерн для строки с числами: "260.00 Ж1 шт. =260.00"
    price_pattern = re.compile(
        r'^(\d+[.,]\d{2})\s+'  # цена
        r'(?:Ж?\d+[.,]?\d*)\s*'  # количество (может быть с буквой Ж)
        r'(?:шт|кг|л|г|мл|уп)?\s*'  # единица измерения
        r'(?:=|@)?\s*'  # разделитель
        r'(\d+[.,]\d{2})'  # сумма
    )
    
    # Паттерн для альтернативного формата: "1.00 260.00"
    simple_pattern = re.compile(
        r'^(\d+[.,]\d{0,2})\s+(\d+[.,]\d{2})\s*$'
    )
    
    skip_keywords = [
        'КАССОВЫЙ', 'ЧЕК', 'ОНЛАЙН', 'КАССА', 'МЕСТО РАСЧЕТОВ',
        'ИТОГО', 'ВСЕГО', 'НДС', 'СУММА', 'КОЛ-ВО', 'ЦЕНА',
        'ОПЛАТА', 'НАЛИЧНЫМИ', 'КАРТОЙ', 'СДАЧА', 'СПАСИБО',
        'МАГАЗИН', 'ТОРГОВЛЯ', 'НЕ ОБЛАГАЕТСЯ'
    ]
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        line_up = line.upper()
        
        # Пропускаем служебные строки
        if any(kw in line_up for kw in skip_keywords):
            i += 1
            continue
        
        # Проверяем, есть ли в строке числа
        m_price = price_pattern.match(line)
        m_simple = simple_pattern.match(line)
        
        if m_price:
            # Нашли строку с ценой, количеством и суммой
            price = _clean_number(m_price.group(1))
            total = _clean_number(m_price.group(3))
            qty = 1.0  # По умолчанию
            
            # Пытаемся найти количество
            qty_match = re.search(r'Ж?(\d+[.,]?\d*)', line)
            if qty_match:
                qty = _clean_number(qty_match.group(1))
                if qty is None or qty <= 0:
                    qty = 1.0
            
            # Собираем название из предыдущих строк
            name_lines = []
            j = i - 1
            while j >= 0 and len(name_lines) < 3:  # Берём максимум 3 предыдущие строки
                prev_line = lines[j].strip()
                if not prev_line:
                    break
                prev_up = prev_line.upper()
                # Останавливаемся, если нашли ключевые слова или слишком короткую строку
                if any(kw in prev_up for kw in skip_keywords):
                    break
                if len(prev_line) < 3:
                    break
                # Если строка содержит только числа - это другая позиция
                if re.match(r'^\d+[.,]?\d*\s+\d+[.,]?\d*$', prev_line):
                    break
                name_lines.insert(0, prev_line)
                j -= 1
            
            if name_lines:
                name = ' '.join(name_lines)
                name = re.sub(r'\s+', ' ', name).strip()
                name = re.sub(r'["\'@]', '', name).strip()
                
                if len(name) >= 5 and price and total:
                    items.append({
                        "name": name,
                        "qty": round(qty, 2),
                        "price": round(price, 2),
                        "sum": round(total, 2),
                    })
        
        elif m_simple:
            # Простой формат: "1.00 260.00"
            qty = _clean_number(m_simple.group(1))
            total = _clean_number(m_simple.group(2))
            
            if qty and total:
                # Собираем название
                name_lines = []
                j = i - 1
                while j >= 0 and len(name_lines) < 3:
                    prev_line = lines[j].strip()
                    if not prev_line:
                        break
                    prev_up = prev_line.upper()
                    if any(kw in prev_up for kw in skip_keywords):
                        break
                    if len(prev_line) < 3:
                        break
                    if re.match(r'^\d+[.,]?\d*\s+\d+[.,]?\d*$', prev_line):
                        break
                    name_lines.insert(0, prev_line)
                    j -= 1
                
                if name_lines:
                    name = ' '.join(name_lines)
                    name = re.sub(r'\s+', ' ', name).strip()
                    name = re.sub(r'["\'@]', '', name).strip()
                    
                    if len(name) >= 5:
                        price = total / qty if qty > 0 else 0
                        items.append({
                            "name": name,
                            "qty": round(qty, 2),
                            "price": round(price, 2),
                            "sum": round(total, 2),
                        })
        
        i += 1
    
    return items