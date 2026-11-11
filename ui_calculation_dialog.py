# ui_calculation_dialog.py
"""Расчёт оплат: расход делится пополам, если у позиции заполнены
оба поля «Чей расход» и «Чей расход 2».
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QDateEdit, QComboBox,
                             QCheckBox, QHeaderView, QFileDialog, QMessageBox,
                             QTabWidget, QWidget, QAbstractItemView)
from PyQt5.QtCore import Qt, QDate
import database as db
import date_utils
import logging

logger = logging.getLogger(__name__)


class CalculationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Расчёт оплат")
        self.resize(950, 620)
        self.totals, self.debts = [], []
        self._build()
        self.recalculate()

    def _build(self):
        lay = QVBoxLayout(self)

        filt = QHBoxLayout()
        filt.addWidget(QLabel("С:"))
        self.ed_from = QDateEdit(); self.ed_from.setCalendarPopup(True)
        self.ed_from.setDisplayFormat(date_utils.QT_DISPLAY)
        self.ed_from.setDate(QDate(2000, 1, 1)); self.ed_from.setMinimumDate(QDate(2000, 1, 1))
        filt.addWidget(self.ed_from)
        filt.addWidget(QLabel("По:"))
        self.ed_to = QDateEdit(); self.ed_to.setCalendarPopup(True)
        self.ed_to.setDisplayFormat(date_utils.QT_DISPLAY)
        self.ed_to.setDate(QDate(2099, 12, 31)); self.ed_to.setMaximumDate(QDate(2099, 12, 31))
        filt.addWidget(self.ed_to)
        filt.addWidget(QLabel("Компания:"))
        self.cb_company = QComboBox(); self.cb_company.addItem("— все —", 0)
        for c in db.fetch_all("companies"):
            self.cb_company.addItem(c["name"], c["id"])
        filt.addWidget(self.cb_company)
        self.chk_processed = QCheckBox("только обработанные")
        filt.addWidget(self.chk_processed)
        filt.addStretch()
        lay.addLayout(filt)

        self.tabs = QTabWidget()

        page1 = QWidget(); p1 = QVBoxLayout(page1)
        self.tbl_totals = QTableWidget(0, 4)
        self.tbl_totals.setHorizontalHeaderLabels(
            ["Плательщик", "Расход (с делением)", "Оплатил", "Баланс"])
        self.tbl_totals.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_totals.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_totals.setEditTriggers(QAbstractItemView.NoEditTriggers)
        p1.addWidget(self.tbl_totals)
        self.lbl_sum = QLabel("")
        self.lbl_sum.setAlignment(Qt.AlignRight)
        p1.addWidget(self.lbl_sum)
        self.tabs.addTab(page1, "Итоги по плательщикам")

        page2 = QWidget(); p2 = QVBoxLayout(page2)
        self.tbl_debts = QTableWidget(0, 3)
        self.tbl_debts.setHorizontalHeaderLabels(["Кто должен", "Кому", "Сумма"])
        self.tbl_debts.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_debts.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_debts.setEditTriggers(QAbstractItemView.NoEditTriggers)
        p2.addWidget(self.tbl_debts)
        self.tabs.addTab(page2, "Кто кому должен")

        lay.addWidget(self.tabs)

        hint = QLabel("Если у позиции заполнены оба поля «Чей расход», её сумма делится пополам между плательщиками.")
        hint.setStyleSheet("color: #555;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        btns = QHBoxLayout()
        b_calc = QPushButton("🔄 Пересчитать"); b_calc.clicked.connect(self.recalculate); btns.addWidget(b_calc)
        b_xlsx = QPushButton("📊 В файл excel"); b_xlsx.clicked.connect(self.export_excel); btns.addWidget(b_xlsx)
        btns.addStretch()
        b_close = QPushButton("❌ Закрыть"); b_close.clicked.connect(self.close); btns.addWidget(b_close)
        lay.addLayout(btns)

    def _filters(self):
        d_from = self.ed_from.date(); d_to = self.ed_to.date()
        return {
            "date_from": d_from.toString(date_utils.QT_ISO) if d_from > QDate(2000, 1, 1) else None,
            "date_to": d_to.toString(date_utils.QT_ISO) if d_to < QDate(2099, 12, 31) else None,
            "company_id": self.cb_company.currentData(),
            "in_process": None,
            "processed": 1 if self.chk_processed.isChecked() else None,
        }

    def recalculate(self):
        try:
            f = self._filters()
            self.totals = db.get_payer_totals(f)
            self.debts = db.get_debts(f)
        except Exception as e:
            logger.exception(f"Ошибка расчёта: {e}")
            QMessageBox.critical(self, "Ошибка", str(e)); return

        self.tbl_totals.setRowCount(0)
        for t in self.totals:
            i = self.tbl_totals.rowCount(); self.tbl_totals.insertRow(i)
            self.tbl_totals.setItem(i, 0, QTableWidgetItem(t["name"]))
            self.tbl_totals.setItem(i, 1, QTableWidgetItem(f"{t['consumed']:.2f}"))
            self.tbl_totals.setItem(i, 2, QTableWidgetItem(f"{t['paid']:.2f}"))
            self.tbl_totals.setItem(i, 3, QTableWidgetItem(f"{t['balance']:.2f}"))

        self.tbl_debts.setRowCount(0)
        for d in self.debts:
            i = self.tbl_debts.rowCount(); self.tbl_debts.insertRow(i)
            self.tbl_debts.setItem(i, 0, QTableWidgetItem(d["debtor"]))
            self.tbl_debts.setItem(i, 1, QTableWidgetItem(d["creditor"]))
            self.tbl_debts.setItem(i, 2, QTableWidgetItem(f"{d['amount']:.2f}"))

        consumed = round(sum(t["consumed"] for t in self.totals), 2)
        paid = round(sum(t["paid"] for t in self.totals), 2)
        self.lbl_sum.setText(f"Расход: {consumed:.2f} ₽    Оплачено: {paid:.2f} ₽")

    def export_excel(self):
        from openpyxl import Workbook
        from openpyxl.styles import Font
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить расчёт", "расчёт_оплат.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            wb = Workbook()
            ws = wb.active; ws.title = "Итоги"
            d1 = date_utils.to_display(self.ed_from.date().toString(date_utils.QT_ISO))
            d2 = date_utils.to_display(self.ed_to.date().toString(date_utils.QT_ISO))
            ws.append([f"Расчёт оплат за период {d1} — {d2}"])
            ws["A1"].font = Font(bold=True, size=12)
            ws.append([])
            ws.append(["Плательщик", "Расход (с делением)", "Оплатил", "Баланс"])
            for c in ws[ws.max_row]:
                c.font = Font(bold=True)
            for t in self.totals:
                ws.append([t["name"], t["consumed"], t["paid"], t["balance"]])
            ws.append(["Итого",
                       round(sum(t["consumed"] for t in self.totals), 2),
                       round(sum(t["paid"] for t in self.totals), 2),
                       round(sum(t["balance"] for t in self.totals), 2)])
            for c in ws[ws.max_row]:
                c.font = Font(bold=True)
            for i, w in enumerate([28, 22, 16, 16], 1):
                ws.column_dimensions[chr(64 + i)].width = w

            ws2 = wb.create_sheet("Кто кому должен")
            ws2.append(["Кто должен", "Кому", "Сумма"])
            for c in ws2[ws2.max_row]:
                c.font = Font(bold=True)
            for d in self.debts:
                ws2.append([d["debtor"], d["creditor"], d["amount"]])
            for i, w in enumerate([28, 28, 16], 1):
                ws2.column_dimensions[chr(64 + i)].width = w

            wb.save(path)
            QMessageBox.information(self, "Готово", f"Расчёт выгружен в:\n{path}")
        except Exception as e:
            logger.exception(f"Ошибка выгрузки расчёта: {e}")
            QMessageBox.critical(self, "Ошибка", str(e))