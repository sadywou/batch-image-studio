"""Бизнес-логика обработки изображений через Pillow."""
from pathlib import Path
from typing import Callable, Optional

from PIL import (Image, ImageDraw, ImageFont, ImageOps,
                 UnidentifiedImageError)

from .models import (RESIZE_MODES, WATERMARK_POSITIONS, WATERMARK_TYPES,
                     Preset)

ProgressCallback = Callable[[int], None]

# Форматы, в которые Pillow умеет записать блок EXIF без потери остальных данных.
EXIF_CAPABLE_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "TIFF", "HEIF", "AVIF"})


def _to_int(value: str, label: str) -> int:
    """Преобразует строку в положительное целое число с понятной ошибкой."""
    try:
        number = int(float(str(value).strip()))
    except (AttributeError, ValueError) as exc:
        raise ValueError(
            f"Значение «{label}» должно быть целым числом, получено «{value}»"
        ) from exc
    if number <= 0:
        raise ValueError(f"Значение «{label}» должно быть положительным числом")
    return number


def _to_float(value: str, label: str) -> float:
    """Преобразует строку в число с понятной ошибкой."""
    try:
        return float(str(value).strip().replace(",", "."))
    except (AttributeError, ValueError) as exc:
        raise ValueError(
            f"Значение «{label}» должно быть числом, получено «{value}»"
        ) from exc


class ImageProcessor:
    """Изменяет размер, накладывает водяной знак и конвертирует изображения.

    Класс не зависит от графического интерфейса и может использоваться
    самостоятельно, например в пакетном конвертере или в тестах.

    Attributes:
        EXTENSIONS: Соответствие поддерживаемых форматов расширениям файлов.
        PIL_FORMATS: Соответствие форматов приложения внутренним именам Pillow.
        ICO_SIZES: Размеры изображений, записываемых в один файл ICO.
    """

    EXTENSIONS = {
        "PNG": ".png", "JPG": ".jpg", "WebP": ".webp", "BMP": ".bmp",
        "TIFF": ".tiff", "GIF": ".gif", "ICO": ".ico",
        "HEIC": ".heic", "AVIF": ".avif",
    }
    PIL_FORMATS = {"PNG": "PNG", "JPG": "JPEG", "WebP": "WEBP", "BMP": "BMP",
                   "TIFF": "TIFF", "GIF": "GIF", "ICO": "ICO", "HEIC": "HEIF", "AVIF": "AVIF"}
    # В один файл ICO записываются три изображения: 16×16, 32×32 и 64×64.
    ICO_SIZES = ((16, 16), (32, 32), (64, 64))
    ICO_BASE_MIN = 64
    ICO_BASE_MAX = 256

    def process(
        self,
        source: Path,
        preset: Preset,
        progress: Optional[ProgressCallback] = None,
    ) -> Path:
        """Обрабатывает один файл и возвращает путь к результату.

        Выполняются следующие операции: проверка исходного файла, создание папки
        назначения, изменение размера с сохранением пропорций, наложение
        водяного знака, очистка EXIF-метаданных, приведение цветового режима
        к совместимому с целевым форматом и сохранение результата.

        Исходный файл никогда не перезаписывается: если имя результата совпадает
        с исходником или с уже существующим файлом, добавляется суффикс
        ``_processed``.

        Args:
            source: Путь к исходному изображению.
            preset: Профиль настроек обработки.
            progress: Необязательный обработчик прогресса, принимающий процент
                выполнения от 0 до 100. Вызывается в начале, на промежуточных
                этапах и в конце обработки.

        Returns:
            Путь к созданному файлу результата.

        Raises:
            FileNotFoundError: Исходный файл не найден.
            ValueError: Некорректный формат, размеры, качество или прозрачность
                водяного знака.
            RuntimeError: Файл повреждён, не является изображением, либо
                результат не удалось сохранить.
        """
        source = Path(source)
        report = progress if progress is not None else lambda _percent: None
        report(8)
        if not source.is_file():
            raise FileNotFoundError(f"Исходный файл не найден: {source}")
        if preset.output_format not in self.EXTENSIONS:
            raise ValueError(f"Неподдерживаемый формат: {preset.output_format}")
        self._validate_preset(preset)
        self._load_optional_codec(preset.output_format)
        source_suffix = source.suffix.lower()
        if source_suffix in {".heic", ".heif"}:
            self._load_optional_codec("HEIC")
        elif source_suffix == ".avif":
            self._load_optional_codec("AVIF")

        output_dir = Path(preset.output_dir).expanduser() if preset.output_dir.strip() else source.parent / "processed"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = self._safe_output_path(output_dir, source, preset.output_format)

        try:
            with Image.open(source) as opened:
                # Convert the first frame of animated formats deliberately and predictably.
                opened.seek(0)
                # EXIF исходника сохраняется только когда пользователь не просил его удалить.
                source_exif = None if preset.clear_exif else opened.getexif()
                image = opened.copy()
        except UnidentifiedImageError as exc:
            raise RuntimeError(
                f"Файл {source.name} не является поддерживаемым изображением или повреждён"
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"Не удалось открыть файл {source.name}: {exc}") from exc
        report(35)
        image = self._resize(image, preset)
        report(60)
        if preset.watermark_enabled and self._watermark_content(preset):
            image = self._apply_watermark(image, preset)
        report(75)
        if preset.clear_exif:
            image.info.clear()
            try:
                image.getexif().clear()
            except (AttributeError, TypeError):
                pass
        report(85)
        image = self._prepare_mode(image, preset.output_format)
        report(93)
        target_format = self.PIL_FORMATS[preset.output_format]
        save_kwargs = {}
        if preset.output_format in {"JPG", "WebP", "AVIF", "HEIC"}:
            save_kwargs["quality"] = preset.quality
        if source_exif and len(source_exif) and target_format in EXIF_CAPABLE_FORMATS:
            save_kwargs["exif"] = source_exif.tobytes()
        if preset.output_format == "ICO":
            image = self._prepare_ico(image)
            save_kwargs["sizes"] = list(self.ICO_SIZES)
        try:
            image.save(output, format=target_format, **save_kwargs)
        except (KeyError, OSError, ValueError) as exc:
            output.unlink(missing_ok=True)
            if preset.output_format in {"HEIC", "AVIF"}:
                raise RuntimeError(
                    f"Не удалось сохранить {preset.output_format}. Установите и проверьте "
                    "соответствующий Pillow-плагин (pillow-heif или pillow-avif-plugin)."
                ) from exc
            raise RuntimeError(f"Не удалось сохранить файл {output.name}: {exc}") from exc
        report(100)
        return output

    @staticmethod
    def _validate_preset(preset: Preset) -> None:
        """Проверяет диапазоны параметров до начала обработки.

        Args:
            preset: Профиль настроек обработки.

        Raises:
            ValueError: Любой из параметров выходит за допустимый диапазон.
        """
        if preset.resize_mode not in RESIZE_MODES:
            raise ValueError(
                f"Неизвестный режим масштабирования: {preset.resize_mode}")
        if preset.resize_mode != "NONE":
            value = (preset.resize_value or "").strip()
            if not value:
                raise ValueError("Укажите значение размера для выбранного режима")
            if preset.resize_mode == "PERCENT":
                if not 0 < _to_float(value, "процент") <= 1000:
                    raise ValueError(
                        "Процент изменения размера должен быть больше 0")
            elif preset.resize_mode == "FIT":
                parts = value.lower().replace("х", "x").split("x", 1)
                if len(parts) != 2:
                    raise ValueError(
                        "Габаритный прямоугольник задаётся в виде «ширина×высота»")
                _to_int(parts[0], "ширина габарита")
                _to_int(parts[1], "высота габарита")
            else:
                _to_int(value, "размер изображения")
        if not 1 <= preset.quality <= 100:
            raise ValueError("Качество должно быть в диапазоне от 1 до 100")
        if not 0 <= preset.watermark_opacity <= 100:
            raise ValueError("Непрозрачность водяного знака должна быть от 0 до 100")
        if not 1 <= preset.watermark_size <= 20:
            raise ValueError("Размер водяного знака должен быть от 1 до 20 процентов")
        if preset.watermark_type not in WATERMARK_TYPES:
            raise ValueError(f"Неизвестный тип водяного знака: {preset.watermark_type}")
        if preset.watermark_position not in WATERMARK_POSITIONS:
            raise ValueError(
                f"Неизвестная позиция водяного знака: {preset.watermark_position}")

    @staticmethod
    def _load_optional_codec(output_format: str) -> None:
        """Подключает необязательные кодеки HEIC/AVIF, если они установлены."""
        try:
            if output_format == "HEIC":
                import pillow_heif  # noqa: F401
                pillow_heif.register_heif_opener()
            elif output_format == "AVIF":
                import pillow_avif  # noqa: F401
        except ImportError as exc:
            package = "pillow-heif" if output_format == "HEIC" else "pillow-avif-plugin"
            raise RuntimeError(
                f"Формат {output_format} требует дополнительный пакет: pip install {package}"
            ) from exc

    @classmethod
    def _safe_output_path(cls, output_dir: Path, source: Path, output_format: str) -> Path:
        """Не допускает перезапись исходника или уже созданного результата."""
        suffix = cls.EXTENSIONS[output_format]
        candidate = output_dir / f"{source.stem}{suffix}"
        if candidate.resolve() == source.resolve() or candidate.exists():
            candidate = output_dir / f"{source.stem}_processed{suffix}"
            number = 2
            while candidate.resolve() == source.resolve() or candidate.exists():
                candidate = output_dir / f"{source.stem}_processed_{number}{suffix}"
                number += 1
        return candidate

    @staticmethod
    def _target_size(image: Image.Image, preset: Preset) -> tuple:
        """Вычисляет размер изображения по режиму масштабирования из ТЗ.

        Поддерживаются пять режимов, требуемых техническим заданием:
        масштабирование по фиксированной ширине, по фиксированной высоте,
        вписывание в габаритный прямоугольник, процентное изменение
        и отказ от изменения размера.

        Args:
            image: Исходное изображение.
            preset: Профиль настроек обработки.

        Returns:
            Пара ``(ширина, высота)`` в пикселях.

        Raises:
            ValueError: Режим неизвестен или значение некорректно.
        """
        mode = preset.resize_mode
        value = (preset.resize_value or "").strip()

        if mode == "NONE":
            return image.size

        if mode == "PERCENT":
            percent = _to_float(value, "процент изменения размера")
            if not 0 < percent <= 1000:
                raise ValueError("Процент изменения размера должен быть больше 0")
            return (max(1, round(image.width * percent / 100)),
                    max(1, round(image.height * percent / 100)))

        if mode == "FIT":
            if "x" not in value.lower().replace("х", "x"):
                raise ValueError(
                    "Габаритный прямоугольник задаётся в виде «ширина×высота»")
            parts = value.lower().replace("х", "x").split("x", 1)
            box_w = _to_int(parts[0], "ширина габарита")
            box_h = _to_int(parts[1], "высота габарита")
            return ImageOps.contain(image, (box_w, box_h),
                                    method=Image.Resampling.LANCZOS).size

        number = _to_int(value, "размер")
        if mode == "WIDTH":
            if not 1 <= number <= 20000:
                raise ValueError("Ширина должна быть от 1 до 20000 пикселей")
            ratio = number / image.width
            height = round(image.height * ratio)
            if preset.keep_ratio:
                return number, max(1, height)
            return number, number

        if mode == "HEIGHT":
            if not 1 <= number <= 20000:
                raise ValueError("Высота должна быть от 1 до 20000 пикселей")
            ratio = number / image.height
            width = round(image.width * ratio)
            if preset.keep_ratio:
                return max(1, width), number
            return number, number

        raise ValueError(f"Неизвестный режим масштабирования: {mode}")

    @classmethod
    def _resize(cls, image: Image.Image, preset: Preset) -> Image.Image:
        """Изменяет размер по выбранному режиму с интерполяцией LANCZOS."""
        width, height = cls._target_size(image, preset)
        if (width, height) == image.size:
            return image.copy()
        return image.resize((width, height), Image.Resampling.LANCZOS)

    @staticmethod
    def _watermark_anchor(position: str, item_w: int, item_h: int,
                          canvas_w: int, canvas_h: int, margin: int) -> tuple:
        """Вычисляет координаты знака для одной из девяти позиций сетки 3×3.

        Args:
            position: Код позиции, например ``top-center``.
            item_w: Ширина накладываемого элемента.
            item_h: Высота накладываемого элемента.
            canvas_w: Ширина изображения-подложки.
            canvas_h: Высота изображения-подложки.
            margin: Отступ от края изображения.

        Returns:
            Координаты левого верхнего угла элемента.
        """
        def left(free: int) -> int:
            return max(margin, (free - item_w) // 2)

        def right(free: int) -> int:
            return max(margin, free - item_w - margin)

        def middle(free: int) -> int:
            return max(margin, (free - item_h) // 2)

        def bottom(free: int) -> int:
            return max(margin, free - item_h - margin)

        columns = {"left": lambda free: margin, "center": left, "right": right}
        rows = {"top": lambda free: margin, "center": middle, "middle": middle,
                "bottom": bottom}
        # Первая часть кода — положение по вертикали, вторая — по горизонтали:
        # «top-center» читается как верх и центр по горизонтали.
        # Позиция «center» без дефиса означает середину по обеим осям.
        parts = (position or "bottom-right").split("-", 1)
        if len(parts) == 2:
            row = parts[0] if parts[0] in rows else "bottom"
            column = parts[1] if parts[1] in columns else "right"
        else:
            row = column = "center" if parts[0] == "center" else None
            if row is None:
                row, column = "bottom", "right"
        return columns[column](canvas_w), rows[row](canvas_h)

    @classmethod
    def _apply_watermark(cls, image: Image.Image, preset: Preset) -> Image.Image:
        """Наносит текстовый или графический водяной знак.

        Графический знак берётся из PNG-файла с альфа-каналом и масштабируется
        относительно меньшей стороны изображения. Текстовый знак рисуется
        с заданным размером и цветом.

        Args:
            image: Обрабатываемое изображение.
            preset: Профиль настроек обработки.

        Returns:
            Изображение с наложенным знаком.

        Raises:
            RuntimeError: Графический знак недоступен или повреждён.
        """
        base = image.convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        alpha = round(255 * preset.watermark_opacity / 100)
        margin = cls._margin(base)

        if preset.watermark_type == "IMAGE" and preset.watermark_image.strip():
            mark = cls._load_logo(preset, base)
            x, y = cls._watermark_anchor(preset.watermark_position, mark.width,
                                         mark.height, base.width, base.height, margin)
            overlay.alpha_composite(mark, (x, y))
            return Image.alpha_composite(base, overlay)

        text = preset.watermark_text.strip()
        if not text:
            return base

        draw = ImageDraw.Draw(overlay)
        size_ratio = max(1, min(20, preset.watermark_size)) / 100
        font_size = max(10, min(400, round(min(base.size) * size_ratio)))
        font = cls._load_font(font_size)
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=1)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = cls._watermark_anchor(preset.watermark_position, text_w, text_h,
                                     base.width, base.height, margin)
        fill = cls._parse_color(preset.watermark_color, alpha)
        outline = ((255, 255, 255, alpha) if fill[:3] == (0, 0, 0)
                   else (0, 0, 0, alpha))
        draw.text((x, y), text, font=font, fill=fill,
                  stroke_width=max(1, font_size // 18), stroke_fill=outline)
        return Image.alpha_composite(base, overlay)

    @staticmethod
    def _watermark_content(preset: Preset) -> str:
        """Возвращает содержимое знака: текст или путь к файлу логотипа."""
        if preset.watermark_type == "IMAGE":
            return preset.watermark_image.strip()
        return preset.watermark_text.strip()

    @staticmethod
    def _margin(image: Image.Image) -> int:
        """Отступ водяного знака от края изображения."""
        return max(6, round(min(image.size) * 0.02))

    @staticmethod
    def _load_font(font_size: int):
        """Загружает шрифт Arial, при его отсутствии — стандартный шрифт Pillow."""
        for name in ("segoeuib.ttf", "arialbd.ttf", "arial.ttf",
                     "DejaVuSans-Bold.ttf"):
            try:
                return ImageFont.truetype(name, font_size)
            except OSError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _parse_color(value: str, alpha: int) -> tuple:
        """Преобразует HEX-цвет в кортеж RGBA с заданной прозрачностью."""
        text = (value or "").strip().lstrip("#")
        if len(text) != 6:
            return (255, 255, 255, alpha)
        try:
            red, green, blue = (int(text[index:index + 2], 16)
                                for index in (0, 2, 4))
        except ValueError:
            return (255, 255, 255, alpha)
        return (red, green, blue, alpha)

    @classmethod
    def _load_logo(cls, preset: Preset, canvas: Image.Image) -> Image.Image:
        """Загружает графический водяной знак и масштабирует его под изображение.

        Логотип вписывается в треть меньшей стороны результата, чтобы
        не перекрывать основное содержимое фотографии.

        Args:
            preset: Профиль с путём к файлу знака.
            canvas: Изображение, на которое наносится знак.

        Returns:
            Изображение знака в режиме RGBA.

        Raises:
            RuntimeError: Файл знака не найден или не является изображением.
        """
        path = Path(preset.watermark_image.strip())
        if not path.is_file():
            raise RuntimeError(f"Файл водяного знака не найден: {path}")
        try:
            with Image.open(path) as opened:
                logo = opened.convert("RGBA")
        except (UnidentifiedImageError, OSError) as exc:
            raise RuntimeError(
                f"Не удалось загрузить водяной знак {path.name}: "
                "ожидается файл изображения с прозрачностью (PNG)"
            ) from exc
        target = max(8, round(min(canvas.size) * 0.25))
        return ImageOps.contain(logo, (target, target),
                                method=Image.Resampling.LANCZOS)

    @classmethod
    def _prepare_ico(cls, image: Image.Image) -> Image.Image:
        """Готовит квадратное полотно, чтобы ICO содержал 16×16, 32×32 и 64×64.

        Pillow не увеличивает изображения при записи ICO и сохраняет пропорции,
        поэтому база делается квадратной и не меньше 64×64: только тогда все три
        размера попадают в файл, а исходное изображение центрируется на
        прозрачном полотне без искажений.
        """
        image = image.convert("RGBA")
        longest = max(image.size)
        if longest > cls.ICO_BASE_MAX:
            ratio = cls.ICO_BASE_MAX / longest
            image = image.resize(
                (max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
                Image.Resampling.LANCZOS,
            )
        side = max(cls.ICO_BASE_MIN, max(image.size))
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
        return canvas

    @staticmethod
    def _prepare_mode(image: Image.Image, output_format: str) -> Image.Image:
        """Подбирает цветовой режим, совместимый с форматом сохранения."""
        if output_format == "JPG":
            if image.mode in {"RGBA", "LA", "P"}:
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                return background
            return image.convert("RGB") if image.mode != "RGB" else image
        if output_format in {"BMP"}:
            return image.convert("RGB")
        if output_format in {"ICO", "PNG", "WebP", "AVIF", "HEIC"}:
            return image.convert("RGBA") if "A" in image.getbands() or image.mode == "P" else image.convert("RGB")
        if output_format == "GIF":
            return image.convert("P", palette=Image.Palette.ADAPTIVE)
        return image
