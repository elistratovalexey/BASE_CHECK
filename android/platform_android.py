# android/platform_android.py
"""Платформенный слой Android: каталоги, разрешения, выбор файла, OCR, PDF, экспорт."""
import logging
import os
import shutil

logger = logging.getLogger(__name__)
IS_ANDROID = "ANDROID_PRIVATE" in os.environ
REQ_PICK = 4711
PICKING = False


def _save_error(title, exc):
    import traceback
    txt = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("%s: %s\n%s", title, exc, txt)
    try:
        with open(os.path.join(data_dir(), "last_error.txt"), "w", encoding="utf-8") as f:
            f.write(txt)
    except Exception:
        pass
    try:
        toast(f"{title}: {exc}")
    except Exception:
        pass


def data_dir():
    if IS_ANDROID:
        return os.environ["ANDROID_PRIVATE"]
    d = os.path.join(os.path.expanduser("~"), ".base_check_mobile")
    os.makedirs(d, exist_ok=True)
    return d


def exports_dir():
    d = os.path.join(data_dir(), "exports")
    os.makedirs(d, exist_ok=True)
    return d


def ensure_tessdata():
    """Копирует bundled *.traineddata в рабочий каталог (нужен tesseract4android)."""
    dst = os.path.join(data_dir(), "tessdata")
    os.makedirs(dst, exist_ok=True)
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tessdata")
    if os.path.isdir(src):
        for name in os.listdir(src):
            if name.endswith(".traineddata"):
                target = os.path.join(dst, name)
                if not os.path.exists(target):
                    shutil.copy2(os.path.join(src, name), target)
    return dst


def request_perms():
    if not IS_ANDROID:
        return
    try:
        from android.permissions import request_permissions, Permission
        perms = [Permission.INTERNET, Permission.ACCESS_NETWORK_STATE]
        try:
            from jnius import autoclass
            sdk = autoclass("android.os.Build$VERSION").SDK_INT
            if sdk >= 33:
                perms += [Permission.READ_MEDIA_IMAGES]
            else:
                perms += [Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE]
        except Exception:
            pass
        request_permissions(perms)
    except Exception as e:
        logger.warning("Разрешения: %s", e)


# ---------- выбор файла ----------
def pick_file(callback, mime="*/*"):
    """Системный выбор файла; callback(local_path или None). Никогда не бросает исключение."""
    global PICKING
    if not IS_ANDROID:
        try:
            import tkinter as tk
            from tkinter import filedialog
            r = tk.Tk(); r.withdraw()
            p = filedialog.askopenfilename()
            r.destroy()
            callback(p or None)
        except Exception:
            callback(None)
        return

    try:
        from jnius import autoclass
        from android import activity
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        act = PythonActivity.mActivity

        def on_result(requestCode, resultCode, data):
            global PICKING
            if requestCode != REQ_PICK:
                return
            try:
                activity.unbind(onActivityResult=on_result)
            except Exception:
                pass
            PICKING = False
            try:
                if resultCode != -1 or data is None:
                    callback(None)
                    return
                uri = data.getData()
                if uri is None:
                    callback(None)
                    return
                callback(_copy_uri(uri))
            except Exception as e:
                _save_error("Выбор файла", e)
                callback(None)

        activity.bind(onActivityResult=on_result)
        PICKING = True
        i = Intent(Intent.ACTION_OPEN_DOCUMENT)
        i.addCategory(Intent.CATEGORY_OPENABLE)
        i.setType(mime)
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        act.startActivityForResult(i, REQ_PICK)
    except Exception as e:
        PICKING = False
        _save_error("Открытие выбора файла", e)
        callback(None)
        

def _copy_uri(uri):
    from jnius import autoclass
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    resolver = PythonActivity.mActivity.getContentResolver()

    name = "receipt.bin"
    cur = None
    try:
        cur = resolver.query(uri, None, None, None, None)
        if cur is not None and cur.moveToFirst():
            idx = cur.getColumnIndex("_display_name")
            if idx >= 0:
                name = cur.getString(idx) or name
    except Exception:
        pass
    finally:
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass

    name = os.path.basename(str(name).replace("\\", "/")) or "receipt.bin"
    dst_dir = os.path.join(data_dir(), "incoming")
    os.makedirs(dst_dir, exist_ok=True)
    path = os.path.join(dst_dir, name)

    pfd = resolver.openFileDescriptor(uri, "r")
    if pfd is None:
        raise RuntimeError("Android не дал доступ к выбранному файлу")
    src = os.fdopen(pfd.detachFd(), "rb")
    try:
        with open(path, "wb") as out:
            shutil.copyfileobj(src, out, 262144)
    finally:
        try:
            src.close()
        except Exception:
            pass
    return path
    

# ---------- OCR ----------
def ocr_image_file(path, lang="rus"):
    """Распознаёт изображение через tesseract4android -> текст."""
    ensure_tessdata()
    from jnius import autoclass
    BitmapFactory = autoclass("android.graphics.BitmapFactory")
    bmp = BitmapFactory.decodeFile(path)
    if bmp is None:
        raise RuntimeError("Не удалось открыть изображение")
    return ocr_bitmap(bmp, lang)


def ocr_bitmap(bmp, lang="rus"):
    from jnius import autoclass
    try:
        TessBaseAPI = autoclass("com.googlecode.tesseract.android.TessBaseAPI")
    except Exception as e:
        raise RuntimeError("В APK нет библиотеки Tesseract (tesseract4android): %s" % e)
    td = ensure_tessdata()
    if not os.path.isfile(os.path.join(td, lang + ".traineddata")):
        raise RuntimeError("Нет файла %s.traineddata в %s" % (lang, td))
    api = TessBaseAPI()
    if not api.init(data_dir(), lang):
        raise RuntimeError("Tesseract не инициализирован (язык %s)" % lang)
    try:
        api.setImage(bmp)
        return api.getUTF8Text() or ""
    finally:
        try:
            api.recycle()
        except Exception:
            pass


def iter_pdf_bitmaps(path, dpi=170, max_pages=8, max_pixels=12_000_000):
    """Отдаёт страницы PDF по одной и сразу освобождает память."""
    from jnius import autoclass
    File = autoclass("java.io.File")
    ParcelFileDescriptor = autoclass("android.os.ParcelFileDescriptor")
    PdfRenderer = autoclass("android.graphics.pdf.PdfRenderer")
    Bitmap = autoclass("android.graphics.Bitmap")
    Config = autoclass("android.graphics.Bitmap$Config")
    Page = autoclass("android.graphics.pdf.PdfRenderer$Page")

    pfd = ParcelFileDescriptor.open(File(path), ParcelFileDescriptor.MODE_READ_ONLY)
    renderer = PdfRenderer(pfd)
    try:
        for i in range(min(renderer.getPageCount(), max_pages)):
            page = renderer.openPage(i)
            bmp = None
            try:
                w_pt = max(1, page.getWidth())
                h_pt = max(1, page.getHeight())
                scale = min(dpi / 72.0, 2200.0 / w_pt, 9000.0 / h_pt)
                while (w_pt * scale) * (h_pt * scale) > max_pixels and scale > 0.2:
                    scale *= 0.8
                w = max(1, int(w_pt * scale))
                h = max(1, int(h_pt * scale))
                bmp = Bitmap.createBitmap(w, h, Config.ARGB_8888)
                bmp.eraseColor(-1)
                page.render(bmp, None, None, Page.RENDER_MODE_FOR_DISPLAY)
                yield bmp
            finally:
                try:
                    page.close()
                except Exception:
                    pass
                if bmp is not None:
                    try:
                        bmp.recycle()
                    except Exception:
                        pass
    finally:
        try:
            renderer.close()
        except Exception:
            pass
        try:
            pfd.close()
        except Exception:
            pass



# ---------- экспорт в «Загрузки» ----------
def save_to_downloads(filename, data,
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
    """Кладёт файл в Downloads (MediaStore на API 29+), возвращает путь/URI."""
    if not IS_ANDROID:
        p = os.path.join(exports_dir(), filename)
        with open(p, "wb") as f:
            f.write(data)
        return p
    from jnius import autoclass, cast
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    ctx = PythonActivity.mActivity
    sdk = autoclass("android.os.Build$VERSION").SDK_INT
    if sdk >= 29:
        MediaStore = autoclass("android.provider.MediaStore")
        ContentValues = autoclass("android.content.ContentValues")
        resolver = ctx.getContentResolver()
        vals = ContentValues()
        vals.put("_display_name", filename)
        vals.put("mime_type", mime)
        vals.put("relative_path", "Download/")
        uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, vals)
        if uri is None:
            raise RuntimeError("MediaStore не создал файл")
        pfd = resolver.openFileDescriptor(uri, "w")
        fd = pfd.detachFd()
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return "Downloads/" + filename
    Environment = autoclass("android.os.Environment")
    d = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
    d.mkdirs()
    p = os.path.join(d.getAbsolutePath(), filename)
    with open(p, "wb") as f:
        f.write(data)
    return p
                          
def storage_diagnostics():
    import paths

    root = data_dir()
    udd = paths.user_data_dir()
    dbp = paths.db_path()
    bkp = os.path.join(udd, "backups")

    lines = [
        f"ANDROID_PRIVATE={os.environ.get('ANDROID_PRIVATE')}",
        f"data_dir={root}",
        f"user_data_dir={udd}",
        f"db_path={dbp}",
        f"backups={bkp}",
    ]

    for p in (root, udd, bkp):
        try:
            os.makedirs(p, exist_ok=True)
            test = os.path.join(p, ".write_test")
            with open(test, "wb") as f:
                f.write(b"ok")
            os.unlink(test)
            lines.append(f"OK write: {p}")
        except Exception as e:
            lines.append(f"FAIL write: {p} -> {e}")

    return "\n".join(lines)

def toast(text):
    if not IS_ANDROID:
        print(text)
        return
    try:
        from jnius import autoclass, cast
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Toast = autoclass("android.widget.Toast")
        String = autoclass("java.lang.String")
        ctx = PythonActivity.mActivity
        Toast.makeText(ctx, cast("java.lang.CharSequence", String(text)), Toast.LENGTH_LONG).show()
    except Exception:
        logger.info("toast: %s", text)
