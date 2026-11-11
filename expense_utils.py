# expense_utils.py
"""Распределение расхода позиции по плательщикам.
Оба поля «Чей расход» заполнены -> сумма делится пополам.
"""


def split_item_amount(item):
    """Возвращает список (payer_id, amount) для одной позиции."""
    total = round(float(item.get("sum") or 0), 2)
    p1 = item.get("expense_payer_id")
    p2 = item.get("expense_payer_id_2")
    if p1 and p2:
        if p1 == p2:
            return [(p1, total)]
        half = round(total / 2, 2)
        return [(p1, half), (p2, round(total - half, 2))]
    single = p1 or p2
    return [(single, total)] if single else []


def allocate_by_name(items):
    """Агрегирует расход по именам плательщиков: [(имя, сумма), ...]."""
    totals = {}
    unassigned = 0.0
    for it in items:
        parts = split_item_amount(it)
        if not parts:
            unassigned = round(unassigned + round(float(it.get("sum") or 0), 2), 2)
            continue
        for pid, amount in parts:
            if pid == it.get("expense_payer_id"):
                name = it.get("expense_payer_name")
            else:
                name = it.get("expense_payer_name_2")
            name = name or f"ID {pid}"
            totals[name] = round(totals.get(name, 0.0) + amount, 2)
    rows = sorted(totals.items(), key=lambda x: (-x[1], x[0]))
    if unassigned:
        rows.append(("— не распределено —", unassigned))
    return rows