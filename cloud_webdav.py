# cloud_webdav.py
"""Минимальный WebDAV-клиент Облака Mail.ru (Basic: почта + пароль приложения)."""
import logging
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote, urlparse

import requests

logger = logging.getLogger(__name__)
NS = "{DAV:}"


class WebDavError(RuntimeError):
    pass


class WebDav:
    def __init__(self, url, login, password, timeout=300, retries=4):
        self.base = (url or "").rstrip("/")
        self.auth = (login or "", password or "")
        self.timeout = max(5, int(timeout or 300))
        self.retries = max(1, int(retries or 1))
        self._s = requests.Session()
        self._s.headers.update({"User-Agent": "BASE_CHECK", "Accept": "*/*"})

    def close(self):
        try:
            self._s.close()
        except Exception:
            pass

    def _url(self, path):
        parts = [p for p in (path or "").split("/") if p]
        return self.base + "/" + "/".join(quote(p, safe="") for p in parts)

    def _req(self, method, path, **kw):
        url, last = self._url(path), None
        for i in range(self.retries):
            try:
                r = self._s.request(method, url, auth=self.auth, timeout=self.timeout, **kw)
                if r.status_code in (429, 500, 502, 503, 504) and i + 1 < self.retries:
                    time.sleep(min(2 ** i, 10))
                    continue
                return r
            except requests.RequestException as e:
                last = e
                if i + 1 < self.retries:
                    time.sleep(min(2 ** i, 10))
        raise WebDavError(f"{method} {path}: сеть недоступна ({last})")

    def ping(self):
        r = self._req("PROPFIND", "", headers={"Depth": "0"})
        if r.status_code in (200, 207):
            return True
        if r.status_code in (401, 403):
            raise WebDavError("Отказано в доступе (401/403). Нужен пароль для внешних приложений.")
        raise WebDavError(f"PROPFIND / -> {r.status_code}")

    def ensure_folder(self, path):
        cur = ""
        for part in [p for p in (path or "").split("/") if p]:
            cur = f"{cur}/{part}" if cur else part
            r = self._req("PROPFIND", cur, headers={"Depth": "0"})
            if r.status_code in (200, 207):
                continue
            if r.status_code == 404:
                rc = self._req("MKCOL", cur)
                if rc.status_code not in (200, 201, 405):
                    raise WebDavError(f"MKCOL {cur} -> {rc.status_code}")
            elif r.status_code in (401, 403):
                raise WebDavError("Отказано в доступе (401/403)")
            else:
                raise WebDavError(f"PROPFIND {cur} -> {r.status_code}")
        return True

    def get(self, path):
        r = self._req("GET", path)
        if r.status_code == 200:
            return r.content
        if r.status_code == 404:
            return None
        raise WebDavError(f"GET {path} -> {r.status_code}")

    def put(self, path, data):
        r = self._req("PUT", path, data=data,
                      headers={"Content-Type": "application/octet-stream"})
        if r.status_code in (200, 201, 204):
            return True
        raise WebDavError(f"PUT {path} -> {r.status_code}")

    def delete(self, path):
        return self._req("DELETE", path).status_code in (200, 202, 204, 404)

    def list(self, path):
        r = self._req("PROPFIND", path, headers={"Depth": "1"})
        if r.status_code == 404:
            return []
        if r.status_code not in (200, 207):
            raise WebDavError(f"PROPFIND {path} -> {r.status_code}")
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError:
            return []
        self_name = ([p for p in (path or "").split("/") if p] or [""])[-1]
        out = []
        for resp in root.findall(f"{NS}response"):
            href = resp.findtext(f"{NS}href") or ""
            name = unquote(urlparse(href).path.rstrip("/").split("/")[-1])
            prop = resp.find(f"{NS}propstat/{NS}prop")
            if prop is None or not name:
                continue
            is_dir = prop.find(f"{NS}resourcetype/{NS}collection") is not None
            if is_dir and name == self_name:
                continue
            out.append({"name": name, "dir": is_dir,
                        "size": int(prop.findtext(f"{NS}getcontentlength") or 0),
                        "mtime": prop.findtext(f"{NS}getlastmodified") or ""})
        return out