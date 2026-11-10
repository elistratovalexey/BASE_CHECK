# ui_calculation_dialog.py
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QPushButton, QFileDialog,
                             QMessageBox, QHeaderView)
from PyQt5.QtCore import QDate
import database as db
from excel_service import create_report

class CalculationDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Расчёт оплат")
        self.resize(600, 400)
        self._build()
        self.calculate()

    def _build(self):
        lay = QVBoxLayout(self)
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["Кто платил", "Кому должен", "Сумма"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.tbl)
        btns = QHBoxLayout()
        b_apply = QPushButton("Применить (снять 'В обработку')"); b_apply.clicked.connect(self.apply)
        b_report = QPushButton("Создать отчёт"); b_report.clicked.connect(self.make_report)
        b_close = QPushButton("Закрыть"); b_close.clicked.connect(self.close)
        btns.addWidget(b_apply); btns.addWidget(b_report); btns.addWidget(b_close)
        lay.addLayout(btns)

    def _get_marked(self):
        return db.get_receipts_filtered({"in_process": 1})

    def calculate(self):
        receipts = self._get_marked()
        payers = db.fetch_all("payers")
        items_by = {r["id"]: db.get_items_for_receipt(r["id"]) for r in receipts}
        debts = {}
        for r in receipts:
            if not r.get("payer_id"): continue
            for it in items_by[r["id"]]:
                ep = it.get("expense_payer_id")
                if ep and ep != r["payer_id"]:
                    debts[(r["payer_id"], ep)] = debts.get((r["payer_id"], ep), 0) + it["sum"]
        pay_map = {p["id"]: p["name"] for p in payers}
        self.tbl.setRowCount(0)
        for (a, b), s in debts.items():
            i = self.tbl.rowCount(); self.tbl.insertRow(i)
            self.tbl.setItem(i, 0, QTableWidgetItem(pay_map.get(a, "")))
            self.tbl.setItem(i, 1, QTableWidgetItem(pay_map.get(b, "")))
            self.tbl.setItem(i, 2, QTableWidgetItem(f"{s:.2f}"))
        self._receipts = receipts
        self._items_by = items_by
        self._payers = payers

    def apply(self):
        today = QDate.currentDate().toString("yyyy-MM-dd")
        for r in self._receipts:
            db.update("receipts", r["id"], {
                "in_process": 0, "processed": 1, "process_date": today
            })
        QMessageBox.information(self, "Готово", "Отметки обновлены")
        self.calculate()

    def make_report(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить отчёт", "report.xlsx",
                                              "Excel (*.xlsx)")
        if not path: return
        create_report(self._receipts, self._items_by, self._payers, path)
        QMessageBox.information(self, "Готово", f"Отчёт сохранён:\n{path}")