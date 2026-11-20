# ui_cloud_dialog.py
"""Окно «Облако Mail.ru — синхронизация базы»: Подключение / Синхронизация / Публикация версии."""
import json
import logging
import os
import subprocess
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                             QLineEdit, QSpinBox, QCheckBox, QPushButton, QTabWidget,
                             QWidget, QTextEdit, QMessageBox, QFileDialog, QGroupBox)

import paths
import cloud_config
import cloud_sync
from cloud_webdav import WebDav, WebDavError
from config import APP_VERSION

logger = logging.getLogger(__name__)


def _ver_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except Exception:
        return (0,)


def open_settings_folder():
    d = paths.user_data_dir()
    try:
        if sys.platform.startswith("win"):
            os.startfile(d)          # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])
    except Exception as e:
        logger.warning("Не удалось открыть папку: %s", e)


class CloudDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Облако Mail.ru — синхронизация базы")
        self.resize(860, 620)
        self.cfg = cloud_config.load()
        self._build()
        self._load_to_ui()

    # ---------- интерфейс ----------
    def _build(self):
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._tab_conn(), "Подключение")
        tabs.addTab(self._tab_sync(), "Синхронизация")
        tabs.addTab(self._tab_pub(), "Публикация версии")
        lay.addWidget(tabs)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        lay.addWidget(self.log)

        btns = QHBoxLayout()
        b_close = QPushButton("Закрыть")
        b_close.clicked.connect(self.accept)
        btns.addStretch()
        btns.addWidget(b_close)
        lay.addLayout(btns)

    def _tab_conn(self):
        w = QWidget()
        v = QVBoxLayout(w)
        f = QFormLayout()
        self.ed_url = QLineEdit()
        self.ed_login = QLineEdit()
        self.ed_pass = QLineEdit()
        self.ed_pass.setEchoMode(QLineEdit.Password)
        self.ed_folder = QLineEdit()
        f.addRow("Адрес WebDAV:", self.ed_url)
        f.addRow("Логин (почта):", self.ed_login)
        f.addRow("Пароль приложения:", self.ed_pass)
        f.addRow("Папка в облаке:", self.ed_folder)
        v.addLayout(f)

        hint = QLabel(
            "Mail.ru: Настройки аккаунта → Пароли для внешних приложений.\n"
            "При включённой 2FA обычный пароль от почты не подойдёт.\n"
            f"Файл настроек: {cloud_config.config_path()}\n"
            "Пароль хранится локально (доступ только у владельца) и НЕ уходит в облако и не попадает в git.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#555;")
        v.addWidget(hint)

        row = QHBoxLayout()
        for text, fn in (("Сохранить", self.save_conn),
                         ("Проверить связь", self.check_conn),
                         ("Полная диагностика", self.full_diag),
                         ("Открыть папку настроек", open_settings_folder)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        v.addLayout(row)
        v.addStretch()
        return w

    def _tab_sync(self):
        w = QWidget()
        v = QVBoxLayout(w)
        f = QFormLayout()
        self.chk_auto = QCheckBox("Автосинхронизация")
        self.sp_interval = QSpinBox(); self.sp_interval.setRange(1, 1440)
        self.sp_debounce = QSpinBox(); self.sp_debounce.setRange(0, 3600)
        self.sp_copies = QSpinBox(); self.sp_copies.setRange(0, 500)
        self.sp_timeout = QSpinBox(); self.sp_timeout.setRange(5, 3600)
        self.sp_retries = QSpinBox(); self.sp_retries.setRange(1, 10)
        self.sp_copy_every = QSpinBox(); self.sp_copy_every.setRange(0, 1440)
        self.chk_start = QCheckBox("Синхронизировать при запуске программы")
        self.chk_exit = QCheckBox("Синхронизировать при закрытии программы")
        f.addRow(self.chk_auto)
        f.addRow("Период, мин:", self.sp_interval)
        f.addRow("Пауза после правки, с:", self.sp_debounce)
        f.addRow("Хранить копий в облаке:", self.sp_copies)
        f.addRow("Таймаут запроса, с:", self.sp_timeout)
        f.addRow("Повторов при сбое:", self.sp_retries)
        f.addRow("Копия в облако каждые, мин (0 = каждый раз):", self.sp_copy_every)
        f.addRow(self.chk_start)
        f.addRow(self.chk_exit)
        v.addLayout(f)

        g = QGroupBox("Ручные операции")
        gl = QHBoxLayout(g)
        for text, fn in (("Сохранить", self.save_sync),
                         ("Синхронизировать сейчас", self.sync_now),
                         ("Скачать из облака", self.pull_now),
                         ("Загрузить в облако", self.push_now)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            gl.addWidget(b)
        v.addWidget(g)

        note = QLabel("При изменении базы и там и там локальная версия сохраняется в облако "
                      "как history/conflict_…db, а рабочей становится облачная. "
                      "Перед каждой заменой базы делается копия в %APPDATA%\\BASE_CHECK\\backups.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        v.addWidget(note)
        v.addStretch()
        return w

    def _tab_pub(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(f"Текущая версия программы: <b>{APP_VERSION}</b>"))
        row = QHBoxLayout()
        b_pub = QPushButton("Опубликовать установщик…")
        b_pub.clicked.connect(self.publish)
        b_chk = QPushButton("Проверить обновление")
        b_chk.clicked.connect(self.check_update)
        row.addWidget(b_pub); row.addWidget(b_chk); row.addStretch()
        v.addLayout(row)
        v.addWidget(QLabel("Установщик кладётся в облако в подпапку release/, "
                           "рядом пишется version.json — по нему другие компьютеры узнают о новой версии."))
        v.addStretch()
        return w

    # ---------- данные ----------
    def _load_to_ui(self):
        c = self.cfg
        self.ed_url.setText(c["url"]); self.ed_login.setText(c["login"])
        self.ed_pass.setText(c["password"]); self.ed_folder.setText(c["folder"])
        self.chk_auto.setChecked(bool(c["autosync"]))
        self.sp_interval.setValue(int(c["interval_min"]))
        self.sp_debounce.setValue(int(c["debounce_sec"]))
        self.sp_copies.setValue(int(c["keep_copies"]))
        self.sp_timeout.setValue(int(c["timeout_sec"]))
        self.sp_retries.setValue(int(c["retries"]))
        self.sp_copy_every.setValue(int(c["copy_every_min"]))
        self.chk_start.setChecked(bool(c["sync_on_start"]))
        self.chk_exit.setChecked(bool(c["sync_on_exit"]))

    def _collect(self):
        c = dict(self.cfg)
        c.update({
            "url": self.ed_url.text().strip(),
            "login": self.ed_login.text().strip(),
            "password": self.ed_pass.text(),
            "folder": self.ed_folder.text().strip() or "BASE_CHECK",
            "autosync": self.chk_auto.isChecked(),
            "interval_min": self.sp_interval.value(),
            "debounce_sec": self.sp_debounce.value(),
            "keep_copies": self.sp_copies.value(),
            "timeout_sec": self.sp_timeout.value(),
            "retries": self.sp_retries.value(),
            "copy_every_min": self.sp_copy_every.value(),
            "sync_on_start": self.chk_start.isChecked(),
            "sync_on_exit": self.chk_exit.isChecked(),
        })
        return c

    def _say(self, text):
        self.log.append(text)

    def _save(self):
        self.cfg = self._collect()
        cloud_config.save(self.cfg)

    def _sync_obj(self):
        return cloud_sync.CloudSync(self.cfg)

    # ---------- кнопки ----------
    def save_conn(self):
        self._save()
        self._say(f"Настройки сохранены: {cloud_config.config_path()}")

    def save_sync(self):
        self._save()
        self._say("Параметры синхронизации сохранены.")

    def check_conn(self):
        self._save()
        s = None
        try:
            s = self._sync_obj()
            s.dav.ping()
            s.prepare()
            self._say("Связь OK, папка доступна.")
            QMessageBox.information(self, "Готово", "Связь с облаком установлена.")
        except Exception as e:
            self._say(f"Ошибка связи: {e}")
            QMessageBox.critical(self, "Ошибка связи", str(e))
        finally:
            if s:
                s.close()

    def full_diag(self):
        self._save()
        s = None
        try:
            s = self._sync_obj()
            self._say(s.diagnostics())
        except Exception as e:
            self._say(f"Диагностика: ошибка — {e}")
        finally:
            if s:
                s.close()

    def _run(self, mode):
        self._save()
        s = None
        try:
            s = self._sync_obj()
            res = s.push() if mode == "push" else s.pull() if mode == "pull" else s.sync()
            act = res.get("action")
            self._say(f"{act}: {res.get('size', '')} байт, sha {str(res.get('sha'))[:12]}")
            if act == "conflict":
                QMessageBox.warning(self, "Конфликт версий",
                                    "База менялась и здесь, и в облаке.\n"
                                    "Ваша версия сохранена в облако (history/conflict_…db),\n"
                                    "рабочей стала облачная версия.")
            return res
        except Exception as e:
            self._say(f"Ошибка: {e}")
            QMessageBox.critical(self, "Ошибка синхронизации", str(e))
            return None
        finally:
            if s:
                s.close()

    def sync_now(self):
        if self._run("auto"):
            QMessageBox.information(self, "Готово", "Синхронизация выполнена.")

    def pull_now(self):
        if QMessageBox.question(self, "Скачать из облака",
                                "Заменить локальную базу версией из облака?\n"
                                "Текущая база будет сохранена в backups.",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            if self._run("pull"):
                QMessageBox.information(self, "Готово", "База загружена из облака.")

    def push_now(self):
        if self._run("push"):
            QMessageBox.information(self, "Готово", "База выгружена в облако.")

    # ---------- публикация ----------
    def publish(self):
        self._save()
        path, _ = QFileDialog.getOpenFileName(self, "Выберите установщик", "", "Установщик (*.exe)")
        if not path:
            return
        s = None
        try:
            s = self._sync_obj()
            s.dav.ensure_folder(f"{s.folder}/release")
            name = os.path.basename(path)
            with open(path, "rb") as f:
                s.dav.put(f"{s.folder}/release/{name}", f.read())
            s.dav.put(f"{s.folder}/release/version.json", json.dumps(
                {"version": APP_VERSION, "file": name, "published_at": cloud_sync._now_iso()},
                ensure_ascii=False, indent=2).encode("utf-8"))
            self._say(f"Опубликовано: {name} (версия {APP_VERSION})")
            QMessageBox.information(self, "Готово", "Установщик опубликован в облаке.")
        except Exception as e:
            self._say(f"Публикация: ошибка — {e}")
            QMessageBox.critical(self, "Ошибка", str(e))
        finally:
            if s:
                s.close()

    def check_update(self):
        self._save()
        s = None
        try:
            s = self._sync_obj()
            raw = s.dav.get(f"{s.folder}/release/version.json")
            if not raw:
                QMessageBox.information(self, "Обновление", "В облаке нет опубликованных версий.")
                return
            info = json.loads(raw.decode("utf-8"))
            if _ver_tuple(info.get("version")) <= _ver_tuple(APP_VERSION):
                QMessageBox.information(self, "Обновление", "У вас актуальная версия.")
                return
            if QMessageBox.question(self, "Доступно обновление",
                                    f"В облаке версия {info['version']} (у вас {APP_VERSION}).\n"
                                    "Скачать установщик?",
                                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
            dst, _ = QFileDialog.getSaveFileName(self, "Сохранить установщик",
                                                 info.get("file") or "setup.exe", "Установщик (*.exe)")
            if not dst:
                return
            data = s.dav.get(f"{s.folder}/release/{info['file']}")
            if not data:
                raise WebDavError("Файл установщика не найден в облаке")
            with open(dst, "wb") as f:
                f.write(data)
            self._say(f"Установщик скачан: {dst}")
            QMessageBox.information(self, "Готово",
                                    f"Скачано:\n{dst}\n\nЗакройте программу и запустите установщик — "
                                    "он обновит программу поверх старой версии.")
        except Exception as e:
            self._say(f"Проверка обновления: ошибка — {e}")
            QMessageBox.critical(self, "Ошибка", str(e))
        finally:
            if s:
                s.close()