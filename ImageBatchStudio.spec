# -*- mode: python ; coding: utf-8 -*-
"""Спецификация PyInstaller для Image Batch Studio.

Собирает один исполняемый файл, который запускается на компьютере без
установленного Python и без отдельной установки зависимостей.

Сборка:  pyinstaller ImageBatchStudio.spec --noconfirm
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).resolve()

# tkinterdnd2 тянёт за собой бинарные файлы tkdnd, а Pillow — плагины кодеков
# HEIC/AVIF. Эти пакеты собираются целиком, иначе Drag-and-Drop и форматы
# перестанут работать в готовом .exe.
# collect_all возвращает готовые пары (исходный путь, папка внутри пакета),
# поэтому datas и binaries не требуют дополнительного преобразования.
COLLECT_PACKAGES = ["tkinterdnd2", "pillow_heif", "pillow_avif"]

datas = []
hiddenimports = [
    "tkinter",
    "tkinter.ttk",
    "tkinter.font",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "sqlite3",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL._tkinter_finder",
]
binaries = []

try:
    from PyInstaller.utils.hooks import collect_all as collect_all_hook
except ImportError:  # pragma: no cover - PyInstaller отсутствует
    collect_all_hook = None

if collect_all_hook is not None:
    for package in COLLECT_PACKAGES:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all_hook(package)
        datas += list(pkg_datas)
        binaries += list(pkg_binaries)
        hiddenimports += list(pkg_hidden)

icon_file = PROJECT_ROOT / "build_assets" / "app.ico"

a = Analysis(
    # Точка входа — отдельный скрипт с абсолютными импортами: app/main.py
    # содержит относительные импорты и не запускается как самостоятельный файл.
    ["run_app.py"],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Служебные модули, не нужные приложению, исключаются: они заметно
    # увеличивают размер готового файла.
    excludes=[
        "PyQt5", "PyQt6", "PySide2", "PySide6", "IPython", "jupyter",
        "notebook", "pytest", "setuptools._distutils",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    # Имя файла задано техническим заданием (разделы 1.7 и 7).
    name="BatchImageStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # приложение оконное, консоль не нужна
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file) if icon_file.exists() else None,
)

if sys.platform == "win32":
    # Подробный лог запуска: создаётся рядом с .exe при ошибке.
    exe = exe  # noqa: F841  (одиночный файл, onedir-часть не используется)