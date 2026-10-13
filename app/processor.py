"""Бизнес-логика обработки изображений через Pillow."""
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from .models import Preset

ProgressCallback = Callable[[int], None]

# Форматы, в которые Pillow умеет записать блок EXIF без потери остальных данных.
EXIF_CAPABLE_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "TIFF", "HEIF", "AVIF"})


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
        if preset.watermark_enabled and preset.watermark_text.strip():
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
        """Проверяет диапазоны параметров до начала обработки."""
        for label, value in (("ширина", preset.width), ("высота", preset.height)):
            if value is not None and (isinstance(value, bool) or value <= 0):
                raise ValueError(f"Значение «{label}» должно быть положительным целым числом")
        if preset.width is None and preset.height is None:
            pass
        if not 1 <= preset.quality <= 100:
            raise ValueError("Качество должно быть в диапазоне от 1 до 100")
        if not 0 <= preset.watermark_opacity <= 100:
            raise ValueError("Непрозрачность водяного знака должна быть от 0 до 100")

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
    def _resize(image: Image.Image, preset: Preset) -> Image.Image:
        """Изменяет размер, сохраняя пропорции при включённой опции."""
        if preset.width is None and preset.height is None:
            return image.copy()
        width = preset.width or image.width
        height = preset.height or image.height
        if preset.keep_ratio:
            ratio = min(width / image.width, height / image.height)
            width = max(1, round(image.width * ratio))
            height = max(1, round(image.height * ratio))
        return image.resize((width, height), Image.Resampling.LANCZOS)

    @staticmethod
    def _apply_watermark(image: Image.Image, preset: Preset) -> Image.Image:
        """Накладывает текстовый водяной знак с заданной позицией и прозрачностью."""
        base = image.convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font_size = max(12, min(48, round(min(base.size) * 0.04)))
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()
        text = preset.watermark_text.strip()
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=1)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        margin = max(8, round(min(base.size) * 0.02))
        positions = {
            "bottom-right": (base.width - text_w - margin, base.height - text_h - margin),
            "top-right": (base.width - text_w - margin, margin),
            "bottom-left": (margin, base.height - text_h - margin),
            "top-left": (margin, margin),
        }
        x, y = positions.get(preset.watermark_position, positions["bottom-right"])
        alpha = round(255 * preset.watermark_opacity / 100)
        draw.text((x, y), text, font=font, fill=(255, 255, 255, alpha),
                  stroke_width=1, stroke_fill=(0, 0, 0, alpha))
        return Image.alpha_composite(base, overlay)

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
