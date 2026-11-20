# test_cloud.py — автотест синхронизации (локальный WebDAV-сервер, реальное облако не трогается)
import base64, json, os, shutil, sqlite3, sys, tempfile, threading, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote, quote

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE); sys.path.insert(0, HERE)
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

PASS, FAIL = [], []
def check(name, fn):
    try:
        fn(); PASS.append(name); print(f"  ✅ {name}")
    except Exception as e:
        FAIL.append((name, e)); print(f"  ❌ {name}: {e}"); traceback.print_exc(limit=1)

ROOT = tempfile.mkdtemp(prefix="dav_root_")
USER, PWD = "user@test", "app-pass"

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _f(self):
        return os.path.join(ROOT, unquote(urlparse(self.path).path).lstrip("/"))
    def _auth(self):
        h = self.headers.get("Authorization", "")
        if not h.startswith("Basic "): return False
        try:
            u, p = base64.b64decode(h[6:]).decode().split(":", 1)
            return (u, p) == (USER, PWD)
        except Exception: return False
    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8"):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        if body: self.wfile.write(body)
    def do_PROPFIND(self):
        if not self._auth(): return self._send(401)
        f = self._f()
        if not os.path.exists(f): return self._send(404)
        entries = [f]
        if os.path.isdir(f) and self.headers.get("Depth", "1") == "1":
            entries += [os.path.join(f, n) for n in sorted(os.listdir(f))]
        xml = ['<?xml version="1.0" encoding="utf-8"?><D:multistatus xmlns:D="DAV:">']
        for e in entries:
            rel = os.path.relpath(e, ROOT).replace("\\", "/")
            href = "/" + ("" if rel == "." else quote(rel))
            isdir = os.path.isdir(e)
            size = 0 if isdir else os.path.getsize(e)
            xml.append(f"<D:response><D:href>{href}</D:href><D:propstat><D:prop>"
                       f"<D:resourcetype>{'<D:collection/>' if isdir else ''}</D:resourcetype>"
                       f"<D:getcontentlength>{size}</D:getcontentlength>"
                       f"<D:getlastmodified>Wed, 01 Jan 2026 00:00:00 GMT</D:getlastmodified>"
                       f"</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>")
        xml.append("</D:multistatus>")
        self._send(207, "".join(xml).encode(), "application/xml; charset=utf-8")
    def do_MKCOL(self):
        if not self._auth(): return self._send(401)
        f = self._f()
        if os.path.exists(f): return self._send(405)
        os.makedirs(f, exist_ok=True); self._send(201)
    def do_PUT(self):
        if not self._auth(): return self._send(401)
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n)
        f = self._f(); os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "wb") as fh: fh.write(data)
        self._send(201)
    def do_GET(self):
        if not self._auth(): return self._send(401)
        f = self._f()
        if not os.path.isfile(f): return self._send(404)
        with open(f, "rb") as fh: self._send(200, fh.read(), "application/octet-stream")
    def do_DELETE(self):
        if not self._auth(): return self._send(401)
        f = self._f()
        if os.path.isdir(f): shutil.rmtree(f)
        elif os.path.isfile(f): os.unlink(f)
        else: return self._send(404)
        self._send(204)

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}"

# изолируем данные пользователя
DATA = tempfile.mkdtemp(prefix="bc_data_")
import paths
paths.user_data_dir = lambda: DATA
import cloud_config, cloud_sync
from cloud_webdav import WebDav, WebDavError

SCHEMA = """
CREATE TABLE companies(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, address TEXT);
CREATE TABLE payers(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT);
CREATE TABLE item_names(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE);
CREATE TABLE receipts(id INTEGER PRIMARY KEY AUTOINCREMENT, row_number INTEGER, receipt_date TEXT,
 company_id INTEGER, total_amount REAL, in_process INTEGER, processed INTEGER, process_date TEXT, payer_id INTEGER);
CREATE TABLE receipt_items(id INTEGER PRIMARY KEY AUTOINCREMENT, receipt_id INTEGER, item_number INTEGER,
 item_name_id INTEGER, quantity REAL, price REAL, sum REAL, expense_payer_id INTEGER, expense_payer_id_2 INTEGER);
INSERT INTO payers(name) VALUES('Леша');
INSERT INTO receipts(row_number, receipt_date, total_amount) VALUES(1,'2026-10-31',11408.46);
"""
def make_db():
    p = paths.db_path()
    if os.path.exists(p): os.unlink(p)
    c = sqlite3.connect(p); c.executescript(SCHEMA); c.commit(); c.close()

def cfg(**kw):
    c = dict(cloud_config.DEFAULTS)
    c.update(url=URL, login=USER, password=PWD, folder="BASE_CHECK_TEST",
             timeout_sec=10, retries=2, copy_every_min=0)
    c.update(kw)
    cloud_config.save(c)
    return c

def S(**kw): return cloud_sync.CloudSync(cfg(**kw))

print("== 1. WebDAV ==")
make_db()
def t_ping():
    s = S(); assert s.dav.ping() is True; s.close()
check("ping c верными данными", t_ping)
def t_bad():
    s = cloud_sync.CloudSync(dict(cfg(), password="wrong"))
    try:
        s.dav.ping(); raise AssertionError("ожидался отказ")
    except WebDavError: pass
    finally: s.close()
check("неверный пароль -> понятная ошибка", t_bad)
def t_folder():
    s = S(); s.dav.ensure_folder("A/B/C"); assert s.dav.exists if False else True
    assert os.path.isdir(os.path.join(ROOT, "A", "B", "C")); s.close()
check("создание вложенных папок", t_folder)
def t_putget():
    s = S(); s.prepare(); s.dav.put(s.p("t.bin"), b"\x00\x01hello")
    assert s.dav.get(s.p("t.bin")) == b"\x00\x01hello"
    assert s.dav.get(s.p("nope.bin")) is None; s.close()
check("PUT/GET двоичных данных", t_putget)

print("== 2. Снимок и проверка базы ==")
def t_snap():
    data = cloud_sync.snapshot_db()
    assert cloud_sync.validate_db(data), "снимок не прошёл проверку"
    assert not cloud_sync.validate_db(b"not a database" * 20)
check("снимок валиден, мусор отклоняется", t_snap)

print("== 3. Синхронизация ==")
def t_push():
    s = S(); r = s.push(make_copy=True); s.close()
    assert r["action"] == "push"
    s2 = S()
    assert s2.dav.get(s2.p("receipts.db"))
    man = json.loads(s2.dav.get(s2.p("manifest.json")))
    assert man["db_sha256"] == r["sha"]
    st = json.loads(s2.dav.get(s2.p("settings.json")))
    assert "password" not in st and "login" not in st, st
    s2.close()
check("push: база+манифест+настройки без пароля", t_push)
def t_noop():
    s = S(); assert s.sync()["action"] == "noop"; s.close()
check("повторный sync -> noop", t_noop)
def t_local_change():
    c = sqlite3.connect(paths.db_path())
    c.execute("INSERT INTO receipts(row_number,receipt_date,total_amount) VALUES(2,'2026-11-01',500)")
    c.commit(); c.close()
    s = S(); assert s.sync()["action"] == "push"; s.close()
check("правка локально -> push", t_local_change)
def t_remote_change():
    other = tempfile.mkdtemp(prefix="other_")
    p = os.path.join(other, "r.db")
    c = sqlite3.connect(p); c.executescript(SCHEMA)
    c.execute("INSERT INTO receipts(row_number,receipt_date,total_amount) VALUES(99,'2026-11-02',777)")
    c.commit(); c.close()
    with open(p, "rb") as f: data = f.read()
    s = S(); s.dav.put(s.p("receipts.db"), data)
    s.dav.put(s.p("manifest.json"), json.dumps(
        {"rev": "other", "db_sha256": cloud_sync.sha256_bytes(data)}).encode())
    s.close()
    s = S(); r = s.sync(); s.close()
    assert r["action"] == "pull", r
    c = sqlite3.connect(paths.db_path())
    rows = c.execute("SELECT row_number FROM receipts ORDER BY row_number").fetchall()
    c.close()
    assert (99,) in rows, rows
    assert os.listdir(os.path.join(DATA, "backups")), "нет локального бэкапа"
check("правка в облаке -> pull + локальный бэкап", t_remote_change)
def t_conflict():
    c = sqlite3.connect(paths.db_path())
    c.execute("INSERT INTO receipts(row_number,receipt_date,total_amount) VALUES(50,'2026-11-03',1)")
    c.commit(); c.close()
    other = tempfile.mkdtemp(prefix="other2_"); p = os.path.join(other, "r.db")
    c = sqlite3.connect(p); c.executescript(SCHEMA)
    c.execute("INSERT INTO receipts(row_number,receipt_date,total_amount) VALUES(77,'2026-11-04',2)")
    c.commit(); c.close()
    with open(p, "rb") as f: data = f.read()
    s = S(); s.dav.put(s.p("receipts.db"), data)
    s.dav.put(s.p("manifest.json"), json.dumps(
        {"rev": "other2", "db_sha256": cloud_sync.sha256_bytes(data)}).encode()); s.close()
    s = S(); r = s.sync(); s.close()
    assert r["action"] == "conflict", r
    s = S()
    names = [x["name"] for x in s.dav.list(f"{s.folder}/history")]
    s.close()
    assert any(n.startswith("conflict_") for n in names), names
check("конфликт -> копия локальной версии в history", t_conflict)
def t_rotate():
    s = S(keep_copies=3)
    for _ in range(6):
        s.make_copy(cloud_sync.snapshot_db())
    names = [x["name"] for x in s.dav.list(f"{s.folder}/history") if x["name"].endswith(".db")]
    s.close()
    assert len(names) <= 3, names
check("ротация копий (keep_copies=3)", t_rotate)
def t_diag():
    s = S(); txt = s.diagnostics(); s.close()
    assert "Связь: OK" in txt and "Копий в облаке" in txt, txt
check("полная диагностика", t_diag)

srv.shutdown()
print("\n===== ИТОГ =====")
print(f"Пройдено: {len(PASS)}   Провалено: {len(FAIL)}")
for n, e in FAIL: print(f"  ❌ {n}: {e}")
sys.exit(1 if FAIL else 0)