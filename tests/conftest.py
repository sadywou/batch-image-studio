"""Общие настройки автотестов.

Drag-and-Drop через tkinterdnd2 зависит от работающего оконного окружения
операционной системы, поэтому в автоматических тестах библиотека отключается:
окно поднимается на обычном Tkinter. Такой прогон детерминирован и заодно
проверяет ветку отката, которая используется на компьютерах без tkdnd.

Здесь же объявлена фикстура ``window``, которой пользуются все наборы
тестов интерфейса: она поднимает главное окно на временной базе,
подменяет диалоговые окна и гарантированно закрывает окно после теста.
"""
import builtins
import sys
import tkinter as tk

import pytest

_real_import = builtins.__import__


def _import_without_tkdnd(name, *args, **kwargs):
    """Блокирует импорт tkinterdnd2 до первого обращения к app.ui."""
    if name == "tkinterdnd2" or name.startswith("tkinterdnd2."):
        raise ImportError("tkinterdnd2 отключена в автоматических тестах")
    return _real_import(name, *args, **kwargs)


for _module in list(sys.modules):
    if _module == "tkinterdnd2" or _module.startswith("tkinterdnd2."):
        del sys.modules[_module]

builtins.__import__ = _import_without_tkdnd


# --------------------------------------------------------------- окно программы


class _SilentMessageBox:
    """Заглушка диалоговых окон: запоминает вызовы и ничего не показывает."""

    def __init__(self) -> None:
        self.calls = []

    def _record(self, kind, title, message=None, **_kwargs):
        self.calls.append((kind, title, message))

    def showinfo(self, title="", message="", **_kwargs):
        self._record("info", title, message)

    def showwarning(self, title="", message="", **_kwargs):
        self._record("warning", title, message)

    def showerror(self, title="", message="", **_kwargs):
        self._record("error", title, message)

    def askyesno(self, title="", message="", **_kwargs):
        self._record("askyesno", title, message)
        return True

    def askstring(self, title="", message="", **_kwargs):
        self._record("askstring", title, message)
        return ""

    def askopenfilename(self, **_kwargs):
        self._record("askopenfilename", "", None)
        return ""

    def askopenfilenames(self, **_kwargs):
        self._record("askopenfilenames", "", None)
        return []

    def askdirectory(self, **_kwargs):
        self._record("askdirectory", "", None)
        return ""


def pytest_configure(config):
    """Регистрирует фикстуры, доступные всем наборам тестов интерфейса."""
    config.addinivalue_line("markers", "ui: проверки графического интерфейса")


@pytest.fixture()
def window(tmp_path, monkeypatch):
    """Открывает главное окно на временной базе и закрывает его после теста.

    Args:
        tmp_path: Временный каталог теста для файла базы.
        monkeypatch: Механизм подмены объектов pytest.

    Yields:
        Экземпляр :class:`app.ui.MainWindow`.
    """
    from app import ui

    dialogs = _SilentMessageBox()
    monkeypatch.setattr(ui, "messagebox", dialogs)

    original = ui.DatabaseManager

    def temp_manager(db_path=None):
        return original(str(tmp_path / "ui.db"))

    monkeypatch.setattr(ui, "DatabaseManager", temp_manager)
    ui._THUMB_CACHE.clear()
    ui.MainWindow._drop_hover = False
    assert ui.DND_AVAILABLE is False, "conftest.py должен отключать tkinterdnd2"

    win = ui.MainWindow()
    win.withdraw()
    win.dialogs = dialogs
    try:
        yield win
    finally:
        if win.worker and win.worker.is_alive():
            win.worker.cancel()
            win.worker.join(10)
        try:
            win.database.close()
        except Exception:  # noqa: BLE001 - закрытие после теста
            pass
        win.destroy()
        ui._THUMB_CACHE.clear()
        # Каждый тест работает в своём интерпретаторе Tk, поэтому ссылку
        # на стандартный корень нужно сбросить до создания следующего окна.
        tk._default_root = None
