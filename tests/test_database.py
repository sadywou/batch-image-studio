"""Модульные проверки слоя доступа к данным (app/database.py)."""
import sqlite3
from pathlib import Path

import pytest

from app.database import DatabaseManager
from app.models import Preset, QueueItem


@pytest.fixture()
def db(tmp_path: Path):
    """Создаёт изолированную базу в временной папке на время одного теста."""
    manager = DatabaseManager(str(tmp_path / "test.db"))
    yield manager
    manager.close()


# ------------------------------------------------------------------ профили


def test_preset_watermark_roundtrip(db: DatabaseManager) -> None:
    preset = Preset(name="demo", output_format="PNG", width=640,
                    watermark_enabled=True, watermark_text="Sample",
                    watermark_position="top-left", watermark_opacity=55)
    db.create_preset(preset)
    loaded = db.get_preset("demo")
    assert loaded is not None
    assert loaded.width == 640
    assert loaded.watermark_enabled is True
    assert loaded.watermark_text == "Sample"
    assert loaded.watermark_position == "top-left"
    assert loaded.watermark_opacity == 55
    db.update_preset(Preset(name="demo", output_format="WebP", quality=90))
    assert db.get_preset("demo").output_format == "WebP"
    db.delete_preset("demo")
    assert db.list_presets() == []


def test_schema_contains_all_tables(db: DatabaseManager) -> None:
    names = {row[0] for row in db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tbl_formats", "tbl_presets", "tbl_watermarks",
            "tbl_history_sessions", "tbl_processed_files"} <= names


def test_formats_are_seeded_with_nine_targets(db: DatabaseManager) -> None:
    formats = db.list_formats()
    assert len(formats) == 9
    assert {"PNG", "JPG", "WebP", "BMP", "TIFF", "GIF", "ICO",
            "HEIC", "AVIF"} == set(formats)


def test_foreign_keys_pragmas_are_enabled(db: DatabaseManager) -> None:
    assert db.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db.connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_get_missing_preset_returns_none(db: DatabaseManager) -> None:
    assert db.get_preset("нет такого") is None


def test_update_missing_preset_raises(db: DatabaseManager) -> None:
    with pytest.raises(ValueError, match="не найден"):
        db.update_preset(Preset(name="ghost", output_format="PNG"))


def test_create_preset_with_unknown_format_raises(db: DatabaseManager) -> None:
    with pytest.raises(ValueError, match="Неизвестный формат"):
        db.create_preset(Preset(name="bad", output_format="EXR"))


def test_duplicate_preset_name_violates_unique_constraint(db: DatabaseManager) -> None:
    db.create_preset(Preset(name="twice", output_format="PNG"))
    with pytest.raises(sqlite3.IntegrityError):
        db.create_preset(Preset(name="twice", output_format="JPG"))


def test_quality_out_of_range_is_rejected_by_database(db: DatabaseManager) -> None:
    """Ограничение CHECK в схеме дублирует проверку бизнес-логики."""
    with pytest.raises(sqlite3.IntegrityError):
        db.create_preset(Preset(name="bad-quality", output_format="PNG", quality=500))


def test_delete_preset_cascades_watermark_row(db: DatabaseManager) -> None:
    db.create_preset(Preset(name="wm", output_format="PNG",
                            watermark_enabled=True, watermark_text="T"))
    assert db.get_watermark("wm") is not None
    db.delete_preset("wm")
    rows = db.connection.execute("SELECT COUNT(*) FROM tbl_watermarks").fetchone()[0]
    assert rows == 0


def test_watermark_upsert_replaces_values(db: DatabaseManager) -> None:
    db.create_preset(Preset(name="wm", output_format="PNG"))
    db.save_watermark("wm", "Первый", opacity=40, position="top-left", enabled=True)
    db.save_watermark("wm", "Второй", opacity=90, position="bottom-left")
    saved = db.get_watermark("wm")
    assert saved["text"] == "Второй"
    assert saved["opacity"] == 90
    assert saved["position"] == "bottom-left"
    rows = db.connection.execute("SELECT COUNT(*) FROM tbl_watermarks").fetchone()[0]
    assert rows == 1
    db.delete_watermark("wm")
    assert db.get_watermark("wm") is None


def test_save_watermark_for_missing_preset_raises(db: DatabaseManager) -> None:
    with pytest.raises(ValueError, match="не найден"):
        db.save_watermark("ghost", "T")


# ------------------------------------------------------------------ форматы


def test_format_and_processed_file_crud(db: DatabaseManager) -> None:
    db.create_format("TESTFMT")
    assert "TESTFMT" in db.list_formats()
    db.update_format("TESTFMT", "TESTFMT2")
    assert "TESTFMT2" in db.list_formats()
    db.delete_format("TESTFMT2")
    assert "TESTFMT2" not in db.list_formats()


@pytest.mark.parametrize("bad_name", ["", "   "])
def test_empty_format_name_rejected(db: DatabaseManager, bad_name: str) -> None:
    with pytest.raises(ValueError, match="не может быть пустым"):
        db.create_format(bad_name)
    with pytest.raises(ValueError, match="не может быть пустым"):
        db.update_format("PNG", bad_name)


def test_format_used_by_preset_cannot_be_deleted(db: DatabaseManager) -> None:
    db.create_preset(Preset(name="uses-png", output_format="PNG"))
    with pytest.raises(ValueError, match="используемый сохранённым профилем"):
        db.delete_format("PNG")


def test_seeded_formats_are_idempotent(db: DatabaseManager) -> None:
    before = db.list_formats()
    db._seed_formats()
    assert db.list_formats() == before


# ------------------------------------------------------------- журнал сессий


def test_session_file_history(db: DatabaseManager, tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"test-data")
    preset = Preset(name="history", output_format="PNG")
    session_id = db.create_session(preset, 1)
    item = QueueItem(source=source, status="Ошибка", error="sample error")
    db.log_processed_file(session_id, item)
    db.finish_session(session_id, 0.25, [item])
    assert db.list_processed_files(session_id)[0][5:] == ("Ошибка", "sample error")
    session = db.list_sessions()[0]
    assert session[4:7] == (1, 0, 1)
    db.delete_session(session_id)
    assert db.list_processed_files(session_id) == []


def test_finish_session_counts_success_and_failure(
        db: DatabaseManager, tmp_path: Path) -> None:
    source = tmp_path / "a.png"
    source.write_bytes(b"x")
    preset = Preset(name="counts", output_format="PNG")
    session_id = db.create_session(preset, 3)
    items = [
        QueueItem(source=source, status="Готово", output=source),
        QueueItem(source=source, status="Ошибка", error="boom"),
        QueueItem(source=source, status="Отменено"),
    ]
    for item in items:
        db.log_processed_file(session_id, item)
    db.finish_session(session_id, 1.5, items)
    session = db.list_sessions()[0]
    assert session[4:7] == (3, 1, 1)
    assert session[7] == pytest.approx(1.5)
    assert session[2] is not None


def test_update_processed_file_rejects_negative_size(
        db: DatabaseManager, tmp_path: Path) -> None:
    session_id = db.create_session(Preset(name="neg"), 1)
    db.log_processed_file(session_id, QueueItem(source=tmp_path / "x.png"))
    file_id = db.list_processed_files(session_id)[0][0]
    with pytest.raises(ValueError, match="не может быть отрицательным"):
        db.update_processed_file(file_id, output_path="o.png", size_after=-1,
                                 status="Готово")


def test_update_missing_processed_file_raises(
        db: DatabaseManager, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="не найдена"):
        db.update_processed_file(999, output_path="o.png", size_after=1,
                                 status="Готово")


def test_delete_session_cascades_files(db: DatabaseManager, tmp_path: Path) -> None:
    session_id = db.create_session(Preset(name="cascade"), 2)
    db.log_processed_file(session_id, QueueItem(source=tmp_path / "a.png"))
    db.log_processed_file(session_id, QueueItem(source=tmp_path / "b.png"))
    assert len(db.list_processed_files(session_id)) == 2
    db.delete_session(session_id)
    assert db.list_processed_files(session_id) == []
    assert db.connection.execute(
        "SELECT COUNT(*) FROM tbl_processed_files").fetchone()[0] == 0


def test_session_without_saved_preset_is_allowed(
        db: DatabaseManager, tmp_path: Path) -> None:
    """Пресета может ещё не быть в базе — сессия всё равно должна записаться."""
    session_id = db.create_session(Preset(name="transient", output_format="PNG"), 1)
    session = db.list_sessions()[0]
    assert session[3] == "transient"
    assert db.connection.execute(
        "SELECT preset_id FROM tbl_history_sessions WHERE id=?",
        (session_id,)).fetchone()[0] is None


def test_log_processed_file_uses_zero_for_missing_source(
        db: DatabaseManager, tmp_path: Path) -> None:
    session_id = db.create_session(Preset(name="nofile"), 1)
    db.log_processed_file(session_id, QueueItem(source=tmp_path / "missing.png"))
    row = db.list_processed_files(session_id)[0]
    assert row[3] == 0 and row[4] == 0 and row[5] == "В очереди"


def test_list_sessions_limit_is_clamped(db: DatabaseManager) -> None:
    for index in range(5):
        db.create_session(Preset(name=f"s{index}", output_format="PNG"), 1)
    assert len(db.list_sessions(limit=2)) == 2
    assert len(db.list_sessions(limit=100000)) == 5


def test_ensure_column_is_idempotent(tmp_path: Path) -> None:
    manager = DatabaseManager(str(tmp_path / "migrate.db"))
    before = {row[1] for row in manager.connection.execute(
        "PRAGMA table_info(tbl_processed_files)")}
    manager._ensure_column("tbl_processed_files", "error", "TEXT")
    after = {row[1] for row in manager.connection.execute(
        "PRAGMA table_info(tbl_processed_files)")}
    assert before == after
    manager.close()


def test_reopening_existing_database_keeps_data(tmp_path: Path) -> None:
    path = str(tmp_path / "persist.db")
    first = DatabaseManager(path)
    first.create_preset(Preset(name="keep", output_format="PNG", quality=42))
    first.close()
    second = DatabaseManager(path)
    assert second.get_preset("keep").quality == 42
    second.close()


def test_database_file_is_created_in_missing_directory(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c" / "app.db"
    manager = DatabaseManager(str(nested))
    assert nested.exists()
    assert len(manager.list_formats()) == 9
    manager.close()