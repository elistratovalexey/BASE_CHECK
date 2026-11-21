#!/usr/bin/env bash
# Автоматический ключ подписи: создаётся при первой сборке, дальше переиспользуется.
set -e

KS_DIR="${KEYSTORE_DIR:-$HOME/.android-basecheck}"
KS="$KS_DIR/basecheck.keystore"
ALIAS="basecheck"
PASS="basecheck"          # пароль не секрет: секретом является сам файл ключа

mkdir -p "$KS_DIR"
# если ключ уже сохранён в репозитории — берём его
if [ ! -f "$KS" ] && [ -f "$(dirname "$0")/basecheck.keystore" ]; then
  cp "$(dirname "$0")/basecheck.keystore" "$KS"
  chmod 600 "$KS" || true
fi

NEW_KEY=0
if [ ! -f "$KS" ]; then
  echo "Ключ подписи не найден — создаю новый…"
  keytool -genkeypair -v \
    -keystore "$KS" -alias "$ALIAS" \
    -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass "$PASS" -keypass "$PASS" \
    -dname "CN=BASE_CHECK, O=Alex Elistratov, C=RU" >/dev/null
  chmod 600 "$KS" || true
  NEW_KEY=1
else
  echo "Ключ подписи найден — использую существующий."
fi

# отпечаток сертификата: должен быть ОДИНАКОВЫМ во всех сборках
FP=$(keytool -list -v -keystore "$KS" -storepass "$PASS" -alias "$ALIAS" \
     | grep -m1 -E 'SHA256:' || true)
echo "Отпечаток подписи: $FP"

if [ -n "${GITHUB_ENV:-}" ]; then
  {
    echo "P4A_RELEASE_KEYSTORE=$KS"
    echo "P4A_RELEASE_KEYALIAS=$ALIAS"
    echo "P4A_RELEASE_KEYSTORE_PASSWD=$PASS"
    echo "P4A_RELEASE_KEYALIAS_PASSWD=$PASS"
    echo "BUILD_MODE=release"
  } >> "$GITHUB_ENV"
  if [ "$NEW_KEY" = "1" ]; then
    echo "::warning::Создан НОВЫЙ ключ подписи. Эту сборку нужно поставить после удаления старой версии; все следующие встанут поверх."
  fi
else
  # локальная сборка
  cat > "$(dirname "$0")/signing.env" <<EOF
export P4A_RELEASE_KEYSTORE="$KS"
export P4A_RELEASE_KEYALIAS="$ALIAS"
export P4A_RELEASE_KEYSTORE_PASSWD="$PASS"
export P4A_RELEASE_KEYALIAS_PASSWD="$PASS"
EOF
  echo "Локально: source android/signing.env && cd android && buildozer android release"
fi
