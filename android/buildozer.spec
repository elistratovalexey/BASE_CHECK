[app]
title = Обработка чеков
package.name = basecheck
package.domain = ru.elistratov
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,traineddata
source.exclude_dirs = bin, .buildozer, __pycache__
version = 1.5.0

p4a.branch = master
p4a.commit = v2024.01.21
p4a.extra_args = --add-gradle-repository "maven { url 'https://jitpack.io' }"

requirements = python3,kivy==2.3.0,pillow,openpyxl,et_xmlfile,pypdf,requests,pyjnius,android

orientation = portrait
fullscreen = 0

android.api = 34
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a
android.allow_backup = True
android.accept_sdk_license = True
android.enable_androidx = True
android.permissions = INTERNET, ACCESS_NETWORK_STATE, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_IMAGES

android.gradle_dependencies = cz.adaptech.tesseract4android:tesseract4android:4.7.0


android.release_artifact = apk
android.debug_artifact = apk
android.numeric_version = 10000000

[buildozer]
log_level = 2
warn_on_root = 0
