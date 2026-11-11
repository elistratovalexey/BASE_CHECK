# database.py
import sqlite3
from config import DB_NAME
from expense_utils import split_item_amount


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(cur, table, column):
    cur.execute(f"PRAGMA table_info({table})")
    return any(r[1] == column for r in cur.fetchall())


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        address TEXT
    );
    CREATE TABLE IF NOT EXISTS payers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS item_names (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        row_number INTEGER,
        receipt_date TEXT,
        company_id INTEGER,
        total_amount REAL DEFAULT 0,
        in_process INTEGER DEFAULT 0,
        processed INTEGER DEFAULT 0,
        process_date TEXT,
        payer_id INTEGER,
        FOREIGN KEY(company_id) REFERENCES companies(id),
        FOREIGN KEY(payer_id) REFERENCES payers(id)
    );
    CREATE TABLE IF NOT EXISTS receipt_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_id INTEGER,
        item_number INTEGER,
        item_name_id INTEGER,
        quantity REAL DEFAULT 1,
        price REAL DEFAULT 0,
        sum REAL DEFAULT 0,
        expense_payer_id INTEGER,
        expense_payer_id_2 INTEGER,
        FOREIGN KEY(receipt_id) REFERENCES receipts(id) ON DELETE CASCADE,
        FOREIGN KEY(item_name_id) REFERENCES item_names(id),
        FOREIGN KEY(expense_payer_id) REFERENCES payers(id),
        FOREIGN KEY(expense_payer_id_2) REFERENCES payers(id)
    );
    """)
    # миграция существующих баз: второе поле «Чей расход»
    if not _column_exists(cur, "receipt_items", "expense_payer_id_2"):
        cur.execute("ALTER TABLE receipt_items ADD COLUMN expense_payer_id_2 INTEGER REFERENCES payers(id)")
    conn.commit()
    conn.close()


# --- CRUD ---
def fetch_all(table):
    conn = get_connection()
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert(table, data: dict):
    conn = get_connection()
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", list(data.values()))
    conn.commit()
    last = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return last


def update(table, id_val, data: dict):
    conn = get_connection()
    sets = ", ".join([f"{k}=?" for k in data.keys()])
    conn.execute(f"UPDATE {table} SET {sets} WHERE id=?", list(data.values()) + [id_val])
    conn.commit()
    conn.close()


def delete(table, id_val):
    conn = get_connection()
    conn.execute(f"DELETE FROM {table} WHERE id=?", (id_val,))
    conn.commit()
    conn.close()


def next_row_number():
    conn = get_connection()
    r = conn.execute("SELECT COALESCE(MAX(row_number),0)+1 FROM receipts").fetchone()[0]
    conn.close()
    return r


def get_receipts_filtered(filters):
    conn = get_connection()
    sql = """
        SELECT r.*, c.name AS company_name, p.name AS payer_name
        FROM receipts r
        LEFT JOIN companies c ON c.id=r.company_id
        LEFT JOIN payers p ON p.id=r.payer_id
        WHERE 1=1
    """
    params = []
    if filters.get("date_from"):
        sql += " AND r.receipt_date >= ?"; params.append(filters["date_from"])
    if filters.get("date_to"):
        sql += " AND r.receipt_date <= ?"; params.append(filters["date_to"])
    if filters.get("in_process") is not None:
        sql += " AND r.in_process = ?"; params.append(int(filters["in_process"]))
    if filters.get("processed") is not None:
        sql += " AND r.processed = ?"; params.append(int(filters["processed"]))
    if filters.get("company_id"):
        sql += " AND r.company_id = ?"; params.append(filters["company_id"])
    sql += " ORDER BY r.row_number"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_items_for_receipt(receipt_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT ri.*, i.name AS item_name,
               p1.name AS expense_payer_name,
               p2.name AS expense_payer_name_2
        FROM receipt_items ri
        LEFT JOIN item_names i ON i.id=ri.item_name_id
        LEFT JOIN payers p1 ON p1.id=ri.expense_payer_id
        LEFT JOIN payers p2 ON p2.id=ri.expense_payer_id_2
        WHERE ri.receipt_id=?
        ORDER BY ri.item_number
    """, (receipt_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_receipt_full(receipt_id):
    conn = get_connection()
    conn.execute("DELETE FROM receipt_items WHERE receipt_id=?", (receipt_id,))
    conn.execute("DELETE FROM receipts WHERE id=?", (receipt_id,))
    conn.commit()
    conn.close()


# --- расчёт оплат с делением расхода пополам ---
def _iter_receipt_items(filters=None):
    for r in get_receipts_filtered(dict(filters or {})):
        yield r, get_items_for_receipt(r["id"])


def get_payer_totals(filters=None):
    """[{'payer_id','name','consumed','paid','balance'}]
    consumed — расход с делением пополам, paid — сколько оплатил, balance = paid - consumed.
    """
    names = {p["id"]: p["name"] for p in fetch_all("payers")}
    consumed, paid = {}, {}
    for r, items in _iter_receipt_items(filters):
        creditor = r.get("payer_id")
        for it in items:
            amount = round(float(it.get("sum") or 0), 2)
            if creditor:
                paid[creditor] = round(paid.get(creditor, 0.0) + amount, 2)
            for pid, part in split_item_amount(it):
                consumed[pid] = round(consumed.get(pid, 0.0) + part, 2)
    rows = []
    for pid in set(list(consumed) + list(paid)):
        c = round(consumed.get(pid, 0.0), 2)
        p = round(paid.get(pid, 0.0), 2)
        rows.append({"payer_id": pid, "name": names.get(pid, f"ID {pid}"),
                     "consumed": c, "paid": p, "balance": round(p - c, 2)})
    rows.sort(key=lambda x: x["name"])
    return rows


def get_debts(filters=None):
    """[{'debtor','creditor','amount'}] — кто кому должен, со взаимозачётом."""
    names = {p["id"]: p["name"] for p in fetch_all("payers")}
    matrix = {}
    for r, items in _iter_receipt_items(filters):
        creditor = r.get("payer_id")
        if not creditor:
            continue
        for it in items:
            for debtor, part in split_item_amount(it):
                if debtor == creditor or not part:
                    continue
                key = (debtor, creditor)
                matrix[key] = round(matrix.get(key, 0.0) + part, 2)
    result, seen = [], set()
    for (d, c), amount in matrix.items():
        if (d, c) in seen:
            continue
        seen.add((d, c)); seen.add((c, d))
        net = round(amount - matrix.get((c, d), 0.0), 2)
        if net > 0:
            result.append({"debtor": names.get(d, str(d)),
                           "creditor": names.get(c, str(c)), "amount": net})
        elif net < 0:
            result.append({"debtor": names.get(c, str(c)),
                           "creditor": names.get(d, str(d)), "amount": round(-net, 2)})
    result.sort(key=lambda x: (-x["amount"], x["debtor"]))
    return result