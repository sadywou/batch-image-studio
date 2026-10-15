"""Проверки диапазонов ползунков и записи файла ICO.

Набор закрывает две жалобы пользователя: ползунок размера водяного
знака позволял выставить больше 20 процентов, из-за чего обработчик
отклонял настройки, и требование о трёх размерах в файле ICO.
"""
import struct

import pytest
from PIL import Image

from app.models import Preset
from app.processor import ImageProcessor


# --------------------------------------------- размер водяного знака (1–20)


def test_watermark_slider_range(window) -> None:
    """Ползунок размера знака ограничен диапазоном от 1 до 20."""
    slider = window.watermark_size
    assert slider.minimum == 1
    assert slider.maximum == 20


@pytest.mark.parametrize("position,expected", [
    (0, 1),
    (-500, 1),
    (1, 1),
    (10 ** 6, 20),
])
def test_watermark_slider_never_exceeds_limit(window, position, expected) -> None:
    """Ни при каком положении курсора ползунок не выйдет за пределы.

    Окно разворачивается: у скрытого окна ширина равна единице,
    и доля положения курсора вычисляется неверно.
    """
    window.deiconify()
    window.update()
    try:
        assert window.watermark_size.winfo_width() > 10, "окно не отрисовано"
        assert window.watermark_size.value_from_position(position) == expected
    finally:
        window.withdraw()


def test_watermark_slider_never_breaks_processing(window, tmp_path) -> None:
    """Значение, выставленное ползунком, всегда принимается обработчиком."""
    window.deiconify()
    window.update()
    slider = window.watermark_size
    try:
        for position in (0, 50, 200, 10 ** 6):
            slider.variable.set(slider.value_from_position(position))
            preset = window._build_preset()
            ImageProcessor._validate_preset(preset)
    finally:
        window.withdraw()


def test_quality_slider_keeps_full_range(window) -> None:
    """Ползунок качества по-прежнему работает в диапазоне 1–100."""
    assert window.slider.minimum == 1
    assert window.slider.maximum == 100
    assert window.slider.value_from_position(10 ** 6) == 100


def test_slider_rejects_inverted_range(window) -> None:
    """Ползунок с обратными границами не создаётся."""
    from app.ui import QualitySlider

    with pytest.raises(ValueError, match="больше минимума"):
        QualitySlider(window, window.quality_var, lambda _v=None: None,
                      minimum=100, maximum=10)


def test_slider_tracks_value_outside_range(window) -> None:
    """Значение вне диапазона не выводит бегунок за края дорожки."""
    slider = window.watermark_size
    slider.variable.set(999)
    slider._draw()
    slider.variable.set(-50)
    slider._draw()
    slider.variable.set(7)
    slider._draw()


# ------------------------------------------------------- файл ICO (16/32/64)


def ico_sizes(path) -> list:
    """Читает размеры изображений прямо из заголовка файла ICO.

    Args:
        path: Путь к файлу ICO.

    Returns:
        Отсортированный список размеров.
    """
    data = path.read_bytes()
    count = struct.unpack("<H", data[4:6])[0]
    sizes = []
    for index in range(count):
        offset = 6 + index * 16
        width, height = data[offset], data[offset + 1]
        sizes.append((width or 256, height or 256))
    return sorted(sizes)


@pytest.mark.parametrize("source_size", [(16, 16), (64, 64), (200, 120),
                                          (800, 600)])
def test_ico_always_contains_three_sizes(tmp_path, source_size) -> None:
    """При любом исходном размере в ICO записаны 16, 32 и 64."""
    source = tmp_path / "source.png"
    Image.new("RGB", source_size, (180, 60, 30)).save(source)
    result = ImageProcessor().process(
        source, Preset(name="ico", output_format="ICO", resize_mode="NONE",
                       resize_value="", output_dir=str(tmp_path / "out")))
    assert ico_sizes(result) == [(16, 16), (32, 32), (64, 64)]
    with Image.open(result) as image:
        assert sorted(image.ico.sizes()) == [(16, 16), (32, 32), (64, 64)]


def test_ico_sizes_survive_resize(tmp_path) -> None:
    """Уменьшение изображения не убирает размеры из ICO."""
    source = tmp_path / "source.png"
    Image.new("RGB", (900, 600), (40, 120, 180)).save(source)
    result = ImageProcessor().process(
        source, Preset(name="ico", output_format="ICO", resize_mode="FIT",
                       resize_value="400x400", output_dir=str(tmp_path / "out")))
    assert ico_sizes(result) == [(16, 16), (32, 32), (64, 64)]


def test_ico_is_square_and_transparent(tmp_path) -> None:
    """Холст ICO квадратный и прозрачный за пределами изображения."""
    from app.processor import ImageProcessor as Processor

    canvas = Processor._prepare_ico(Image.new("RGB", (300, 150), (0, 0, 255)))
    assert canvas.size[0] == canvas.size[1]
    assert canvas.mode == "RGBA"
    assert canvas.getpixel((0, 0))[3] == 0
    assert canvas.getpixel((canvas.width // 2, canvas.height // 2))[:3] == (0, 0, 255)