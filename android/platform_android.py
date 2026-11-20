# android/platform_android.py
"""Платформенный слой Android: каталоги, разрешения, выбор файла, OCR, PDF, экспорт."""
import logging
import os
import shutil

logger = logging.getLogger(__name__)
IS_ANDROID = "ANDROID_PRIVATE" in os.environ
REQ_PICK = 4711


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
    """Открывает системный выбор файла; callback(local_path или None)."""
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
    from jnius import autoclass
    from android import activity
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    act = PythonActivity.mActivity

    def on_result(requestCode, resultCode, data):
        if requestCode != REQ_PICK:
            return
        activity.unbind(onActivityResult=on_result)
        try:
            if resultCode != -1 or data is None:
                callback(None)
                return
            callback(_copy_uri(data.getData()))
        except Exception as e:
            logger.exception("Выбор файла: %s", e)
            callback(None)

    activity.bind(onActivityResult=on_result)
    i = Intent(Intent.ACTION_OPEN_DOCUMENT)
    i.addCategory(Intent.CATEGORY_OPENABLE)
    i.setType(mime)
    act.startActivityForResult(i, REQ_PICK)


def _copy_uri(uri):
    from jnius import autoclass
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    resolver = PythonActivity.mActivity.getContentResolver()
    name = "receipt.bin"
    try:
        cur = resolver.query(uri, None, None, None, None)
        if cur and cur.moveToFirst():
            idx = cur.getColumnIndex("_display_name")
            if idx >= 0:
                name = cur.getString(idx) or name
        if cur:
            cur.close()
    except Exception:
        pass
    dst = os.path.join(data_dir(), "incoming")
    os.makedirs(dst, exist_ok=True)
    path = os.path.join(dst, name)
    pfd = resolver.openFileDescriptor(uri, "r")
    fd = pfd.detachFd()
    with os.fdopen(fd, "rb") as f, open(path, "wb") as out:
        shutil.copyfileobj(f, out)
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
    TessBaseAPI = autoclass("com.googlecode.tesseract.android.TessBaseAPI")
    api = TessBaseAPI()
    if not api.init(data_dir(), lang):
        raise RuntimeError("Tesseract: нет %s.traineddata в %s/tessdata" % (lang, data_dir()))
    try:
        api.setImage(bmp)
        return api.getUTF8Text() or ""
    finally:
        try:
            api.recycle()
        except Exception:
            pass


def render_pdf_bitmaps(path, dpi=200, max_pages=10):
    """Рендер страниц PDF средствами Android (замена poppler)."""
    from jnius import autoclass
    File = autoclass("java.io.File")
    ParcelFileDescriptor = autoclass("android.os.ParcelFileDescriptor")
    PdfRenderer = autoclass("android.graphics.pdf.PdfRenderer")
    Bitmap = autoclass("android.graphics.Bitmap")
    Config = autoclass("android.graphics.Bitmap$Config")
    Page = autoclass("android.graphics.pdf.PdfRenderer$Page")

    pfd = ParcelFileDescriptor.open(File(path), ParcelFileDescriptor.MODE_READ_ONLY)
    renderer = PdfRenderer(pfd)
    out = []
    try:
        for i in range(min(renderer.getPageCount(), max_pages)):
            page = renderer.openPage(i)
            try:
                scale = dpi / 72.0
                scale = min(scale, 2000.0 / max(1, page.getWidth()),
                            8000.0 / max(1, page.getHeight()))
                w = max(1, int(page.getWidth() * scale))
                h = max(1, int(page.getHeight() * scale))
                bmp = Bitmap.createBitmap(w, h, Config.ARGB_8888)
                bmp.eraseColor(-1)
                page.render(bmp, None, None, Page.RENDER_MODE_FOR_DISPLAY)
                out.append(bmp)
            finally:
                page.close()
    finally:
        renderer.close()
        pfd.close()
    return out


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