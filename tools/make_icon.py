"""Создаёт иконку приложения build_assets/app.ico для сборки .exe."""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
ROOT = Path(__file__).resolve().parent.parent


def build() -> Path:
    """Рисует иконку в палитре приложения и сохраняет в build_assets/app.ico."""
    page = (8, 15, 29)
    card = (14, 25, 43)
    accent = (67, 139, 255)
    accent_light = (90, 155, 255)
    mint = (67, 214, 160)

    image = Image.new("RGBA", (SIZE, SIZE), page + (255,))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=54,
                           fill=card, outline=(29, 43, 64), width=6)

    # Увеличенное изображение с водяным знаком и стрелкой конвертации.
    draw.rounded_rectangle((46, 58, 170, 132), radius=14, fill=accent + (255,))
    draw.polygon([(66, 104), (108, 78), (150, 104), (108, 126)],
                 fill=accent_light + (255,))
    draw.ellipse((118, 70, 148, 100), fill=(241, 245, 252, 255))
    draw.rounded_rectangle((46, 150, 176, 172), radius=11, fill=(38, 53, 75, 255))
    draw.rounded_rectangle((46, 184, 140, 206), radius=11, fill=(38, 53, 75, 255))

    # Галочка готовности.
    draw.ellipse((150, 148, 226, 224), fill=mint + (255,))
    draw.line((168, 186, 184, 202, 210, 170), fill=page + (255,),
              width=13, joint="curve")

    target = ROOT / "build_assets"
    target.mkdir(exist_ok=True)
    path = target / "app.ico"
    image.save(path, format="ICO",
               sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"Иконка сохранена: {path}")
    return path


if __name__ == "__main__":
    build()
