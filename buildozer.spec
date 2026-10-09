[app]
title = Smart Land Divider
package.name = smartlanddivider
package.domain = org.surveyor
source.dir = .
source.include_exts = py,png,jpg,kv,ttf
source.exclude_dirs = .github,bin,.buildozer
version = 1.0
requirements = python3,kivy==2.3.0,pillow,reportlab,charset-normalizer
orientation = portrait
fullscreen = 0
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
