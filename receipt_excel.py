# receipt_excel.py
"""Выгрузка чека в Excel. Первая строка: компания + дата (дд-мм-гггг).
Колонки «Чей расход» и «Чей расход 2» + распределение расхода пополам.
"""
from openpyxl import Workbook
from openpyxl.styles import Font
import date_utils
from expense_utils import allocate_by_name


def export_receipt(path, receipt, items):
    wb = Workbook()
    ws = wb.active
    ws.title = "Чек"

    ws.append([receipt.get("company_name") or "",
               date_utils.to_display(receipt.get("receipt_date"))])
    ws["A1"].font = Font(bold=True, size=12)
    ws["B1"].font = Font(bold=True, size=12)

    ws.append([])
    ws.append(["Номер строки", receipt.get("row_number")])
    ws.append(["Кто платил", receipt.get("payer_name") or ""])
    ws.append(["В обработку", "да" if receipt.get("in_process") else "нет"])
    ws.append(["Обработан", "да" if receipt.get("processed") else "нет"])
    ws.append(["Дата обработки", date_utils.to_display(receipt.get("process_date"))])
    ws.append(["Сумма чека", receipt.get("total_amount") or 0])
    ws.append([])

    ws.append(["№", "Наименование", "Кол-во", "Цена", "Сумма", "Чей расход", "Чей расход 2"])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)

    total = 0.0
    for it in items:
        ws.append([
            it.get("item_number"),
            it.get("item_name") or "",
            it.get("quantity"),
            it.get("price"),
            it.get("sum"),
            it.get("expense_payer_name") or "",
            it.get("expense_payer_name_2") or "",
        ])
        total += it.get("sum") or 0

    ws.append(["", "", "", "Итого", round(total, 2), "", ""])
    ws[ws.max_row][3].font = Font(bold=True)
    ws[ws.max_row][4].font = Font(bold=True)

    ws.append([])
    ws.append(["Распределение расхода (оба поля заполнены — пополам)"])
    ws[ws.max_row][0].font = Font(bold=True)
    ws.append(["Плательщик", "Сумма"])
    for c in ws[ws.max_row][:2]:
        c.font = Font(bold=True)
    allocated = 0.0
    for name, amount in allocate_by_name(items):
        ws.append([name, amount])
        allocated += amount
    ws.append(["Итого распределено", round(allocated, 2)])
    ws[ws.max_row][0].font = Font(bold=True)
    ws[ws.max_row][1].font = Font(bold=True)

    for i, w in enumerate([10, 50, 10, 12, 12, 22, 22], 1):
        ws.column_dimensions[chr(64 + i)].width = w

    wb.save(path)
    return path