# receipt_excel.py
"""Выгрузка одного чека в Excel. Первая строка: компания + дата чека."""
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment


def export_receipt(path, receipt, items):
    wb = Workbook()
    ws = wb.active
    ws.title = "Чек"

    # Первая строка — название компании и дата чека (по требованию)
    ws.append([receipt.get("company_name") or "", receipt.get("receipt_date") or ""])
    ws["A1"].font = Font(bold=True, size=12)
    ws["B1"].font = Font(bold=True, size=12)

    ws.append([])
    ws.append(["Номер строки", receipt.get("row_number")])
    ws.append(["Кто платил", receipt.get("payer_name") or ""])
    ws.append(["В обработку", "да" if receipt.get("in_process") else "нет"])
    ws.append(["Обработан", "да" if receipt.get("processed") else "нет"])
    ws.append(["Дата обработки", receipt.get("process_date") or ""])
    ws.append(["Сумма чека", receipt.get("total_amount") or 0])
    ws.append([])

    header = ["№", "Наименование", "Кол-во", "Цена", "Сумма", "Чей расход"]
    ws.append(header)
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
        ])
        total += it.get("sum") or 0

    ws.append(["", "", "", "Итого", round(total, 2), ""])
    ws[ws.max_row][3].font = Font(bold=True)
    ws[ws.max_row][4].font = Font(bold=True)

    widths = [10, 50, 10, 12, 12, 20]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w

    wb.save(path)
    return path