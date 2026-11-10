# ui_companies_dialog.py
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QPushButton, QMessageBox, QHeaderView,
                             QInputDialog)
from PyQt5.QtCore import Qt  # ← ДОБАВЛЕНО
import database as db
import logging

logger = logging.getLogger(__name__)

class CompaniesDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("База компаний")
        self.resize(500, 400)
        lay = QVBoxLayout(self)
        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["Название", "Адрес"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.tbl)
        btns = QHBoxLayout()
        b_add = QPushButton("Добавить"); b_add.clicked.connect(self.add)
        b_del = QPushButton("Удалить"); b_del.clicked.connect(self.delete)
        b_close = QPushButton("Закрыть"); b_close.clicked.connect(self.close)
        btns.addWidget(b_add); btns.addWidget(b_del); btns.addWidget(b_close)
        lay.addLayout(btns)
        self.refresh()

    def refresh(self):
        self.tbl.setRowCount(0)
        for c in db.fetch_all("companies"):
            i = self.tbl.rowCount(); self.tbl.insertRow(i)
            self.tbl.setItem(i, 0, QTableWidgetItem(c["name"]))
            self.tbl.setItem(i, 1, QTableWidgetItem(c["address"] or ""))
            self.tbl.item(i, 0).setData(Qt.UserRole, c["id"])

    def add(self):
        name, ok = QInputDialog.getText(self, "Компания", "Название:")
        if not ok or not name: return
        addr, ok2 = QInputDialog.getText(self, "Компания", "Адрес:")
        try:
            db.insert("companies", {"name": name, "address": addr or ""})
            self.refresh()
        except Exception as e:
            logger.error(f"Ошибка добавления компании: {e}")
            QMessageBox.critical(self, "Ошибка", str(e))

    def delete(self):
        r = self.tbl.currentRow()
        if r < 0: return
        cid = self.tbl.item(r, 0).data(Qt.UserRole)
        if QMessageBox.question(self, "Удалить", "Удалить компанию?") == QMessageBox.Yes:
            try:
                db.delete("companies", cid)
                self.refresh()
            except Exception as e:
                logger.error(f"Ошибка удаления компании: {e}")
                QMessageBox.critical(self, "Ошибка", str(e))