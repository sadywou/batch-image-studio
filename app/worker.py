"""Фоновый поток пакетной обработки."""
import threading
import time
from typing import Callable, List, Optional

from .models import Preset, QueueItem
from .processor import ImageProcessor


class ProcessingWorker(threading.Thread):
    """Обрабатывает очередь изображений без блокировки Tkinter.

    Работает в отдельном потоке: обработчик не должен ждать конца пакетной
    обработки, иначе окно перестанет отвечать. В поток нельзя вызывать
    методы Tkinter напрямую, поэтому ход работы сообщается через функции
    обратной связи. Ошибка одного файла не прерывает очередь — она
    фиксируется в статусе элемента.

    Args:
        items: Список элементов очереди :class:`~app.models.QueueItem`.
        preset: Профиль настроек обработки.
        processor: Экземпляр :class:`~app.processor.ImageProcessor`.
        on_update: Вызывается после смены статуса элемента очереди.
        on_finish: Вызывается один раз в конце обработки и получает
            длительность работы в секундах.
        on_progress: Необязательный обработчик процента выполнения
            по конкретному файлу очереди.

    Attributes:
        cancel_event: Событие отмены. После его установки очередь
            прекращает обрабатываться, а оставшиеся файлы получают
            статус «Отменено».
    """

    def __init__(
        self,
        items: List[QueueItem],
        preset: Preset,
        processor: ImageProcessor,
        on_update: Callable[[int, QueueItem], None],
        on_finish: Callable[[float], None],
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Создаёт поток обработки и callback-функции интерфейса."""
        super().__init__(daemon=True)
        self.items = items
        self.preset = preset
        self.processor = processor
        self.on_update = on_update
        self.on_finish = on_finish
        self.on_progress = on_progress
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        """Запрашивает остановку обработки.

        Метод безопасен для вызова из главного потока: он только устанавливает
        событие, после чего фоновый поток сам переводит оставшиеся элементы
        очереди в статус «Отменено».
        """
        self.cancel_event.set()

    def run(self) -> None:
        """Последовательно обрабатывает элементы очереди.

        Метод вызывается автоматически при запуске потока. Для каждого файла
        устанавливается статус «В обработке», затем вызывается
        :meth:`ImageProcessor.process`, и в конце файла статус становится
        «Готово» либо «Ошибка» с текстом исключения.
        """
        started = time.perf_counter()
        for index, item in enumerate(self.items):
            if self.cancel_event.is_set():
                for pending_index in range(index, len(self.items)):
                    pending = self.items[pending_index]
                    if pending.status == "В очереди":
                        pending.status = "Отменено"
                        pending.progress = 0
                        self._report(pending_index, 0)
                        self.on_update(pending_index, pending)
                break
            item.status = "В обработке"
            item.progress = 0
            self._report(index, 0)
            self.on_update(index, item)
            try:
                item.output = self.processor.process(
                    item.source,
                    self.preset,
                    progress=lambda percent, position=index: self._report(position, percent),
                )
                item.status = "Готово"
                item.progress = 100
                item.error = None
            except Exception as exc:
                item.status = "Ошибка"
                item.error = str(exc)
                item.progress = 100
            self._report(index, item.progress)
            self.on_update(index, item)
        self.on_finish(time.perf_counter() - started)

    def _report(self, index: int, percent: int) -> None:
        """Передаёт процент выполнения текущего файла в интерфейс."""
        if self.on_progress is not None:
            self.on_progress(index, percent)
