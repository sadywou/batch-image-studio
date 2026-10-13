"""Модели данных приложения пакетной обработки изображений."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Preset:
    """Профиль настроек обработки изображения.

    Объединяет параметры, которые пользователь задаёт в панели настроек.
    Экземпляры сохраняются в базе данных SQLite, поэтому все значения должны
    быть простыми и сериализуемыми.

    Attributes:
        name: Название профиля.
        output_format: Целевой формат: PNG, JPG, WebP, BMP, TIFF, GIF, ICO,
            HEIC или AVIF.
        width: Требуемая ширина в пикселях или ``None``, если не менять.
        height: Требуемая высота в пикселях или ``None``, если не менять.
        quality: Качество сжатия от 1 до 100.
        clear_exif: Удалять ли EXIF-метаданные из результата.
        keep_ratio: Сохранять ли пропорции при изменении размера.
        output_dir: Папка сохранения результата.
        watermark_enabled: Включён ли водяной знак.
        watermark_text: Текст водяного знака.
        watermark_position: Положение знака: ``bottom-right``, ``top-right``,
            ``bottom-left`` или ``top-left``.
        watermark_opacity: Прозрачность водяного знака от 0 до 100.
    """

    name: str
    output_format: str = "PNG"
    width: Optional[int] = None
    height: Optional[int] = None
    quality: int = 85
    clear_exif: bool = True
    keep_ratio: bool = True
    output_dir: str = ""
    watermark_enabled: bool = False
    watermark_text: str = ""
    watermark_position: str = "bottom-right"
    watermark_opacity: int = 75


@dataclass
class QueueItem:
    """Отдельный файл очереди обработки и его текущее состояние.

    Элемент очереди создаётся при добавлении файла и затем многократно
    обновляется фоновым потоком обработки.

    Attributes:
        source: Путь к исходному файлу.
        status: Текущий статус: «В очереди», «В обработке», «Готово»,
            «Ошибка» или «Отменено».
        output: Путь к созданному результату или ``None``.
        error: Текст последней ошибки или ``None``.
        progress: Процент выполнения по этому файлу от 0 до 100.
    """

    source: Path
    status: str = "В очереди"
    output: Optional[Path] = None
    error: Optional[str] = None
    progress: int = 0
