"""Системные и UI-тесты главного окна: проверка реального поведения приложения.

Тесты поднимают настоящее окно Tkinter, подменяя файловую СУБД временной папкой
и модальные диалоги, чтобы проверять полный пользовательский сценарий:
добавление файлов -> настройка -> запуск -> отмена/завершение -> журнал.
"""
import time
from pathlib import Path

import pytest

from PIL import Image

tk = pytest.importorskip("tkinter")

from app import ui  # noqa: E402
from app.ui import (STATE_DONE, STATE_IDLE,  # noqa: E402
                    STATE_QUEUED, STATE_RUNNING,
                    SUPPORTED_EXTENSIONS, human_size, load_thumbnail,
                    mix_colors)


# ------------------------------------------------------------ заглушки диалогов


class FakeMessageBox:
    """Заменяет модальные окна, чтобы тест не блокировался."""

    def __init__(self) -> None:
        self.calls: list = []

    def _record(self, kind, title, message=None):
        self.calls.append((kind, title, message))

    def showinfo(self, title="", message=""):
        self._record("info", title, message)

    def showwarning(self, title="", message=""):
        self._record("warning", title, message)

    def showerror(self, title="", message=""):
        self._record("error", title, message)


def make_png(path: Path, size=(200, 150), color=(90, 140, 200)) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def pump(window, predicate, timeout=30.0):
    """Прогоняет цикл событий Tkinter до выполнения условия."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        window.update()
        if predicate():
            return True
        time.sleep(0.02)
    window.update()
    return predicate()


# ------------------------------------------------------- чистые функции UI


@pytest.mark.parametrize("size,expected", [
    (0, "0.0 КБ"),
    (512, "0.5 КБ"),
    (1024, "1.0 КБ"),
    (1024 * 1024, "1.0 МБ"),
    (5 * 1024 * 1024, "5.0 МБ"),
])
def test_human_size(size, expected):
    assert human_size(size) == expected


def test_mix_colors_boundaries():
    assert mix_colors("#000000", "#FFFFFF", 0.0) == "#000000"
    assert mix_colors("#000000", "#FFFFFF", 1.0) == "#FFFFFF"
    assert mix_colors("#000000", "#FFFFFF", -5) == "#000000"
    assert mix_colors("#000000", "#FFFFFF", 99) == "#FFFFFF"
    assert mix_colors("#000000", "#FFFFFF", 0.5) == "#808080"


def test_supported_extensions_cover_nine_formats():
    assert len(SUPPORTED_EXTENSIONS) == 11          # с учётом .jpeg и .tif
    assert {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff",
            ".gif", ".ico", ".heic", ".avif"} <= set(SUPPORTED_EXTENSIONS)


def test_load_thumbnail_returns_none_for_missing_file(tmp_path):
    assert load_thumbnail(tmp_path / "нет.png") is None


def test_load_thumbnail_returns_none_for_broken_file(tmp_path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"broken")
    assert load_thumbnail(broken) is None


# ------------------------------------------------ работа очереди в окне


def test_window_starts_in_idle_state(window):
    assert window.state == STATE_IDLE
    assert window.items == []
    assert window.selected_index == -1


def test_append_paths_switches_to_queued(window, tmp_path):
    first = make_png(tmp_path / "a.png")
    second = make_png(tmp_path / "b.png")
    window._append_paths([str(first), str(second)])
    assert window.state == STATE_QUEUED
    assert [item.source for item in window.items] == [first, second]
    assert window.selected_index == 0


def test_append_paths_ignores_duplicates_and_unsupported(window, tmp_path):
    good = make_png(tmp_path / "a.png")
    text = tmp_path / "note.txt"
    text.write_text("не изображение", encoding="utf-8")
    window._append_paths([str(good), str(good), str(text)])
    assert len(window.items) == 1
    assert window.items[0].source == good


def test_remove_row_drops_file(window, tmp_path):
    first = make_png(tmp_path / "a.png")
    second = make_png(tmp_path / "b.png")
    window._append_paths([str(first), str(second)])
    window._on_row_remove(window.queue_list._rows[1])
    assert [item.source for item in window.items] == [first]


def test_removing_last_file_returns_to_idle(window, tmp_path):
    only = make_png(tmp_path / "a.png")
    window._append_paths([str(only)])
    window._on_row_remove(window.queue_list._rows[0])
    assert window.items == [] and window.state == STATE_IDLE


def test_clear_queue_returns_to_idle(window, tmp_path):
    window._append_paths([str(make_png(tmp_path / "a.png"))])
    window.clear_queue()
    assert window.items == [] and window.state == STATE_IDLE


def test_add_folder_reads_supported_files_only(window, tmp_path, monkeypatch):
    folder = tmp_path / "folder"
    folder.mkdir()
    make_png(folder / "one.png")
    make_png(folder / "two.jpg")
    (folder / "skip.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(ui.filedialog, "askdirectory", lambda **_: str(folder))
    window.add_folder()
    assert len(window.items) == 2


# ---------------------------------------------- настройки и профили в БД


def test_build_preset_reads_form_fields(window, tmp_path):
    window.format_var.set("PNG")
    window.width_var.set("640")
    window.height_var.set("480")
    window.quality_var.set(65)
    window.exif_var.set(False)
    window.ratio_var.set(False)
    window.preset_var.set("Профиль из формы")
    window.output_var.set(str(tmp_path))
    preset = window._build_preset()
    assert (preset.name, preset.output_format) == ("Профиль из формы", "PNG")
    assert (preset.resize_mode, preset.resize_value, preset.quality) == ("FIT", "640x480", 65)
    assert preset.clear_exif is False and preset.keep_ratio is False


def test_save_and_load_preset_roundtrip(window, tmp_path):
    window.preset_var.set("Круговой тест")
    window.format_var.set("BMP")
    window.width_var.set("320")
    window.quality_var.set(55)
    window.watermark_text_var.set("SIGN")
    window.output_var.set(str(tmp_path))
    window.save_preset()
    assert "Круговой тест" in window.database.list_presets()
    assert any(call[0] == "info" for call in window.dialogs.calls)

    window.format_var.set("PNG")
    window.width_var.set("999")
    window.quality_var.set(10)
    window._load_selected_preset()
    assert window.format_var.get() == "BMP"
    assert window.width_var.get() == "320"
    assert window.quality_var.get() == 55
    assert window.watermark_text_var.get() == "SIGN"


def test_save_preset_with_invalid_size_shows_error(window):
    window.preset_var.set("Сломанный")
    window.width_var.set("0")
    window.save_preset()
    assert any(call[0] == "error" for call in window.dialogs.calls)
    assert "Сломанный" not in window.database.list_presets()


def test_loading_absent_preset_does_nothing(window):
    window.preset_var.set("отсутствующий")
    before = window.format_var.get()
    window._load_selected_preset()
    assert window.format_var.get() == before


# ------------------------------------------------------- полный сценарий


def test_start_without_files_warns(window):
    window.start_processing()
    assert any(call[0] == "warning" for call in window.dialogs.calls)


def test_full_processing_scenario(window, tmp_path):
    output = tmp_path / "out"
    window._append_paths([str(make_png(tmp_path / f"f{i}.png")) for i in range(3)])
    window.format_var.set("PNG")
    window.width_var.set("120")
    window.watermark_var.set(False)
    window.output_var.set(str(output))

    window.start_processing()
    assert window.state == STATE_RUNNING
    # У RoundedButton нет публичного геттера, надпись хранится в _text.
    assert window.action_button._text == "ОТМЕНА"

    assert pump(window, lambda: window.state == STATE_DONE, timeout=30)
    assert all(item.status == "Готово" for item in window.items)
    assert all(item.output.exists() for item in window.items)
    assert window.action_button._text == "ОБРАБОТАТЬ ЕЩЁ"
    assert len(list(output.glob("*.png"))) == 3

    session = window.database.list_sessions()[0]
    assert (session[4], session[5], session[6]) == (3, 3, 0)
    assert len(window.database.list_processed_files(session[0])) == 3


def test_broken_file_does_not_stop_queue(window, tmp_path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image at all")
    window._append_paths([str(make_png(tmp_path / "ok1.png")), str(broken),
                          str(make_png(tmp_path / "ok2.png"))])
    window.format_var.set("PNG")
    window.output_var.set(str(tmp_path / "out"))
    window.start_processing()
    assert pump(window, lambda: window.state == STATE_DONE, timeout=30)

    statuses = [item.status for item in window.items]
    assert statuses == ["Готово", "Ошибка", "Готово"]
    assert any(call[0] == "warning" for call in window.dialogs.calls)
    session = window.database.list_sessions()[0]
    assert (session[5], session[6]) == (2, 1)


def test_start_processing_rejects_invalid_dimensions(window, tmp_path):
    window._append_paths([str(make_png(tmp_path / "a.png"))])
    window.width_var.set("-10")
    window.start_processing()
    assert any(call[0] == "error" for call in window.dialogs.calls)
    assert window.state != STATE_RUNNING
    assert window.items[0].status == "В очереди"


def test_start_processing_detects_missing_file(window, tmp_path):
    ghost = tmp_path / "ghost.png"
    window.items.append(ui.QueueItem(ghost))
    window.output_var.set(str(tmp_path / "out"))
    window.start_processing()
    assert any(call[0] == "error" for call in window.dialogs.calls)
    assert window.state != STATE_RUNNING


def test_cancel_stops_queue_and_marks_rest(window, tmp_path):
    window._append_paths([str(make_png(tmp_path / f"c{i}.png", (900, 700)))
                          for i in range(6)])
    window.format_var.set("PNG")
    window.output_var.set(str(tmp_path / "out"))
    window.start_processing()
    assert window.state == STATE_RUNNING
    window.cancel_processing()
    assert pump(window, lambda: window.state == STATE_DONE, timeout=30)
    assert any(item.status in {"Отменено", "Готово"} for item in window.items)
    assert window.summary_title.cget("text").startswith("Обработка")


def test_start_over_clears_state(window, tmp_path):
    window._append_paths([str(make_png(tmp_path / "a.png"))])
    window.start_over()
    assert window.items == [] and window.state == STATE_IDLE
    assert window.selected_index == -1


def test_queue_is_blocked_while_running(window, tmp_path):
    window._append_paths([str(make_png(tmp_path / f"r{i}.png", (900, 700)))
                          for i in range(5)])
    window.format_var.set("PNG")
    window.output_var.set(str(tmp_path / "out"))
    window.start_processing()
    count = len(window.items)
    window._append_paths([str(make_png(tmp_path / "extra.png"))])
    assert len(window.items) == count
    assert any(call[0] == "warning" for call in window.dialogs.calls)
    window.worker.cancel()
    pump(window, lambda: window.state == STATE_DONE, timeout=30)


def test_progress_display_counts_finished_files(window, tmp_path):
    window._append_paths([str(make_png(tmp_path / f"p{i}.png")) for i in range(2)])
    window.format_var.set("PNG")
    window.output_var.set(str(tmp_path / "out"))
    window.start_processing()
    assert pump(window, lambda: window.state == STATE_DONE, timeout=30)
    assert "2 из 2 файлов" in window.summary_detail.cget("text")


def test_preview_shows_processed_result(window, tmp_path):
    """Регрессия: блок «После обработки» не должен оставаться пустым."""
    window._append_paths([str(make_png(tmp_path / "one.png"))])
    window.format_var.set("PNG")
    window.width_var.set("160")
    window.output_var.set(str(tmp_path / "out"))
    window.start_processing()
    assert pump(window, lambda: window.state == STATE_DONE, timeout=30)
    item = window.items[0]
    assert item.output.exists()
    assert item.source.exists()
    before_label = window.preview.before[1]
    after_label = window.preview.after[1]
    # Обе панели «Сравнение до и после» показывают изображение, а не заглушку.
    assert before_label.cget("text") == "" and before_label.cget("image")
    assert after_label.cget("text") == "" and after_label.cget("image")