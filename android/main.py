# android/main.py — «Программа обработки чеков» для Android (Kivy)
import logging
import os
import sys
import threading
import traceback
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import NumericProperty, ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox

import paths
import database as db
import date_utils
import cloud_config
import cloud_sync
import receipt_excel
import ocr_service
from expense_utils import allocate_by_name
from config import APP_TITLE, APP_VERSION
import platform_android as pa

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    handlers=[logging.FileHandler(paths.log_path(), encoding="utf-8")])
log = logging.getLogger("mobile")

NONE = "—"


def num(text, default=0.0):
    try:
        return float(str(text).replace(",", ".").strip() or default)
    except ValueError:
        return default


def btn(text, fn, h=48):
    b = Button(text=text, size_hint_y=None, height=dp(h))
    b.bind(on_release=lambda *_: fn())
    return b


def field(value="", hint="", numeric=False, h=44):
    t = TextInput(text=str(value), hint_text=hint, multiline=False,
                  size_hint_y=None, height=dp(h))
    if numeric:
        t.input_filter = "float"
    return t


def spinner(values, current=None, h=44):
    vals = list(values) or [NONE]
    return Spinner(text=current if current in vals else vals[0],
                   values=vals, size_hint_y=None, height=dp(h))


def scroll_list():
    rv = RecycleView()
    bl = RecycleBoxLayout(default_size=(None, dp(56)), default_size_hint=(1, None),
                          size_hint_y=None, orientation="vertical", spacing=dp(2))
    bl.bind(minimum_height=bl.setter("height"))
    rv.add_widget(bl)
    rv.viewclass = Row
    return rv


class Row(Button):
    owner = ObjectProperty(None, allownone=True)
    idx = NumericProperty(-1)

    def on_release(self):
        if self.owner is not None:
            self.owner.on_row(self.idx)


def popup(title, content, size=(0.95, 0.85)):
    p = Popup(title=title, content=content, size_hint=size, auto_dismiss=False)
    p.open()
    return p


def info(title, text):
    box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
    sv = ScrollView()
    lbl = Label(text=text, halign="left", valign="top", size_hint_y=None)
    lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
    lbl.bind(texture_size=lambda i, s: setattr(i, "height", s[1]))
    sv.add_widget(lbl)
    box.add_widget(sv)
    p = popup(title, box, (0.92, 0.7))
    box.add_widget(btn("Закрыть", p.dismiss))


def run_bg(work, done=None):
    def worker():
        try:
            res = work()
            err = None
        except Exception as e:
            log.error("bg: %s\n%s", e, traceback.format_exc())
            res, err = None, str(e)
        if done:
            Clock.schedule_once(lambda *_: done(res, err), 0)
    threading.Thread(target=worker, daemon=True).start()


def names(table):
    return [r["name"] for r in db.fetch_all(table)]


def id_by_name(table, name):
    if not name or name == NONE:
        return None
    for r in db.fetch_all(table):
        if r["name"] == name:
            return r["id"]
    return db.insert(table, {"name": name})


# ============================ ЭКРАНЫ ============================

class Base(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.root_box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        self.add_widget(self.root_box)

    def header(self, title, back=None):
        bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        if back:
            b = Button(text="‹ Назад", size_hint_x=None, width=dp(110))
            b.bind(on_release=lambda *_: back())
            bar.add_widget(b)
        bar.add_widget(Label(text=f"[b]{title}[/b]", markup=True))
        self.root_box.add_widget(bar)

    def on_row(self, idx):
        pass


class ReceiptsScreen(Base):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.rows = []
        self.header(f"{APP_TITLE}  v{APP_VERSION}")
        f = GridLayout(cols=2, size_hint_y=None, height=dp(96), spacing=dp(4))
        self.d_from = field("01-01-2000", "с дд-мм-гггг")
        self.d_to = field("31-12-2099", "по дд-мм-гггг")
        self.cb_company = spinner([NONE] + names("companies"))
        f.add_widget(self.d_from); f.add_widget(self.d_to)
        f.add_widget(Label(text="Компания:", size_hint_y=None, height=dp(44)))
        f.add_widget(self.cb_company)
        self.root_box.add_widget(f)
        self.rv = scroll_list()
        self.root_box.add_widget(self.rv)
        self.status = Label(text="", size_hint_y=None, height=dp(24))
        self.root_box.add_widget(self.status)
        g = GridLayout(cols=3, size_hint_y=None, height=dp(150), spacing=dp(4))
        for t, fn in (("Новый чек", self.new_receipt), ("Сканировать", self.go_scan),
                      ("Справочники", self.go_dirs), ("Расчёт оплат", self.go_calc),
                      ("Облако", self.go_cloud), ("Обновить", self.reload)):
            g.add_widget(btn(t, fn))
        self.root_box.add_widget(g)

    def on_pre_enter(self, *a):
        self.cb_company.values = [NONE] + names("companies")
        self.reload()

    def reload(self):
        f = {}
        d1 = date_utils.to_iso(self.d_from.text)
        d2 = date_utils.to_iso(self.d_to.text)
        if d1 and d1 != "2000-01-01":
            f["date_from"] = d1
        if d2 and d2 != "2099-12-31":
            f["date_to"] = d2
        cid = id_by_name("companies", self.cb_company.text) if self.cb_company.text != NONE else None
        if self.cb_company.text != NONE:
            f["company_id"] = cid
        self.rows = db.get_receipts_filtered(f)
        data = []
        for i, r in enumerate(self.rows):
            data.append({"text": f"{r['row_number']}  {date_utils.to_display(r['receipt_date'])}  "
                                 f"{r.get('company_name') or ''}\n"
                                 f"{r['total_amount']:.2f} ₽   платил: {r.get('payer_name') or '—'}",
                         "owner": self, "idx": i, "halign": "left"})
        self.rv.data = data
        self.status.text = f"Чеков: {len(self.rows)}"

    def on_row(self, idx):
        if 0 <= idx < len(self.rows):
            s = self.manager.get_screen("receipt")
            s.load(self.rows[idx]["id"])
            self.manager.current = "receipt"

    def new_receipt(self):
        rid = db.insert("receipts", {
            "row_number": db.next_row_number(),
            "receipt_date": date_utils.to_iso(self.d_from.text) if False else
                            __import__("datetime").date.today().isoformat(),
            "company_id": None, "total_amount": 0, "in_process": 0, "processed": 0,
            "payer_id": None})
        s = self.manager.get_screen("receipt")
        s.load(rid)
        self.manager.current = "receipt"

    def go_scan(self):
        self.manager.current = "scan"

    def go_dirs(self):
        self.manager.current = "dirs"

    def go_calc(self):
        self.manager.current = "calc"

    def go_cloud(self):
        self.manager.current = "cloud"


class ReceiptScreen(Base):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.rid = None
        self.items = []
        self.header("Чек", back=lambda: setattr(self.manager, "current", "receipts"))
        g = GridLayout(cols=2, size_hint_y=None, height=dp(144), spacing=dp(4))
        self.ed_date = field("", "дд-мм-гггг")
        self.cb_company = spinner([NONE])
        self.cb_payer = spinner([NONE])
        g.add_widget(Label(text="Дата:")); g.add_widget(self.ed_date)
        g.add_widget(Label(text="Компания:")); g.add_widget(self.cb_company)
        g.add_widget(Label(text="Кто платил:")); g.add_widget(self.cb_payer)
        self.root_box.add_widget(g)
        self.rv = scroll_list()
        self.root_box.add_widget(self.rv)
        self.lbl_total = Label(text="", size_hint_y=None, height=dp(26))
        self.lbl_split = Label(text="", size_hint_y=None, height=dp(44), halign="left")
        self.lbl_split.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        self.root_box.add_widget(self.lbl_total)
        self.root_box.add_widget(self.lbl_split)
        b = GridLayout(cols=3, size_hint_y=None, height=dp(100), spacing=dp(4))
        for t, fn in (("Сохранить шапку", self.save_head), ("+ Позиция", self.add_item),
                      ("Excel", self.export), ("Удалить чек", self.delete),
                      ("В обработку", self.toggle_process), ("Обработан", self.toggle_done)):
            b.add_widget(btn(t, fn))
        self.root_box.add_widget(b)

    def load(self, rid):
        self.rid = rid
        self.cb_company.values = [NONE] + names("companies")
        self.cb_payer.values = [NONE] + names("payers")
        r = next((x for x in db.fetch_all("receipts") if x["id"] == rid), None)
        if not r:
            return
        self.ed_date.text = date_utils.to_display(r["receipt_date"])
        self.cb_company.text = next((c["name"] for c in db.fetch_all("companies")
                                     if c["id"] == r["company_id"]), NONE)
        self.cb_payer.text = next((p["name"] for p in db.fetch_all("payers")
                                   if p["id"] == r["payer_id"]), NONE)
        self.reload_items()

    def reload_items(self):
        self.items = db.get_items_for_receipt(self.rid)
        data = []
        total = 0.0
        for i, it in enumerate(self.items):
            total += it["sum"] or 0
            p1 = it.get("expense_payer_name") or "—"
            p2 = it.get("expense_payer_name_2") or ""
            data.append({"text": f"{it['item_number']}. {it.get('item_name') or ''}\n"
                                 f"{it['quantity']} × {it['price']:.2f} = {it['sum']:.2f}   "
                                 f"[{p1}{' / ' + p2 if p2 else ''}]",
                         "owner": self, "idx": i, "halign": "left"})
        self.rv.data = data
        self.lbl_total.text = f"Итого: {total:.2f} ₽"
        self.lbl_split.text = "Пополам: " + " | ".join(
            f"{n}: {a:.2f}" for n, a in allocate_by_name(self.items))
        db.update("receipts", self.rid, {"total_amount": round(total, 2)})

    def on_row(self, idx):
        if 0 <= idx < len(self.items):
            self.item_popup(self.items[idx])

    def save_head(self):
        db.update("receipts", self.rid, {
            "receipt_date": date_utils.to_iso(self.ed_date.text),
            "company_id": id_by_name("companies", self.cb_company.text),
            "payer_id": id_by_name("payers", self.cb_payer.text)})
        pa.toast("Чек сохранён")

    def add_item(self):
        nid = id_by_name("item_names", "Новая позиция")
        iid = db.insert("receipt_items", {
            "receipt_id": self.rid, "item_number": len(self.items) + 1,
            "item_name_id": nid, "quantity": 1, "price": 0, "sum": 0,
            "expense_payer_id": None, "expense_payer_id_2": None})
        self.reload_items()
        it = next(x for x in self.items if x["id"] == iid)
        self.item_popup(it)

    def item_popup(self, it):
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        g = GridLayout(cols=2, spacing=dp(4), size_hint_y=None, height=dp(330))
        sp_name = spinner(names("item_names"), it.get("item_name"))
        ed_new = field("", "или введите новое наименование")
        ed_q = field(it["quantity"], numeric=True)
        ed_p = field(f"{it['price']:.2f}", numeric=True)
        ed_s = field(f"{it['sum']:.2f}", numeric=True)
        sp_p1 = spinner([NONE] + names("payers"), it.get("expense_payer_name") or NONE)
        sp_p2 = spinner([NONE] + names("payers"), it.get("expense_payer_name_2") or NONE)
        for cap, w in (("Наименование:", sp_name), ("Новое имя:", ed_new),
                       ("Кол-во:", ed_q), ("Цена:", ed_p), ("Сумма:", ed_s),
                       ("Чей расход:", sp_p1), ("Чей расход 2:", sp_p2)):
            g.add_widget(Label(text=cap, size_hint_y=None, height=dp(44)))
            g.add_widget(w)
        box.add_widget(g)

        def recalc(*_):
            ed_s.text = f"{num(ed_q.text) * num(ed_p.text):.2f}"
        ed_q.bind(text=recalc)
        ed_p.bind(text=recalc)

        p = popup("Позиция", box)

        def save():
            name = ed_new.text.strip() or sp_name.text
            nid = id_by_name("item_names", name)
            q, pr, s = num(ed_q.text, 1), num(ed_p.text), num(ed_s.text)
            db.update("receipt_items", it["id"], {
                "item_name_id": nid, "quantity": q, "price": pr, "sum": round(s, 2),
                "expense_payer_id": id_by_name("payers", sp_p1.text),
                "expense_payer_id_2": id_by_name("payers", sp_p2.text)})
            p.dismiss()
            self.reload_items()

        def delete():
            db.delete("receipt_items", it["id"])
            p.dismiss()
            self.reload_items()

        row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
        row.add_widget(btn("Сохранить", save))
        row.add_widget(btn("Удалить", delete))
        row.add_widget(btn("Отмена", p.dismiss))
        box.add_widget(row)

    def delete(self):
        db.delete_receipt_full(self.rid)
        self.manager.current = "receipts"

    def toggle_process(self):
        r = next(x for x in db.fetch_all("receipts") if x["id"] == self.rid)
        db.update("receipts", self.rid, {"in_process": 0 if r["in_process"] else 1})
        pa.toast("Флаг «В обработку» переключён")

    def toggle_done(self):
        r = next(x for x in db.fetch_all("receipts") if x["id"] == self.rid)
        db.update("receipts", self.rid, {"processed": 0 if r["processed"] else 1})
        pa.toast("Флаг «Обработан» переключён")

    def export(self):
        r = next(x for x in db.fetch_all("receipts") if x["id"] == self.rid)
        r["company_name"] = next((c["name"] for c in db.fetch_all("companies")
                                  if c["id"] == r["company_id"]), "")
        r["payer_name"] = next((p["name"] for p in db.fetch_all("payers")
                                if p["id"] == r["payer_id"]), "")
        tmp = os.path.join(pa.exports_dir(), "receipt.xlsx")
        receipt_excel.export_receipt(tmp, r, db.get_items_for_receipt(self.rid))
        with open(tmp, "rb") as f:
            data = f.read()
        name = f"чек_{r['row_number']}_{date_utils.to_display(r['receipt_date'])}.xlsx"
        try:
            where = pa.save_to_downloads(name, data)
            info("Excel", f"Файл сохранён:\n{where}")
        except Exception as e:
            info("Ошибка", str(e))


class DirsScreen(Base):
    TABLES = {"Компании": "companies", "Плательщики": "payers", "Наименования": "item_names"}

    def __init__(self, **kw):
        super().__init__(**kw)
        self.rows = []
        self.header("Справочники", back=lambda: setattr(self.manager, "current", "receipts"))
        self.sp = spinner(list(self.TABLES))
        self.sp.bind(text=lambda *_: self.reload())
        self.root_box.add_widget(self.sp)
        self.rv = scroll_list()
        self.root_box.add_widget(self.rv)
        g = GridLayout(cols=2, size_hint_y=None, height=dp(50), spacing=dp(4))
        g.add_widget(btn("Добавить", self.add))
        g.add_widget(btn("Удалить выбранный", self.delete_selected))
        self.root_box.add_widget(g)
        self.selected = None

    def on_pre_enter(self, *a):
        self.reload()

    def reload(self):
        self.rows = db.fetch_all(self.TABLES[self.sp.text])
        self.rv.data = [{"text": r["name"], "owner": self, "idx": i, "halign": "left"}
                        for i, r in enumerate(self.rows)]

    def on_row(self, idx):
        self.selected = self.rows[idx]
        pa.toast("Выбрано: " + self.rows[idx]["name"])

    def add(self):
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        ed = field("", "Наименование")
        box.add_widget(ed)
        p = popup("Добавить", box, (0.9, 0.4))

        def ok():
            if ed.text.strip():
                db.insert(self.TABLES[self.sp.text], {"name": ed.text.strip()})
            p.dismiss()
            self.reload()
        box.add_widget(btn("Сохранить", ok))

    def delete_selected(self):
        if self.selected:
            db.delete(self.TABLES[self.sp.text], self.selected["id"])
            self.selected = None
            self.reload()


class CalcScreen(Base):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.header("Расчёт оплат", back=lambda: setattr(self.manager, "current", "receipts"))
        self.txt = Label(text="", halign="left", valign="top", size_hint_y=None)
        self.txt.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        self.txt.bind(texture_size=lambda i, s: setattr(i, "height", s[1]))
        sv = ScrollView()
        sv.add_widget(self.txt)
        self.root_box.add_widget(sv)
        g = GridLayout(cols=2, size_hint_y=None, height=dp(50), spacing=dp(4))
        g.add_widget(btn("Пересчитать", self.reload))
        g.add_widget(btn("Excel", self.export))
        self.root_box.add_widget(g)

    def on_pre_enter(self, *a):
        self.reload()

    def reload(self):
        totals = db.get_payer_totals({})
        debts = db.get_debts({})
        lines = ["[b]Итоги по плательщикам[/b]"]
        for t in totals:
            lines.append(f"{t['name']}: расход {t['consumed']:.2f} · оплатил {t['paid']:.2f} "
                         f"· баланс {t['balance']:.2f}")
        lines.append("")
        lines.append("[b]Кто кому должен[/b]")
        for d in debts:
            lines.append(f"{d['debtor']} → {d['creditor']}: {d['amount']:.2f}")
        self.txt.markup = True
        self.txt.text = "\n".join(lines) or "Нет данных"

    def export(self):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Итоги"
        ws.append(["Плательщик", "Расход (с делением)", "Оплатил", "Баланс"])
        for t in db.get_payer_totals({}):
            ws.append([t["name"], t["consumed"], t["paid"], t["balance"]])
        ws2 = wb.create_sheet("Долги")
        ws2.append(["Кто должен", "Кому", "Сумма"])
        for d in db.get_debts({}):
            ws2.append([d["debtor"], d["creditor"], d["amount"]])
        tmp = os.path.join(pa.exports_dir(), "calc.xlsx")
        wb.save(tmp)
        with open(tmp, "rb") as f:
            data = f.read()
        try:
            info("Excel", "Сохранено: " + pa.save_to_downloads("расчёт_оплат.xlsx", data))
        except Exception as e:
            info("Ошибка", str(e))


class ScanScreen(Base):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.data = None
        self.header("Сканирование чека", back=lambda: setattr(self.manager, "current", "receipts"))
        self.status = Label(text="Выберите PDF или фото чека", size_hint_y=None, height=dp(40))
        self.root_box.add_widget(self.status)
        self.txt = Label(text="", halign="left", valign="top", size_hint_y=None)
        self.txt.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        self.txt.bind(texture_size=lambda i, s: setattr(i, "height", s[1]))
        sv = ScrollView()
        sv.add_widget(self.txt)
        self.root_box.add_widget(sv)
        g = GridLayout(cols=2, size_hint_y=None, height=dp(100), spacing=dp(4))
        g.add_widget(btn("Выбрать PDF", lambda: pa.pick_file(self.on_file, "application/pdf")))
        g.add_widget(btn("Выбрать фото", lambda: pa.pick_file(self.on_file, "image/*")))
        g.add_widget(btn("Сохранить чек", self.save))
        g.add_widget(btn("Отмена", lambda: setattr(self.manager, "current", "receipts")))
        self.root_box.add_widget(g)

    def on_file(self, path):
        if not path:
            self.status.text = "Файл не выбран"
            return
        self.status.text = "Распознавание…"

        def work():
            if path.lower().endswith(".pdf"):
                text = ocr_service.extract_text_from_pdf(path)
                if not text:
                    parts = []
                    if pa.IS_ANDROID:
                        for bmp in pa.render_pdf_bitmaps(path):
                            parts.append(pa.ocr_bitmap(bmp))
                    text = "\n".join(parts)
            else:
                text = pa.ocr_image_file(path) if pa.IS_ANDROID else ocr_service.extract_text(path)
            return ocr_service.parse_receipt(text or "")

        def done(res, err):
            if err:
                self.status.text = "Ошибка"
                info("Ошибка распознавания", err)
                return
            self.data = res
            self.status.text = f"Позиций: {len(res['items'])} · итого {res['total']:.2f}"
            lines = [f"Дата: {res['date'] or '—'}", f"Компания: {res['company'] or '—'}",
                     f"Итого: {res['total']:.2f}", f"Скидки: {res['discount_total']:.2f}", ""]
            for it in res["items"]:
                lines.append(f"{it['name']} — {it['qty']} × {it['price']:.2f} = {it['sum']:.2f}")
            for w in res.get("warnings", []):
                lines.append("⚠ " + w)
            self.txt.text = "\n".join(lines)
        run_bg(work, done)

    def save(self):
        if not self.data:
            pa.toast("Сначала распознайте чек")
            return
        d = self.data
        cid = id_by_name("companies", d["company"]) if d["company"] else None
        rid = db.insert("receipts", {
            "row_number": db.next_row_number(),
            "receipt_date": date_utils.to_iso(d["date"]) or __import__("datetime").date.today().isoformat(),
            "company_id": cid, "total_amount": round(d["total"], 2),
            "in_process": 0, "processed": 0, "payer_id": None})
        for i, it in enumerate(d["items"], 1):
            nid = id_by_name("item_names", it["name"])
            db.insert("receipt_items", {
                "receipt_id": rid, "item_number": i, "item_name_id": nid,
                "quantity": it["qty"], "price": it["price"], "sum": round(it["sum"], 2),
                "expense_payer_id": None, "expense_payer_id_2": None})
        s = self.manager.get_screen("receipt")
        s.load(rid)
        self.manager.current = "receipt"
        pa.toast("Чек сохранён — проставьте «Чей расход»")


class CloudScreen(Base):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cfg = cloud_config.load()
        self.header("Облако Mail.ru", back=lambda: setattr(self.manager, "current", "receipts"))
        g = GridLayout(cols=2, size_hint_y=None, height=dp(400), spacing=dp(4))
        self.ed_url = field(self.cfg["url"])
        self.ed_login = field(self.cfg["login"])
        self.ed_pass = field(self.cfg["password"]); self.ed_pass.password = True
        self.ed_folder = field(self.cfg["folder"])
        self.sp_interval = field(self.cfg["interval_min"], numeric=True)
        self.sp_copies = field(self.cfg["keep_copies"], numeric=True)
        self.sp_timeout = field(self.cfg["timeout_sec"], numeric=True)
        self.sp_retries = field(self.cfg["retries"], numeric=True)
        for cap, w in (("Адрес WebDAV:", self.ed_url), ("Логин (почта):", self.ed_login),
                       ("Пароль приложения:", self.ed_pass), ("Папка:", self.ed_folder),
                       ("Период, мин:", self.sp_interval), ("Копий хранить:", self.sp_copies),
                       ("Таймаут, с:", self.sp_timeout), ("Повторов:", self.sp_retries)):
            g.add_widget(Label(text=cap, size_hint_y=None, height=dp(44)))
            g.add_widget(w)
        sv = ScrollView(size_hint_y=None, height=dp(300))
        g.size_hint_y = None
        g.bind(minimum_height=g.setter("height"))
        sv.add_widget(g)
        self.root_box.add_widget(sv)
        self.status = Label(text="", size_hint_y=None, height=dp(60), halign="left")
        self.status.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        self.root_box.add_widget(self.status)
        b = GridLayout(cols=2, size_hint_y=None, height=dp(200), spacing=dp(4))
        for t, fn in (("Сохранить", self.save_cfg), ("Проверить связь", self.check),
                      ("Синхронизировать", lambda: self.run("auto")),
                      ("Скачать из облака", lambda: self.run("pull")),
                      ("Загрузить в облако", lambda: self.run("push")),
                      ("Диагностика", self.diag)):
            b.add_widget(btn(t, fn))
        self.root_box.add_widget(b)

    def save_cfg(self):
        c = dict(self.cfg)
        c.update(url=self.ed_url.text.strip(), login=self.ed_login.text.strip(),
                 password=self.ed_pass.text, folder=self.ed_folder.text.strip() or "BASE_CHECK",
                 interval_min=int(num(self.sp_interval.text, 15)),
                 keep_copies=int(num(self.sp_copies.text, 10)),
                 timeout_sec=int(num(self.sp_timeout.text, 300)),
                 retries=int(num(self.sp_retries.text, 4)))
        cloud_config.save(c)
        self.cfg = c
        self.status.text = "Сохранено: " + cloud_config.config_path()

    def _sync(self):
        return cloud_sync.CloudSync(self.cfg)

    def check(self):
        self.save_cfg()

        def work():
            s = self._sync()
            try:
                s.dav.ping()
                s.prepare()
                return "Связь OK, папка доступна"
            finally:
                s.close()
        run_bg(work, lambda r, e: setattr(self.status, "text", e or r))

    def run(self, mode):
        self.save_cfg()

        def work():
            s = self._sync()
            try:
                return s.push() if mode == "push" else s.pull() if mode == "pull" else s.sync()
            finally:
                s.close()

        def done(res, err):
            if err:
                self.status.text = "Ошибка: " + err
                return
            self.status.text = f"{res.get('action')} · {res.get('size', 0)} байт"
            if res.get("action") == "conflict":
                info("Конфликт", "База менялась и здесь, и в облаке.\n"
                                 "Ваша версия сохранена в history/conflict_…db,\n"
                                 "рабочей стала облачная.")
            App.get_running_app().refresh_all()
        run_bg(work, done)

    def diag(self):
        self.save_cfg()

        def work():
            s = self._sync()
            try:
                return s.diagnostics()
            finally:
                s.close()
        run_bg(work, lambda r, e: info("Диагностика", e or r))


# ============================ ПРИЛОЖЕНИЕ ============================

class BaseCheckApp(App):
    title = APP_TITLE

    def build(self):
        Window.softinput_mode = "below_target"
        pa.request_perms()
        pa.ensure_tessdata()
        db.init_db()
        # OCR на Android — через tesseract4android вместо CLI
        if pa.IS_ANDROID:
            ocr_service._ocr_image = lambda img: pa.ocr_bitmap(img)
        self.sm = ScreenManager()
        self.sm.add_widget(ReceiptsScreen(name="receipts"))
        self.sm.add_widget(ReceiptScreen(name="receipt"))
        self.sm.add_widget(ScanScreen(name="scan"))
        self.sm.add_widget(DirsScreen(name="dirs"))
        self.sm.add_widget(CalcScreen(name="calc"))
        self.sm.add_widget(CloudScreen(name="cloud"))
        self.sm.current = "receipts"
        return self.sm

    def refresh_all(self):
        for name in ("receipts", "dirs", "calc"):
            s = self.sm.get_screen(name)
            if hasattr(s, "reload"):
                s.reload()

    def _sync_bg(self, mode):
        cfg = cloud_config.load()
        if not cloud_config.is_configured(cfg):
            return

        def work():
            s = cloud_sync.CloudSync(cfg)
            try:
                s.dav.timeout = 60
                return s.push() if mode == "push" else s.sync()
            finally:
                s.close()

        def done(res, err):
            if err:
                log.warning("Синхронизация: %s", err)
                return
            log.info("Синхронизация %s: %s", mode, res)
            self.refresh_all()
            if res and res.get("action") in ("pull", "conflict"):
                pa.toast("База обновлена из облака")
        run_bg(work, done)

    def on_start(self):
        cfg = cloud_config.load()
        if cfg.get("sync_on_start"):
            self._sync_bg("auto")
        if cfg.get("autosync"):
            Clock.schedule_interval(lambda *_: self._sync_bg("auto"),
                                    max(60, int(cfg.get("interval_min", 15)) * 60))

    def on_pause(self):
        cfg = cloud_config.load()
        if cfg.get("sync_on_exit"):
            self._sync_bg("push")
        return True

    def on_resume(self):
        cfg = cloud_config.load()
        if cfg.get("sync_on_start"):
            self._sync_bg("auto")

    def on_stop(self):
        cfg = cloud_config.load()
        if cfg.get("sync_on_exit"):
            try:
                s = cloud_sync.CloudSync(cfg)
                s.dav.timeout = 30
                s.sync()
                s.close()
            except Exception as e:
                log.warning("Синхронизация при выходе: %s", e)


if __name__ == "__main__":
    BaseCheckApp().run()
