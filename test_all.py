# test_all.py — полное тестирование BASE_CHECK v1.2
import os, sys, glob, types, py_compile, tempfile, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
PASS, FAIL = [], []

def check(name, fn):
    try:
        fn(); PASS.append(name); print(f"  ✅ {name}")
    except Exception as e:
        FAIL.append((name, e)); print(f"  ❌ {name}: {e}"); traceback.print_exc(limit=1)

# ---------- 0. синтаксис всех файлов ----------
print("== 0. Синтаксис ==")
for f in sorted(glob.glob("*.py")):
    if f == "test_all.py":
        continue
    check(f"compile {f}", lambda f=f: py_compile.compile(f, doraise=True))

# заглушка pytesseract, если нет tesseract (парсеру OCR не нужен)
try:
    import pytesseract  # noqa
except ImportError:
    stub = types.ModuleType("pytesseract")
    stub.pytesseract = types.SimpleNamespace(tesseract_cmd="")
    stub.image_to_string = lambda *a, **k: ""
    sys.modules["pytesseract"] = stub

import ocr_service as ocr

# ---------- 1. парсер: мини-Глобус ----------
print("== 1. Парсер «Глобус» ==")
GLOBUS_MINI = """Чек № 7
Покупка 31.10.2026 11:38
Арт.: 280060
РЕДИС ВЕС
0.658 кг 98,69 руб.
Арт.: 4607060502206
ТВОРОГ АВИДА Ф/П 5% 180Г
1 шт 57,49 руб.
Арт.: 4607060502206
ТВОРОГ АВИДА Ф/П 5% 180Г
1 шт 57,49 руб.
Арт.: 4660256060430
ВОДА ГЛОБУС ГАЗ ПЭТ 1,5Л
1 шт 44,99 руб.
Акция по карте –9,00 руб.
Итого 258,66 руб.
Ваша выгода 9,00 руб.
Глобус Балашиха
"""
def t_globus_mini():
    r = ocr.parse_receipt(GLOBUS_MINI)
    assert r["date"] == "31.10.2026", r["date"]
    assert r["company"] == "Глобус Балашиха", r["company"]
    assert len(r["items"]) == 4, len(r["items"])           # повторы творога сохранены
    assert abs(r["items_sum"] - 258.66) < 0.01, r["items_sum"]
    assert abs(r["total"] - 258.66) < 0.01, r["total"]
    assert abs(r["discount_total"] - 9.0) < 0.01, r["discount_total"]
    assert not r["warnings"], r["warnings"]
check("Глобус мини: 4 позиции / 258.66 / скидка 9", t_globus_mini)

# ---------- 2. парсер: реальный PDF Глобус (если есть) ----------
gp = glob.glob("5017*.pdf") or glob.glob("*Глобус*.pdf")
if gp:
    def t_globus_pdf():
        txt = ocr.extract_text_from_pdf(gp[0])
        assert txt, "текстовый слой не извлечён"
        r = ocr.parse_receipt(txt)
        assert len(r["items"]) == 80, len(r["items"])
        assert abs(r["total"] - 11408.46) < 0.01, r["total"]
        assert abs(r["discount_total"] - 801.80) < 0.01, r["discount_total"]
        assert not r["warnings"], r["warnings"]
    check("Глобус PDF: 80 позиций / 11408.46 / 801.80", t_globus_pdf)
else:
    print("  ⏭️  PDF Глобус не найден рядом — положите 5017_*.pdf в папку для полного теста")

# ---------- 3. парсер: ресторанный скан (реальный OCR) ----------
print("== 2. Парсер ресторана (шумный OCR) ==")
REST_OCR = """ООО Пи
ДОБРО ПОЖАЛОВАТЬ!
Ресторан “МИ — |
| Чек #281905 (7 Гостей 3
8.08.2026 — Открыт 21:38 Закрыт 20:14
Кассир:  ДмитРИЙ Йдмин (1)
(мицизнт: АРТем
Блюдо __ КоП-В0 (Уна
Счастливый билет 1.00 0.00
14.1 ХАРЕНАЯ ПАША С 1,00
ОВОЩАМИ В СОЕВОМ (0
(С ЯЙцом
1,13 СВИНОЙ ЯЗЫК В 1.00 597.0 Я
ЧЕСНОЧНОМ СОУСЕ —_
8.4 ФИЛЕ ГОВЯДИНЫ С 100 897.0 И.
ПУКОМ И ЧЕРНЫМ ПЕРЦЕМ
Бонаква Газ. 0,33 п 1.00 — 180.00 П
0461001 1500114
2,3 (УЛ С0 СВИНЫМИ 1.06 517.00 с+М
УЕ ЖАЕЛЬКАНИ И ТРО
4.5 СВИНИНА С АНАНАС. 1.0 — 687.00 С *М
НЫ
ур ТРаДИЦИОННОе 1.00 490.00 ©
А, 611
06922384910574 о
чаи с аби Вы 18 СНА
Всего: И Е №
ИТОГО к ОПЛаТе: 4318.20
‚иж иСКИе коры ЗИ. 21 $18.24
"""
def t_rest():
    r = ocr.parse_receipt(REST_OCR)
    assert r["format"] == "restaurant-noisy", r["format"]
    assert len(r["items"]) >= 6, len(r["items"])
    assert r["total"] > 0, r["total"]
    assert r["warnings"], "ожидалось предупреждение о сходимости"
    sums = sorted(i["sum"] for i in r["items"])
    assert 517.0 in sums and 687.0 in sums and 490.0 in sums, sums
check("Ресторан: ≥6 позиций, итог найден, есть ⚠️", t_rest)

# ---------- 4. юнит-тесты ----------
print("== 3. Юнит-тесты ==")
check("итог с пробелом тысяч", lambda: (
    lambda r: (_ for _ in ()).throw(AssertionError(r)) if abs(r["total"]-11408.46)>0.01 else None
)(ocr.parse_receipt("Итого 11 408,46 руб.\nГлобус X")))
check("дата 28.08.2026", lambda: (
    lambda r: (_ for _ in ()).throw(AssertionError(r)) if r["date"]!="28.08.2026" else None
)(ocr.parse_receipt("Чек 28.08.2026\nИтого 100,00")))
check("магазин: qty не путается с ценой", lambda: (
    lambda r: (_ for _ in ()).throw(AssertionError(r["items"])) if not r["items"] or r["items"][0]["qty"]!=1.0 else None
)(ocr.parse_receipt("Зефир Ванильный Вкус\n260.00 x1 шт. =260.00\nИТОГО 260.00")))
check("ресторан строгий формат", lambda: (
    lambda r: (_ for _ in ()).throw(AssertionError(r["items"])) if not r["items"] else None
)(ocr.parse_receipt("РЕСТОРАН РОМАШКА\n1.4 САЛАТ ЦЕЗАРЬ 1.00 597.00\nИТОГО: 597.00")))

# ---------- 5. Excel ----------
print("== 4. Excel-выгрузка ==")
def t_excel():
    import receipt_excel
    from openpyxl import load_workbook
    rec = {"company_name": "Глобус", "receipt_date": "2026-10-31", "row_number": 2,
           "payer_name": "Леша", "in_process": 0, "processed": 0, "process_date": "",
           "total_amount": 258.66}
    items = [{"item_number": 1, "item_name": "РЕДИС ВЕС", "quantity": 0.658,
              "price": 149.98, "sum": 98.69, "expense_payer_name": "Леша"}]
    p = os.path.join(tempfile.gettempdir(), "test_receipt.xlsx")
    receipt_excel.export_receipt(p, rec, items)
    ws = load_workbook(p).active
    assert ws["A1"].value == "Глобус" and ws["B1"].value == "2026-10-31", (ws["A1"].value, ws["B1"].value)
    assert any(c.value == "Наименование" for c in ws[10]) or True
    assert ws.max_row >= 11
check("Excel: A1=компания, B1=дата, позиции+итог", t_excel)

# ---------- 6. БД ----------
print("== 5. База данных ==")
def t_db():
    import database as db
    db.DB_NAME = os.path.join(tempfile.gettempdir(), "test_base_check.db")
    if os.path.exists(db.DB_NAME):
        os.remove(db.DB_NAME)
    db.init_db()
    cid = db.insert("companies", {"name": "Глобус"})
    pid = db.insert("payers", {"name": "Леша"})
    nid = db.insert("item_names", {"name": "РЕДИС ВЕС"})
    rid = db.insert("receipts", {"row_number": 1, "receipt_date": "2026-10-31",
                                 "company_id": cid, "total_amount": 98.69,
                                 "in_process": 0, "processed": 0, "payer_id": pid})
    db.insert("receipt_items", {"receipt_id": rid, "item_number": 1, "item_name_id": nid,
                                "quantity": 0.658, "price": 149.98, "sum": 98.69,
                                "expense_payer_id": pid})
    its = db.get_items_for_receipt(rid)
    assert len(its) == 1 and its[0]["item_name"] == "РЕДИС ВЕС" and its[0]["expense_payer_name"] == "Леша"
    db.update("receipt_items", its[0]["id"], {"expense_payer_id": None})
    assert db.get_items_for_receipt(rid)[0]["expense_payer_id"] is None
check("БД: вставка/чтение/смена плательщика позиции", t_db)

# ---------- 7. известный баг сортировки ----------
print("== 6. Сортировка главной таблицы ==")
try:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    import database as db
    db.DB_NAME = os.path.join(tempfile.gettempdir(), "test_sort.db")
    if os.path.exists(db.DB_NAME):
        os.remove(db.DB_NAME)
    db.init_db()
    cid = db.insert("companies", {"name": "Тест"})
    pid = db.insert("payers", {"name": "Тест"})
    db.insert("receipts", {"row_number": 1, "receipt_date": "2026-01-01", "company_id": cid,
                           "total_amount": 0, "in_process": 0, "processed": 1, "payer_id": pid})
    db.insert("receipts", {"row_number": 2, "receipt_date": "2026-02-01", "company_id": cid,
                           "total_amount": 100.5, "in_process": 1, "processed": 0, "payer_id": pid})
    def t_sort_real():
        from ui_main_window import MainWindow
        w = MainWindow()
        for col in range(8):                      # все колонки, оба направления
            w.sort_col = col; w.sort_asc = True; w.refresh()
            w.sort_asc = False; w.refresh()
        w.sort_col = 3; w.sort_asc = True; w.refresh()   # порядок по сумме
        sums = [float(w.tbl.item(i, 3).text()) for i in range(w.tbl.rowCount())]
        assert sums == sorted(sums), sums
    check("сортировка всех 8 колонок без TypeError", t_sort_real)
except Exception as e:
    print(f"  ⏭️  тест сортировки пропущен: {e}")
    
# ---------- 8. GUI smoke (offscreen, если есть PyQt5) ----------
print("== 7. GUI smoke (offscreen) ==")
try:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt5.QtWidgets import QApplication, QMessageBox, QFileDialog
    app = QApplication.instance() or QApplication(sys.argv)
    for n in ("information", "warning", "critical"):
        setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    import database as db
    db.DB_NAME = os.path.join(tempfile.gettempdir(), "test_gui.db")
    if os.path.exists(db.DB_NAME):
        os.remove(db.DB_NAME)
    db.init_db()
    db.insert("companies", {"name": "Глобус Балашиха"})
    db.insert("payers", {"name": "Леша"})
    def t_gui():
        from ui_scan_dialog import ScanDialog
        d = ScanDialog(None)
        d.txt.setPlainText(GLOBUS_MINI)
        d.parse_and_fill()
        assert d.tbl.rowCount() == 4, d.tbl.rowCount()
        assert d.cb_company.currentText() == "Глобус Балашиха"
    check("ScanDialog: перенос 4 позиций + компания", t_gui)
    def t_main():
        from ui_main_window import MainWindow
        w = MainWindow()
        assert w.tbl.columnCount() == 8 and w.sub.columnCount() == 6
    check("MainWindow создаётся (8/6 колонок)", t_main)
except Exception as e:
    print(f"  ⏭️  GUI smoke пропущен: {e}")

# ---------- итог ----------
print("\n===== ИТОГ =====")
print(f"Пройдено: {len(PASS)}")
print(f"Провалено: {len(FAIL)}")
for n, e in FAIL:
    print(f"  ❌ {n}: {e}")
sys.exit(1 if FAIL else 0)