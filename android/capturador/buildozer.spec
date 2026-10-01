[app]
title = Formatos Traducidos - Capturador
package.name = formatostraduccionescapt
package.domain = com.serco
source.dir = .
source.include_exts = py,png,jpg,jpeg,json,fdt,ttf
version = 0.1.0
requirements = python3,kivy,pillow
orientation = portrait
fullscreen = 0

[buildozer]
log_level = 2
warn_on_root = 1

[android]
android.accept_sdk_license = True
android.api = 35
android.minapi = 23
android.archs = arm64-v8a, armeabi-v7a
