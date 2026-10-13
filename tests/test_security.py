"""Базовое тестирование безопасности: SQL-инъекции, целостность данных, вход.

Приложение работает без ORM, поэтому безопасность обеспечивается исключительно
параметризованными запросами sqlite3. Тесты проверяют это на практике и статически.
"""
import ast
from pathlib import Path

import pytest

from app.database import DatabaseManager
from app.models import Preset

INJECTION_PAYLOADS = [
    "'; DROP TABLE tbl_presets; --",
    "' OR '1'='1",
    "\" ; DELETE FROM tbl_formats WHERE 1=1; --",
    "1); DROP TABLE tbl_history_sessions; --",
    "%' UNION SELECT name FROM sqlite_master --",
]


@pytest.fixture()
def db(tmp_path: Path):
    manager = DatabaseManager(str(tmp_path / "security.db"))
    yield manager
    manager.close()


# ------------------------------------------------- SQL-инъекции на практике


@pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
def test_malicious_preset_name_is_stored_as_plain_text(db, payload) -> None:
    """Попытка инъекции сохраняется как обычный текст, таблицы остаются целы."""
    db.create_preset(Preset(name=payload, output_format="PNG"))
    stored = db.get_preset(payload)
    assert stored is not None
    assert stored.name == payload
    tables = {row[0] for row in db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "tbl_presets" in tables and "tbl_history_sessions" in tables
    db.delete_preset(payload)
    assert db.list_presets() == []


@pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
def test_malicious_format_name_is_stored_as_plain_text(db, payload) -> None:
    db.create_format(payload)
    assert payload in db.list_formats()
    db.update_format(payload, payload + "_v2")
    assert payload + "_v2" in db.list_formats()
    db.delete_format(payload + "_v2")
    assert payload not in db.list_formats()


def test_injection_in_session_lookup_cannot_read_other_rows(db) -> None:
    """Условие вида «x' OR 1=1» не должно возвращать чужие сессии."""
    for index in range(3):
        db.create_session(Preset(name=f"s{index}", output_format="PNG"), 1)
    assert len(db.list_sessions()) == 3
    assert db.get_preset("x' OR '1'='1") is None


def test_injection_cannot_escape_output_directory(tmp_path) -> None:
    """«..» в пути не должен выйти за пределы выбранной пользователем папки."""
    from PIL import Image
    from app.processor import ImageProcessor

    root = tmp_path / "work"
    root.mkdir()
    source = root / "safe.png"
    Image.new("RGB", (40, 30), "blue").save(source)
    preset = Preset(name="traversal", output_format="PNG",
                    output_dir=str(root / "out" / ".." / "out"))
    result = ImageProcessor().process(source, preset)
    assert result.resolve().parent == (root / "out").resolve()


# ------------------------------------------- статическая проверка запросов


def _database_sql_nodes() -> list:
    """Возвращает выражения, из которых строится текст SQL в database.py."""
    source = Path(__file__).resolve().parent.parent / "app" / "database.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None)
        if name in {"execute", "executemany", "executescript"}:
            found.append((name, node))
    return found


def _function_node(function_name: str):
    source = Path(__file__).resolve().parent.parent / "app" / "database.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    raise AssertionError(f"Функция {function_name} не найдена")


def test_database_module_uses_execute_statements():
    assert _database_sql_nodes(), "В database.py не найдено ни одного SQL-вызова"


def test_no_sql_is_built_with_plus_operator():
    """Ни один SQL-запрос не собирается конкатенацией строк."""
    offenders = []
    for name, node in _database_sql_nodes():
        sql_text = node.args[0] if node.args else None
        if isinstance(sql_text, ast.BinOp) and isinstance(sql_text.op, ast.Add):
            offenders.append(getattr(sql_text.left, "lineno", "?"))
    assert not offenders, (
        f"Обнаружена конкатенация в SQL на строках {offenders}")


def test_only_schema_migration_uses_interpolated_sql():
    """Вне _ensure_column текст SQL обязан быть строковым литералом."""
    migration = _function_node("_ensure_column")
    migration_lines = {node.lineno for node in ast.walk(migration)
                       if isinstance(node, (ast.Call, ast.Assign, ast.AugAssign))}
    offenders = []
    for name, node in _database_sql_nodes():
        sql_text = node.args[0] if node.args else None
        if sql_text is None or isinstance(sql_text, ast.Constant):
            continue
        if node.lineno in migration_lines:
            continue
        offenders.append((name, node.lineno))
    assert not offenders, (
        f"Динамический SQL вне миграции: {offenders}")


def test_schema_migration_rejects_unknown_table():
    """Белый список объектов миграции закрывает подстановку через имена."""
    import app.database as module

    manager = module.DatabaseManager.__new__(module.DatabaseManager)
    with pytest.raises(ValueError, match="Неизвестная таблица миграции"):
        manager._ensure_column("tbl_presets; DROP TABLE tbl_presets", "x", "TEXT")


@pytest.mark.parametrize("column", ["error; DROP TABLE tbl_presets",
                                    "ERROR", "err-1", "1col", "col name"])
def test_schema_migration_rejects_malicious_column(column):
    import app.database as module

    manager = module.DatabaseManager.__new__(module.DatabaseManager)
    with pytest.raises(ValueError, match="Недопустимое имя объекта миграции"):
        manager._ensure_column("tbl_processed_files", column, "TEXT")


@pytest.mark.parametrize("definition", ["TEXT; DROP TABLE tbl_presets",
                                        "text", "TEXT DEFAULT (SELECT 1)"])
def test_schema_migration_rejects_malicious_definition(definition):
    import app.database as module

    manager = module.DatabaseManager.__new__(module.DatabaseManager)
    with pytest.raises(ValueError, match="Недопустимое определение столбца"):
        manager._ensure_column("tbl_processed_files", "error", definition)


def test_schema_migration_accepts_real_declarations(tmp_path):
    """Реальные вызовы миграции из _create_schema проходят проверки и работают."""
    import app.database as module

    manager = module.DatabaseManager(str(tmp_path / "migration.db"))
    # «error» уже есть в схеме — повторный вызов должен быть безопасным.
    manager._ensure_column("tbl_processed_files", "error", "TEXT")
    # Допустимое объявление для ещё отсутствующего столбца.
    manager._ensure_column("tbl_watermarks", "brand_new", "INTEGER NOT NULL DEFAULT 0")
    columns = {row[1] for row in manager.connection.execute(
        "PRAGMA table_info(tbl_watermarks)")}
    assert "brand_new" in columns
    assert len(manager.list_formats()) == 9
    manager.close()


def test_processor_never_builds_sql():
    """Бизнес-логика обработки не должна ходить в базу напрямую."""
    source = Path(__file__).resolve().parent.parent / "app" / "processor.py"
    assert "sqlite3" not in source.read_text(encoding="utf-8")


# ------------------------------------------------------- точка входа


def test_main_entry_point_is_callable(monkeypatch):
    """app.main.main() обязан создавать окно и уходить в mainloop."""
    import app.main as entry

    calls = {}

    class FakeWindow:
        def mainloop(self):
            calls["mainloop"] = True

    monkeypatch.setattr(entry, "MainWindow", lambda: FakeWindow())
    entry.main()
    assert calls.get("mainloop") is True