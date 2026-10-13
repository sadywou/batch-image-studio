"""Точка входа в приложение."""
from .ui import MainWindow


def main() -> None:
    """Запускает главное окно приложения."""
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
