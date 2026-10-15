"""Снимки подсветки при перетаскивании и всплывающих подсказок.

Скрипт открывает окно, программно включает подсветку карточки так же,
как это делает событие перетаскивания файлов, показывает подсказку на
кнопке и сохраняет кадры в build/screenshots. Нужен для визуальной
проверки оформления до сборки исполняемого файла.

Запуск:  python tools/screenshot_drag.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ui import MainWindow  # noqa: E402
from tools.screenshot_ui import capture_hwnd, make_samples  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "build" / "screenshots"


def grab_region(widget, path: Path) -> bool:
    """Снимает со схемы прямоугольник, занятый виджетом.

    Всплывающая подсказка — окно без рамки: PrintWindow такое окно
    рисует искажённо, поэтому для неё берётся настоящий снимок экрана.
    """
    from PIL import ImageGrab

    widget.update_idletasks()
    x = widget.winfo_rootx() - 6
    y = widget.winfo_rooty() - 6
    box = (x, y, x + widget.winfo_width() + 12, y + widget.winfo_height() + 12)
    print(f"снимок подсказки: {box}")
    ImageGrab.grab(bbox=box).save(path)
    return True


def main() -> None:
    """Делает кадры подсветки и подсказки."""
    window = MainWindow()
    window.update()
    hwnd = int(window.wm_frame(), 16)
    work = ROOT / "build" / "screenshots"
    samples = make_samples(work / "samples", 3)
    window._append_paths([str(path) for path in samples])
    window.output_var.set(str(work / "out"))
    window.update()
    time.sleep(0.6)

    SHOTS.mkdir(parents=True, exist_ok=True)

    # Подсветка карточки очереди при перетаскивании файлов.
    window._drag_over("queue")
    window.update()
    time.sleep(0.4)
    capture_hwnd(hwnd, SHOTS / "10_drag_queue.png")
    window._drag_out("queue")
    window.update()

    # Подсветка карточки профилей.
    window._drag_over("presets")
    window.update()
    time.sleep(0.4)
    capture_hwnd(hwnd, SHOTS / "11_drag_presets.png")
    window._drag_out("presets")
    window.update()

    # Всплывающая подсказка на кнопке удаления профиля.
    probe = TooltipProbe(window)
    window.update()
    time.sleep(0.2)
    capture_hwnd(hwnd, SHOTS / "12_tooltip.png")
    # Подсказка — отдельное окно без рамки, поэтому снимают её со схемы.
    grab_region(probe.tooltip._window, SHOTS / "12_tooltip_popup.png")
    print("подсказка показана на кнопке «Удалить»")
    probe.hide()

    if window.worker and window.worker.is_alive():
        window.worker.cancel()
    window.database.close()
    window.destroy()
    print(f"Снимки сохранены в {SHOTS}")


class TooltipProbe:
    """Показывает подсказку на кнопке «Удалить» в панели профилей."""

    def __init__(self, window) -> None:
        """Создаёт и показывает подсказку на кнопке удаления профиля."""
        from app.ui import Tooltip
        self.tooltip = Tooltip(window.delete_preset_button,
                               "Удалить выбранный профиль из базы")
        self.tooltip._show()

    def hide(self) -> None:
        """Убирает показанную подсказку."""
        self.tooltip._hide()


if __name__ == "__main__":
    main()