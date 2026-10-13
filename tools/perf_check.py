"""Базовое тестирование производительности и потребления памяти.

Скрипт повторяет ключевые действия пользователя и измеряет время отклика,
а также пиковое потребление памяти процесса. Результат печатается в консоль
и сохраняется в performance_report.json.

Запуск:  python tools/perf_check.py
"""
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

try:
    import psutil
except ImportError:  # pragma: no cover - psutil ставится вместе с инструментами
    psutil = None

from app.database import DatabaseManager  # noqa: E402
from app.models import Preset, QueueItem  # noqa: E402
from app.processor import ImageProcessor  # noqa: E402

FULL_HD = (1920, 1080)


def make_sources(folder: Path, count: int) -> list:
    """Готовит реалистичные снимки Full HD с мелкими деталями."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(count):
        path = folder / f"sample_{index:04d}.jpg"
        if not path.exists():
            base = Image.effect_noise((FULL_HD[0] // 4, FULL_HD[1] // 4), 60)
            image = base.resize(FULL_HD, Image.Resampling.BICUBIC).convert("RGB")
            image.save(path, quality=92)
        paths.append(path)
    return paths


def measure(label: str, function, repeats: int = 3) -> dict:
    """Выполняет действие несколько раз и возвращает статистику времени."""
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        function()
        samples.append((time.perf_counter() - started) * 1000)
    result = {
        "label": label,
        "repeats": repeats,
        "min_ms": round(min(samples), 1),
        "avg_ms": round(statistics.mean(samples), 1),
        "max_ms": round(max(samples), 1),
    }
    print(f"{label:<46} мин {result['min_ms']:>9.1f} мс   "
          f"сред {result['avg_ms']:>9.1f} мс   макс {result['max_ms']:>9.1f} мс")
    return result


def rss_mb() -> float:
    """Возвращает рабочую память процесса в мегабайтах."""
    if psutil is None:
        return 0.0
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    work = root / "build" / "perf"
    if work.exists():
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    source_folder = work / "sources"
    output_folder = work / "out"
    db_path = work / "perf.db"

    print("=" * 92)
    print("Базовое тестирование производительности — Image Batch Studio")
    print("=" * 92)
    print(f"Файлов в наборе: 200, разрешение {FULL_HD[0]}x{FULL_HD[1]}")
    print()

    report = {"environment": {}, "measurements": [], "memory": {}}

    started = time.perf_counter()
    sources = make_sources(source_folder, 200)
    print(f"Подготовка 200 снимков Full HD: "
          f"{(time.perf_counter() - started):.1f} с\n")

    processor = ImageProcessor()
    preset = Preset(name="perf", output_format="WebP", resize_mode="WIDTH",
                    resize_value="1280", quality=80, keep_ratio=True,
                    watermark_enabled=True, watermark_type="TEXT",
                    watermark_text="STUDIO", watermark_opacity=70,
                    output_dir=str(output_folder))

    report["memory"]["baseline_mb"] = round(rss_mb(), 1)

    # --- одиночная обработка ------------------------------------------------
    report["measurements"].append(measure(
        "Обработка одного снимка Full HD -> WebP 1280x720",
        lambda: processor.process(sources[0], preset), repeats=5))

    # --- пакетная обработка -------------------------------------------------
    for count in (50, 200):
        def run_batch(count=count):
            batch = [QueueItem(path) for path in sources[:count]]
            for item in batch:
                processor.process(item.source, preset)
        entry = measure(f"Пакетная обработка {count} снимков (среднее на файл)",
                        run_batch, repeats=1)
        entry["per_file_ms"] = round(entry["avg_ms"] / count, 1)
        entry["files"] = count
        report["measurements"].append(entry)

    report["memory"]["after_processing_mb"] = round(rss_mb(), 1)

    # --- операции со слоем данных ------------------------------------------
    database = DatabaseManager(str(db_path))
    form_preset = Preset(name="perf", output_format="WebP",
                         resize_mode="WIDTH", resize_value="1280",
                         quality=80, watermark_enabled=True,
                         watermark_type="TEXT", watermark_text="STUDIO",
                         output_dir=str(output_folder))
    database.create_preset(form_preset)

    report["measurements"].append(measure(
        "Открытие и создание схемы БД SQLite",
        lambda: DatabaseManager(str(db_path)), repeats=5))
    report["measurements"].append(measure(
        "Чтение профиля из БД", lambda: database.get_preset("perf"), repeats=20))
    report["measurements"].append(measure(
        "Сохранение профиля в БД", lambda: database.update_preset(form_preset),
        repeats=20))
    report["measurements"].append(measure(
        "Создание записи сессии в БД",
        lambda: database.create_session(form_preset, 200), repeats=20))
    report["measurements"].append(measure(
        "Чтение последних 100 сессий", lambda: database.list_sessions(100),
        repeats=20))

    # --- имитация работы окна ------------------------------------------------
    def build_queue():
        items = [QueueItem(path) for path in sources]
        known = {item.source for item in items}
        return len(items), len(known)

    report["measurements"].append(measure(
        "Формирование очереди из 200 файлов (без отрисовки)",
        build_queue, repeats=5))

    database.close()

    # --- окно Tkinter --------------------------------------------------------
    try:
        import tkinter as tk

        def open_window():
            root = tk.Tk()
            root.withdraw()
            root.destroy()

        report["measurements"].append(measure(
            "Создание окна Tkinter", open_window, repeats=3))
    except Exception as error:  # pragma: no cover - без графического окружения
        report["measurements"].append(
            {"label": "Создание окна Tkinter", "error": str(error)})

    report["environment"] = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "pillow": Image.__version__,
        "source_count": len(sources),
        "resolution": f"{FULL_HD[0]}x{FULL_HD[1]}",
    }

    print()
    print("-" * 92)
    print("Потребление памяти процесса:")
    for key, value in report["memory"].items():
        print(f"  {key:<28} {value:>8} МБ")
    peak = max(report["memory"].values())
    print(f"  {'пик (рост)':<28} {peak - report['memory']['baseline_mb']:>8} МБ")
    report["memory"]["peak_growth_mb"] = round(
        peak - report["memory"]["baseline_mb"], 1)

    target = work / "performance_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print()
    print(f"Отчёт сохранён: {target}")


if __name__ == "__main__":
    main()
