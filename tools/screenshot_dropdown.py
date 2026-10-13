"""Снимок раскрытого выпадающего списка и блока выбора логотипа.

Скрипт открывает список типов водяного знака и снимает окно, чтобы
проверить оформление всплывающего меню и поля выбора файла PNG.

Запуск:  python tools/screenshot_dropdown.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tests.conftest  # noqa: E402,F401  отключает tkinterdnd2

from app.ui import MainWindow  # noqa: E402
from tools.screenshot_ui import capture_hwnd  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def capture_screen(path: Path) -> None:
    """Снимает весь экран целиком.

    Раскрывающийся список является отдельным окном поверх главного,
    поэтому снимок окна его не содержит — нужен снимок экрана.

    Args:
        path: Путь сохраняемого изображения.
    """
    from PIL import ImageGrab

    ImageGrab.grab().save(path)


def main() -> int:
    """Открывает список и сохраняет два снимка окна."""
    window = MainWindow()
    window.update()
    OUT.mkdir(parents=True, exist_ok=True)
    hwnd = int(window.wm_frame(), 16)

    print("Открываю список типов водяного знака...")
    window.watermark_type_combo._open()
    window.update()
    time.sleep(0.4)
    capture_screen(OUT / "06_dropdown_open.png")
    print("  список показан:", window.watermark_type_combo._popup is not None)

    window.watermark_type_combo.close()
    window.update()

    print("Переключаю знак на логотип PNG...")
    window.watermark_type_combo.select("Логотип (PNG)")
    window.update()
    time.sleep(0.3)
    capture_hwnd(hwnd, OUT / "07_logo_picker.png")
    print("  поле выбора файла:",
          window.watermark_image_frame.winfo_manager() or "скрыто")

    window.destroy()
    print("Снимки сохранены в", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())