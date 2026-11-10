# excel_service.py
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

def create_report(receipts, items_by_receipt, payers, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Отчёт"
    ws.append(["№", "Дата", "Компания", "Плательщик", "Наименование", "Кол-во", "Цена", "Сумма", "Чей расход"])
    bold = Font(bold=True)

    for r in receipts:
        ws.append([r["row_number"], r["receipt_date"], r.get("company_name", ""), r.get("payer_name", ""),
                   "", "", "", "", ""])
        for c in ws[ws.max_row]:
            c.font = bold
        for it in items_by_receipt.get(r["id"], []):
            ws.append(["", "", "", "",
                       it.get("item_name", ""), it.get("quantity", 0),
                       it.get("price", 0), it.get("sum", 0),
                       it.get("expense_payer_name", "")])

    ws.append([])
    ws.append(["ИТОГИ РАСЧЁТОВ"])
    ws[ws.max_row][0].font = bold
    ws.append(["Кто", "Кому", "Сумма"])
    for line in _calc_debts(receipts, items_by_receipt, payers):
        ws.append(list(line))

    wb.save(path)

def _calc_debts(receipts, items_by_receipt, payers):
    """Возвращает список (кто, кому, сумма)."""
    debts = {}  # (payer_id, expense_payer_id) -> sum
    for r in receipts:
        if not r.get("payer_id"):
            continue
        for it in items_by_receipt.get(r["id"], []):
            ep = it.get("expense_payer_id")
            if ep and ep != r["payer_id"]:
                key = (r["payer_id"], ep)
                debts[key] = debts.get(key, 0) + it.get("sum", 0)

    pay_map = {p["id"]: p["name"] for p in payers}
    result = []
    for (payer, expense), s in debts.items():
        result.append((pay_map.get(payer, ""), pay_map.get(expense, ""), s))
    return result