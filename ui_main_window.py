# ui_main_window.py
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                             QDateEdit, QComboBox, QCheckBox, QHeaderView, QMenu,
                             QMessageBox, QAbstractItemView)
from PyQt5.QtCore import Qt, QTimer, QDate
from config import APP_VERSION, APP_DATE, APP_TITLE
import database as db
from filters import build_filters
from ui_receipt_dialog import ReceiptDialog
from ui_companies_dialog import CompaniesDialog
from ui_items_dialog import ItemsDialog
from ui_payers_dialog import PayersDialog
from ui_scan_dialog import ScanDialog
from ui_calculation_dialog import CalculationDialog
import logging

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        logger.info("Создание главного окна")
        self.setWindowTitle(APP_TITLE)
        self.resize(1200, 700)
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

        # --- Верхняя шапка ---
        top = QHBoxLayout()
        self.lbl_version = QLabel(f"v{APP_VERSION} от {APP_DATE}")
        self.lbl_title = QLabel(f"<b>{APP_TITLE}</b>")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_clock = QLabel()
        top.addWidget(self.lbl_version)
        top.addStretch()
        top.addWidget(self.lbl_title)
        top.addStretch()
        top.addWidget(self.lbl_clock)
        lay.addLayout(top)

        # --- Фильтры ---
        filt = QHBoxLayout()
        filt.addWidget(QLabel("С:"))
        self.f_date_from = QDateEdit()
        self.f_date_from.setCalendarPopup(True)
        self.f_date_from.setDate(QDate(2000, 1, 1))
        self.f_date_from.setMinimumDate(QDate(2000, 1, 1))
        filt.addWidget(self.f_date_from)

        filt.addWidget(QLabel("По:"))
        self.f_date_to = QDateEdit()
        self.f_date_to.setCalendarPopup(True)
        self.f_date_to.setDate(QDate(2099, 12, 31))  # ← ВАЖНО: по умолчанию далёкое будущее
        self.f_date_to.setMaximumDate(QDate(2099, 12, 31))
        filt.addWidget(self.f_date_to)

        self.f_in = QCheckBox("В обработку")
        self.f_in.stateChanged.connect(self.refresh)
        filt.addWidget(self.f_in)
        self.f_proc = QCheckBox("Обработан")
        self.f_proc.stateChanged.connect(self.refresh)
        filt.addWidget(self.f_proc)

        filt.addWidget(QLabel("Компания:"))
        self.f_company = QComboBox()
        self.f_company.addItem("— все —", 0)
        for c in db.fetch_all("companies"):
            self.f_company.addItem(c["name"], c["id"])
        self.f_company.currentIndexChanged.connect(self.refresh)
        filt.addWidget(self.f_company)
        lay.addLayout(filt)

        # --- Кнопки ---
        btns = QHBoxLayout()
        buttons = [
            ("Создать новый чек", self.new_receipt),
            ("Удалить чек", self.delete_receipt),
            ("База компаний", self.open_companies),
            ("База наименований", self.open_items),
            ("База плательщиков", self.open_payers),
            ("Сканировать чек", self.scan_receipt),
            ("Рассчитать оплаты", self.calc_payments),
        ]
        for text, fn in buttons:
            b = QPushButton(text)
            b.clicked.connect(fn)
            btns.addWidget(b)
        lay.addLayout(btns)

        # --- Таблица чеков ---
        self.tbl = QTableWidget(0, 8)
        self.tbl.setHorizontalHeaderLabels([
            "Номер строки", "Дата чека", "Компания", "Сумма чека",
            "В обработку", "Обработан", "Дата обработки", "Кто платил"
        ])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.horizontalHeader().sectionClicked.connect(self._on_sort)
        self.tbl.itemChanged.connect(self._on_item_changed)
        self.tbl.currentCellChanged.connect(self._on_current_changed)
        lay.addWidget(self.tbl)

        # --- Подчинённая таблица позиций ---
        self.sub = QTableWidget(0, 6)
        self.sub.setHorizontalHeaderLabels([
            "Номер", "Наименование", "Кол-во", "Цена", "Сумма", "Чей расход"
        ])
        self.sub.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sub.itemChanged.connect(self._on_sub_changed)
        lay.addWidget(self.sub)

        self.lbl_total = QLabel("Итого: 0.00 ₽")
        self.lbl_total.setAlignment(Qt.AlignRight)
        lay.addWidget(self.lbl_total)

    def _tick_clock(self):
        from PyQt5.QtCore import QDateTime
        now = QDateTime.currentDateTime().toString("dd.MM.yyyy HH:mm:ss")
        self.lbl_clock.setText(now)
        QTimer.singleShot(1000, self._tick_clock)

    def refresh(self):
        """Обновление таблицы чеков с учётом фильтров."""
        logger.debug("Обновление таблицы чеков")
        self._refresh_companies_combo()

        # Исправленная логика фильтра дат:
        # - f_date_from = 01.01.2000 — не применяем фильтр "С"
        # - f_date_to = 31.12.2099 — не применяем фильтр "По"
        date_from = self.f_date_from.date()
        date_to = self.f_date_to.date()

        f = build_filters(
            date_from.toString("yyyy-MM-dd") if date_from > QDate(2000, 1, 1) else None,
            date_to.toString("yyyy-MM-dd") if date_to < QDate(2099, 12, 31) else None,
            1 if self.f_in.isChecked() else None,
            1 if self.f_proc.isChecked() else None,
            self.f_company.currentData(),
        )

        try:
            rows = db.get_receipts_filtered(f)
            logger.debug(f"Получено {len(rows)} записей из БД")
        except Exception as e:
            logger.exception(f"Ошибка получения записей: {e}")
            rows = []

        self.tbl.blockSignals(True)
        self.tbl.setRowCount(0)
        for r in rows:
            i = self.tbl.rowCount()
            self.tbl.insertRow(i)
            self.tbl.setItem(i, 0, QTableWidgetItem(str(r["row_number"])))
            self.tbl.setItem(i, 1, QTableWidgetItem(r["receipt_date"] or ""))
            self.tbl.setItem(i, 2, QTableWidgetItem(r.get("company_name") or ""))
            self.tbl.setItem(i, 3, QTableWidgetItem(f"{r['total_amount']:.2f}"))
            chk1 = QTableWidgetItem()
            chk1.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk1.setCheckState(Qt.Checked if r["in_process"] else Qt.Unchecked)
            self.tbl.setItem(i, 4, chk1)
            chk2 = QTableWidgetItem()
            chk2.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk2.setCheckState(Qt.Checked if r["processed"] else Qt.Unchecked)
            self.tbl.setItem(i, 5, chk2)
            self.tbl.setItem(i, 6, QTableWidgetItem(r.get("process_date") or ""))
            self.tbl.setItem(i, 7, QTableWidgetItem(r.get("payer_name") or ""))
            self.tbl.item(i, 0).setData(Qt.UserRole, r["id"])
        self.tbl.blockSignals(False)

    def _refresh_companies_combo(self):
        """Обновление выпадающего списка компаний в фильтре."""
        cur = self.f_company.currentData()
        self.f_company.blockSignals(True)
        self.f_company.clear()
        self.f_company.addItem("— все —", 0)
        for c in db.fetch_all("companies"):
            self.f_company.addItem(c["name"], c["id"])
        idx = self.f_company.findData(cur)
        if idx >= 0:
            self.f_company.setCurrentIndex(idx)
        self.f_company.blockSignals(False)

    def _on_sort(self, col):
        """Сортировка по клику на заголовок столбца."""
        if col == self.sort_col:
            self.sort_asc = not self.sort_asc
        else:
            self.sort_col = col
            self.sort_asc = True
        order = Qt.AscendingOrder if self.sort_asc else Qt.DescendingOrder
        self.tbl.sortItems(col, order)

    def _current_receipt_id(self):
        """Получить ID текущего выбранного чека."""
        row = self.tbl.currentRow()
        if row < 0:
            return None
        item = self.tbl.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_item_changed(self, item):
        """Сохранение изменений в основной таблице."""
        rid = self._current_receipt_id()
        if not rid:
            return
        col = item.column()
        data = {}
        try:
            if col == 1:
                data["receipt_date"] = item.text()
            elif col == 2:
                cid = next(
                    (c["id"] for c in db.fetch_all("companies") if c["name"] == item.text()),
                    None
                )
                if cid:
                    data["company_id"] = cid
            elif col == 4:
                data["in_process"] = 1 if item.checkState() == Qt.Checked else 0
            elif col == 5:
                data["processed"] = 1 if item.checkState() == Qt.Checked else 0
            elif col == 6:
                data["process_date"] = item.text()
            elif col == 7:
                pid = next(
                    (p["id"] for p in db.fetch_all("payers") if p["name"] == item.text()),
                    None
                )
                if pid:
                    data["payer_id"] = pid
            if data:
                db.update("receipts", rid, data)
                logger.debug(f"Обновлён чек {rid}: {data}")
        except Exception as e:
            logger.error(f"Ошибка сохранения изменений чека {rid}: {e}")

    def _on_current_changed(self, r, c, pr, pc):
        """При смене выбранной строки — загрузить позиции."""
        rid = self._current_receipt_id()
        self._load_sub(rid)

    def _load_sub(self, rid):
        """Загрузка позиций чека в подчинённую таблицу."""
        self.sub.blockSignals(True)
        self.sub.setRowCount(0)
        total = 0.0
        if rid:
            try:
                items = db.get_items_for_receipt(rid)
                for it in items:
                    i = self.sub.rowCount()
                    self.sub.insertRow(i)
                    self.sub.setItem(i, 0, QTableWidgetItem(str(it["item_number"])))
                    self.sub.setItem(i, 1, QTableWidgetItem(it.get("item_name") or ""))
                    self.sub.setItem(i, 2, QTableWidgetItem(str(it["quantity"])))
                    self.sub.setItem(i, 3, QTableWidgetItem(str(it["price"])))
                    self.sub.setItem(i, 4, QTableWidgetItem(str(it["sum"])))
                    self.sub.setItem(i, 5, QTableWidgetItem(it.get("expense_payer_name") or ""))
                    self.sub.item(i, 0).setData(Qt.UserRole, it["id"])
                    total += it["sum"] or 0
            except Exception as e:
                logger.error(f"Ошибка загрузки позиций чека {rid}: {e}")

        # Строка "Итого"
        i = self.sub.rowCount()
        self.sub.insertRow(i)
        self.sub.setItem(i, 0, QTableWidgetItem("Итого"))
        self.sub.setItem(i, 4, QTableWidgetItem(f"{total:.2f}"))
        self.sub.blockSignals(False)
        self.lbl_total.setText(f"Итого: {total:.2f} ₽")

        # Обновляем сумму в основной таблице
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

    def _on_sub_changed(self, item):
        """Сохранение изменений в подчинённой таблице."""
        rid = self._current_receipt_id()
        if not rid:
            return
        iid = self.sub.item(item.row(), 0).data(Qt.UserRole)
        if not iid:
            return
        data = {}
        c = item.column()
        try:
            if c == 1:
                names = db.fetch_all("item_names")
                nid = next((n["id"] for n in names if n["name"] == item.text()), None)
                if nid:
                    data["item_name_id"] = nid
            elif c == 2:
                try:
                    data["quantity"] = float(item.text().replace(",", "."))
                except ValueError:
                    pass
            elif c == 3:
                try:
                    data["price"] = float(item.text().replace(",", "."))
                except ValueError:
                    pass
            elif c == 5:
                pid = next(
                    (p["id"] for p in db.fetch_all("payers") if p["name"] == item.text()),
                    None
                )
                if pid:
                    data["expense_payer_id"] = pid
            if data:
                if "quantity" in data or "price" in data:
                    it = next((x for x in db.get_items_for_receipt(rid) if x["id"] == iid), None)
                    q = data.get("quantity", it["quantity"] if it else 0)
                    p = data.get("price", it["price"] if it else 0)
                    data["sum"] = q * p
                db.update("receipt_items", iid, data)
                self._load_sub(rid)
        except Exception as e:
            logger.error(f"Ошибка сохранения позиции {iid}: {e}")

    # ========== КНОПКИ ==========

    def new_receipt(self):
        """Создать новый чек."""
        logger.info("Открытие диалога создания чека")
        try:
            dlg = ReceiptDialog(self)
            if dlg.exec_() == ReceiptDialog.Accepted:
                logger.info("Чек создан, обновление таблицы")
                self.refresh()
        except Exception as e:
            logger.exception(f"Ошибка создания чека: {e}")
            QMessageBox.critical(self, "Ошибка", str(e))

    def delete_receipt(self):
        """Удалить выбранный чек."""
        rid = self._current_receipt_id()
        if not rid:
            QMessageBox.warning(self, "Внимание", "Выберите чек для удаления.")
            return
        if QMessageBox.question(self, "Удалить", "Удалить выбранный чек?") == QMessageBox.Yes:
            try:
                db.delete_receipt_full(rid)
                logger.info(f"Чек {rid} удалён")
                self.refresh()
            except Exception as e:
                logger.error(f"Ошибка удаления чека {rid}: {e}")
                QMessageBox.critical(self, "Ошибка", str(e))

    def open_companies(self):
        """Открыть базу компаний."""
        logger.info("Открытие базы компаний")
        try:
            CompaniesDialog(self).exec_()
            self.refresh()
        except Exception as e:
            logger.exception(f"Ошибка открытия базы компаний: {e}")
            QMessageBox.critical(self, "Ошибка", str(e))

    def open_items(self):
        """Открыть базу наименований."""
        logger.info("Открытие базы наименований")
        try:
            ItemsDialog(self).exec_()
        except Exception as e:
            logger.exception(f"Ошибка открытия базы наименований: {e}")
            QMessageBox.critical(self, "Ошибка", str(e))

    def open_payers(self):
        """Открыть базу плательщиков."""
        logger.info("Открытие базы плательщиков")
        try:
            PayersDialog(self).exec_()
        except Exception as e:
            logger.exception(f"Ошибка открытия базы плательщиков: {e}")
            QMessageBox.critical(self, "Критическая ошибка", f"Произошла ошибка:\n{e}")

    def scan_receipt(self):
        """Открыть диалог сканирования чека."""
        logger.info("Открытие диалога сканирования чека")
        try:
            dlg = ScanDialog(self)
            if dlg.exec_() == ScanDialog.Accepted:
                logger.info("Чек отсканирован, обновление таблицы")
                self.refresh()
        except Exception as e:
            logger.exception(f"Ошибка сканирования чека: {e}")
            QMessageBox.critical(self, "Ошибка", str(e))

    def calc_payments(self):
        """Открыть диалог расчёта оплат."""
        logger.info("Открытие диалога расчёта оплат")
        try:
            CalculationDialog(self).exec_()
            self.refresh()
        except Exception as e:
            logger.exception(f"Ошибка расчёта оплат: {e}")
            QMessageBox.critical(self, "Ошибка", str(e))