"""Снимки трёх состояний окна приложения для отчёта.

Скрипт запускает главное окно из исходников, приводит его к состояниям
«Начало», «Процесс» и «Готово» и сохраняет изображения окна в
docs/screenshots. Снимок делается через Win32 PrintWindow, поэтому окно
не обязано быть поверх других окон.

Запуск:  python tools/screenshot_ui.py
"""
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from app.ui import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class BITMAPINFOHEADER(ctypes.Structure):
    """Заголовок структуры BITMAPINFO, нужный для чтения пикселей."""

    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    """Структура BITMAPINFO целиком."""

    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def capture_hwnd(hwnd: int, path: Path) -> bool:
    """Сохраняет содержимое окна по его дескриптору в PNG."""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return False

    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(memory_dc, bitmap)
    try:
        # PW_RENDERFULLCONTENT = 2: рисует окно целиком, даже если оно перекрыто.
        if not user32.PrintWindow(hwnd, memory_dc, 2):
            user32.PrintWindow(hwnd, memory_dc, 0)

        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height          # отрицательная высота: сверху вниз
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0           # BI_RGB
        buffer = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer,
                        ctypes.byref(info), 0)
        image = Image.frombuffer("RGB", (width, height), buffer,
                                 "raw", "BGRX", 0, 1)
        SHOTS.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return True
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)


def make_samples(folder: Path, count: int = 4) -> list:
    """Создаёт разноцветные изображения для наполнения очереди."""
    from PIL import Image as PILImage

    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    palette = [(67, 139, 255), (67, 214, 160), (255, 176, 64), (190, 120, 255)]
    for index in range(count):
        path = folder / f"photo_{index + 1}.png"
        base = PILImage.effect_noise((320, 240), 55)
        image = base.convert("RGB").resize((640, 480), PILImage.Resampling.BICUBIC)
        overlay = PILImage.new("RGB", image.size, palette[index % len(palette)])
        image = PILImage.blend(image, overlay, 0.35)
        image.save(path)
        paths.append(path)
    return paths


def pump(window, predicate, timeout=30.0) -> bool:
    """Прогоняет цикл событий Tkinter до выполнения условия."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        window.update()
        if predicate():
            return True
        time.sleep(0.02)
    window.update()
    return predicate()


def main() -> None:
    window = MainWindow()
    window.update()
    hwnd = int(window.wm_frame(), 16)
    work = ROOT / "build" / "screenshots"

    print(f"Дескриптор окна: {hwnd}")

    # --- состояние «Начало» ---------------------------------------------
    window.update()
    time.sleep(0.5)
    capture_hwnd(hwnd, SHOTS / "01_state_start.png")
    print("снимок: 01_state_start.png")

    # --- состояние «Файлы в очереди» -------------------------------------
    samples = make_samples(work / "samples", 4)
    window._append_paths([str(path) for path in samples])
    window.output_var.set(str(work / "out"))
    window.format_var.set("PNG")
    window.width_var.set("640")
    window.height_var.set("480")
    window.watermark_text_var.set("STUDIO")
    window.update()
    time.sleep(1.0)
    capture_hwnd(hwnd, SHOTS / "02_state_queue.png")
    print("снимок: 02_state_queue.png")

    # --- состояние «Процесс» --------------------------------------------
    window.start_processing()
    pump(window, lambda: any(item.status == "Готово" for item in window.items), 30)
    window.update()
    capture_hwnd(hwnd, SHOTS / "03_state_process.png")
    print("снимок: 03_state_process.png")

    # --- состояние «Готово» ----------------------------------------------
    pump(window, lambda: window.state == "Готово — результат обработки", 60)
    window.update()
    time.sleep(0.5)
    capture_hwnd(hwnd, SHOTS / "04_state_done.png")
    print("снимок: 04_state_done.png")

    preset = window._build_preset()
    print(f"профиль после обработки: {preset.name} -> {preset.output_format} "
          f"{preset.resize_mode} {preset.resize_value}")
    sessions = window.database.list_sessions()
    if sessions:
        session = sessions[0]
        print(f"журнал: всего {session[4]}, успешно {session[5]}, "
              f"ошибок {session[6]}, длительность {session[7]:.2f} с")

    if window.worker and window.worker.is_alive():
        window.worker.cancel()
    window.database.close()
    window.destroy()
    print(f"Снимки сохранены в {SHOTS}")


if __name__ == "__main__":
    main()
