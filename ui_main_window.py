# ui_main_window.py
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                             QDateEdit, QComboBox, QCheckBox, QHeaderView,
                             QMessageBox, QAbstractItemView, QFileDialog)
from PyQt5.QtCore import Qt, QTimer, QDate
from config import APP_VERSION, APP_DATE, APP_TITLE
import database as db
import date_utils
from filters import build_filters
from ui_receipt_dialog import ReceiptDialog
from ui_companies_dialog import CompaniesDialog
from ui_items_dialog import ItemsDialog
from ui_payers_dialog import PayersDialog
from ui_scan_dialog import ScanDialog
from ui_calculation_dialog import CalculationDialog
import receipt_excel
import logging

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        logger.info("Создание главного окна")
        self.setWindowTitle(APP_TITLE)
        self.resize(1300, 750)
        self.sort_col = None
        self.sort_asc = True
        self._build_ui()
        self._tick_clock()
        QTimer.singleShot(1000, self._tick_clock)
        self.refresh()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)

        top = QHBoxLayout()
        self.lbl_version = QLabel(f"v{APP_VERSION} от {APP_DATE}")
        self.lbl_title = QLabel(f"<b>{APP_TITLE}</b>")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_clock = QLabel()
        top.addWidget(self.lbl_version); top.addStretch()
        top.addWidget(self.lbl_title); top.addStretch()
        top.addWidget(self.lbl_clock)
        lay.addLayout(top)

        filt = QHBoxLayout()
        filt.addWidget(QLabel("С:"))
        self.f_date_from = QDateEdit(); self.f_date_from.setCalendarPopup(True)
        self.f_date_from.setDisplayFormat(date_utils.QT_DISPLAY)
        self.f_date_from.setDate(QDate(2000, 1, 1)); self.f_date_from.setMinimumDate(QDate(2000, 1, 1))
        filt.addWidget(self.f_date_from)
        filt.addWidget(QLabel("По:"))
        self.f_date_to = QDateEdit(); self.f_date_to.setCalendarPopup(True)
        self.f_date_to.setDisplayFormat(date_utils.QT_DISPLAY)
        self.f_date_to.setDate(QDate(2099, 12, 31)); self.f_date_to.setMaximumDate(QDate(2099, 12, 31))
        filt.addWidget(self.f_date_to)
        self.f_in = QCheckBox("В обработку"); self.f_in.stateChanged.connect(self.refresh)
        filt.addWidget(self.f_in)
        self.f_proc = QCheckBox("Обработан"); self.f_proc.stateChanged.connect(self.refresh)
        filt.addWidget(self.f_proc)
        filt.addWidget(QLabel("Компания:"))
        self.f_company = QComboBox(); self.f_company.addItem("— все —", 0)
        for c in db.fetch_all("companies"):
            self.f_company.addItem(c["name"], c["id"])
        self.f_company.currentIndexChanged.connect(self.refresh)
        filt.addWidget(self.f_company)
        lay.addLayout(filt)

        btns = QHBoxLayout()
        buttons = [
            ("Создать новый чек", self.new_receipt),
            ("Удалить чек", self.delete_receipt),
            ("База компаний", self.open_companies),
            ("База наименований", self.open_items),
            ("База плательщиков", self.open_payers),
            ("Сканировать чек", self.scan_receipt),
            ("Рассчитать оплаты", self.calc_payments),
            ("В файл excel", self.export_excel),
        ]
        for text, fn in buttons:
            b = QPushButton(text); b.clicked.connect(fn); btns.addWidget(b)
        lay.addLayout(btns)

        self.tbl = QTableWidget(0, 8)
        self.tbl.setHorizontalHeaderLabels([
            "Номер строки", "Дата чека", "Компания", "Сумма чека",
            "В обработку", "Обработан", "Дата обработки", "Кто платил"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.horizontalHeader().sectionClicked.connect(self._on_sort)
        self.tbl.itemChanged.connect(self._on_item_changed)
        self.tbl.currentCellChanged.connect(self._on_current_changed)
        lay.addWidget(self.tbl)

        self.sub = QTableWidget(0, 7)
        self.sub.setHorizontalHeaderLabels([
            "Номер", "Наименование", "Кол-во", "Цена", "Сумма",
            "Чей расход", "Чей расход 2"])
        self.sub.horizontalHeaderItem(1).setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)      
        self.sub.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sub.itemChanged.connect(self._on_sub_changed)
        lay.addWidget(self.sub)

        self.lbl_total = QLabel("Итого: 0.00 ₽")
        self.lbl_total.setAlignment(Qt.AlignRight)
        lay.addWidget(self.lbl_total)

        self.lbl_split = QLabel("")
        self.lbl_split.setAlignment(Qt.AlignRight)
        self.lbl_split.setStyleSheet("color: #555;")
        lay.addWidget(self.lbl_split)

    def _tick_clock(self):
        from PyQt5.QtCore import QDateTime
        self.lbl_clock.setText(QDateTime.currentDateTime().toString("dd-MM-yyyy HH:mm:ss"))
        QTimer.singleShot(1000, self._tick_clock)

    # ---------- выпадающие списки ----------
    def _company_combo(self, current_id, on_change):
        cb = QComboBox(); cb.addItem("— не выбрана —", None)
        for c in db.fetch_all("companies"):
            cb.addItem(c["name"], c["id"])
        idx = cb.findData(current_id); cb.setCurrentIndex(idx if idx >= 0 else 0)
        cb.currentIndexChanged.connect(lambda _=None, w=cb: on_change(w))
        return cb

    def _payer_combo(self, current_id, on_change, none_label="— не выбран —"):
        cb = QComboBox(); cb.addItem(none_label, None)
        for p in db.fetch_all("payers"):
            cb.addItem(p["name"], p["id"])
        idx = cb.findData(current_id); cb.setCurrentIndex(idx if idx >= 0 else 0)
        cb.currentIndexChanged.connect(lambda _=None, w=cb: on_change(w))
        return cb

    def _name_combo(self, current_name, on_change):
        cb = QComboBox(); cb.setEditable(True)
        cb.addItem(current_name or "")
        for n in db.fetch_all("item_names"):
            if n["name"] != current_name:
                cb.addItem(n["name"])
        cb.setEditText(current_name or "")
        le = cb.lineEdit()
        le.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        le.setCursorPosition(0)

        def pick(_=None, w=cb):
            w.lineEdit().setCursorPosition(0)
            on_change(w)

        cb.currentIndexChanged.connect(pick)
        le.editingFinished.connect(lambda w=cb: on_change(w))
        return cb
    
    # ---------- обновление ----------
    def refresh(self):
        logger.debug("Обновление таблицы чеков")
        self._refresh_companies_combo()
        date_from = self.f_date_from.date(); date_to = self.f_date_to.date()
        f = build_filters(
            date_from.toString(date_utils.QT_ISO) if date_from > QDate(2000, 1, 1) else None,
            date_to.toString(date_utils.QT_ISO) if date_to < QDate(2099, 12, 31) else None,
            1 if self.f_in.isChecked() else None,
            1 if self.f_proc.isChecked() else None,
            self.f_company.currentData(),
        )
        try:
            rows = db.get_receipts_filtered(f)
        except Exception as e:
            logger.exception(f"Ошибка получения записей: {e}"); rows = []

        if self.sort_col is not None:
            keys = {0: "row_number", 1: "receipt_date", 2: "company_name", 3: "total_amount",
                    4: "in_process", 5: "processed", 6: "process_date", 7: "payer_name"}
            k = keys.get(self.sort_col)
            if k:
                numeric = k in ("row_number", "total_amount", "in_process", "processed")
                if numeric:
                    rows = sorted(rows, key=lambda r: (r.get(k) is None, r.get(k) or 0),
                                  reverse=not self.sort_asc)
                else:
                    rows = sorted(rows, key=lambda r: (r.get(k) is None, str(r.get(k) or "")),
                                  reverse=not self.sort_asc)

        self.tbl.blockSignals(True)
        self.tbl.setRowCount(0)
        for r in rows:
            i = self.tbl.rowCount(); self.tbl.insertRow(i)
            self.tbl.setItem(i, 0, QTableWidgetItem(str(r["row_number"])))
            self.tbl.setItem(i, 1, QTableWidgetItem(date_utils.to_display(r["receipt_date"])))
            self.tbl.setItem(i, 3, QTableWidgetItem(f"{r['total_amount']:.2f}"))
            chk1 = QTableWidgetItem(); chk1.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk1.setCheckState(Qt.Checked if r["in_process"] else Qt.Unchecked)
            self.tbl.setItem(i, 4, chk1)
            chk2 = QTableWidgetItem(); chk2.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk2.setCheckState(Qt.Checked if r["processed"] else Qt.Unchecked)
            self.tbl.setItem(i, 5, chk2)
            self.tbl.setItem(i, 6, QTableWidgetItem(date_utils.to_display(r.get("process_date"))))
            self.tbl.item(i, 0).setData(Qt.UserRole, r["id"])

            rid = r["id"]
            self.tbl.setCellWidget(i, 2, self._company_combo(
                r["company_id"], lambda w, rid=rid: self._set_company(rid, w)))
            self.tbl.setCellWidget(i, 7, self._payer_combo(
                r["payer_id"], lambda w, rid=rid: self._set_payer(rid, w)))
        self.tbl.blockSignals(False)

    def _set_company(self, rid, w):
        try:
            db.update("receipts", rid, {"company_id": w.currentData()})
        except Exception as e:
            logger.error(f"Ошибка смены компании: {e}")

    def _set_payer(self, rid, w):
        try:
            db.update("receipts", rid, {"payer_id": w.currentData()})
        except Exception as e:
            logger.error(f"Ошибка смены плательщика: {e}")

    def _refresh_companies_combo(self):
        cur = self.f_company.currentData()
        self.f_company.blockSignals(True)
        self.f_company.clear(); self.f_company.addItem("— все —", 0)
        for c in db.fetch_all("companies"):
            self.f_company.addItem(c["name"], c["id"])
        idx = self.f_company.findData(cur)
        if idx >= 0:
            self.f_company.setCurrentIndex(idx)
        self.f_company.blockSignals(False)

    def _on_sort(self, col):
        if col == self.sort_col:
            self.sort_asc = not self.sort_asc
        else:
            self.sort_col = col; self.sort_asc = True
        self.refresh()

    def _current_receipt_id(self):
        row = self.tbl.currentRow()
        if row < 0:
            return None
        item = self.tbl.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _on_item_changed(self, item):
        rid = self._current_receipt_id()
        if not rid:
            return
        col = item.column(); data = {}
        try:
            if col == 1:
                data["receipt_date"] = date_utils.to_iso(item.text())
            elif col == 4:
                data["in_process"] = 1 if item.checkState() == Qt.Checked else 0
            elif col == 5:
                data["processed"] = 1 if item.checkState() == Qt.Checked else 0
            elif col == 6:
                data["process_date"] = date_utils.to_iso(item.text())
            if data:
                db.update("receipts", rid, data)
                if col in (1, 6):
                    key = "receipt_date" if col == 1 else "process_date"
                    self.tbl.blockSignals(True)
                    item.setText(date_utils.to_display(data[key]))
                    self.tbl.blockSignals(False)
        except Exception as e:
            logger.error(f"Ошибка сохранения изменений чека {rid}: {e}")

    def _on_current_changed(self, r, c, pr, pc):
        self._load_sub(self._current_receipt_id())

    def _load_sub(self, rid):
        from expense_utils import allocate_by_name
        self.sub.blockSignals(True)
        self.sub.setRowCount(0)
        total = 0.0
        items = []
        if rid:
            try:
                items = db.get_items_for_receipt(rid)
                for it in items:
                    i = self.sub.rowCount(); self.sub.insertRow(i)
                    self.sub.setItem(i, 0, QTableWidgetItem(str(it["item_number"])))
                    self.sub.setItem(i, 2, QTableWidgetItem(str(it["quantity"])))
                    self.sub.setItem(i, 3, QTableWidgetItem(str(it["price"])))
                    self.sub.setItem(i, 4, QTableWidgetItem(str(it["sum"])))
                    self.sub.item(i, 0).setData(Qt.UserRole, it["id"])
                    total += it["sum"] or 0
                    iid = it["id"]
                    self.sub.setCellWidget(i, 1, self._name_combo(
                        it.get("item_name"), lambda w, iid=iid: self._set_item_name(iid, w)))
                    self.sub.setCellWidget(i, 5, self._payer_combo(
                        it.get("expense_payer_id"), lambda w, iid=iid: self._set_item_payer(iid, w), "—"))
                    self.sub.setCellWidget(i, 6, self._payer_combo(
                        it.get("expense_payer_id_2"), lambda w, iid=iid: self._set_item_payer_2(iid, w), "—"))
            except Exception as e:
                logger.error(f"Ошибка загрузки позиций чека {rid}: {e}")
        i = self.sub.rowCount(); self.sub.insertRow(i)
        self.sub.setItem(i, 0, QTableWidgetItem("Итого"))
        self.sub.setItem(i, 4, QTableWidgetItem(f"{total:.2f}"))
        self.sub.blockSignals(False)
        self.lbl_total.setText(f"Итого: {total:.2f} ₽")

        if items:
            parts = [f"{n}: {a:.2f}" for n, a in allocate_by_name(items)]
            self.lbl_split.setText("Расход (оба поля — пополам): " + " | ".join(parts))
        else:
            self.lbl_split.setText("")

        if rid:
            try:
                db.update("receipts", rid, {"total_amount": total})
                row = self.tbl.currentRow()
                if row >= 0:
                    self.tbl.blockSignals(True)
                    self.tbl.setItem(row, 3, QTableWidgetItem(f"{total:.2f}"))
                    self.tbl.blockSignals(False)
            except Exception as e:
                logger.error(f"Ошибка обновления суммы чека {rid}: {e}")

    def _set_item_name(self, iid, w):
        text = w.currentText().strip()
        if not text:
            return
        try:
            names = db.fetch_all("item_names")
            n = next((x for x in names if x["name"] == text), None)
            nid = n["id"] if n else db.insert("item_names", {"name": text})
            db.update("receipt_items", iid, {"item_name_id": nid})
        except Exception as e:
            logger.error(f"Ошибка смены наименования {iid}: {e}")

    def _set_item_payer(self, iid, w):
        try:
            db.update("receipt_items", iid, {"expense_payer_id": w.currentData()})
            self._load_sub(self._current_receipt_id())
        except Exception as e:
            logger.error(f"Ошибка смены расхода {iid}: {e}")

    def _set_item_payer_2(self, iid, w):
        try:
            db.update("receipt_items", iid, {"expense_payer_id_2": w.currentData()})
            self._load_sub(self._current_receipt_id())
        except Exception as e:
            logger.error(f"Ошибка смены расхода 2 {iid}: {e}")

    def _on_sub_changed(self, item):
        rid = self._current_receipt_id()
        if not rid:
            return
        row = item.row(); col = item.column()
        if col not in (2, 3):
            return
        iid = self.sub.item(row, 0).data(Qt.UserRole)
        if not iid:
            return
        try:
            q = float(self.sub.item(row, 2).text().replace(",", "."))
            p = float(self.sub.item(row, 3).text().replace(",", "."))
            s = q * p
            self.sub.blockSignals(True)
            self.sub.setItem(row, 4, QTableWidgetItem(f"{s:.2f}"))
            self.sub.blockSignals(False)
            db.update("receipt_items", iid, {"quantity": q, "price": p, "sum": s})
            self._load_sub(rid)
        except (ValueError, AttributeError) as e:
            logger.error(f"Ошибка сохранения позиции {iid}: {e}")

    # ---------- кнопки ----------
    def new_receipt(self):
        try:
            if ReceiptDialog(self).exec_() == ReceiptDialog.Accepted:
                self.refresh()
        except Exception as e:
            logger.exception(f"Ошибка создания чека: {e}"); QMessageBox.critical(self, "Ошибка", str(e))

    def delete_receipt(self):
        rid = self._current_receipt_id()
        if not rid:
            QMessageBox.warning(self, "Внимание", "Выберите чек для удаления."); return
        if QMessageBox.question(self, "Удалить", "Удалить выбранный чек?") == QMessageBox.Yes:
            try:
                db.delete_receipt_full(rid); self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))

    def open_companies(self):
        try:
            CompaniesDialog(self).exec_(); self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def open_items(self):
        try:
            ItemsDialog(self).exec_(); self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def open_payers(self):
        try:
            PayersDialog(self).exec_(); self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def scan_receipt(self):
        try:
            if ScanDialog(self).exec_() == ScanDialog.Accepted:
                self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def calc_payments(self):
        try:
            CalculationDialog(self).exec_(); self.refresh()
        except Exception as e:
            logger.exception(f"Ошибка расчёта оплат: {e}")
            QMessageBox.critical(self, "Ошибка", str(e))

    def export_excel(self):
        rid = self._current_receipt_id()
        if not rid:
            QMessageBox.warning(self, "Внимание", "Выберите чек для выгрузки в Excel."); return
        try:
            rec = next((r for r in db.fetch_all("receipts") if r["id"] == rid), None)
            if not rec:
                QMessageBox.warning(self, "Внимание", "Чек не найден."); return
            comp = next((c["name"] for c in db.fetch_all("companies") if c["id"] == rec["company_id"]), "")
            payer = next((p["name"] for p in db.fetch_all("payers") if p["id"] == rec["payer_id"]), "")
            rec = dict(rec); rec["company_name"] = comp; rec["payer_name"] = payer
            items = db.get_items_for_receipt(rid)
            d = date_utils.to_display(rec.get("receipt_date")) or "без_даты"
            default = f"чек_{rec['row_number']}_{d}.xlsx"
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить чек в Excel", default, "Excel (*.xlsx)")
            if not path:
                return
            receipt_excel.export_receipt(path, rec, items)
            QMessageBox.information(self, "Готово", f"Чек выгружен в:\n{path}")
        except Exception as e:
            logger.exception(f"Ошибка выгрузки Excel: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось выгрузить чек:\n{e}")