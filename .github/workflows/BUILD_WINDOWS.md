# Сборка exe и установщика для Windows 11 (x64)

## Вариант A — в облаке (Windows не нужен)
1. Закоммитьте все файлы, включая `.github/workflows/windows-build.yml`.
2. GitHub → Actions → **Windows build** → Run workflow.
3. Через ~5–8 минут скачайте артефакт `BASE_CHECK-windows`:
   `BASE_CHECK-1.4.0-win64-setup.exe` — установщик.
4. Либо создайте тег `git tag v1.4.0 && git push --tags` — установщик попадёт в Releases.

## Вариант B — на Windows-машине
1. Python 3.11–3.12 **x64** с python.org (галочка «Add to PATH»).
2. `winget install UB-Mannheim.TesseractOCR` и `winget install JRSoftware.InnoSetup`.
3. Двойной клик по `build_windows.bat`.
4. Результат: `dist\BASE_CHECK-1.4.0-win64-setup.exe`.
   Портативная версия без установки: `dist\BASE_CHECK\BASE_CHECK.exe`.

## Где лежат данные
- БД: `%APPDATA%\BASE_CHECK\receipts.db`
- Лог: `%APPDATA%\BASE_CHECK\app.log`

При первом запуске старая `receipts.db` из каталога программы автоматически
копируется туда. Удаление программы данные не стирает.

## Иконка (необязательно)
Положите `assets\app.ico` — она подхватится и exe, и установщиком.

## Проверка после установки
1. Запустить ярлык — окно открывается без консоли.
2. «Сканировать чек» → электронный PDF Глобуса → 80 позиций, 11 408.46.
3. Сканированный PDF → должен пойти OCR (Tesseract и Poppler внутри сборки).
4. «В файл excel» и «Рассчитать оплаты» → файлы создаются.
5. При масштабе экрана 150 % интерфейс не «мылится».
