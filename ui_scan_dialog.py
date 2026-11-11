# ui_scan_dialog.py
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QTextEdit, QTableWidget, QTableWidgetItem,
                             QPushButton, QFileDialog, QMessageBox, QComboBox,
                             QHeaderView, QDateEdit, QGroupBox, QSplitter, QWidget,
                             QListWidget)
from PyQt5.QtCore import Qt, QDate
import database as db
import date_utils
from ocr_service import extract_text_best, extract_text_from_pdf, parse_receipt
import os
import tempfile
import logging
import re

logger = logging.getLogger(__name__)


class ScanDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Сканирование чека")
        self.resize(1200, 700)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)

        left = QWidget(); left_lay = QVBoxLayout(left)
        left_lay.addWidget(QLabel("<b>📄 Распознанный текст (можно редактировать):</b>"))
        self.txt = QTextEdit()
        self.txt.setPlaceholderText("Здесь появится текст после сканирования...\n\nВы можете отредактировать его перед переносом данных.")
        left_lay.addWidget(self.txt); left.setLayout(left_lay)

        right = QWidget(); right_lay = QVBoxLayout(right)
        right_lay.addWidget(QLabel("<b>📊 Распознанные данные:</b>"))
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["№", "Наименование", "Кол-во", "Цена", "Сумма", "Чей расход"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.itemChanged.connect(self._on_item_changed)
        right_lay.addWidget(self.tbl)

        btn_lay = QHBoxLayout()
        b_add = QPushButton("➕ Добавить"); b_add.clicked.connect(self.add_item); btn_lay.addWidget(b_add)
        b_remove = QPushButton("➖ Удалить"); b_remove.clicked.connect(self.remove_item); btn_lay.addWidget(b_remove)
        b_manual = QPushButton("✏️ Ручная разметка"); b_manual.clicked.connect(self.manual_mark_items); btn_lay.addWidget(b_manual)
        btn_lay.addStretch(); right_lay.addLayout(btn_lay)
        right.setLayout(right_lay)

        splitter.addWidget(left); splitter.addWidget(right); splitter.setSizes([400, 600])
        lay.addWidget(splitter)

        info_group = QGroupBox("Информация о чеке"); info_lay = QHBoxLayout()
        info_lay.addWidget(QLabel("Дата:"))
        self.ed_date = QDateEdit(); self.ed_date.setCalendarPopup(True)
        self.ed_date.setDisplayFormat(date_utils.QT_DISPLAY)
        self.ed_date.setDate(QDate.currentDate())
        info_lay.addWidget(self.ed_date)
        info_lay.addWidget(QLabel("Компания:"))
        self.cb_company = QComboBox(); self.cb_company.addItem("— не выбрана —", None)
        for c in db.fetch_all("companies"):
            self.cb_company.addItem(c["name"], c["id"])
        info_lay.addWidget(self.cb_company)
        info_lay.addWidget(QLabel("Плательщик:"))
        self.cb_payer = QComboBox(); self.cb_payer.addItem("— не выбран —", None)
        for p in db.fetch_all("payers"):
            self.cb_payer.addItem(p["name"], p["id"])
        info_lay.addWidget(self.cb_payer)
        info_group.setLayout(info_lay); lay.addWidget(info_group)

        self.lbl_total = QLabel("Итого: 0.00 ₽")
        self.lbl_total.setStyleSheet("font-size: 14px; font-weight: bold; color: #2196F3;")
        self.lbl_total.setAlignment(Qt.AlignRight); lay.addWidget(self.lbl_total)

        btns = QHBoxLayout()
        b_open = QPushButton("📁 Выбрать файл"); b_open.clicked.connect(self.open_file); btns.addWidget(b_open)
        b_parse = QPushButton("🔄 Перенести данные")
        b_parse.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        b_parse.clicked.connect(self.parse_and_fill); btns.addWidget(b_parse)
        b_save = QPushButton("💾 Сохранить")
        b_save.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 10px;")
        b_save.clicked.connect(self.save); btns.addWidget(b_save)
        b_close = QPushButton("❌ Закрыть"); b_close.clicked.connect(self.close); btns.addWidget(b_close)
        lay.addLayout(btns)

    def add_item(self):
        i = self.tbl.rowCount(); self.tbl.insertRow(i)
        self.tbl.setItem(i, 0, QTableWidgetItem(str(i + 1))); self.tbl.item(i, 0).setFlags(Qt.ItemIsEnabled)
        cb = QComboBox(); cb.setEditable(True); cb.addItem("")
        for n in db.fetch_all("item_names"):
            cb.addItem(n["name"])
        self.tbl.setCellWidget(i, 1, cb)
        self.tbl.setItem(i, 2, QTableWidgetItem("1.00"))
        self.tbl.setItem(i, 3, QTableWidgetItem("0.00"))
        self.tbl.setItem(i, 4, QTableWidgetItem("0.00")); self.tbl.item(i, 4).setFlags(Qt.ItemIsEnabled)
        cb_p = QComboBox(); cb_p.addItem("—", None)
        for p in db.fetch_all("payers"):
            cb_p.addItem(p["name"], p["id"])
        self.tbl.setCellWidget(i, 5, cb_p)
        self._update_total()

    def remove_item(self):
        row = self.tbl.currentRow()
        if row >= 0:
            self.tbl.removeRow(row)
            for i in range(self.tbl.rowCount()):
                self.tbl.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self._update_total()

    def manual_mark_items(self):
        text = self.txt.toPlainText(); lines = text.split('\n')
        dlg = QDialog(self); dlg.setWindowTitle("Выберите строки с позициями"); dlg.resize(600, 400)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Отметьте строки, которые содержат позиции (Ctrl+Click):"))
        list_widget = QListWidget(); list_widget.setSelectionMode(QListWidget.MultiSelection)
        for i, line in enumerate(lines):
            if line.strip():
                list_widget.addItem(f"{i}: {line}")
        lay.addWidget(list_widget)
        btn_lay = QHBoxLayout(); b_ok = QPushButton("OK"); b_cancel = QPushButton("Отмена")
        btn_lay.addWidget(b_ok); btn_lay.addWidget(b_cancel); lay.addLayout(btn_lay)

        def on_ok():
            for item in list_widget.selectedItems():
                line_text = item.text().split(': ', 1)[1] if ': ' in item.text() else item.text()
                numbers = self._find_all_numbers_in_line(line_text)
                if len(numbers) >= 2:
                    qty = numbers[-2]['value']; total = numbers[-1]['value']
                    if self._is_likely_quantity(qty) and self._is_likely_price(total):
                        name = line_text[:numbers[0]['start']].strip()
                        name = re.sub(r'[^\w\s\-]', '', name).strip()
                        if len(name) >= 3:
                            price = total / qty if qty > 0 else 0
                            r = self.tbl.rowCount(); self.tbl.insertRow(r)
                            self.tbl.setItem(r, 0, QTableWidgetItem(str(r + 1))); self.tbl.item(r, 0).setFlags(Qt.ItemIsEnabled)
                            cb = QComboBox(); cb.setEditable(True); cb.addItem(name)
                            for n in db.fetch_all("item_names"):
                                cb.addItem(n["name"])
                            cb.setEditText(name); self.tbl.setCellWidget(r, 1, cb)
                            self.tbl.setItem(r, 2, QTableWidgetItem(str(qty)))
                            self.tbl.setItem(r, 3, QTableWidgetItem(f"{price:.2f}"))
                            self.tbl.setItem(r, 4, QTableWidgetItem(f"{total:.2f}")); self.tbl.item(r, 4).setFlags(Qt.ItemIsEnabled)
                            cb_payer = QComboBox(); cb_payer.addItem("—", None)
                            for p in db.fetch_all("payers"):
                                cb_payer.addItem(p["name"], p["id"])
                            self.tbl.setCellWidget(r, 5, cb_payer)
            self._update_total(); dlg.accept()

        b_ok.clicked.connect(on_ok); b_cancel.clicked.connect(dlg.reject); dlg.exec_()

    def _find_all_numbers_in_line(self, line):
        numbers = []
        for m in re.finditer(r'\d+[.,]?\d*', line):
            num = self._clean_number(m.group())
            if num is not None:
                numbers.append({'value': num, 'start': m.start(), 'end': m.end(), 'text': m.group()})
        return numbers

    def _clean_number(self, s):
        if not s:
            return None
        s = str(s).strip()
        replacements = {"'": "7", "`": "7", "´": "7", "l": "1", "I": "1", "|": "1", "i": "1",
                        "о": "0", "О": "0", "ш": "4", "Ш": "4", "з": "3", "З": "3", "у": "4", "У": "4",
                        "y": "4", "с": "6", "С": "6", "c": "6", "г": "7", "Г": "7", "т": "7", "Т": "7",
                        "р": "8", "Р": "8", "ь": "6", "Ь": "6", "б": "6", "Б": "6", "н": "4", "Н": "4",
                        "к": "4", "К": "4", "м": "4", "М": "4", "х": "4", "Х": "4", "q": "0", "Q": "0",
                        "g": "9", "G": "9", "e": "3", "E": "3", "a": "4", "A": "4", "S": "5", "s": "5",
                        "B": "8", "b": "8", "~": "", "+": ""}
        for old, new in replacements.items():
            s = s.replace(old, new)
        s = re.sub(r'[^\d.,]', '', s); s = s.replace(',', '.')
        if s.count('.') > 1:
            parts = s.split('.'); s = ''.join(parts[:-1]) + '.' + parts[-1]
        try:
            return float(s)
        except:
            return None

    def _is_likely_quantity(self, num):
        return 0 < num <= 1000

    def _is_likely_price(self, num):
        return num > 10

    def _on_item_changed(self, item):
        row = item.row(); col = item.column()
        if col in [2, 3]:
            try:
                qty = float(self.tbl.item(row, 2).text().replace(",", "."))
                price = float(self.tbl.item(row, 3).text().replace(",", "."))
                self.tbl.blockSignals(True)
                self.tbl.setItem(row, 4, QTableWidgetItem(f"{qty * price:.2f}"))
                self.tbl.blockSignals(False)
                self._update_total()
            except (ValueError, AttributeError):
                pass

    def _update_total(self):
        total = 0.0
        for i in range(self.tbl.rowCount()):
            try:
                s = self.tbl.item(i, 4)
                if s:
                    total += float(s.text().replace(",", "."))
            except (ValueError, AttributeError):
                pass
        self.lbl_total.setText(f"Итого: {total:.2f} ₽")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите чек", "",
                                              "Images and PDFs (*.png *.jpg *.jpeg *.bmp *.tif *.pdf)")
        if not path:
            return
        try:
            text = ""; from_text_layer = False
            if path.lower().endswith('.pdf'):
                text = extract_text_from_pdf(path) or ""
                if text:
                    from_text_layer = True
                else:
                    from pdf2image import convert_from_path
                    images = convert_from_path(path, dpi=300)
                    if not images:
                        QMessageBox.critical(self, "Ошибка", "Не удалось извлечь изображение из PDF"); return
                    parts = []
                    for n, img in enumerate(images, 1):
                        tf = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                        try:
                            img.save(tf.name, 'PNG'); parts.append(extract_text_best(tf.name))
                        finally:
                            os.unlink(tf.name)
                    text = "\n".join(parts)
            else:
                text = extract_text_best(path)
            self.txt.setPlainText(text)
            source = "извлечён из PDF без OCR" if from_text_layer else "распознан (OCR)"
            QMessageBox.information(self, "Готово", f"Текст {source} ({len(text)} символов).\n\nНажмите ' Перенести данные'.")
        except Exception as e:
            logger.error(f"Ошибка OCR: {e}"); QMessageBox.critical(self, "Ошибка OCR", str(e))

    def _offer_add_company(self, name):
        idx = self.cb_company.findText(name, Qt.MatchExactly)
        if idx < 0:
            idx = self.cb_company.findText(name, Qt.MatchContains)
        if idx >= 0:
            self.cb_company.setCurrentIndex(idx); return
        if QMessageBox.question(self, "Новая компания",
                                f"Компания «{name}» не найдена в базе.\nДобавить её в базу компаний?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            try:
                nid = db.insert("companies", {"name": name})
                self.cb_company.addItem(name, nid)
                self.cb_company.setCurrentIndex(self.cb_company.count() - 1)
            except Exception as e:
                logger.error(f"Не удалось добавить компанию: {e}")

    def parse_and_fill(self):
        text = self.txt.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "Внимание", "Сначала выберите файл или введите текст вручную."); return
        try:
            data = parse_receipt(text)
            if data["date"]:
                for fmt in ("dd.MM.yyyy", "dd-MM-yyyy", "dd/MM/yyyy"):
                    d = QDate.fromString(data["date"], fmt)
                    if d.isValid():
                        self.ed_date.setDate(d); break
            if data["company"]:
                self._offer_add_company(data["company"])

            self.tbl.setRowCount(0)
            for it in data["items"]:
                r = self.tbl.rowCount(); self.tbl.insertRow(r)
                self.tbl.setItem(r, 0, QTableWidgetItem(str(r + 1))); self.tbl.item(r, 0).setFlags(Qt.ItemIsEnabled)
                cb_name = QComboBox(); cb_name.setEditable(True); cb_name.addItem(it["name"])
                for n in db.fetch_all("item_names"):
                    cb_name.addItem(n["name"])
                cb_name.setEditText(it["name"]); self.tbl.setCellWidget(r, 1, cb_name)
                self.tbl.setItem(r, 2, QTableWidgetItem(str(it["qty"])))
                self.tbl.setItem(r, 3, QTableWidgetItem(f"{it['price']:.2f}"))
                self.tbl.setItem(r, 4, QTableWidgetItem(f"{it['sum']:.2f}")); self.tbl.item(r, 4).setFlags(Qt.ItemIsEnabled)
                cb_payer = QComboBox(); cb_payer.addItem("—", None)
                for p in db.fetch_all("payers"):
                    cb_payer.addItem(p["name"], p["id"])
                self.tbl.setCellWidget(r, 5, cb_payer)
            self._update_total()

            msg = (f"✅ Распознано позиций: {len(data['items'])}\n"
                   f"📅 Дата: {data['date'] or 'не найдена'}\n"
                   f"🏢 Компания: {data['company'] or 'не найдена'}\n"
                   f"💰 Итого: {data['total']:.2f}\n")
            if data.get("discount_total"):
                msg += f"🏷️ Скидки: {data['discount_total']:.2f}\n"
            if data.get("warnings"):
                msg += "\n⚠️ " + "\n⚠️ ".join(data["warnings"]) + "\n"
            msg += "\nПроверьте данные и при необходимости отредактируйте."
            QMessageBox.information(self, "Готово", msg)
        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}"); QMessageBox.critical(self, "Ошибка парсинга", str(e))

    def save(self):
        if self.cb_company.currentData() is None:
            QMessageBox.warning(self, "Внимание", "Выберите компанию!"); return
        if self.cb_payer.currentData() is None:
            QMessageBox.warning(self, "Внимание", "Выберите плательщика!"); return
        if self.tbl.rowCount() == 0:
            QMessageBox.warning(self, "Внимание", "Нет позиций для сохранения."); return
        for i in range(self.tbl.rowCount()):
            if not self.tbl.cellWidget(i, 1).currentText().strip():
                QMessageBox.warning(self, "Внимание", f"Заполните наименование в строке {i + 1}!"); return
        try:
            date = self.ed_date.date().toString(date_utils.QT_ISO)
            total_amount = 0.0
            for r in range(self.tbl.rowCount()):
                try:
                    total_amount += float(self.tbl.item(r, 4).text().replace(",", "."))
                except (ValueError, AttributeError):
                    pass
            rn = db.next_row_number()
            rid = db.insert("receipts", {"row_number": rn, "receipt_date": date,
                                         "company_id": self.cb_company.currentData(),
                                         "total_amount": round(total_amount, 2),
                                         "in_process": 0, "processed": 0,
                                         "payer_id": self.cb_payer.currentData()})
            added, skipped = 0, 0
            for r in range(self.tbl.rowCount()):
                name = self.tbl.cellWidget(r, 1).currentText().strip()
                if not name:
                    continue
                existing = next((n for n in db.fetch_all("item_names") if n["name"] == name), None)
                if not existing:
                    try:
                        nid = db.insert("item_names", {"name": name}); added += 1
                    except Exception:
                        nid = next(n["id"] for n in db.fetch_all("item_names") if n["name"] == name); skipped += 1
                else:
                    nid = existing["id"]; skipped += 1
                try:
                    q = float(self.tbl.item(r, 2).text().replace(",", "."))
                except (ValueError, AttributeError):
                    q = 1.0
                try:
                    p = float(self.tbl.item(r, 3).text().replace(",", "."))
                except (ValueError, AttributeError):
                    p = 0.0
                try:
                    s = float(self.tbl.item(r, 4).text().replace(",", "."))
                except (ValueError, AttributeError):
                    s = q * p
                db.insert("receipt_items", {"receipt_id": rid, "item_number": r + 1, "item_name_id": nid,
                                            "quantity": q, "price": p, "sum": round(s, 2),
                                            "expense_payer_id": self.tbl.cellWidget(r, 5).currentData()})
            QMessageBox.information(self, "Успешно", f"✅ Чек сохранён!\n\n💰 Сумма: {total_amount:.2f} ₽\nНовых наименований: {added}\nУже было: {skipped}")
            self.accept()
        except Exception as e:
            logger.exception(f"Ошибка сохранения: {e}"); QMessageBox.critical(self, "Ошибка", str(e))