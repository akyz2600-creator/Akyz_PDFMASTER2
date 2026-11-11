[app]

title = Akyz_PDFMASTER
package.name = akyzpdfmaster
package.domain = com.akyz
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas
version = 1.0.0
requirements = python3,kivy,plyer,pypdf
orientation = portrait
fullscreen = 0

# Android: el selector nativo de archivos de Android administra el acceso.
android.api = 35
android.minapi = 23
android.ndk = 27b
android.archs = arm64-v8a
android.allow_backup = True

# No se solicitan permisos amplios de almacenamiento:
# el usuario elige archivos mediante el selector del sistema.
android.permissions =

[buildozer]
log_level = 2
warn_on_root = 1
