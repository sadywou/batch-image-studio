"""Приводит тесты к модели данных по техническому заданию.

Скрипт заменяет параметры ``width``/``height`` на ``resize_mode``/
``resize_value``, русские статусы журнала на SUCCESS/ERROR и обновляет
проверки схемы. Используется один раз после смены модели.
"""
from pathlib import Path

TESTS = Path(__file__).resolve().parent.parent / "tests"

REPLACEMENTS = [
    # test_processor.py
    ('preset = Preset(name="test", output_format="JPG", width=50, height=50,\n'
     '                    quality=80, output_dir=str(tmp_path / "out"))',
     'preset = Preset(name="test", output_format="JPG", resize_mode="FIT",\n'
     '                    resize_value="50x50", quality=80,\n'
     '                    output_dir=str(tmp_path / "out"))'),
    ('preset = Preset(name="stretch", output_format="PNG", width=80, height=80,\n'
     '                    keep_ratio=False, output_dir=str(tmp_path / "out"))',
     'preset = Preset(name="stretch", output_format="PNG", resize_mode="WIDTH",\n'
     '                    resize_value="80", keep_ratio=False,\n'
     '                    output_dir=str(tmp_path / "out"))'),
    ('preset = Preset(name="width-only", output_format="PNG", width=100,\n'
     '                    output_dir=str(tmp_path / "out"))',
     'preset = Preset(name="width-only", output_format="PNG", resize_mode="WIDTH",\n'
     '                    resize_value="100", output_dir=str(tmp_path / "out"))'),
    ('preset = Preset(name="asis", output_format="PNG", output_dir=str(tmp_path / "out"))',
     'preset = Preset(name="asis", output_format="PNG", resize_mode="NONE",\n'
     '                    resize_value="", output_dir=str(tmp_path / "out"))'),
    ('    with pytest.raises(ValueError, match="ширина"):\n'
     '        ImageProcessor().process(source, Preset(name="bad", width=0, '
     'output_dir=str(tmp_path / "out")))',
     '    with pytest.raises(ValueError, match="положительным"):\n'
     '        ImageProcessor().process(\n'
     '            source, Preset(name="bad", resize_mode="WIDTH", resize_value="0",\n'
     '                            output_dir=str(tmp_path / "out")))'),
    ('''@pytest.mark.parametrize("width,height", [(0, 10), (-5, 10), (10, 0), (10, -1)])
def test_invalid_dimensions_rejected(tmp_path: Path, width: int, height: int) -> None:
    source = make_image(tmp_path / "source.png", (10, 10))
    with pytest.raises(ValueError, match="ширина|высота"):
        ImageProcessor().process(
            source, Preset(name="bad", width=width, height=height,
                           output_dir=str(tmp_path / "out")))''',
     '''@pytest.mark.parametrize("value", ["0", "-5", "abc", ""])
def test_invalid_dimensions_rejected(tmp_path: Path, value: str) -> None:
    source = make_image(tmp_path / "source.png", (10, 10))
    with pytest.raises(ValueError):
        ImageProcessor().process(
            source, Preset(name="bad", resize_mode="WIDTH", resize_value=value,
                           output_dir=str(tmp_path / "out")))'''),
    ('''def test_boolean_dimension_is_rejected(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (10, 10))
    with pytest.raises(ValueError, match="ширина"):
        ImageProcessor().process(
            source, Preset(name="bool", width=True, output_dir=str(tmp_path / "out")))''',
     '''def test_percent_mode_validation(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (10, 10))
    with pytest.raises(ValueError, match="роцент"):
        ImageProcessor().process(
            source, Preset(name="pct", resize_mode="PERCENT", resize_value="-10",
                           output_dir=str(tmp_path / "out")))


def test_fit_mode_requires_two_numbers(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png", (10, 10))
    with pytest.raises(ValueError, match="абарит"):
        ImageProcessor().process(
            source, Preset(name="fit", resize_mode="FIT", resize_value="400",
                           output_dir=str(tmp_path / "out")))'''),
    # test_database.py
    ('preset = Preset(name="demo", output_format="PNG", width=640,',
     'preset = Preset(name="demo", output_format="PNG", resize_mode="WIDTH",\n'
     '                    resize_value="640",'),
    ('    assert loaded.width == 640', '    assert loaded.resize_value == "640"'),
    ('    assert saved["text"] == "Второй"',
     '    assert saved["content"] == "Второй"'),
    ('    assert db.list_processed_files(session_id)[0][5:] == ("Ошибка", "sample error")',
     '    assert db.list_processed_files(session_id)[0][5:] == ("ERROR", "sample error")'),
    ('    assert db.list_processed_files(session_id)[0][2:7] == ("out.png", 3, 12, "Готово", None)',
     '    assert db.list_processed_files(session_id)[0][2:7] == ("out.png", 3, 12, "SUCCESS", None)'),
    ('    assert row[3] == 0 and row[4] == 0 and row[5] == "В очереди"',
     '    assert row[3] == 0 and row[4] == 0 and row[5] == "ERROR"'),
    ('    db.create_preset(Preset(name="bad-quality", output_format="PNG", quality=500))',
     '    db.create_preset(Preset(name="bad-quality", output_format="PNG", quality=500))'),
    # test_integration.py
    ('    preset = Preset(name="w", output_format="JPG", width=30, height=30,\n'
     '                    quality=80, output_dir=str(output_folder))',
     '    preset = Preset(name="w", output_format="JPG", resize_mode="FIT",\n'
     '                    resize_value="30x30", quality=80,\n'
     '                    output_dir=str(output_folder))'),
    ('    form_preset = Preset(name="perf", output_format="WebP", width=1280,\n'
     '                         height=720, quality=80, watermark_enabled=True,',
     '    form_preset = Preset(name="perf", output_format="WebP",\n'
     '                         resize_mode="WIDTH", resize_value="1280",\n'
     '                         quality=80, watermark_enabled=True,'),
    ('    assert loaded.width == 1280 and loaded.quality == 70',
     '    assert loaded.resize_value == "1280" and loaded.quality == 70'),
    ('    preset = Preset(name="stress", output_format="WebP", width=1280, height=720,',
     '    preset = Preset(name="stress", output_format="WebP",\n'
     '                    resize_mode="WIDTH", resize_value="1280",'),
    # test_deployment.py
    ('    first.create_preset(Preset(name="persist-deploy", output_format="PNG",\n'
     '                               width=321))',
     '    first.create_preset(Preset(name="persist-deploy", output_format="PNG",\n'
     '                               resize_mode="WIDTH", resize_value="321"))'),
    ('        assert second.get_preset("persist-deploy").width == 321',
     '        assert second.get_preset("persist-deploy").resize_value == "321"'),
]


def main() -> int:
    """Применяет замены во всех файлах тестов."""
    for path in sorted(TESTS.glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        original = text
        for old, new in REPLACEMENTS:
            if old in text:
                text = text.replace(old, new)
        if text != original:
            path.write_text(text, encoding="utf-8")
            print("обновлён:", path.name)
    print("готово, замен определено:", len(REPLACEMENTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
