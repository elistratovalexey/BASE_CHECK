# Android-версия «Программа обработки чеков»

Тот же функционал, что и в Windows-версии, интерфейс на Kivy.
Общее ядро (парсер чеков, БД, деление расхода пополам, расчёт оплат,
Excel, синхронизация с Облаком Mail.ru) используется без изменений.

## Сборка APK без Android-Studio
1. GitHub → Actions → **Android build** → Run workflow.
2. Через 20–40 минут скачайте артефакт `BASE_CHECK-android` → `*.apk`.
3. Установите APK на телефон (разрешив установку из неизвестных источников).

## Сборка локально (Linux/WSL)
```bash
pip install "cython<3.0" buildozer
bash android/prepare.sh
cd android && buildozer -v android debug
# результат: android/bin/*.apk