"""Сборка презентации для защиты практики.

Создаёт файл docs/_build/BatchImageStudio_презентация.pptx со слайдами
в тёмной теме приложения: титульный, проблема, решение, архитектура,
демонстрация, качество, развёртывание, документация, итоги, план.

Запуск:  python tools/make_presentation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from pptx import Presentation  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.text import PP_ALIGN  # noqa: E402
from pptx.util import Cm, Pt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
OUT = ROOT / "docs" / "_build" / "BatchImageStudio_презентация.pptx"

PAGE = RGBColor(0x08, 0x0F, 0x1D)
CARD = RGBColor(0x0E, 0x19, 0x2B)
BORDER = RGBColor(0x1D, 0x2B, 0x40)
TEXT = RGBColor(0xF1, 0xF5, 0xFC)
MUTED = RGBColor(0xA5, 0xB3, 0xC8)
HINT = RGBColor(0x65, 0x75, 0x8D)
ACCENT = RGBColor(0x43, 0x8B, 0xFF)
ACCENT_LIGHT = RGBColor(0x5A, 0x9B, 0xFF)
MINT = RGBColor(0x43, 0xD6, 0xA0)
CYAN = RGBColor(0x42, 0xB9, 0xD5)
ALERT = RGBColor(0xFF, 0x6B, 0x78)

TITLE_FONT = "Segoe UI Semibold"
BODY_FONT = "Segoe UI"

SLIDE_W = Cm(33.87)
SLIDE_H = Cm(19.05)


def add_slide(presentation: Presentation):
    """Добавляет пустой слайд с фоном приложения."""
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    background = slide.background.fill
    background.solid()
    background.fore_color.rgb = PAGE
    return slide


def set_text(frame, blocks, align=PP_ALIGN.LEFT, space=8):
    """Заполняет текстовый блок абзацами вида (текст, размер, цвет, жирный)."""
    frame.clear()
    for index, (value, size, color, bold) in enumerate(blocks):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = align
        paragraph.space_after = Pt(space)
        run = paragraph.add_run()
        run.text = value
        run.font.size = Pt(size)
        run.font.color.rgb = color
        run.font.bold = bold
        run.font.name = BODY_FONT


def slide_title(slide, title: str, subtitle: str = ""):
    """Добавляет заголовок слайда с акцентной полосой."""
    bar = slide.shapes.add_shape(1, Cm(1.6), Cm(1.5), Cm(0.18), Cm(1.5))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    bar.shadow.inherit = False

    box = slide.shapes.add_textbox(Cm(2.2), Cm(1.1), Cm(29), Cm(2.8))
    blocks = [(title, 32, TEXT, True)]
    if subtitle:
        blocks.append((subtitle, 15, HINT, False))
    set_text(box.text_frame, blocks)
    return box


def bullets(slide, items, left=2.4, top=4.6, width=28.5, height=12.0, size=17):
    """Добавляет маркированный список."""
    box = slide.shapes.add_textbox(Cm(left), Cm(top), Cm(width), Cm(height))
    frame = box.text_frame
    frame.word_wrap = True
    blocks = []
    for item in items:
        if isinstance(item, tuple):
            head, tail = item
            blocks.append((f"•  {head} — {tail}", size, MUTED, False))
        else:
            blocks.append((f"•  {item}", size, MUTED, False))
    set_text(frame, blocks, space=12)
    return box


def metric_cards(slide, cards, top=5.0, left=2.4, width=29.0, height=3.6):
    """Добавляет ряд карточек с числовыми показателями."""
    count = len(cards)
    gap = 0.6
    card_width = (width - gap * (count - 1)) / count
    for index, (value, label, color) in enumerate(cards):
        left_cm = left + (card_width + gap) * index
        shape = slide.shapes.add_shape(1, Cm(left_cm), Cm(top), Cm(card_width), Cm(height))
        shape.fill.solid()
        shape.fill.fore_color.rgb = CARD
        shape.line.color.rgb = BORDER
        shape.line.width = Pt(1)
        shape.shadow.inherit = False
        frame = shape.text_frame
        frame.margin_top = Cm(0.5)
        set_text(frame, [(value, 34, color, True), (label, 13, MUTED, False)],
                 align=PP_ALIGN.CENTER, space=4)


def picture(slide, filename, left, top, width=None, height=None, caption=""):
    """Добавляет снимок экрана с подписью под ним.

    Высота подписи рассчитывается по реальным пропорциям изображения,
    иначе подпись наезжает на нижний край снимка.
    """
    path = SHOTS / filename
    if not path.exists():
        return
    if width is not None and height is None:
        with Image.open(path) as source:
            ratio = source.height / source.width
        height = width * ratio
    kwargs = {}
    if width is not None:
        kwargs["width"] = Cm(width)
    if height is not None:
        kwargs["height"] = Cm(height)
    slide.shapes.add_picture(str(path), Cm(left), Cm(top), **kwargs)
    if caption:
        box = slide.shapes.add_textbox(Cm(left), Cm(top + height + 0.25),
                                       Cm(width or 20), Cm(1.0))
        set_text(box.text_frame, [(caption, 12, HINT, False)], align=PP_ALIGN.CENTER)


def footer(slide, number: int):
    """Добавляет нижний колонтитул с номером слайда."""
    box = slide.shapes.add_textbox(Cm(1.6), Cm(17.2), Cm(30), Cm(1.0))
    frame = box.text_frame
    frame.clear()
    paragraph = frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.RIGHT
    run = paragraph.add_run()
    run.text = f"Image Batch Studio  ·  {number}"
    run.font.size = Pt(11)
    run.font.color.rgb = HINT
    run.font.name = BODY_FONT


def build() -> Path:
    presentation = Presentation()
    presentation.slide_width = SLIDE_W
    presentation.slide_height = SLIDE_H
    number = 0

    # ------------------------------------------------------- 1. Титульный
    slide = add_slide(presentation)
    number += 1
    band = slide.shapes.add_shape(1, 0, 0, SLIDE_W, Cm(0.5))
    band.fill.solid()
    band.fill.fore_color.rgb = ACCENT
    band.line.fill.background()
    band.shadow.inherit = False

    box = slide.shapes.add_textbox(Cm(2.4), Cm(5.4), Cm(29), Cm(9))
    set_text(box.text_frame, [
        ("СТУДИЯ ПАКЕТНОЙ ОБРАБОТКИ ГРАФИКИ", 16, ACCENT, True),
        ("Image Batch Studio", 52, TEXT, True),
        ("Настольное приложение для массовой обработки изображений", 19, MUTED, False),
    ], space=14)

    box = slide.shapes.add_textbox(Cm(2.4), Cm(14.2), Cm(29), Cm(3))
    set_text(box.text_frame, [
        ("Учебная практика УП.01 · Разработка программных модулей", 14, HINT, False),
        ("Студент группы ИСП-34 · 2026", 14, HINT, False),
    ], space=6)
    footer(slide, number)

    # ------------------------------------------------------- 2. Проблема
    slide = add_slide(presentation)
    number += 1
    slide_title(slide, "Проблема", "Что мешает пользователю сегодня")
    bullets(slide, [
        ("Поштучная обработка", "десятки фотографий обрабатываются вручную часами"),
        ("Публичные метаданные", "при загрузке в сеть утекает геолокация и модель камеры"),
        ("Разные требования площадок", "каждому сайту нужен свой формат и размер"),
        ("Копирайт вручную", "надпись на фото наносится по одной"),
    ])
    metric_cards(slide, [
        ("часы", "на 100 фотографий вручную", ALERT),
        ("риск", "утечки геолокации", ALERT),
        ("1 файл", "за операцию в простом редакторе", ALERT),
    ], top=12.0)
    footer(slide, number)

    # ------------------------------------------------------- 3. Решение
    slide = add_slide(presentation)
    number += 1
    slide_title(slide, "Решение", "Одна программа вместо ручной работы")
    bullets(slide, [
        ("Пакетный режим", "файлы, папки и перетаскивание — вся очередь сразу"),
        ("Девять форматов", "PNG, JPG, WebP, BMP, TIFF, GIF, ICO, HEIC, AVIF"),
        ("Размер с пропорциями", "алгоритм LANCZOS, картинка не растягивается"),
        ("Чистка EXIF", "один переключатель убирает скрытые метаданные"),
        ("Водяной знак", "текст в четырёх углах с настройкой прозрачности"),
        ("Профили", "настройки сохраняются и применяются повторно"),
    ], top=4.4, height=10.0)
    metric_cards(slide, [
        ("0,21 с", "обработка снимка Full HD", CYAN),
        ("9", "целевых форматов", ACCENT),
        ("5000", "файлов без утечек памяти", MINT),
    ], top=13.4)
    footer(slide, number)

    # ------------------------------------------------------- 4. Архитектура
    slide = add_slide(presentation)
    number += 1
    slide_title(slide, "Архитектура", "Три слоя, между ними нет прямых связей")
    layers = [
        ("Интерфейс", "app/ui.py — окно, очередь, предпросмотр", ACCENT),
        ("Бизнес-логика", "app/processor.py · app/worker.py — обработка и фоновый поток", CYAN),
        ("Данные", "app/database.py · SQLite — профили и журнал", MINT),
    ]
    for index, (name, detail, color) in enumerate(layers):
        top = 4.6 + index * 3.4
        shape = slide.shapes.add_shape(1, Cm(2.4), Cm(top), Cm(29), Cm(2.8))
        shape.fill.solid()
        shape.fill.fore_color.rgb = CARD
        shape.line.color.rgb = color
        shape.line.width = Pt(1.5)
        shape.shadow.inherit = False
        set_text(shape.text_frame, [(name, 20, color, True), (detail, 14, MUTED, False)],
                 space=2)
    box = slide.shapes.add_textbox(Cm(2.4), Cm(15.2), Cm(29), Cm(2.4))
    set_text(box.text_frame, [
        ("Следствие: обработку можно тестировать без окна, а внешний вид менять, "
         "не трогая математику пикселей.", 14, HINT, False),
    ])
    footer(slide, number)

    # ------------------------------------------------------- 5. Демонстрация
    slide = add_slide(presentation)
    number += 1
    slide_title(slide, "Как это выглядит", "Три состояния по макету Figma")
    picture(slide, "02_state_queue.png", 1.6, 4.2, width=15.2,
            caption="Файлы в очереди и пресет")
    picture(slide, "04_state_done.png", 17.2, 4.2, width=15.2,
            caption="Результат и сравнение до и после")
    footer(slide, number)

    slide = add_slide(presentation)
    number += 1
    slide_title(slide, "Демонстрация: живой прогресс", "Окно отвечает во время обработки")
    picture(slide, "03_state_process.png", 1.6, 4.6, width=17.4,
            caption="Состояние «Процесс»: статусы, индикатор, отмена")
    box = slide.shapes.add_textbox(Cm(20.2), Cm(5.0), Cm(12.4), Cm(11))
    set_text(box.text_frame, [
        ("Фоновая обработка", 17, ACCENT, True),
        ("", 8, MUTED, False),
        ("Работа идёт в отдельном потоке, окно остаётся отзывчивым", 15, MUTED, False),
        ("", 8, MUTED, False),
        ("Ошибка одного файла", 17, ACCENT, True),
        ("", 8, MUTED, False),
        ("не останавливает очередь: остальные обрабатываются", 15, MUTED, False),
        ("", 8, MUTED, False),
        ("Отмена", 17, ACCENT, True),
        ("", 8, MUTED, False),
        ("оставшиеся файлы получают статус «Отменено»", 15, MUTED, False),
    ], space=4)
    footer(slide, number)

    # ------------------------------------------------------- 6. Качество
    slide = add_slide(presentation)
    number += 1
    slide_title(slide, "Качество", "143 теста, покрытие кода 88 %")
    metric_cards(slide, [
        ("143", "автоматических теста", MINT),
        ("88 %", "покрытие кода", ACCENT),
        ("0", "замечаний flake8", CYAN),
    ], top=4.4)
    bullets(slide, [
        ("Модульные", "обработка изображений, слой данных, граничные случаи"),
        ("Интеграционные", "фоновый поток + обработчик + SQLite вместе"),
        ("Системные", "настоящее окно Tkinter и полный пользовательский сценарий"),
        ("Безопасность", "попытки SQL-инъекций и статический анализ текста запросов"),
    ], top=9.2, height=7.4)
    footer(slide, number)

    slide = add_slide(presentation)
    number += 1
    slide_title(slide, "Что нашли тесты", "Восемь дефектов, четыре видны только автоматически")
    rows = [
        ("EXIF", "флажок очистки не влиял на результат"),
        ("Битый файл", "необработанное исключение вместо сообщения"),
        (".exe", "не запускался из-за относительных импортов"),
        ("База в .exe", "сохранялась во временной папке и терялась"),
        ("ALTER TABLE", "имена объектов подставлялись в текст запроса"),
        ("Предпросмотр", "блок «После обработки» оставался пустым"),
        ("tkdnd", "приложение падало, если библиотека не загрузилась"),
        ("Кэш миниатюр", "ошибка при повторном создании окна"),
    ]
    for index, (name, detail) in enumerate(rows):
        column = index % 2
        row = index // 2
        left = 2.4 + column * 15.0
        top = 4.6 + row * 2.7
        shape = slide.shapes.add_shape(1, Cm(left), Cm(top), Cm(14.2), Cm(2.3))
        shape.fill.solid()
        shape.fill.fore_color.rgb = CARD
        shape.line.color.rgb = BORDER
        shape.shadow.inherit = False
        set_text(shape.text_frame, [(name, 14, ACCENT_LIGHT, True),
                                    (detail, 12, MUTED, False)], space=1)
    footer(slide, number)

    # ------------------------------------------------------- 7. Производительность
    slide = add_slide(presentation)
    number += 1
    slide_title(slide, "Производительность", "Измерено на 200 снимках Full HD")
    metric_cards(slide, [
        ("39 мс", "открытие окна", MINT),
        ("0,4 мс", "запись в базу", MINT),
        ("0,21 с", "снимок Full HD", ACCENT),
        ("+6 МБ", "память на 1200 файлов", MINT),
    ], top=4.4)
    bullets(slide, [
        ("Требование ТЗ «отклик не более 0,3 с»", "выполнено с запасом"),
        ("Требование «Full HD не более 0,1 с»", "не выполнено: 0,21 с"),
        ("Причина найдена профилированием", "82 % времени — кодирование WebP"),
        ("Вывод", "собственная обработка укладывается в 39 мс, медленный кодек — нет"),
    ], top=9.2, height=7.6)
    footer(slide, number)

    # ------------------------------------------------------- 8. Развёртывание
    slide = add_slide(presentation)
    number += 1
    slide_title(slide, "Развёртывание", "Один файл — и Python не нужен")
    metric_cards(slide, [
        ("34,3 МБ", "размер BatchImageStudio.exe", ACCENT),
        ("1,0 с", "до готовности окна", MINT),
        ("5", "шагов в build_windows.bat", CYAN),
    ], top=4.4)
    bullets(slide, [
        ("Сборка PyInstaller", "окно без консоли, tkdnd и кодеки внутри файла"),
        ("Проверка автономности", "запуск из произвольной папки без Python"),
        ("Данные рядом с программой", "при отсутствии прав — %LOCALAPPDATA%"),
        ("CI/CD на GitHub Actions", "тесты на трёх версиях Python, сборка после них"),
    ], top=9.2, height=7.6)
    footer(slide, number)

    # ------------------------------------------------------- 9. Документация
    slide = add_slide(presentation)
    number += 1
    slide_title(slide, "Документация и передача знаний", "Sphinx, автодокументация из docstrings")
    bullets(slide, [
        ("11 разделов", "обзор, архитектура, функциональность, API, руководства"),
        ("Автодокументация", "раздел API собирается из docstrings модулей"),
        ("Сборка без предупреждений", "HTML и PDF на 49 страниц с закладками"),
        ("Руководство пользователя", "сценарий работы и 12 типовых проблем"),
        ("Руководство разработчика", "окружение, тесты, сборка, соглашения"),
        ("Передача проекта", "документ HANDOVER: что читать и что делать"),
        ("Бэклог", "20 задач на три ближайшие версии"),
    ], top=4.4, height=12.0)
    footer(slide, number)

    # ------------------------------------------------------- 10. Итоги
    slide = add_slide(presentation)
    number += 1
    slide_title(slide, "Итоги работы", "Что сделано и что освоено")
    box = slide.shapes.add_textbox(Cm(2.4), Cm(4.4), Cm(14.2), Cm(12))
    set_text(box.text_frame, [
        ("Результат", 20, ACCENT, True),
        ("Готовое приложение, один файл .exe, документация Sphinx, "
         "143 теста, презентация и бэклог", 15, MUTED, False),
        ("", 10, MUTED, False),
        ("Практическая польза", 20, ACCENT, True),
        ("Решение задачи «поштучная обработка и утечка метаданных» "
         "с измеримым результатом", 15, MUTED, False),
    ], space=6)
    box = slide.shapes.add_textbox(Cm(18.0), Cm(4.4), Cm(14.2), Cm(12))
    set_text(box.text_frame, [
        ("Освоенные навыки", 20, MINT, True),
        ("Многослойная архитектура и MVC, SQLite, многопоточность и "
         "потокобезопасность, pytest и coverage.py, PyInstaller, Sphinx, "
         "CI/CD, профилирование производительности", 15, MUTED, False),
        ("", 10, MUTED, False),
        ("Честный вывод", 20, MINT, True),
        ("Одно требование ТЗ не выполнено — время обработки. "
         "Причина установлена и обоснована, а не скрыта", 15, MUTED, False),
    ], space=6)
    footer(slide, number)

    # ------------------------------------------------------- 11. Спасибо
    slide = add_slide(presentation)
    number += 1
    box = slide.shapes.add_textbox(Cm(2.4), Cm(6.4), Cm(29), Cm(6))
    set_text(box.text_frame, [
        ("Спасибо за внимание", 44, TEXT, True),
        ("Готов ответить на вопросы и показать работающее приложение", 18, MUTED, False),
    ], space=12)
    box = slide.shapes.add_textbox(Cm(2.4), Cm(12.6), Cm(29), Cm(3.4))
    set_text(box.text_frame, [
        ("Демонстрация: dist\\BatchImageStudio.exe", 15, HINT, False),
        ("Документация: docs\\_build\\html\\index.html", 15, HINT, False),
    ], space=4)
    footer(slide, number)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(OUT)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"Презентация сохранена: {path}")
    print(f"Слайдов: {len(Presentation(str(path)).slides.__iter__.__self__._sldIdLst)}")
