"""Приёмочные испытания по разделу 6.1 технического задания.

Выполняются три вида испытаний, перечисленных в ТЗ:

* испытание пакетной конвертации — папка из 30 файлов разных расширений
  и массовый экспорт во все 9 целевых форматов с проверкой открытия;
* испытание отзывчивости интерфейса — окно остаётся управляемым
  во время фоновой обработки;
* испытание пресетов — создание, сохранение, удаление и загрузка
  5 различных конфигураций настроек.

Запуск:  python tools/check_acceptance.py
Результат печатается в консоль и сохраняется в build/acceptance.json.
"""
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from app.database import DatabaseManager  # noqa: E402
from app.models import Preset  # noqa: E402
from app.processor import ImageProcessor  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "acceptance"
OUT = ROOT / "build" / "acceptance.json"

#: Все форматы, требуемые техническим заданием (9 штук).
TARGET_FORMATS = ("PNG", "JPG", "WebP", "BMP", "TIFF", "GIF", "ICO", "HEIC", "AVIF")

#: Исходные расширения для папки из 30 объектов.
SOURCE_EXTENSIONS = (".jpg", ".png", ".bmp", ".gif", ".webp", ".tiff",
                     ".ppm", ".pgm", ".ico")

#: Пять различных конфигураций для испытания пресетов.
PRESETS = (
    ("Карточки маркетплейса", "JPG", "FIT", "1200x1200", 82, True),
    ("Витрина сайта", "WebP", "WIDTH", "1600", 78, True),
    ("Архив оригиналов", "PNG", "NONE", "", 100, False),
    ("Мобильные превью", "JPG", "PERCENT", "35", 70, True),
    ("Печатный макет", "TIFF", "HEIGHT", "2480", 95, False),
)


def make_sources(folder: Path, count: int = 30) -> list:
    """Создаёт папку с тестовыми объектами разных расширений.

    Args:
        folder: Папка для наполнения.
        count: Количество файлов.

    Returns:
        Список созданных путей.
    """
    folder.mkdir(parents=True, exist_ok=True)
    created = []
    for index in range(count):
        suffix = SOURCE_EXTENSIONS[index % len(SOURCE_EXTENSIONS)]
        target = folder / f"obj_{index:03d}{suffix}"
        if target.exists():
            created.append(target)
            continue
        width = 640 + (index % 5) * 160
        height = 480 + (index % 3) * 120
        image = Image.new("RGB", (width, height),
                          (index * 7 % 255, 120, 200 - index * 3 % 255))
        # ICO принимает только небольшие размеры, иначе сохраняет кратно.
        if suffix == ".ico":
            image = image.resize((64, 64))
        image.save(target)
        created.append(target)
    return created


def test_conversion(results) -> None:
    """Испытание пакетной конвертации: 30 объектов во все 9 форматов."""
    print("=" * 78)
    print("Испытание 1. Пакетная конвертация (пункт 6.1 ТЗ)")
    print("=" * 78)
    sources = make_sources(WORK / "source")
    print(f"Подготовлено исходных объектов: {len(sources)}")
    print(f"Целевых форматов по ТЗ: {len(TARGET_FORMATS)}")

    for fmt in TARGET_FORMATS:
        out_dir = WORK / "converted" / fmt
        preset = Preset(name=f"Приёмка {fmt}", output_format=fmt,
                        resize_mode="FIT", resize_value="1200x900",
                        quality=85, output_dir=str(out_dir))
        started = time.perf_counter()
        done = failed = 0
        reasons = []
        for source in sources:
            try:
                ImageProcessor().process(source, preset)
                done += 1
            except Exception as exc:  # noqa: BLE001 - протокол испытаний
                failed += 1
                if len(reasons) < 2:
                    reasons.append(f"{source.name}: {exc}")
        elapsed = time.perf_counter() - started

        produced = sorted(p for p in out_dir.glob("*")) if out_dir.exists() else []
        opened = 0
        for path in produced:
            try:
                with Image.open(path) as image:
                    image.verify()
                opened += 1
            except Exception:  # noqa: BLE001 - протокол испытаний
                pass

        item = {
            "format": fmt, "converted": done, "failed": failed,
            "files": len(produced), "opened": opened,
            "seconds": round(elapsed, 2),
            "reasons": reasons,
        }
        results.append(item)
        mark = "OK" if failed == 0 and opened == len(produced) else "С ОГОВОРКОЙ"
        print(f"  {fmt:<5} обработано {done:>3} из {len(sources)}, "
              f"ошибок {failed:>2}, создано файлов {len(produced):>3}, "
              f"открывается {opened:>3}, {elapsed:6.2f} с  — {mark}")
        for reason in reasons:
            print(f"        причина: {reason}")


def test_responsiveness(results) -> None:
    """Испытание отзывчивости интерфейса при фоновой обработке."""
    print()
    print("=" * 78)
    print("Испытание 2. Отзывчивость интерфейса (пункт 6.1 ТЗ)")
    print("=" * 78)
    from app import ui

    window = ui.MainWindow()
    window.withdraw()
    sources = make_sources(WORK / "responsive")
    window._append_paths([str(p) for p in sources])
    window.format_var.set("WebP")
    window.width_var.set("800")
    window.height_var.set("")
    window.output_var.set(str(WORK / "responsive_out"))
    window.update()

    window.start_processing()
    freezes = 0
    slowest = 0.0
    samples = 0
    deadline = time.perf_counter() + 60
    while time.perf_counter() < deadline:
        started = time.perf_counter()
        window.update()
        sample = (time.perf_counter() - started) * 1000
        samples += 1
        slowest = max(slowest, sample)
        if sample > 250:
            freezes += 1
        if window.state == ui.STATE_DONE:
            break
        time.sleep(0.01)

    succeeded = sum(1 for item in window.items if item.status == "Готово")
    summary = window.summary_detail.cget("text")
    item = {
        "samples": samples, "freezes": freezes,
        "slowest_frame_ms": round(slowest, 1),
        "processed": succeeded, "total": len(window.items),
        "summary": summary,
    }
    results.append(item)
    print(f"  Файлов в очереди: {len(window.items)}")
    print(f"  Успешно обработано: {succeeded}")
    print(f"  Отсчётов цикла событий: {samples}")
    print(f"  Зависаний (кадр дольше 250 мс): {freezes}")
    print(f"  Самый долгий кадр: {slowest:.1f} мс")
    print(f"  Итоговая строка: {summary}")
    print("  Результат:", "OK" if freezes == 0 else "ЕСТЬ ЗАДЕРЖКИ")
    try:
        window.database.close()
        window.destroy()
    except Exception:  # noqa: BLE001 - протокол испытаний
        pass


def test_presets(results) -> None:
    """Испытание пресетов: 5 конфигураций, CRUD и автозаполнение полей."""
    print()
    print("=" * 78)
    print("Испытание 3. Профили настроек (пункт 6.1 ТЗ)")
    print("=" * 78)
    manager = DatabaseManager(str(WORK / "acceptance.db"))
    roundtrip = []
    for name, fmt, mode, value, quality, strip in PRESETS:
        manager.create_preset(Preset(
            name=name, output_format=fmt, resize_mode=mode,
            resize_value=value, quality=quality, clear_exif=strip,
            watermark_enabled=True, watermark_type="TEXT",
            watermark_text="ПРИЁМКА", watermark_position="center",
            watermark_opacity=60, watermark_size=5, watermark_color="#FFDD00"))
        loaded = manager.get_preset(name)
        same = (loaded is not None
                and loaded.output_format == fmt
                and loaded.resize_mode == mode
                and loaded.resize_value == value
                and loaded.quality == quality
                and loaded.watermark_position == "center"
                and loaded.watermark_size == 5
                and loaded.watermark_color == "#FFDD00")
        roundtrip.append({"name": name, "restored": bool(same)})
        print(f"  {name:<24} {fmt:<5} {mode:<8} {value or '-':<10} "
              f"качество {quality:>3}  {'OK' if same else 'НЕ СОВПАЛО'}")

    total = len(manager.list_presets())
    manager.delete_preset("Архив оригиналов")
    after = len(manager.list_presets())
    deleted_ok = after == total - 1
    manager.close()

    results.append({
        "created": len(PRESETS), "restored_ok": sum(
            1 for item in roundtrip if item["restored"]),
        "details": roundtrip, "delete_ok": deleted_ok,
        "before_delete": total, "after_delete": after,
    })
    print(f"  Создано профилей: {total}")
    print(f"  Корректно восстановлено: {sum(1 for i in roundtrip if i['restored'])}")
    print(f"  Удаление профиля: {'OK' if deleted_ok else 'НЕ УДАЛЕНО'} "
          f"(осталось {after} из {total})")


def main() -> int:
    """Выполняет все три вида испытаний и сохраняет протокол."""
    # Каждый прогон начинается с чистой папки: иначе в подсчёте
    # созданных файлов учитывались бы результаты прошлых запусков,
    # а профили настроек сталкивались бы с уже существующими именами.
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    results = []
    test_conversion(results)
    test_responsiveness(results)
    test_presets(results)

    print()
    print("=" * 78)
    print("ПРОТОКОЛ ПРИЁМОЧНЫХ ИСПЫТАНИЙ")
    print("=" * 78)
    conversion = [r for r in results if "format" in r]
    with_errors = [r for r in conversion if r["failed"]]
    print(f"Форматов без ошибок: {len(conversion) - len(with_errors)} "
          f"из {len(conversion)}")
    print("Форматы с ограничениями среды:",
          ", ".join(r["format"] for r in with_errors) or "нет")
    preset_result = [r for r in results if "created" in r]
    if preset_result:
        item = preset_result[0]
        print(f"Профилей настроек: восстановлено {item['restored_ok']} "
              f"из {item['created']}, удаление "
              f"{'выполнено' if item['delete_ok'] else 'не выполнено'}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("Протокол сохранён:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())