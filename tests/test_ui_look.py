"""Проверки оформления: значок, бейджи, панель профилей и экспорт.

Набор дополняет проверки поведения интерфейса: он смотрит на то, что
пользователь видит глазами — значок программы, подпись экономии в
карточке файла, карточки профилей, подсветку при перетаскивании и
выгрузку отчёта в CSV.
"""
from pathlib import Path

from app.models import QueueItem


def _make_row(window, source: Path, output: Path, status: str,
              size_after: int = 250) -> QueueItem:
    """Создаёт обработанный элемент очереди с заданными размерами."""
    source.write_bytes(b"x" * 1000)
    output.write_bytes(b"x" * size_after)
    return QueueItem(source=source, status=status, output=output)


# ---------------------------------------------------------------- значок


def test_app_icon_contains_expected_sizes():
    """Файл значка содержит размеры, нужные Проводнику и заголовку окна."""
    from PIL import Image

    from app.ui import ICON_FILE

    assert ICON_FILE.exists(), "файл значка должен собираться в build_assets"
    with Image.open(ICON_FILE) as icon:
        sizes = set(icon.ico.sizes())
    for side in (16, 32, 64):
        assert (side, side) in sizes, f"в значке нет размера {side}x{side}"


def test_window_title_bar_uses_own_icon(window):
    """В заголовке окна стоит собственный значок, а не значок интерпретатора."""
    assert getattr(window, "_icon_photo", None) is not None


# ------------------------------------------------------- бейдж экономии


def test_saving_badge_hidden_before_processing(window, tmp_path):
    """До обработки экономия не показана: сравнивать ещё нечего."""
    from app.ui import QueueRow

    source = tmp_path / "a.png"
    source.write_bytes(b"x" * 1000)
    row = QueueRow(window, lambda _row: None, lambda _row: None)
    row.update_item(QueueItem(source=source), False)
    assert row.saving.cget("text") == ""


def test_saving_badge_shows_reduction(window, tmp_path):
    """После обработки показывается сокращение размера файла."""
    from app.ui import COLORS, QueueRow

    source = tmp_path / "a.png"
    output = tmp_path / "a.webp"
    row = QueueRow(window, lambda _row: None, lambda _row: None)
    row.update_item(_make_row(window, source, output, "Готово"), False)
    assert row.saving.cget("text") == "−75 % размера"
    assert row.saving.cget("fg") == COLORS["saving"]


def test_saving_badge_marks_growth(window, tmp_path):
    """Если результат больше исходника, бейдж краснеет и показывает плюс."""
    from app.ui import COLORS, QueueRow

    source = tmp_path / "a.png"
    output = tmp_path / "a.tiff"
    row = QueueRow(window, lambda _row: None, lambda _row: None)
    row.update_item(_make_row(window, source, output, "Готово", size_after=2500), False)
    assert row.saving.cget("text") == "+150 % размера"
    assert row.saving.cget("fg") == COLORS["growth"]


def test_saving_badge_absent_for_failed_file(window, tmp_path):
    """У ошибочного файла результата нет, поэтому бейдж не показывается."""
    from app.ui import QueueRow

    source = tmp_path / "a.png"
    source.write_bytes(b"x" * 1000)
    row = QueueRow(window, lambda _row: None, lambda _row: None)
    row.update_item(QueueItem(source=source, status="Ошибка", error="битый файл"), False)
    assert row.saving.cget("text") == ""


# ---------------------------------------------------- боковая панель


def test_preset_panel_shows_cards(window, tmp_path):
    """Сохранённые профили показаны карточками, а не списком в выпадающем окне."""
    window.preset_var.set("Витрина")
    window.format_var.set("WebP")
    window.width_var.set("1280")
    window.output_var.set(str(tmp_path))
    window.save_preset()

    assert "Витрина" in window.database.list_presets()
    assert [card.preset_name for card in window._preset_cards] == ["Витрина"]
    summary = window._preset_cards[0].subtitle.cget("text")
    assert "WebP" in summary and "1280" in summary


def test_preset_panel_card_applies_profile(window, tmp_path):
    """Клик по карточке загружает параметры профиля в форму."""
    window.preset_var.set("Каталог")
    window.format_var.set("BMP")
    window.width_var.set("640")
    window.quality_var.set(55)
    window.output_var.set(str(tmp_path))
    window.save_preset()

    window.format_var.set("PNG")
    window.quality_var.set(10)
    window.apply_preset("Каталог")

    assert window.format_var.get() == "BMP"
    assert window.width_var.get() == "640"
    assert window.quality_var.get() == 55
    assert window._preset_cards[0]._selected is True


def test_preset_panel_shows_hint_when_empty(window):
    """Без профилей панель объясняет, как их создать."""
    window._load_presets()
    assert window._preset_cards == []
    labels = [child.cget("text") for child in window.preset_list.winfo_children()
              if isinstance(child, type(window.queue_title))]
    assert any("Сохранить" in text for text in labels)


def test_preset_delete_removes_card(window, tmp_path):
    """Удаление профиля убирает его карточку из панели."""
    window.preset_var.set("Черновик")
    window.output_var.set(str(tmp_path))
    window.save_preset()
    assert "Черновик" in window.database.list_presets()

    window._confirm_delete_preset("Черновик")

    assert "Черновик" not in window.database.list_presets()
    assert window._preset_cards == []


def test_preset_delete_without_name_warns(window):
    """Пустое имя не приводит к удалению и показывает предупреждение."""
    window.preset_var.set("   ")
    window.delete_preset()
    assert any(call[0] == "warning" for call in window.dialogs.calls)


# ------------------------------------------------------- подсветка


def test_card_pulse_lights_and_clears_border(window):
    """Перетаскивание зажигает рамку карточки, уход возвращает её исходный вид."""
    from app.ui import COLORS

    pulse = window._pulses["queue"]
    assert pulse.active is False

    window._drag_over("queue")
    assert pulse.active is True
    assert pulse.border.cget("bg") != COLORS["card_border"]
    assert pulse.card.pack_info()["padx"] > 1

    window._drag_out("queue")
    assert pulse.active is False
    assert pulse.border.cget("bg") == COLORS["card_border"]
    assert pulse.card.pack_info()["padx"] == 1


def test_drag_moves_pulse_between_cards(window):
    """Подсветка переходит на ту карточку, над которой находится курсор."""
    window._drag_over("presets")
    assert window._pulses["presets"].active is True
    assert window._pulses["queue"].active is False
    assert window.queue_title.cget("text") == "Очередь файлов для обработки"

    window._drag_over("queue")
    assert window._pulses["queue"].active is True
    assert window._pulses["presets"].active is False
    assert "Отпустите файлы" in window.queue_title.cget("text")


# ------------------------------------------------- закреплённый блок


def test_action_button_is_outside_scroll_area(window):
    """Кнопка запуска закреплена и не уезжает в прокрутку формы."""
    from app.ui import PAD

    viewport = window._settings_viewport
    scroll_top = viewport.canvasy(0)
    scroll_bottom = scroll_top + viewport.winfo_height()
    top = window.action_button.winfo_rooty() - window.winfo_rooty()
    assert top < scroll_bottom + PAD, "кнопка запуска должна быть видна без прокрутки"


def test_export_button_shares_action_block(window):
    """Кнопка выгрузки отчёта стоит рядом с кнопкой запуска."""
    assert window.export_button.master is window.action_button.master


# ------------------------------------------------------------- подсказки


def test_tooltip_appears_and_disappears(window):
    """Подсказка показывается по наведению и убирается по уходу курсора."""
    from app.ui import Tooltip

    tooltip = Tooltip(window.export_button, "Подсказка для проверки")
    assert tooltip._window is None

    tooltip._show()
    assert tooltip._window is not None
    assert tooltip._window.winfo_exists() == 1

    tooltip._hide()
    assert tooltip._window is None


def test_tooltip_is_delayed_and_cancelable(window):
    """Подсказка не появляется мгновенно и отменяется уходом курсора."""
    import time

    from app.ui import Tooltip

    tooltip = Tooltip(window.export_button, "Подсказка для проверки")
    tooltip._schedule()
    assert tooltip._after_id is not None
    assert tooltip._window is None, "подсказка не должна появляться мгновенно"

    time.sleep(tooltip.DELAY / 1000 + 0.15)
    window.update()
    assert tooltip._window is not None, "подсказка должна появиться после задержки"

    tooltip._schedule()
    tooltip._hide()
    time.sleep(tooltip.DELAY / 1000 + 0.15)
    window.update()
    assert tooltip._window is None


# --------------------------------------------------------- экспорт CSV


def test_export_report_writes_csv(window, tmp_path):
    """Выгрузка отчёта создаёт файл и сообщает о нём в журнал."""
    window.output_var.set(str(tmp_path))
    window._append_paths([str(sample) for sample in _make_samples(tmp_path)])
    window.start_processing()
    _pump_until(window, lambda: all(item.status != "В обработке"
                                    for item in window.items))

    target = tmp_path / "отчёт.csv"
    window.dialogs.asksaveasfilename = lambda **_kwargs: str(target)
    window.export_report()

    assert target.exists()
    text = target.read_text(encoding="utf-8-sig")
    assert "Номер сессии" in text and "Экономия, %" in text
    assert any(call[0] == "info" for call in window.dialogs.calls)
    assert "Отчёт сохранён" in window.log_text.get("1.0", "end")


def test_export_report_cancelled(window, tmp_path):
    """Отмена диалога сохранения не создаёт файл и не пишет в журнал."""
    window.dialogs.asksaveasfilename = lambda **_kwargs: ""
    before = window.log_text.get("1.0", "end")
    window.export_report()
    assert window.log_text.get("1.0", "end") == before
    assert list(tmp_path.glob("*.csv")) == []


def test_export_report_reports_write_error(window, tmp_path):
    """Недоступная для записи папка приводит к понятному сообщению."""
    window.dialogs.asksaveasfilename = lambda **_kwargs: str(
        tmp_path / "нет-такой-папки" / "отчёт.csv")
    window.export_report()
    assert any(call[0] == "error" for call in window.dialogs.calls)


def test_export_button_uses_csv_extension(window, monkeypatch):
    """Диалог сохранения отчёта предлагает имя файла с расширением .csv."""
    from app import reporting, ui

    captured = {}

    def fake_dialog(**kwargs):
        captured.update(kwargs)
        return ""

    monkeypatch.setattr(ui, "filedialog", type("D", (), {
        "asksaveasfilename": staticmethod(fake_dialog)})())
    window.export_report()
    assert captured["defaultextension"] == ".csv"
    assert captured["initialfile"].endswith(".csv")
    assert reporting.default_file_name().endswith(".csv")


# ---------------------------------------------------------- вспомогательное


def _pump_until(window, predicate, timeout: float = 30.0) -> bool:
    """Прогоняет цикл событий окна до выполнения условия."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        window.update()
        if predicate():
            return True
        time.sleep(0.02)
    window.update()
    return predicate()


def _make_samples(folder: Path, count: int = 2) -> list:
    """Создаёт простые изображения для заполнения очереди."""
    from PIL import Image

    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(count):
        path = folder / f"shot_{index + 1}.png"
        Image.new("RGB", (320, 240), (40 + index * 20, 90, 160)).save(path)
        paths.append(path)
    return paths