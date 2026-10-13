"""Общие настройки автотестов.

Drag-and-Drop через tkinterdnd2 зависит от работающего оконного окружения
операционной системы, поэтому в автоматических тестах библиотека отключается:
окно поднимается на обычном Tkinter. Такой прогон детерминирован и заодно
проверяет ветку отката, которая используется на компьютерах без tkdnd.
"""
import builtins
import sys

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
