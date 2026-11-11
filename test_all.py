# test_v13.py — тестирование v1.3: второе поле «Чей расход», деление пополам
import os, sys, sqlite3, tempfile, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
PASS, FAIL = [], []

def check(name, fn):
    try:
        fn(); PASS.append(name); print(f"  ✅ {name}")
    except Exception as e:
        FAIL.append((name, e)); print(f"  ❌ {name}: {e}"); traceback.print_exc(limit=1)

import database as db
from expense_utils import split_item_amount, allocate_by_name
import ocr_service as ocr

mk = lambda s, p1, p2: {"sum": s, "expense_payer_id": p1, "expense_payer_id_2": p2,
                        "expense_payer_name": "Леша" if p1 else None,
                        "expense_payer_name_2": "Катя" if p2 else None}

print("== 1. Деление пополам ==")
check("оба поля -> пополам", lambda: (_ for _ in ()).throw(AssertionError())
      if split_item_amount(mk(100.0, 1, 2)) != [(1, 50.0), (2, 50.0)] else None)
def t_kop():
    parts = split_item_amount(mk(98.69, 1, 2))
    assert abs(sum(a for _, a in parts) - 98.69) < 0.005, parts
check("копейки не теряются (98.69)", t_kop)
check("один плательщик -> вся сумма", lambda: (_ for _ in ()).throw(AssertionError())
      if split_item_amount(mk(100.0, 1, None)) != [(1, 100.0)] else None)
check("только 2-е поле -> вся сумма", lambda: (_ for _ in ()).throw(AssertionError())
      if split_item_amount(mk(100.0, None, 2)) != [(2, 100.0)] else None)
check("одинаковый в обоих -> один раз", lambda: (_ for _ in ()).throw(AssertionError())
      if split_item_amount(mk(100.0, 1, 1)) != [(1, 100.0)] else None)
check("никто не указан -> пусто", lambda: (_ for _ in ()).throw(AssertionError())
      if split_item_amount(mk(100.0, None, None)) != [] else None)

print("== 2. Миграция старой БД ==")
OLD = os.path.join(tempfile.gettempdir(), "v13_old.db")
def t_migrate():
    if os.path.exists(OLD): os.remove(OLD)
    c = sqlite3.connect(OLD)
    c.executescript("""
    CREATE TABLE payers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);
    CREATE TABLE companies (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, address TEXT);
    CREATE TABLE item_names (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE);
    CREATE TABLE receipts (id INTEGER PRIMARY KEY AUTOINCREMENT, row_number INTEGER, receipt_date TEXT,
      company_id INTEGER, total_amount REAL DEFAULT 0, in_process INTEGER DEFAULT 0,
      processed INTEGER DEFAULT 0, process_date TEXT, payer_id INTEGER);
    CREATE TABLE receipt_items (id INTEGER PRIMARY KEY AUTOINCREMENT, receipt_id INTEGER,
      item_number INTEGER, item_name_id INTEGER, quantity REAL DEFAULT 1, price REAL DEFAULT 0,
      sum REAL DEFAULT 0, expense_payer_id INTEGER);
    INSERT INTO payers(name) VALUES('Леша'),('Катя');
    INSERT INTO companies(name) VALUES('Глобус');
    INSERT INTO item_names(name) VALUES('ХЛЕБ');
    INSERT INTO receipts(row_number,receipt_date,company_id,total_amount,payer_id)
      VALUES(1,'2026-10-03',1,100.0,1);
    INSERT INTO receipt_items(receipt_id,item_number,item_name_id,quantity,price,sum,expense_payer_id)
      VALUES(1,1,1,1,100,100,1);
    """)
    c.commit(); c.close()
    db.DB_NAME = OLD
    db.init_db()
    cols = [r[1] for r in sqlite3.connect(OLD).execute("PRAGMA table_info(receipt_items)")]
    assert "expense_payer_id_2" in cols, cols
    it = db.get_items_for_receipt(1)[0]
    assert it["sum"] == 100.0 and it["expense_payer_name"] == "Леша"
    db.init_db()  # идемпотентность
check("колонка добавлена, данные целы, повторно не падает", t_migrate)

print("== 3. Расчёт оплат ==")
def t_calc():
    db.update("receipt_items", 1, {"expense_payer_id_2": 2})
    nid = db.insert("item_names", {"name": "МОЛОКО"})
    db.insert("receipt_items", {"receipt_id": 1, "item_number": 2, "item_name_id": nid,
                                "quantity": 1, "price": 60.0, "sum": 60.0,
                                "expense_payer_id": 2, "expense_payer_id_2": None})
    d = {t["name"]: t for t in db.get_payer_totals({})}
    assert d["Леша"]["consumed"] == 50.0 and d["Катя"]["consumed"] == 110.0, d
    assert d["Леша"]["paid"] == 160.0 and d["Катя"]["balance"] == -110.0, d
    debts = db.get_debts({})
    assert debts == [{"debtor": "Катя", "creditor": "Леша", "amount": 110.0}], debts
check("пополам + долги (Катя -> Леша 110)", t_calc)

print("== 4. Excel чека ==")
def t_excel():
    from openpyxl import load_workbook
    import receipt_excel
    rec = dict(db.fetch_all("receipts")[0]); rec["company_name"] = "Глобус"; rec["payer_name"] = "Леша"
    p = os.path.join(tempfile.gettempdir(), "v13_chk.xlsx")
    receipt_excel.export_receipt(p, rec, db.get_items_for_receipt(1))
    ws = load_workbook(p).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    h = next(i for i, r in enumerate(rows) if r[0] == "№")
    assert rows[h][5] == "Чей расход" and rows[h][6] == "Чей расход 2", rows[h]
    assert ws["B1"].value == "03-10-2026", ws["B1"].value
    assert any(r[0] == "Катя" and r[1] == 110.0 for r in rows), rows
check("7 колонок + дата дд-мм-гггг + распределение", t_excel)

print("== 5. Регрессия RPAIR (нужен патч) ==")
def t_rpair():
    r = ocr.parse_receipt("14.1 ХАРЕНАЯ ЛАПША С\nОВОЩАМИ В СОЕВОМ СОУСЕ\n1.00   587.00\nВсего:\nИТОГО 587.00")
    assert len(r["items"]) == 1 and r["items"][0]["sum"] == 587.0, r["items"]
check("номер позиции 14.1 не создаёт ложную позицию", t_rpair)

print("== 6. GUI (offscreen) ==")
KEEP = []          # держим ссылки, иначе PyQt удалит C++-объекты
try:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from PyQt5.QtCore import Qt as _Qt
    app = QApplication.instance() or QApplication(sys.argv)
    for n in ("information", "warning", "critical"):
        setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)

    def t_gui():
        from ui_main_window import MainWindow
        w = MainWindow(); KEEP.append(w)
        assert w.tbl.columnCount() == 8 and w.sub.columnCount() == 7
        assert w.sub.horizontalHeaderItem(6).text() == "Чей расход 2"
        w.tbl.setCurrentCell(0, 0); w._load_sub(1)
        assert w.sub.cellWidget(0, 5).currentText() == "Леша"
        assert w.sub.cellWidget(0, 6).currentText() == "Катя"
        assert w.tbl.item(0, 1).text() == "03-10-2026"
        assert "Катя: 110.00" in w.lbl_split.text(), w.lbl_split.text()
        for col in range(8):
            w.sort_col = col; w.sort_asc = True; w.refresh(); w.sort_asc = False; w.refresh()
    check("MainWindow: 8/7 колонок, 2-е комбо, метка деления, сортировка", t_gui)

    def t_dlg():
        from ui_calculation_dialog import CalculationDialog
        from ui_scan_dialog import ScanDialog
        d = CalculationDialog(None); KEEP.append(d)
        assert any(t["name"] == "Катя" and t["consumed"] == 110.0 for t in d.totals), d.totals
        assert d.debts and d.debts[0]["amount"] == 110.0, d.debts
        s = ScanDialog(None); KEEP.append(s)
        assert s.tbl.columnCount() == 7
    check("CalcDialog итоги/долги + ScanDialog 7 колонок", t_dlg)

    def t_align():
        s = KEEP[-1]
        s.add_item()
        cb = s.tbl.cellWidget(0, 1)
        assert cb.lineEdit().alignment() & _Qt.AlignLeft, cb.lineEdit().alignment()
        assert cb.lineEdit().cursorPosition() == 0, cb.lineEdit().cursorPosition()
        long_name = "ОЧЕНЬ ДЛИННОЕ НАИМЕНОВАНИЕ ТОВАРА ДЛЯ ПРОВЕРКИ ПРОКРУТКИ"
        cb.setEditText(long_name); cb.lineEdit().setCursorPosition(0)
        assert cb.lineEdit().cursorPosition() == 0
    check("Наименование: выравнивание слева, курсор в начале", t_align)
except Exception as e:
    print(f"  ⏭️  GUI пропущен: {e}")
    
print("\n===== ИТОГ =====")
print(f"Пройдено: {len(PASS)}   Провалено: {len(FAIL)}")
for n, e in FAIL:
    print(f"  ❌ {n}: {e}")
sys.exit(1 if FAIL else 0)