# ui_payers_dialog.py
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QPushButton, QMessageBox, QHeaderView,
                             QInputDialog)
from PyQt5.QtCore import Qt  # ← ДОБАВЛЕНО
import database as db
import logging

logger = logging.getLogger(__name__)

class PayersDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("База плательщиков")
        self.resize(400, 400)
        lay = QVBoxLayout(self)
        self.tbl = QTableWidget(0, 1)
        self.tbl.setHorizontalHeaderLabels(["Имя"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.tbl)
        btns = QHBoxLayout()
        for t, f in [("Добавить", self.add), ("Редактировать", self.edit),
                     ("Удалить", self.delete), ("Закрыть", self.close)]:
            b = QPushButton(t); b.clicked.connect(f); btns.addWidget(b)
        lay.addLayout(btns)
        self.refresh()

    def refresh(self):
        self.tbl.setRowCount(0)
        for p in db.fetch_all("payers"):
            i = self.tbl.rowCount(); self.tbl.insertRow(i)
            self.tbl.setItem(i, 0, QTableWidgetItem(p["name"]))
            self.tbl.item(i, 0).setData(Qt.UserRole, p["id"])

    def add(self):
        name, ok = QInputDialog.getText(self, "Плательщик", "Имя:")
        if ok and name:
            try:
                db.insert("payers", {"name": name})
                self.refresh()
            except Exception as e:
                logger.error(f"Ошибка добавления плательщика: {e}")
                QMessageBox.critical(self, "Ошибка", str(e))

    def edit(self):
        r = self.tbl.currentRow()
        if r < 0: return
        pid = self.tbl.item(r, 0).data(Qt.UserRole)
        name, ok = QInputDialog.getText(self, "Редактировать", "Имя:",
                                        text=self.tbl.item(r, 0).text())
        if ok and name:
            try:
                db.update("payers", pid, {"name": name})
                self.refresh()
            except Exception as e:
                logger.error(f"Ошибка редактирования: {e}")
                QMessageBox.critical(self, "Ошибка", str(e))

    def delete(self):
        r = self.tbl.currentRow()
        if r < 0: return
        pid = self.tbl.item(r, 0).data(Qt.UserRole)
        if QMessageBox.question(self, "Удалить", "Удалить?") == QMessageBox.Yes:
            try:
                db.delete("payers", pid)
                self.refresh()
            except Exception as e:
                logger.error(f"Ошибка удаления: {e}")
                QMessageBox.critical(self, "Ошибка", str(e))