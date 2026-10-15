"""Генерация иконки приложения.

Рисуется знак студии пакетной обработки: скруглённый синий квадрат
с пиксельной сеткой и стрелкой обработки. Иконка сохраняется сразу
в нескольких размерах, поэтому один файл .ico содержит варианты
16, 24, 32, 48, 64 и 256 пикселей и корректно выглядит и в списке
файлов, и в заголовке окна.

Запуск:  python tools/make_icon.py
Результат: build_assets/app.ico и build_assets/app.png
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "build_assets"
#: Имя файла совпадает с ожиданием файла сборки ImageBatchStudio.spec,
#: поэтому иконка автоматически попадает в исполняемый файл.
OUT_FILE = OUT_DIR / "app.ico"

#: Размеры, которые записываются в файл иконки.
SIZES = (16, 24, 32, 48, 64, 128, 256)

#: Палитра знака в фирменных цветах приложения.
BACK_TOP = (67, 139, 255)
BACK_BOTTOM = (66, 185, 213)
GRID = (255, 255, 255, 40)
MARK = (255, 255, 255)


def draw_icon(size: int) -> Image.Image:
    """Рисует знак приложения в квадрате заданного размера.

    Args:
        size: Сторона квадрата в пикселях.

    Returns:
        Изображение RGBA со знаком.
    """
    scale = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Скруглённый квадрат с вертикальным градиентом.
    corner = max(2, int(56 * scale))
    gradient = Image.new("RGB", (1, size))
    for row in range(size):
        ratio = row / max(size - 1, 1)
        gradient.putpixel((0, row), tuple(
            round(BACK_TOP[channel] + (BACK_BOTTOM[channel] - BACK_TOP[channel]) * ratio)
            for channel in range(3)))
    gradient = gradient.resize((size, size), Image.Resampling.BILINEAR)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=corner, fill=255)
    image.paste(gradient.convert("RGBA"), (0, 0), mask)

    # Пиксельная сетка: символ пакетной обработки изображений.
    step = max(2, int(32 * scale))
    for row in range(step, size - step // 2, step):
        draw.rectangle(
            (int(52 * scale), row, int(204 * scale), row + max(1, int(4 * scale))),
            fill=GRID)
    for column in range(step, size - step // 2, step):
        draw.rectangle(
            (column, int(52 * scale), column + max(1, int(4 * scale)),
             int(204 * scale)),
            fill=GRID)

    # Стрелка обработки поверх сетки.
    width = max(2, int(14 * scale))
    arrow_x = size / 2
    head_y = int(108 * scale)
    tail_y = int(176 * scale)
    draw.line((arrow_x, tail_y, arrow_x, head_y), fill=MARK, width=width)
    half = max(2, int(20 * scale))
    draw.polygon(
        [(arrow_x, int(84 * scale)),
         (arrow_x - half, head_y),
         (arrow_x + half, head_y)],
        fill=MARK)
    return image


def main() -> int:
    """Создаёт файл иконки со всеми размерами."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    largest = draw_icon(max(SIZES))
    # Pillow масштабирует первое переданное изображение до каждого
    # запрошенного размера, поэтому достаточно одного исходника.
    largest.save(OUT_FILE, format="ICO",
                 sizes=[(size, size) for size in SIZES])
    # Копия в PNG нужна для заголовка окна и документации. Имя совпадает
    # с файлом .ico без расширения, поэтому программа находит её рядом
    # и в папке проекта, и рядом с собранным исполняемым файлом.
    largest.save(OUT_DIR / "app.png")
    with Image.open(OUT_FILE) as check:
        found = sorted(check.ico.sizes())
    print("Иконка сохранена:", OUT_FILE)
    print("Размеры внутри файла:", found)
    print("Размер файла:", OUT_FILE.stat().st_size, "байт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())