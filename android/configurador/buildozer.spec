[app]
title = Formatos Traducidos - Configurador
package.name = formatostraduccionesconfig
package.domain = com.serco
source.dir = .
source.include_exts = py,png,jpg,jpeg,json,fdt,ttf,otf
version = 0.1.0

# ¡CRÍTICO! pyjnius es obligatorio para que funcione el selector de archivos de Android
requirements = python3,kivy,pillow,pyjnius

orientation = portrait
fullscreen = 0
android.accept_sdk_license = True

# Versiones estables y probadas para Kivy en 2024/2026
android.api = 34
android.minapi = 21
android.sdk = 34
android.ndk = 27c

p4a.branch = develop
android.archs = armeabi-v7a,arm64-v8a

# Permisos necesarios para leer archivos, incluso usando el selector nativo
android.permissions = READ_EXTERNAL_STORAGE, READ_MEDIA_IMAGES

[buildozer]
log_level = 2
warn_on_root = 1