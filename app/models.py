"""Модели данных приложения пакетной обработки изображений."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: Режимы масштабирования, заданные техническим заданием.
RESIZE_MODES = ("WIDTH", "HEIGHT", "FIT", "PERCENT", "NONE")

#: Позиции водяного знака: сетка 3×3 по требованию технического задания.
WATERMARK_POSITIONS = (
    "top-left", "top-center", "top-right",
    "middle-left", "center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
)

#: Типы водяного знака.
WATERMARK_TYPES = ("TEXT", "IMAGE")


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
        resize_mode: Режим масштабирования: ``WIDTH`` — по ширине,
            ``HEIGHT`` — по высоте, ``FIT`` — вписать в габаритный прямоугольник,
            ``PERCENT`` — в процентах, ``NONE`` — без изменения размера.
        resize_value: Значение для выбранного режима: ширина или высота
            в пикселях, габарит в формате ``ширина×высота`` либо процент.
        quality: Качество сжатия от 1 до 100.
        clear_exif: Удалять ли EXIF-метаданные из результата.
        keep_ratio: Сохранять ли пропорции при изменении размера.
        output_dir: Папка сохранения результата.
        watermark_enabled: Включён ли водяной знак.
        watermark_type: Тип знака: ``TEXT`` или ``IMAGE``.
        watermark_text: Текст водяного знака.
        watermark_image: Путь к файлу логотипа с прозрачностью.
        watermark_position: Положение знака, одна из девяти позиций сетки 3×3.
        watermark_opacity: Прозрачность водяного знака от 0 до 100.
        watermark_size: Размер шрифта текстового знака в процентах от
            меньшей стороны изображения, от 1 до 20.
        watermark_color: Цвет текста в формате ``#RRGGBB``.
    """

    name: str
    output_format: str = "PNG"
    resize_mode: str = "WIDTH"
    resize_value: str = "1920"
    quality: int = 85
    clear_exif: bool = True
    keep_ratio: bool = True
    output_dir: str = ""
    watermark_enabled: bool = False
    watermark_type: str = "TEXT"
    watermark_text: str = ""
    watermark_image: str = ""
    watermark_position: str = "bottom-right"
    watermark_opacity: int = 75
    watermark_size: int = 4
    watermark_color: str = "#FFFFFF"


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
