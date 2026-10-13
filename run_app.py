"""Точка входа для PyInstaller.

Модуль app/main.py запускается командой `python -m app.main` и использует
относительные импорты, поэтому в качестве скрипта сборки он не подходит:
PyInstaller выполняет файл как самостоятельный скрипт, без пакета app.
Этот модуль использует абсолютный импорт и годится и для python run_app.py,
и для сборки исполняемого файла.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    # При запуске одним файлом пакет app лежит рядом, но не в путях импорта.
    sys.path.insert(0, str(ROOT))

from app.ui import MainWindow  # noqa: E402


def main() -> None:
    """Открывает главное окно и передаёт управление циклу событий Tkinter."""
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()