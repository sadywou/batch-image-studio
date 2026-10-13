"""Снимок окна готового исполняемого файла.

Запускает dist\\BatchImageStudio.exe, находит его окно по заголовку и сохраняет
изображение через Win32 PrintWindow. Нужен для подтверждения в отчёте, что
приложение запускается как один файл, без установленного Python.

Запуск:  python tools/screenshot_exe.py
"""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.screenshot_ui import capture_hwnd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "BatchImageStudio.exe"
SHOTS = ROOT / "docs" / "screenshots"
TITLE = "Batch Image Processor"

user32 = ctypes.windll.user32


def find_window(title: str, timeout: float = 60.0):
    """Ищет верхнее окно с указанным заголовком."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if title.lower() in buffer.value.lower():
                found.append(hwnd)
            return True

        user32.EnumWindows(callback, 0)
        if found:
            return found[0]
        time.sleep(0.5)
    return None


def seed_demo_preset() -> None:
    """Кладёт в базу рядом с .exe демонстрационный профиль.

    Так снимок показывает, что собранный файл работает с той же базой данных,
    что и программа, запущенная из исходников, а не просто пустое окно.
    """
    from app.database import DatabaseManager
    from app.models import Preset

    manager = DatabaseManager(str(EXE.parent / "data" / "presets.db"))
    manager.delete_preset("Презентация для сайта")
    manager.create_preset(Preset(name="Презентация для сайта", output_format="WebP",
                                 resize_mode="WIDTH", resize_value="1600",
                                 quality=85, clear_exif=True, keep_ratio=True,
                                 output_dir="C:\\Processed",
                                 watermark_enabled=True,
                                 watermark_type="TEXT",
                                 watermark_text="СТУДИЯ", watermark_opacity=70))
    manager.close()


def main() -> None:
    if not EXE.exists():
        print(f"{EXE} не найден — сначала выполните сборку.")
        return 1
    print(f"Запуск {EXE.name} ({EXE.stat().st_size / (1024 * 1024):.1f} МБ)")
    seed_demo_preset()
    process = subprocess.Popen([str(EXE)], cwd=str(EXE.parent))
    try:
        hwnd = find_window(TITLE)
        if not hwnd:
            print("Окно не найдено за отведённое время.")
            return 1
        print(f"Окно найдено, дескриптор {hwnd}")
        time.sleep(4)
        SHOTS.mkdir(parents=True, exist_ok=True)
        path = SHOTS / "05_exe_launch.png"
        if capture_hwnd(hwnd, path):
            print(f"Снимок сохранён: {path}")
        else:
            print("Не удалось сохранить снимок окна.")
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
