# ui_receipt_dialog.py
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QDateEdit, QComboBox, QPushButton,
                             QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
                             QGroupBox, QWidget)
from PyQt5.QtCore import QDate, Qt
import database as db
import logging

logger = logging.getLogger(__name__)


class ReceiptDialog(QDialog):
    """Диалог создания нового чека вручную."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Создание нового чека")
        self.resize(900, 600)
        self.parent_w = parent
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)

        # === Основная информация ===
        info_group = QGroupBox("Основная информация")
        info_lay = QHBoxLayout()

        info_lay.addWidget(QLabel("Дата:"))
        self.ed_date = QDateEdit()
        self.ed_date.setCalendarPopup(True)
        self.ed_date.setDate(QDate.currentDate())
        info_lay.addWidget(self.ed_date)

        info_lay.addWidget(QLabel("Компания:"))
        self.cb_company = QComboBox()
        self.cb_company.addItem("— не выбрана —", None)
        for c in db.fetch_all("companies"):
            self.cb_company.addItem(c["name"], c["id"])
        info_lay.addWidget(self.cb_company)

        info_lay.addWidget(QLabel("Кто платил:"))
        self.cb_payer = QComboBox()
        self.cb_payer.addItem("— не выбран —", None)
        for p in db.fetch_all("payers"):
            self.cb_payer.addItem(p["name"], p["id"])
        info_lay.addWidget(self.cb_payer)

        info_group.setLayout(info_lay)
        lay.addWidget(info_group)

        # === Таблица позиций ===
        items_group = QGroupBox("Позиции чека")
        items_lay = QVBoxLayout()

        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels([
            "№", "Наименование", "Кол-во", "Цена", "Сумма", "Чей расход"
        ])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.itemChanged.connect(self._on_item_changed)
        items_lay.addWidget(self.tbl)

        # Кнопки управления позициями
        btn_lay = QHBoxLayout()
        b_add = QPushButton("➕ Добавить позицию")
        b_add.clicked.connect(self.add_item)
        btn_lay.addWidget(b_add)

        b_remove = QPushButton("➖ Удалить позицию")
        b_remove.clicked.connect(self.remove_item)
        btn_lay.addWidget(b_remove)

        btn_lay.addStretch()
        items_lay.addLayout(btn_lay)

        items_group.setLayout(items_lay)
        lay.addWidget(items_group)

        # === Итого ===
        self.lbl_total = QLabel("Итого: 0.00 ₽")
        self.lbl_total.setStyleSheet("font-size: 14px; font-weight: bold; color: #2196F3;")
        self.lbl_total.setAlignment(Qt.AlignRight)
        lay.addWidget(self.lbl_total)

        # === Кнопки действий ===
        btns = QHBoxLayout()
        b_save = QPushButton("💾 Сохранить чек")
        b_save.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;"
        )
        b_save.clicked.connect(self.save)
        btns.addWidget(b_save)

        b_close = QPushButton("❌ Отмена")
        b_close.clicked.connect(self.close)
        btns.addWidget(b_close)
        lay.addLayout(btns)

    def add_item(self):
        """Добавить новую пустую позицию."""
        i = self.tbl.rowCount()
        self.tbl.insertRow(i)

        # Номер (только для отображения)
        self.tbl.setItem(i, 0, QTableWidgetItem(str(i + 1)))
        self.tbl.item(i, 0).setFlags(Qt.ItemIsEnabled)

        # Наименование — выпадающий список с возможностью ввода
        cb = QComboBox()
        cb.setEditable(True)
        cb.addItem("")
        for n in db.fetch_all("item_names"):
            cb.addItem(n["name"])
        self.tbl.setCellWidget(i, 1, cb)

        # Кол-во
        self.tbl.setItem(i, 2, QTableWidgetItem("1.00"))

        # Цена
        self.tbl.setItem(i, 3, QTableWidgetItem("0.00"))

        # Сумма (автоматически, только для чтения)
        self.tbl.setItem(i, 4, QTableWidgetItem("0.00"))
        self.tbl.item(i, 4).setFlags(Qt.ItemIsEnabled)

        # Чей расход
        cb_p = QComboBox()
        cb_p.addItem("—", None)
        for p in db.fetch_all("payers"):
            cb_p.addItem(p["name"], p["id"])
        self.tbl.setCellWidget(i, 5, cb_p)

        self._update_total()

    def remove_item(self):
        """Удалить выбранную позицию."""
        row = self.tbl.currentRow()
        if row < 0:
            QMessageBox.information(self, "Внимание", "Выберите строку для удаления.")
            return
        self.tbl.removeRow(row)
        # Перенумерация
        for i in range(self.tbl.rowCount()):
            self.tbl.setItem(i, 0, QTableWidgetItem(str(i + 1)))
        self._update_total()

    def _on_item_changed(self, item):
        """Пересчёт суммы при изменении кол-ва или цены."""
        row = item.row()
        col = item.column()

        if col in [2, 3]:  # Кол-во или Цена
            try:
                qty_item = self.tbl.item(row, 2)
                price_item = self.tbl.item(row, 3)
                if qty_item is None or price_item is None:
                    return
                qty = float(qty_item.text().replace(",", "."))
                price = float(price_item.text().replace(",", "."))
                total = qty * price
                self.tbl.blockSignals(True)
                self.tbl.setItem(row, 4, QTableWidgetItem(f"{total:.2f}"))
                self.tbl.blockSignals(False)
                self._update_total()
            except (ValueError, AttributeError):
                pass

    def _update_total(self):
        """Обновить итоговую сумму по всем позициям."""
        total = 0.0
        for i in range(self.tbl.rowCount()):
            try:
                sum_item = self.tbl.item(i, 4)
                if sum_item:
                    total += float(sum_item.text().replace(",", "."))
            except (ValueError, AttributeError):
                pass
        self.lbl_total.setText(f"Итого: {total:.2f} ₽")

    def save(self):
        """Сохранить чек с валидацией."""
        # Валидация обязательных полей
        if self.cb_company.currentData() is None:
            QMessageBox.warning(self, "Внимание", "Выберите компанию!")
            return

        if self.cb_payer.currentData() is None:
            QMessageBox.warning(self, "Внимание", "Выберите плательщика!")
            return

        if self.tbl.rowCount() == 0:
            QMessageBox.warning(self, "Внимание", "Добавьте хотя бы одну позицию!")
            return

        # Проверка заполненности наименований
        for i in range(self.tbl.rowCount()):
            name = self.tbl.cellWidget(i, 1).currentText().strip()
            if not name:
                QMessageBox.warning(
                    self, "Внимание", f"Заполните наименование в строке {i + 1}!"
                )
                return

        try:
            date = self.ed_date.date().toString("yyyy-MM-dd")
            cid = self.cb_company.currentData()
            pid = self.cb_payer.currentData()
            rn = db.next_row_number()

            rid = db.insert("receipts", {
                "row_number": rn,
                "receipt_date": date,
                "company_id": cid,
                "total_amount": 0,
                "in_process": 0,
                "processed": 0,
                "payer_id": pid
            })

            added, skipped = 0, 0
            for r in range(self.tbl.rowCount()):
                name = self.tbl.cellWidget(r, 1).currentText().strip()
                if not name:
                    continue

                # Проверяем/добавляем наименование в базу
                existing = next(
                    (n for n in db.fetch_all("item_names") if n["name"] == name),
                    None
                )
                if not existing:
                    try:
                        nid = db.insert("item_names", {"name": name})
                        added += 1
                    except Exception:
                        # Если UNIQUE-ограничение сработало — берём существующий
                        nid = next(
                            n["id"] for n in db.fetch_all("item_names")
                            if n["name"] == name
                        )
                        skipped += 1
                else:
                    nid = existing["id"]
                    skipped += 1

                try:
                    q = float(self.tbl.item(r, 2).text().replace(",", "."))
                except (ValueError, AttributeError):
                    q = 1.0
                try:
                    p = float(self.tbl.item(r, 3).text().replace(",", "."))
                except (ValueError, AttributeError):
                    p = 0.0
                ep = self.tbl.cellWidget(r, 5).currentData()

                db.insert("receipt_items", {
                    "receipt_id": rid,
                    "item_number": r + 1,
                    "item_name_id": nid,
                    "quantity": q,
                    "price": p,
                    "sum": q * p,
                    "expense_payer_id": ep
                })

            logger.info(
                f"Чек создан: ID={rid}, добавлено={added}, пропущено={skipped}"
            )
            QMessageBox.information(
                self,
                "Успешно",
                f"Чек сохранён!\n\n"
                f"Новых наименований: {added}\n"
                f"Уже было в базе: {skipped}"
            )
            self.accept()

        except Exception as e:
            logger.exception(f"Ошибка сохранения чека: {e}")
            QMessageBox.critical(
                self, "Ошибка", f"Не удалось сохранить чек:\n{e}"
            )