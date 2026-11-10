# database.py
import sqlite3
from config import DB_NAME

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

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
        FOREIGN KEY(receipt_id) REFERENCES receipts(id) ON DELETE CASCADE,
        FOREIGN KEY(item_name_id) REFERENCES item_names(id),
        FOREIGN KEY(expense_payer_id) REFERENCES payers(id)
    );
    """)
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
        SELECT ri.*, i.name AS item_name, p.name AS expense_payer_name
        FROM receipt_items ri
        LEFT JOIN item_names i ON i.id=ri.item_name_id
        LEFT JOIN payers p ON p.id=ri.expense_payer_id
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