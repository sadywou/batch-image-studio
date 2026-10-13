"""Интеграционные проверки связки UI, ProcessingWorker, ImageProcessor и SQLite.

Эти тесты проверяют не отдельные функции, а «разговор» модулей между собой:
окно формирует профиль из полей формы -> worker прогоняет очередь -> обработчик
пишет файлы -> журнал SQLite фиксирует результат сессии.
"""
import queue
import threading
from pathlib import Path

from PIL import Image

from app.database import DatabaseManager
from app.models import Preset, QueueItem
from app.processor import ImageProcessor
from app.worker import ProcessingWorker


# --------------------------------------------------- worker + processor


def make_queue(tmp_path: Path, count: int, name: str = "photo") -> list:
    """Создаёт очередь реальных PNG-файлов."""
    items = []
    for index in range(count):
        path = tmp_path / f"{name}{index}.png"
        Image.new("RGB", (60, 40), (index * 20 % 255, 90, 160)).save(path)
        items.append(QueueItem(path))
    return items


def run_worker(items, preset, processor, timeout=30.0):
    """Запускает worker и собирает события обратной связи."""
    events = []
    finished = {}

    def on_update(index, item):
        events.append(("update", index, item.status))

    def on_finish(duration):
        finished["duration"] = duration

    worker = ProcessingWorker(items, preset, processor, on_update, on_finish,
                              lambda index, percent: events.append(("progress", index, percent)))
    worker.start()
    worker.join(timeout)
    assert not worker.is_alive(), "Фоновый поток не завершился за отведённое время"
    return events, finished


def test_worker_processes_whole_queue(tmp_path: Path) -> None:
    items = make_queue(tmp_path, 3)
    preset = Preset(name="w", output_format="JPG", resize_mode="FIT",
                    resize_value="30x30", output_dir=str(tmp_path / "out"))
    events, finished = run_worker(items, preset, ImageProcessor())

    assert [item.status for item in items] == ["Готово"] * 3
    assert all(item.output and item.output.exists() for item in items)
    assert all(item.progress == 100 for item in items)
    assert any(event[0] == "progress" for event in events)
    assert finished["duration"] > 0
    updates = [event for event in events if event[0] == "update"]
    assert len(updates) >= 2 * len(items)  # «в обработке» + итоговый статус


def test_worker_reports_progress_in_order(tmp_path: Path) -> None:
    items = make_queue(tmp_path, 2)
    preset = Preset(name="w", output_format="PNG", output_dir=str(tmp_path / "out"))
    events, _ = run_worker(items, preset, ImageProcessor())
    for index in range(len(items)):
        percents = [event[2] for event in events
                    if event[0] == "progress" and event[1] == index]
        assert percents == sorted(percents)
        assert percents[-1] == 100


def test_worker_isolates_failing_file(tmp_path: Path) -> None:
    """Ошибка одного файла не должна останавливать очередь."""
    good_a = make_queue(tmp_path, 1, "good_a")
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"definitely not an image")
    good_b = make_queue(tmp_path, 1, "good_b")
    items = good_a + [QueueItem(broken)] + good_b
    preset = Preset(name="w", output_format="PNG", output_dir=str(tmp_path / "out"))
    _, _ = run_worker(items, preset, ImageProcessor())

    assert items[0].status == "Готово"
    assert items[1].status == "Ошибка"
    assert items[1].error and "broken.png" in items[1].error
    assert items[1].progress == 100
    assert items[2].status == "Готово"


def test_worker_marks_rest_as_cancelled(tmp_path: Path) -> None:
    items = make_queue(tmp_path, 6)
    preset = Preset(name="w", output_format="PNG", output_dir=str(tmp_path / "out"))
    cancel_flag = threading.Event()

    def on_update(index, item):
        if index == 0 and item.status == "Готово":
            cancel_flag.set()
            worker.cancel()

    finished = threading.Event()
    worker = ProcessingWorker(items, preset, ImageProcessor(),
                              on_update, lambda _d: finished.set())
    worker.start()
    assert finished.wait(30)
    worker.join(10)

    statuses = [item.status for item in items]
    assert statuses[0] == "Готово"
    assert statuses[1:] == ["Отменено"] * 5
    assert all(item.progress == 0 for item in items[1:])


def test_worker_cancel_before_start_processes_nothing(tmp_path: Path) -> None:
    items = make_queue(tmp_path, 2)
    preset = Preset(name="w", output_format="PNG", output_dir=str(tmp_path / "out"))
    worker = ProcessingWorker(items, preset, ImageProcessor(),
                              lambda *_: None, lambda _d: None)
    worker.cancel()
    worker.start()
    worker.join(10)
    assert [item.status for item in items] == ["Отменено"] * 2


def test_worker_runs_in_separate_thread(tmp_path: Path) -> None:
    main_thread = threading.get_ident()
    seen = []
    items = make_queue(tmp_path, 1)
    worker = ProcessingWorker(items, Preset(name="w", output_format="PNG",
                                            output_dir=str(tmp_path / "out")),
                              ImageProcessor(),
                              lambda *_: seen.append(threading.get_ident()),
                              lambda _d: None)
    worker.start()
    worker.join(10)
    assert seen and all(ident != main_thread for ident in seen)
    assert worker.daemon is True


# ----------------------------------------- worker + processor + database


def test_full_pipeline_ui_preset_to_journal(tmp_path: Path) -> None:
    """Сквозной сценарий: профиль из формы -> обработка -> журнал SQLite."""
    database = DatabaseManager(str(tmp_path / "app.db"))
    processor = ImageProcessor()

    # 1. Пользователь настроил профиль и сохранил его через форму.
    form_preset = Preset(name="Для сайта", output_format="WebP",
                         resize_mode="FIT", resize_value="120x90",
                         quality=70, clear_exif=True, keep_ratio=True,
                        output_dir=str(tmp_path / "out"),
                        watermark_enabled=True, watermark_text="STUDIO",
                        watermark_position="bottom-right", watermark_opacity=80)
    database.create_preset(form_preset)

    # 2. Окно перечитало профиль из базы перед запуском.
    loaded = database.get_preset("Для сайта")
    assert loaded is not None and loaded.output_format == "WebP"
    assert loaded.resize_value == "120x90" and loaded.quality == 70

    # 3. Пользователь добавил файлы и запустил обработку.
    items = make_queue(tmp_path, 3)
    session_id = database.create_session(loaded, len(items))
    _, finished = run_worker(items, loaded, processor)

    # 4. Окно записало результат сессии в журнал.
    for item in items:
        database.log_processed_file(session_id, item)
    database.finish_session(session_id, finished["duration"], items)

    rows = database.list_processed_files(session_id)
    # Колонки: id, source_path, output_path, size_before, size_after, status, error
    assert len(rows) == 3
    assert all(row[5] == "SUCCESS" for row in rows)
    assert all(row[3] > 0 for row in rows)          # размер исходника записан
    assert all(row[4] > 0 for row in rows)          # размер результата записан
    assert all(Path(row[2]).exists() for row in rows)  # результат лежит на диске

    session = database.list_sessions()[0]
    assert session[3] == "Для сайта"
    assert (session[4], session[5], session[6]) == (3, 3, 0)
    database.close()


def test_failed_file_is_logged_with_error_text(tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "app.db"))
    preset = Preset(name="log", output_format="PNG", output_dir=str(tmp_path / "out"))
    database.create_preset(preset)
    items = make_queue(tmp_path, 1)
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"garbage")
    items.append(QueueItem(broken))
    session_id = database.create_session(preset, len(items))
    _, finished = run_worker(items, preset, ImageProcessor())
    for item in items:
        database.log_processed_file(session_id, item)
    database.finish_session(session_id, finished["duration"], items)

    session = database.list_sessions()[0]
    assert (session[4], session[5], session[6]) == (2, 1, 1)
    errors = [row[6] for row in database.list_processed_files(session_id)]
    assert any(error for error in errors)
    database.close()


def test_deleting_preset_keeps_session_history(tmp_path: Path) -> None:
    """ON DELETE SET NULL не должен удалять журнал прошлых сессий."""
    database = DatabaseManager(str(tmp_path / "app.db"))
    preset = Preset(name="temp", output_format="PNG", output_dir=str(tmp_path / "out"))
    database.create_preset(preset)
    session_id = database.create_session(preset, 1)
    database.delete_preset("temp")
    assert database.get_preset("temp") is None
    assert len(database.list_sessions()) == 1
    assert database.list_sessions()[0][3] == "temp"
    database.delete_session(session_id)
    database.close()


# --------------------------------------------- потокобезопасность UI-моста


def test_worker_events_are_thread_safe(tmp_path: Path) -> None:
    """UI получает события через очередь, а не напрямую из фонового потока."""
    events: queue.Queue = queue.Queue()
    items = make_queue(tmp_path, 4)
    preset = Preset(name="w", output_format="PNG", output_dir=str(tmp_path / "out"))
    worker = ProcessingWorker(
        items, preset, ImageProcessor(),
        lambda index, item: events.put(("update", index, item.status)),
        lambda duration: events.put(("finish", duration)),
        lambda index, percent: events.put(("progress", index, percent)),
    )
    worker.start()
    worker.join(30)
    assert not worker.is_alive(), "Фоновый поток не завершился за 30 секунд"

    received = []
    while not events.empty():
        received.append(events.get_nowait())
    assert any(event[0] == "finish" for event in received)
    assert sum(1 for event in received if event[0] == "update") >= 2 * len(items)


def test_two_workers_do_not_share_state(tmp_path: Path) -> None:
    """Параллельные сессии не должны путать элементы очереди."""
    first_items = make_queue(tmp_path, 2, "first")
    second_items = make_queue(tmp_path, 2, "second")
    preset = Preset(name="w", output_format="PNG", output_dir=str(tmp_path / "out"))
    workers = [
        ProcessingWorker(first_items, preset, ImageProcessor(),
                         lambda *_: None, lambda _d: None),
        ProcessingWorker(second_items, preset, ImageProcessor(),
                         lambda *_: None, lambda _d: None),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(20)
    assert all(item.status == "Готово" for item in first_items + second_items)
    assert all(item.output.name.startswith("first") or item.output.name.startswith("second")
               for item in first_items + second_items)