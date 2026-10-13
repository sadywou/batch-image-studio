"""Проверки требований технического задания, добавленных при сверке.

Набор закрывает пункты 4.2.1 ТЗ: пять режимов масштабирования, девять
позиций водяного знака, графический знак с прозрачностью, настройки
размера и цвета текста, а также схему базы данных и журнал выполнения.
"""
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from app.database import DatabaseManager
from app.models import (RESIZE_MODES, WATERMARK_POSITIONS, Preset)
from app.processor import ImageProcessor


def make_image(path: Path, size=(1600, 900), color=(20, 20, 20)) -> Path:
    """Создаёт исходное изображение."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


# ------------------------------------------------- режимы масштабирования (ТЗ 4.2.1)


def test_all_five_resize_modes_are_declared():
    """ТЗ требует режимы WIDTH, HEIGHT, FIT (габарит) и PERCENT."""
    assert set(RESIZE_MODES) == {"WIDTH", "HEIGHT", "FIT", "PERCENT", "NONE"}


@pytest.mark.parametrize("mode,value,expected", [
    ("WIDTH", "800", (800, 450)),
    ("HEIGHT", "450", (800, 450)),
    ("FIT", "400x400", (400, 225)),
    ("FIT", "400х400", (400, 225)),      # русская «х» тоже принимается
    ("PERCENT", "50", (800, 450)),
    ("NONE", "", (1600, 900)),
])
def test_resize_modes(tmp_path: Path, mode, value, expected) -> None:
    source = make_image(tmp_path / "src.png")
    result = ImageProcessor().process(
        source, Preset(name=mode, output_format="PNG", resize_mode=mode,
                       resize_value=value, output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        assert image.size == expected


def test_fit_mode_keeps_proportions(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.png", (1000, 500))
    result = ImageProcessor().process(
        source, Preset(name="fit", output_format="PNG", resize_mode="FIT",
                       resize_value="300x300", output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        assert image.size == (300, 150)


def test_width_mode_without_ratio_stretches(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.png", (1000, 500))
    result = ImageProcessor().process(
        source, Preset(name="stretch", output_format="PNG", resize_mode="WIDTH",
                       resize_value="200", keep_ratio=False,
                       output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        assert image.size == (200, 200)


@pytest.mark.parametrize("mode,value", [
    ("WIDTH", "0"), ("WIDTH", "-10"), ("WIDTH", "abc"), ("WIDTH", ""),
    ("HEIGHT", "0"), ("PERCENT", "0"), ("PERCENT", "-5"),
    ("FIT", "400"), ("FIT", "axb"), ("NONE", ""),
])
def test_invalid_resize_values_rejected(tmp_path: Path, mode, value) -> None:
    source = make_image(tmp_path / "src.png")
    if mode == "NONE":
        pytest.skip("Режим NONE не требует значения")
    with pytest.raises(ValueError):
        ImageProcessor().process(
            source, Preset(name="bad", resize_mode=mode, resize_value=value,
                           output_dir=str(tmp_path / "out")))


def test_unknown_resize_mode_rejected(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.png")
    with pytest.raises(ValueError, match="режим масштабирования"):
        ImageProcessor().process(
            source, Preset(name="bad", resize_mode="DIAGONAL", resize_value="10",
                           output_dir=str(tmp_path / "out")))


# ----------------------------------------------------- водяной знак (ТЗ 4.2.1)


def test_nine_watermark_positions_are_declared():
    """ТЗ требует сетку из девяти стандартных позиций."""
    assert len(WATERMARK_POSITIONS) == 9
    assert "center" in WATERMARK_POSITIONS


@pytest.mark.parametrize("position", WATERMARK_POSITIONS)
def test_watermark_is_placed_in_its_cell(tmp_path: Path, position) -> None:
    """Знак должен попадать именно в свою треть изображения по каждой оси."""
    source = make_image(tmp_path / "src.png", (900, 600), (0, 0, 0))
    result = ImageProcessor().process(
        source, Preset(name=position, output_format="PNG", resize_mode="NONE",
                       watermark_enabled=True, watermark_type="TEXT",
                       watermark_text="STUDIO", watermark_position=position,
                       watermark_opacity=100, watermark_size=14,
                       output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        grey = image.convert("L")
        pixels = grey.load()
        width, height = grey.size
        xs = [x for y in range(height) for x in range(width) if pixels[x, y] > 10]
        ys = [y for y in range(height) for x in range(width) if pixels[x, y] > 10]
    center_x = (min(xs) + max(xs)) // 2
    center_y = (min(ys) + max(ys)) // 2
    column = ("left" if center_x < width // 3
              else "center" if center_x < 2 * width // 3 else "right")
    row = ("top" if center_y < height // 3
           else "middle" if center_y < 2 * height // 3 else "bottom")
    if position == "center":
        assert row in ("middle", "center") and column == "center"
    else:
        assert f"{row}-{column}" == position


def test_graphic_watermark_uses_logo_file(tmp_path: Path) -> None:
    """ТЗ требует графический знак из внешнего PNG с прозрачностью."""
    logo = tmp_path / "logo.png"
    mark = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    mark.putpixel((100, 100), (255, 0, 0, 255))
    mark.save(logo)
    source = make_image(tmp_path / "src.png", (600, 400), (0, 0, 0))
    result = ImageProcessor().process(
        source, Preset(name="logo", output_format="PNG", resize_mode="NONE",
                       watermark_enabled=True, watermark_type="IMAGE",
                       watermark_image=str(logo), watermark_position="center",
                       watermark_opacity=100, output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        rgb = image.convert("RGB")
        assert ImageChops.difference(
            rgb, Image.new("RGB", rgb.size, (0, 0, 0))).getbbox()


def test_missing_logo_file_raises_friendly_error(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.png")
    with pytest.raises(RuntimeError, match="водяного знака"):
        ImageProcessor().process(
            source, Preset(name="logo", resize_mode="NONE",
                           watermark_enabled=True, watermark_type="IMAGE",
                           watermark_image=str(tmp_path / "нет.png"),
                           output_dir=str(tmp_path / "out")))


def test_corrupted_logo_raises_friendly_error(tmp_path: Path) -> None:
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"not an image")
    source = make_image(tmp_path / "src.png")
    with pytest.raises(RuntimeError, match="Не удалось загрузить"):
        ImageProcessor().process(
            source, Preset(name="logo", resize_mode="NONE",
                           watermark_enabled=True, watermark_type="IMAGE",
                           watermark_image=str(logo),
                           output_dir=str(tmp_path / "out")))


def test_watermark_color_is_applied(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.png", (600, 400), (0, 0, 0))
    result = ImageProcessor().process(
        source, Preset(name="red", output_format="PNG", resize_mode="NONE",
                       watermark_enabled=True, watermark_type="TEXT",
                       watermark_text="X", watermark_color="#FF0000",
                       watermark_opacity=100, watermark_size=20,
                       watermark_position="center",
                       output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        red_channel, green_channel, _ = image.convert("RGB").split()
        assert red_channel.getextrema()[1] > 150
        assert green_channel.getextrema()[1] < 90


def test_watermark_size_changes_coverage(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.png", (600, 400), (0, 0, 0))
    areas = []
    for size in (3, 18):
        result = ImageProcessor().process(
            source, Preset(name=f"s{size}", output_format="PNG",
                           resize_mode="NONE", watermark_enabled=True,
                           watermark_type="TEXT", watermark_text="S",
                           watermark_size=size, watermark_opacity=100,
                           watermark_position="center",
                           output_dir=str(tmp_path / "out")))
        with Image.open(result) as image:
            grey = image.convert("L")
            lit = sum(1 for row in range(0, grey.size[1], 2)
                      for column in range(0, grey.size[0], 2)
                      if grey.getpixel((column, row)) > 10)
        areas.append(lit)
    assert areas[1] > areas[0] * 4, "крупный знак должен покрывать больше пикселей"


def test_opacity_zero_leaves_no_visible_mark(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.png", (400, 300), (5, 5, 5))
    result = ImageProcessor().process(
        source, Preset(name="zero", output_format="PNG", resize_mode="NONE",
                       watermark_enabled=True, watermark_type="TEXT",
                       watermark_text="HIDE", watermark_opacity=0,
                       output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        assert ImageChops.difference(
            image.convert("RGB"),
            Image.new("RGB", image.size, (5, 5, 5))).getbbox() is None


@pytest.mark.parametrize("value", [0, 21, -3])
def test_watermark_size_out_of_range_rejected(value: int) -> None:
    with pytest.raises(ValueError, match="Размер водяного знака"):
        ImageProcessor()._validate_preset(Preset(name="s", watermark_size=value))


# -------------------------------------------------- схема базы (ТЗ 4.3.2)


EXPECTED_COLUMNS = {
    "tbl_formats": ["id", "format_name"],
    "tbl_presets": ["id", "preset_name", "format_id", "resize_mode",
                    "resize_value", "compression_quality", "strip_metadata",
                    "keep_ratio", "output_dir"],
    "tbl_watermarks": ["preset_id", "wm_type", "wm_content", "wm_opacity",
                       "wm_position", "wm_size", "wm_color", "enabled"],
    "tbl_history_sessions": ["id", "session_date", "finished_at", "preset_id",
                             "preset_name", "total_files", "successful_files",
                             "failed_files", "duration_sec"],
    "tbl_processed_files": ["id", "session_id", "source_path", "result_path",
                            "file_size_before", "file_size_after", "status",
                            "error"],
}


@pytest.mark.parametrize("table,columns", list(EXPECTED_COLUMNS.items()))
def test_schema_matches_technical_specification(tmp_path, table, columns) -> None:
    """Набор таблиц и столбцов должен совпадать с разделом 4.3.2 ТЗ."""
    manager = DatabaseManager(str(tmp_path / "schema.db"))
    try:
        actual = [row[1] for row in
                  manager.connection.execute(f"PRAGMA table_info({table})")]
    finally:
        manager.close()
    assert actual == columns


def test_status_is_stored_as_success_and_error(tmp_path) -> None:
    """ТЗ задаёт статусы журнала в виде SUCCESS и ERROR."""
    from app.models import QueueItem

    manager = DatabaseManager(str(tmp_path / "status.db"))
    source = tmp_path / "a.png"
    source.write_bytes(b"x")
    preset = Preset(name="s", output_format="PNG")
    session = manager.create_session(preset, 2)
    manager.log_processed_file(session, QueueItem(source=source, status="Готово"))
    manager.log_processed_file(session, QueueItem(source=source, status="Ошибка",
                                                  error="boom"))
    manager.log_processed_file(session, QueueItem(source=source,
                                                  status="Отменено"))
    statuses = [row[5] for row in manager.list_processed_files(session)]
    manager.close()
    assert statuses == ["SUCCESS", "ERROR", "ERROR"]


def test_resize_settings_survive_roundtrip(tmp_path) -> None:
    """Режим и значение масштабирования должны сохраняться без потерь."""
    manager = DatabaseManager(str(tmp_path / "round.db"))
    manager.create_preset(Preset(name="r", output_format="WebP",
                                 resize_mode="FIT", resize_value="1200x800",
                                 quality=77))
    loaded = manager.get_preset("r")
    manager.close()
    assert loaded.resize_mode == "FIT"
    assert loaded.resize_value == "1200x800"
    assert loaded.quality == 77


def test_watermark_settings_survive_roundtrip(tmp_path) -> None:
    manager = DatabaseManager(str(tmp_path / "wm.db"))
    manager.create_preset(Preset(
        name="w", output_format="PNG", watermark_enabled=True,
        watermark_type="TEXT", watermark_text="ЗНАК",
        watermark_position="middle-left", watermark_opacity=45,
        watermark_size=9, watermark_color="#FF8800"))
    loaded = manager.get_preset("w")
    manager.close()
    assert loaded.watermark_text == "ЗНАК"
    assert loaded.watermark_position == "middle-left"
    assert loaded.watermark_opacity == 45
    assert loaded.watermark_size == 9
    assert loaded.watermark_color == "#FF8800"
