"""Проверка показателей назначения из технического задания (4.1.3).

Измеряются:
* холодный старт и инициализация окна — не более 1,5 секунды;
* чтение папки со 100 файлами и добавление в очередь — не более 0,5 секунды;
* отсутствие критической деградации при очереди из 5000 файлов.

Запуск:  python tools/check_spec_metrics.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from app.ui import SUPPORTED_EXTENSIONS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "spec_metrics"
OUT = ROOT / "build" / "spec_metrics.json"

#: Требования технического задания.
COLD_START_LIMIT = 1.5
FOLDER_READ_LIMIT = 0.5
LARGE_QUEUE = 5000


def make_folder(path: Path, count: int, size=(64, 48)) -> None:
    """Создаёт папку с тестовыми изображениями."""
    path.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        target = path / f"img_{index:05d}.png"
        if not target.exists():
            Image.new("RGB", size, (index % 255, 90, 160)).save(target)


def main() -> int:
    """Выполняет замеры и печатает отчёт."""
    import tkinter as tk
    from app import ui

    WORK.mkdir(parents=True, exist_ok=True)
    small = WORK / "hundred"
    make_folder(small, 100)

    results = []

    # ---------------------------------------------- холодный старт окна
    started = time.perf_counter()
    root = tk.Tk()
    root.withdraw()
    cold = time.perf_counter() - started
    root.destroy()
    results.append({
        "metric": "Создание окна Tkinter (без окна приложения)",
        "limit": COLD_START_LIMIT, "value": round(cold, 3),
        "unit": "с", "ok": cold <= COLD_START_LIMIT,
    })

    # ------------------------------- полный старт приложения с базой
    started = time.perf_counter()
    window = ui.MainWindow()
    window.withdraw()
    window.update()
    full = time.perf_counter() - started
    results.append({
        "metric": "Полная инициализация приложения (окно, база, профили)",
        "limit": COLD_START_LIMIT, "value": round(full, 3),
        "unit": "с", "ok": full <= COLD_START_LIMIT,
    })

    # ------------------------------------ чтение папки со 100 файлами
    paths = [str(p) for p in sorted(small.iterdir())
             if p.suffix.lower() in SUPPORTED_EXTENSIONS]
    started = time.perf_counter()
    window._append_paths(paths)
    window.update()
    folder_read = time.perf_counter() - started
    results.append({
        "metric": f"Добавление папки ({len(paths)} файлов) в очередь",
        "limit": FOLDER_READ_LIMIT, "value": round(folder_read, 3),
        "unit": "с", "ok": folder_read <= FOLDER_READ_LIMIT,
    })

    # ------------------------------------------- очередь из 5000 файлов
    from app.models import QueueItem
    big = WORK / "big"
    make_folder(big, 200)
    sources = sorted(big.iterdir())[:200]
    started = time.perf_counter()
    window.items = [QueueItem(p) for _ in range(LARGE_QUEUE // 200)
                    for p in sources]
    queue_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    window.queue_list.set_items(window.items, 0)
    window.update()
    render_ms = (time.perf_counter() - started) * 1000
    rows = len(window.queue_list._rows)
    results.append({
        "metric": f"Отрисовка очереди из {LARGE_QUEUE} файлов",
        "limit": None, "value": round(render_ms, 1),
        "unit": "мс", "ok": render_ms <= 1500,
        "note": f"создано карточек: {rows} (ленивое создание)",
    })
    results.append({
        "metric": f"Формирование списка из {LARGE_QUEUE} элементов",
        "limit": None, "value": round(queue_ms, 1),
        "unit": "мс", "ok": True,
    })

    # ------------------------------------------------ прокрутка большой очереди
    started = time.perf_counter()
    for _ in range(5):
        window.queue_list.scroll(50)
        window.update()
    scroll_ms = (time.perf_counter() - started) * 1000 / 5
    results.append({
        "metric": "Прокрутка очереди (шаг 50 px)",
        "limit": None, "value": round(scroll_ms, 1),
        "unit": "мс", "ok": scroll_ms <= 200,
    })

    try:
        if window.worker and window.worker.is_alive():
            window.worker.cancel()
        window.database.close()
        window.destroy()
    except Exception:
        pass

    print("=" * 78)
    print("Проверка показателей назначения по техническому заданию (4.1.3)")
    print("=" * 78)
    print(f"{'Показатель':<52}{'Норма':>8}{'Факт':>10}  Итог")
    print("-" * 78)
    for item in results:
        limit = f"{item['limit']} {item['unit']}" if item["limit"] else "—"
        mark = "OK" if item["ok"] else "НЕ СОООТВ."
        print(f"{item['metric'][:50]:<52}{limit:>8}"
              f"{str(item['value']) + ' ' + item['unit']:>10}  {mark}")
        if item.get("note"):
            print(f"    {item['note']}")
    print("-" * 78)
    passed = all(item["ok"] for item in results)
    print("Итог:", "все показатели ТЗ выполнены" if passed
          else "есть показатели вне нормы")

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("Отчёт сохранён:", OUT)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
