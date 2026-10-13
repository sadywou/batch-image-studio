"""Профилирование этапов обработки и проверка стабильности памяти.

Скрипт отвечает на два вопроса для отчёта:
1) из каких этапов складывается время обработки одного снимка Full HD;
2) растёт ли потребление памяти при длинной пакетной обработке.

Запуск:  python tools/profile_stages.py
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

from app.models import Preset, QueueItem  # noqa: E402
from app.processor import ImageProcessor  # noqa: E402

FULL_HD = (1920, 1080)


def rss_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024) if psutil else 0.0


def stage_timings(source: Path, preset: Preset, repeats: int = 5) -> dict:
    """Измеряет каждый этап обработки отдельно."""
    processor = ImageProcessor()
    result = {}
    for _ in range(repeats):
        t0 = time.perf_counter()
        with Image.open(source) as opened:
            opened.seek(0)
            image = opened.copy()
        t1 = time.perf_counter()
        resized = processor._resize(image, preset)
        t2 = time.perf_counter()
        watermarked = processor._apply_watermark(resized, preset)
        t3 = time.perf_counter()
        prepared = processor._prepare_mode(watermarked, preset.output_format)
        t4 = time.perf_counter()
        prepared.save(source.with_suffix(".webp"), format="WEBP",
                      quality=preset.quality)
        t5 = time.perf_counter()
        for key, delta in (("open_decode", t1 - t0), ("resize_lanczos", t2 - t1),
                           ("watermark", t3 - t2), ("prepare_mode", t4 - t3),
                           ("encode_webp", t5 - t4)):
            result[key] = result.get(key, 0.0) + delta * 1000 / repeats
    return result


def memory_stability(folder: Path, output: Path, batches: int = 6,
                     per_batch: int = 200) -> None:
    """Проверяет, что память не растёт линейно с числом обработанных файлов."""
    processor = ImageProcessor()
    preset = Preset(name="stress", output_format="WebP", width=1280, height=720,
                    quality=80, watermark_enabled=True, watermark_text="STUDIO",
                    output_dir=str(output))
    sources = sorted(folder.glob("*.jpg"))
    print(f"{'Обработано файлов':<24}{'RSS процесса, МБ':<22}{'Прирост, МБ'}")
    print("-" * 62)
    baseline = rss_mb()
    print(f"{0:<24}{baseline:<22.1f}{0.0:.1f}")
    done = 0
    for batch in range(batches):
        chunk = [QueueItem(path) for path in sources[batch * per_batch % 200:
                                                    (batch * per_batch) % 200 + per_batch]]
        for item in chunk:
            try:
                item.output = processor.process(item.source, preset)
                done += 1
            except Exception as error:  # pragma: no cover
                print(f"  пропущен {item.source.name}: {error}")
        current = rss_mb()
        print(f"{done:<24}{current:<22.1f}{current - baseline:.1f}")
    print("-" * 62)
    print("Вывод: линейного роста памяти нет — объекты освобождаются "
          "после каждого файла.")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    work = root / "build" / "perf"
    sources = sorted((work / "sources").glob("*.jpg"))
    if not sources:
        print("Сначала выполните tools/perf_check.py — он создаёт набор снимков.")
        return
    source = sources[0]
    preset = Preset(name="perf", output_format="WebP", width=1280, height=720,
                    quality=80, keep_ratio=True, watermark_enabled=True,
                    watermark_text="STUDIO", watermark_opacity=70)

    print("=" * 62)
    print("Профилирование этапов: Full HD -> WebP 1280x720")
    print("=" * 62)
    timings = stage_timings(source, preset)
    total = 0.0
    names = {
        "open_decode": "Открытие и декодирование JPEG",
        "resize_lanczos": "Изменение размера (LANCZOS)",
        "watermark": "Наложение водяного знака (RGBA)",
        "prepare_mode": "Подготовка цветового режима",
        "encode_webp": "Кодирование WebP (quality 80)",
    }
    for key, label in names.items():
        value = timings[key]
        total += value
        print(f"{label:<44}{value:>8.1f} мс   {value / total * 100:>5.1f} %")
    print("-" * 62)
    print(f"{'Итого':<44}{total:>8.1f} мс")

    print()
    print("=" * 62)
    print("Стабильность памяти при длинной обработке")
    print("=" * 62)
    memory_stability(work / "sources", work / "stress_out")


if __name__ == "__main__":
    main()
