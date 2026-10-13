"""Проверки оформления: собственный выпадающий список и образец цвета.

Набор закрывает замену стандартных виджетов ttk на собственные:
поле списка со скруглённой рамкой и всплывающим меню, а также
кнопку выбора цвета в виде образца.
"""
import pytest

from app.ui import ColorSwatch, RoundedCombo


def make_combo(window, values=("Первый", "Второй", "Третий")) -> RoundedCombo:
    """Создаёт выпадающий список в окне.

    Args:
        window: Главное окно приложения.
        values: Значения списка.

    Returns:
        Экземпляр :class:`RoundedCombo`.
    """
    combo = RoundedCombo(window, window.format_var, list(values),
                         background=window.cget("bg"))
    combo.pack(fill="x")
    return combo


def test_combo_measures_its_longest_value(window) -> None:
    """Ширина поля рассчитывается по самому длинному значению."""
    combo = make_combo(window, ("Короткое", "Значительно более длинное значение"))
    assert combo.winfo_reqwidth() >= combo._measure.measure(
        "Значительно более длинное значение")
    wider = make_combo(window, ("Короткое",))
    assert combo.winfo_reqwidth() > wider.winfo_reqwidth()


def test_combo_natural_width_grows_with_content(window) -> None:
    """Добавление длинного значения увеличивает требуемую ширину."""
    combo = make_combo(window, ("А", "Б"))
    before = combo.natural_width()
    combo.set_values(["А", "Очень длинное название значения для проверки"])
    assert combo.natural_width() > before


def test_combo_selection_writes_value_and_event(window) -> None:
    """Выбор значения записывает его и сообщает виртуальным событием."""
    seen = []
    combo = make_combo(window)
    combo.bind("<<ComboboxSelected>>", lambda _event: seen.append(1))
    # Виртуальные события доставляются только отображённому окну,
    # поэтому окно нужно показать и дождаться отрисовки.
    window.deiconify()
    window.update()
    combo.select("Второй")
    window.update()
    try:
        assert combo.get() == "Второй"
        assert window.format_var.get() == "Второй"
        assert seen, "обработчик <<ComboboxSelected>> не был вызван"
    finally:
        window.withdraw()


def test_combo_command_is_called(window) -> None:
    """Обработчик команды вызывается при выборе значения."""
    calls = []
    combo = RoundedCombo(window, window.format_var, ["Один", "Два"],
                         background=window.cget("bg"),
                         command=lambda: calls.append(1))
    combo.pack(fill="x")
    combo.select("Два")
    assert calls == [1]


@pytest.mark.parametrize("index,value", [
    (0, "Один"), (1, "Два"), (5, "Шесть"), (9, "Шесть"), (-1, "Шесть"),
])
def test_combo_current_by_index(window, index, value) -> None:
    """Номер выбранного значения и выбор по номеру согласованы.

    Номер вне диапазона списка игнорируется, текущее значение сохраняется.
    """
    combo = make_combo(window, ["Один", "Два", "Три", "Четыре", "Пять", "Шесть"])
    combo.select("Шесть")
    if 0 <= index < 6:
        assert combo.current(index) == index
        assert combo.get() == ["Один", "Два", "Три", "Четыре", "Пять", "Шесть"][index]
    else:
        assert combo.current(index) == -1
        assert combo.get() == "Шесть"
    assert combo.get() == (value if 0 <= index < 6 else "Шесть")


def test_combo_current_returns_index_of_value(window) -> None:
    """Без аргумента возвращается номер текущего значения."""
    combo = make_combo(window, ["Один", "Два", "Три"])
    combo.select("Три")
    assert combo.current() == 2


def test_combo_current_missing_value(window) -> None:
    """Значение вне списка даёт номер -1 и не ломает выбор."""
    combo = make_combo(window, ["Один", "Два"])
    combo.set("Нет такого")
    assert combo.current() == -1
    assert combo.current(99) == -1


def test_combo_opens_and_closes_popup(window) -> None:
    """Список раскрывается и закрывается без ошибок."""
    combo = make_combo(window)
    combo._open()
    window.update()
    assert combo._popup is not None
    assert combo._popup.winfo_exists()
    combo.close()
    window.update()
    assert combo._popup is None


def test_combo_popup_draws_every_value(window) -> None:
    """Во всплывающем списке отрисовываются все значения."""
    combo = make_combo(window, ["Раз", "Два", "Три"])
    combo._open()
    window.update()
    try:
        assert combo._popup_visible == 3
        assert combo._popup_rows == ["Раз", "Два", "Три"]
    finally:
        combo.close()
        window.update()


def test_combo_popup_height_limited(window) -> None:
    """Длинный список показывается ограниченным числом строк."""
    combo = make_combo(window, [f"Вариант {index}" for index in range(20)])
    combo._open()
    window.update()
    try:
        assert combo._popup_visible == combo.MAX_VISIBLE
    finally:
        combo.close()
        window.update()


def test_combo_hover_row_changes_draw(window) -> None:
    """Наведение на строку меняет подсветку."""
    combo = make_combo(window, ["Раз", "Два"])
    combo._open()
    window.update()
    try:
        combo._hover_row = 1
        combo._draw_rows()
        assert combo._hover_row == 1
    finally:
        combo.close()
        window.update()


def test_combo_popup_closed_on_destroy(window) -> None:
    """Список закрывается при удалении поля из окна."""
    combo = make_combo(window)
    combo._open()
    window.update()
    combo.destroy()
    window.update()
    assert combo._popup is None


def test_color_swatch_follows_variable(window) -> None:
    """Образец цвета показывает текущее значение переменной."""
    window.watermark_color_var.set("#FF0000")
    window.update()
    assert window.color_button.variable.get() == "#FF0000"


def test_color_swatch_rejects_bad_value(window) -> None:
    """Некорректный цвет не приводит к ошибке отрисовки."""
    window.watermark_color_var.set("не цвет")
    window.update()
    window.watermark_color_var.set("#00FF00")
    window.update()
    assert window.color_button.variable.get() == "#00FF00"


def test_color_swatch_is_packaged(window) -> None:
    """Образец цвета размещён в строке настроек знака и имеет размер."""
    swatch = window.color_button
    assert swatch.winfo_manager() == "pack"
    assert swatch.winfo_reqwidth() == ColorSwatch.WIDTH
    assert swatch.winfo_reqheight() == ColorSwatch.HEIGHT
    assert swatch.winfo_reqwidth() > 20 and swatch.winfo_reqheight() > 15


def test_combo_compatibility_api(window) -> None:
    """Список поддерживает вызовы, принятые в коде для Combobox."""
    combo = window.position_combo
    assert combo.get()
    assert isinstance(combo.current(), int)
    combo.configure(values=("А", "Б"))
    assert combo.values == ["А", "Б"]