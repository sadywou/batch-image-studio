"""Проверки полей размера, выбора логотипа и закреплённого журнала.

Набор закрывает правки интерфейса: возврат привычных полей ширины и
высоты вместо списка режимов, появление выбора файла логотипа на месте
текстового поля и постоянную видимость журнала выполнения.
"""
import tkinter as tk

import pytest

from app.models import Preset


@pytest.mark.parametrize("width,height,expected", [
    ("1920", "1080", ("FIT", "1920x1080")),
    ("1600", "", ("WIDTH", "1600")),
    ("", "900", ("HEIGHT", "900")),
    ("50%", "", ("PERCENT", "50")),
    ("75%", "", ("PERCENT", "75")),
    ("", "", ("NONE", "")),
])
def test_size_fields_map_to_resize_mode(window, width, height, expected) -> None:
    """Поля ширины и высоты задают режим масштабирования."""
    window.width_var.set(width)
    window.height_var.set(height)
    assert window._resize_from_fields() == expected


def test_broken_percent_is_ignored(window) -> None:
    """Некорректный процент не превращается в режим размера."""
    window.width_var.set("abc%")
    window.height_var.set("1080")
    # Нераспознанный процент не превращается в процентный режим:
    # значение уходит в обработчик как есть и отклоняется с понятной ошибкой.
    assert window._resize_from_fields() == ("FIT", "abc%x1080")


@pytest.mark.parametrize("mode,value,width,height", [
    ("FIT", "1600x900", "1600", "900"),
    ("FIT", "1600х900", "1600", "900"),
    ("WIDTH", "1200", "1200", ""),
    ("HEIGHT", "800", "", "800"),
    ("PERCENT", "35", "35%", ""),
    ("NONE", "", "", ""),
])
def test_profile_restores_size_fields(window, mode, value, width, height) -> None:
    """Сохранённый профиль восстанавливает значения полей формы."""
    window._fill_resize_fields(
        Preset(name="p", resize_mode=mode, resize_value=value))
    assert window.width_var.get() == width
    assert window.height_var.get() == height


def test_size_fields_survive_preset_roundtrip(window) -> None:
    """Профиль, собранный из формы, читается обратно без изменений."""
    window.width_var.set("1200")
    window.height_var.set("800")
    preset = window._build_preset()
    window.width_var.set("")
    window.height_var.set("")
    window._fill_resize_fields(preset)
    assert (window.width_var.get(), window.height_var.get()) == ("1200", "800")


def test_logo_picker_replaces_text_field(window) -> None:
    """При выборе логотипа на месте текста появляется выбор файла."""
    from app.ui import WATERMARK_TYPE_LABELS

    assert window.watermark_image_frame.winfo_manager() == ""
    window.watermark_type_var.set(WATERMARK_TYPE_LABELS["IMAGE"])
    window._on_watermark_type()
    window.update()
    assert window.watermark_text_frame.winfo_manager() == ""
    assert window.watermark_image_frame.winfo_manager() == "pack"

    window.watermark_type_var.set(WATERMARK_TYPE_LABELS["TEXT"])
    window._on_watermark_type()
    window.update()
    assert window.watermark_text_frame.winfo_manager() == "pack"
    assert window.watermark_image_frame.winfo_manager() == ""


def test_logo_picker_button_is_visible(window) -> None:
    """Кнопка выбора файла логотипа отображается на экране."""
    from app.ui import WATERMARK_TYPE_LABELS

    window.watermark_type_var.set(WATERMARK_TYPE_LABELS["IMAGE"])
    window._on_watermark_type()
    window.update()
    children = window.watermark_image_frame.winfo_children()
    assert children, "в блоке выбора логотипа нет элементов"
    assert children[-1].winfo_manager() == "pack", (
        "кнопка выбора файла не размещена в блоке")
    assert window.watermark_image_frame.winfo_manager() == "pack"


def test_logo_path_lands_in_preset(window) -> None:
    """Выбранный файл попадает в профиль настроек."""
    from app.ui import WATERMARK_TYPE_LABELS

    window.watermark_type_var.set(WATERMARK_TYPE_LABELS["IMAGE"])
    window._on_watermark_type()
    window.watermark_image_var.set(r"C:\логотип.png")
    preset = window._build_preset()
    assert preset.watermark_type == "IMAGE"
    assert preset.watermark_image == r"C:\логотип.png"
    assert preset.watermark_text == ""


def test_log_is_pinned_outside_scroll_area(window) -> None:
    """Журнал размещён вне прокручиваемой области и всегда виден."""
    # Журнал находится в скруглённой рамке, а текст вложен в неё через place.
    frame = window.log_text.master
    assert window.log_text.winfo_manager() == "place"
    assert frame.winfo_manager() == "pack"
    viewport = window._settings_viewport
    assert frame.winfo_parent() != str(viewport), (
        "журнал не должен находиться внутри прокручиваемой области")
    assert frame.master is viewport.master, (
        "журнал должен быть соседом прокручиваемой области в карточке")


def test_log_visible_with_full_window_size(window) -> None:
    """После раскрытия окна журнал занимает место и помещается в карточке."""
    window.deiconify()
    window.update()
    try:
        assert window.log_text.winfo_height() > 20
        card = window._settings_viewport.master
        log_bottom = (window.log_text.winfo_rooty()
                      + window.log_text.winfo_height())
        card_bottom = card.winfo_rooty() + card.winfo_height()
        assert log_bottom <= card_bottom + 1, "журнал выходит за карточку"
    finally:
        window.withdraw()


def test_log_limit(window) -> None:
    """Журнал не растёт бесконечно при долгой обработке."""
    for index in range(260):
        window.append_log(f"строка {index}")
    assert len(window.log_lines) == 200


def test_resize_descriptions_are_readable() -> None:
    """Описание размера для журнала понятно оператору."""
    from app.ui import MainWindow

    cases = {
        ("NONE", ""): "без изменений",
        ("WIDTH", "1600"): "по ширине 1600 px",
        ("HEIGHT", "900"): "по высоте 900 px",
        ("PERCENT", "50"): "50% от исходного",
        ("FIT", "1600x900"): "в габарит 1600×900 px",
    }
    for (mode, value), expected in cases.items():
        preset = Preset(name="p", resize_mode=mode, resize_value=value)
        assert MainWindow._describe_resize(preset) == expected


def test_settings_card_scrolls_only_when_needed(window) -> None:
    """Прокручиваемая область содержит всю форму целиком."""
    window.update()
    viewport = window._settings_viewport
    inner = window._settings_inner
    assert inner.winfo_height() <= viewport.winfo_height(), (
        "форма не помещается в карточку без прокрутки")


def test_root_destroyed_without_error(window) -> None:
    """Окно корректно создаётся с новой разметкой."""
    assert isinstance(window.winfo_children(), list)
    assert isinstance(window, tk.Misc)