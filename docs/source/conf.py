"""Конфигурация Sphinx для документации Image Batch Studio.

Сборка:  sphinx-build -b html docs/source docs/_build/html
         sphinx-build -b latexpdf docs/source docs/_build/pdf
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

project = "Image Batch Studio"
author = "Студент группы ИСП-34"
copyright = "2026, ГБПОУ НСО «Новосибирский электромеханический колледж»"
release = "1.0.0"

extensions = [
    "sphinx.ext.autodoc",        # автоматическая генерация из docstrings
    "sphinx.ext.napoleon",       # разбор docstrings в стиле Google
    "sphinx.ext.viewcode",       # исходный код рядом с описанием
    "sphinx.ext.todo",           # раздел «Известные ограничения»
    "sphinx.ext.intersphinx",    # ссылки на документацию Python
    "sphinx.ext.mathjax",
]

exclude_patterns = ["_build"]
nitpicky = False

# --------------------------------------------------------------- оформление
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_title = "Image Batch Studio — документация"
html_short_title = "Image Batch Studio"
html_theme_options = {
    "navigation_depth": 3,
    "style_external_links": True,
}
html_css_files = ["custom.css"]

# --------------------------------------------------------------- autodoc
autodoc_member_order = "bysource"
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_use_param = True
napoleon_use_rtype = True
# Атрибуты dataclass описаны в разделе Attributes и одновременно видны как
# поля класса. Ivar помечает их как переменные экземпляра, благодаря чему
# Sphinx перестаёт создавать дублирующие записи.
napoleon_use_ivar = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

todo_include_todos = True

if os.environ.get("SPHINX_DEBUG"):
    print("Sphinx настроен для", project, release)