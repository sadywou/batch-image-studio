"""Модульные проверки бизнес-логики обработки изображений (app/processor.py)."""
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from app.models import Preset
from app.processor import ImageProcessor


def make_image(path: Path, size=(100, 50), color="white", mode="RGB") -> Path:
    """Создаёт исходное изображение для проверки."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path)
    return path


# --------------------------------------------------- основной сценарий


def test_resize_and_convert(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png")
    preset = Preset(name="test", output_format="JPG", width=50, height=50,
                    quality=80, output_dir=str(tmp_path / "out"))
    result = ImageProcessor().process(source, preset)
    assert result.exists()
    with Image.open(result) as image:
        assert image.size == (50, 25)
        assert image.format == "JPEG"
    assert source.exists()


def test_keep_ratio_false_resizes_to_exact_size(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (100, 50))
    preset = Preset(name="stretch", output_format="PNG", width=80, height=80,
                    keep_ratio=False, output_dir=str(tmp_path / "out"))
    with Image.open(ImageProcessor().process(source, preset)) as image:
        assert image.size == (80, 80)


def test_only_one_dimension_keeps_second_side(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (400, 200))
    preset = Preset(name="width-only", output_format="PNG", width=100,
                    output_dir=str(tmp_path / "out"))
    with Image.open(ImageProcessor().process(source, preset)) as image:
        assert image.size == (100, 50)


def test_no_dimensions_returns_identical_image(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (64, 48))
    preset = Preset(name="asis", output_format="PNG", output_dir=str(tmp_path / "out"))
    with Image.open(ImageProcessor().process(source, preset)) as image:
        assert image.size == (64, 48)


def test_process_reports_monotonic_progress(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png")
    preset = Preset(name="progress", output_format="PNG", output_dir=str(tmp_path / "out"))
    steps: list[int] = []
    ImageProcessor().process(source, preset, progress=steps.append)
    assert steps[0] == 8 and steps[-1] == 100
    assert steps == sorted(steps)


# ------------------------------------------------------------ водяной знак


def test_watermark_changes_image(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (320, 180), (20, 20, 20))
    preset = Preset(name="wm", output_format="PNG", output_dir=str(tmp_path / "out"),
                    watermark_enabled=True, watermark_text="TEST", watermark_opacity=100)
    result = ImageProcessor().process(source, preset)
    with Image.open(result) as image:
        assert ImageChops.difference(
            image.convert("RGB"), Image.new("RGB", image.size, (20, 20, 20))
        ).getbbox()


def test_watermark_disabled_leaves_image_untouched(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (200, 120), (10, 30, 60))
    preset = Preset(name="nowm", output_format="PNG", output_dir=str(tmp_path / "out"),
                    watermark_enabled=False, watermark_text="TEST")
    result = ImageProcessor().process(source, preset)
    with Image.open(result) as image:
        assert ImageChops.difference(
            image.convert("RGB"), Image.new("RGB", image.size, (10, 30, 60))
        ).getbbox() is None


@pytest.mark.parametrize("position", ["bottom-right", "top-right",
                                     "bottom-left", "top-left"])
def test_watermark_all_four_positions(tmp_path: Path, position: str) -> None:
    source = make_image(tmp_path / "source.png", (240, 160), (0, 0, 0))
    preset = Preset(name=f"wm-{position}", output_format="PNG",
                    output_dir=str(tmp_path / "out"), watermark_enabled=True,
                    watermark_text="STUDIO", watermark_position=position)
    result = ImageProcessor().process(source, preset)
    with Image.open(result) as image:
        assert ImageChops.difference(
            image.convert("RGB"), Image.new("RGB", image.size, (0, 0, 0))
        ).getbbox()


def test_watermark_zero_opacity_is_invisible(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (160, 120), (5, 5, 5))
    preset = Preset(name="wm0", output_format="PNG", output_dir=str(tmp_path / "out"),
                    watermark_enabled=True, watermark_text="HIDE",
                    watermark_opacity=0)
    result = ImageProcessor().process(source, preset)
    with Image.open(result) as image:
        assert ImageChops.difference(
            image.convert("RGB"), Image.new("RGB", image.size, (5, 5, 5))
        ).getbbox() is None


# ------------------------------------------------ защита исходных данных


def test_output_does_not_overwrite_source(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (10, 10), "red")
    original_size = source.stat().st_size
    result = ImageProcessor().process(
        source, Preset(name="same", output_format="PNG", output_dir=str(tmp_path)))
    assert result != source
    assert source.stat().st_size == original_size
    assert result.exists()


def test_duplicate_output_name_is_not_overwritten(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.jpg", (10, 10), "red")
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "source.png"
    Image.new("RGB", (10, 10), "blue").save(existing)
    result = ImageProcessor().process(
        source, Preset(name="dup", output_format="PNG", output_dir=str(out)))
    assert result.name == "source_processed.png"
    with Image.open(existing) as image:
        assert image.getpixel((0, 0)) == (0, 0, 255)


def test_third_collision_gets_numbered_suffix(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.jpg", (10, 10), "red")
    out = tmp_path / "out"
    out.mkdir()
    Image.new("RGB", (10, 10), "blue").save(out / "source.png")
    Image.new("RGB", (10, 10), "green").save(out / "source_processed.png")
    result = ImageProcessor().process(
        source, Preset(name="dup3", output_format="PNG", output_dir=str(out)))
    assert result.name == "source_processed_2.png"


def test_default_output_dir_is_processed_subfolder(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (20, 20))
    result = ImageProcessor().process(source, Preset(name="def", output_format="PNG"))
    assert result.parent == tmp_path / "processed"


# ------------------------------------------------------ форматы и ICO


def test_jpeg_with_alpha_channel_is_saved(tmp_path: Path) -> None:
    source = make_image(tmp_path / "alpha.png", (40, 30), (200, 30, 30, 128), "RGBA")
    result = ImageProcessor().process(
        source, Preset(name="alpha", output_format="JPG",
                       output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        assert image.format == "JPEG" and image.mode == "RGB"


def test_gif_is_palette_based(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (30, 30))
    result = ImageProcessor().process(
        source, Preset(name="gif", output_format="GIF",
                       output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        assert image.format == "GIF" and image.mode == "P"


def test_animated_gif_uses_first_frame(tmp_path: Path) -> None:
    source = tmp_path / "anim.gif"
    Image.new("P", (16, 16)).save(source, save_all=True,
                                 append_images=[Image.new("P", (16, 16), 1)], duration=100,
                                 loop=0)
    result = ImageProcessor().process(
        source, Preset(name="anim", output_format="PNG",
                       output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        assert image.size == (16, 16)


def test_ico_contains_three_sizes(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (480, 320), (10, 120, 200))
    result = ImageProcessor().process(
        source, Preset(name="ico", output_format="ICO",
                       output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        assert image.format == "ICO"
        assert set(image.info["sizes"]) == {(16, 16), (32, 32), (64, 64)}


def test_ico_from_small_source_still_contains_three_sizes(tmp_path: Path) -> None:
    source = make_image(tmp_path / "tiny.png", (20, 14), "red")
    result = ImageProcessor().process(
        source, Preset(name="tiny-ico", output_format="ICO",
                       output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        assert set(image.info["sizes"]) == {(16, 16), (32, 32), (64, 64)}
        assert image.size == (64, 64)


def test_ico_from_huge_source_is_scaled_down(tmp_path: Path) -> None:
    source = make_image(tmp_path / "huge.png", (2000, 1000), "green")
    result = ImageProcessor().process(
        source, Preset(name="huge-ico", output_format="ICO",
                       output_dir=str(tmp_path / "out")))
    with Image.open(result) as image:
        # По ТЗ в файл ICO пишутся ровно три изображения, базовое полотно
        # ограничено 256x256, поэтому самый крупный кадр в файле — 64x64.
        assert set(image.info["sizes"]) == {(16, 16), (32, 32), (64, 64)}
        assert image.size == (64, 64)


# ----------------------------------------------------------- граничные случаи


def test_missing_source_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ImageProcessor().process(
            tmp_path / "missing.png",
            Preset(name="missing", output_format="PNG",
                   output_dir=str(tmp_path / "out")))


def test_corrupted_source_raises_friendly_runtime_error(tmp_path: Path) -> None:
    """Битый файл не должен приводить к необработанному исключению Pillow."""
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image at all")
    with pytest.raises(RuntimeError) as error:
        ImageProcessor().process(
            broken, Preset(name="broken", output_format="PNG",
                           output_dir=str(tmp_path / "out")))
    assert "broken.png" in str(error.value)
    assert "UnidentifiedImageError" not in str(error.value)


def test_unsupported_output_format_rejected(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (10, 10))
    with pytest.raises(ValueError, match="Неподдерживаемый формат"):
        ImageProcessor().process(
            source, Preset(name="bad-fmt", output_format="EXR",
                           output_dir=str(tmp_path / "out")))


@pytest.mark.parametrize("width,height", [(0, 10), (-5, 10), (10, 0), (10, -1)])
def test_invalid_dimensions_rejected(tmp_path: Path, width: int, height: int) -> None:
    source = make_image(tmp_path / "source.png", (10, 10))
    with pytest.raises(ValueError, match="ширина|высота"):
        ImageProcessor().process(
            source, Preset(name="bad", width=width, height=height,
                           output_dir=str(tmp_path / "out")))


def test_boolean_dimension_is_rejected(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (10, 10))
    with pytest.raises(ValueError, match="ширина"):
        ImageProcessor().process(
            source, Preset(name="bool", width=True, output_dir=str(tmp_path / "out")))


@pytest.mark.parametrize("quality", [0, -1, 101, 1000])
def test_quality_out_of_range_rejected(tmp_path: Path, quality: int) -> None:
    source = make_image(tmp_path / "source.png", (10, 10))
    with pytest.raises(ValueError, match="Качество"):
        ImageProcessor().process(
            source, Preset(name="q", quality=quality,
                           output_dir=str(tmp_path / "out")))


@pytest.mark.parametrize("opacity", [-1, 101, 500])
def test_watermark_opacity_out_of_range_rejected(tmp_path: Path, opacity: int) -> None:
    source = make_image(tmp_path / "source.png", (10, 10))
    with pytest.raises(ValueError, match="Непрозрачность"):
        ImageProcessor().process(
            source, Preset(name="op", watermark_opacity=opacity,
                           output_dir=str(tmp_path / "out")))


def _write_exif_jpeg(path: Path) -> Path:
    """Готовит JPEG с заполненными EXIF-тегами описания и ПО."""
    Image.new("RGB", (80, 60), "red").save(path)
    with Image.open(path) as image:
        exif = image.getexif()
        exif[0x010E] = "SecretDescription"   # ImageDescription
        exif[0x0131] = "SecretSoftware"      # Software
        image.save(path, exif=exif)
    return path


def test_exif_metadata_is_removed_when_enabled(tmp_path: Path) -> None:
    source = _write_exif_jpeg(tmp_path / "source.jpg")
    with Image.open(source) as image:
        assert image.getexif().get(0x010E) == "SecretDescription"

    preset = Preset(name="exif-on", output_format="JPG", clear_exif=True,
                    output_dir=str(tmp_path / "clean"))
    with Image.open(ImageProcessor().process(source, preset)) as image:
        assert not image.getexif().get(0x010E)


def test_exif_metadata_is_kept_when_option_disabled(tmp_path: Path) -> None:
    """Регрессия: флажок «очистить EXIF» выключен — метаданные должны сохраняться."""
    source = _write_exif_jpeg(tmp_path / "source.jpg")
    preset = Preset(name="exif-off", output_format="JPG", clear_exif=False,
                    output_dir=str(tmp_path / "kept"))
    with Image.open(ImageProcessor().process(source, preset)) as image:
        assert image.getexif().get(0x010E) == "SecretDescription"


def test_quality_setting_affects_jpeg_size(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    Image.effect_noise((400, 400), 90).save(source, quality=100)
    low = ImageProcessor().process(
        source, Preset(name="low", output_format="JPG", quality=10,
                       output_dir=str(tmp_path / "low")))
    high = ImageProcessor().process(
        source, Preset(name="high", output_format="JPG", quality=95,
                       output_dir=str(tmp_path / "high")))
    assert low.stat().st_size < high.stat().st_size