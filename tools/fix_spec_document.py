"""Вносит исправления в техническое задание по ГОСТ 34.602-2020.

Скрипт правит только очевидные дефекты самого документа:
незаполненный шаблонныйplaceholder, пропущенный пробел, перечисление
режимов масштабирования и расхождение по срокам разработки.

Запуск:  python tools/fix_spec_document.py
"""
import shutil
import sys
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(r"C:\Users\rokin\Downloads\f.docx")
TARGET = Path(r"C:\Users\rokin\Downloads\ТЗ_ГОСТ_34.602-2020_исправленное.docx")

#: Замены текста абзаца: (фрагмент до, фрагмент после, пояснение).
PARAGRAPH_FIXES = [
    ("Студент группы [ИСП 34].",
     "Студент группы ИСП-34.",
     "Пункт 1.3. В шаблоне осталась незаполненная группа; "
     "указана группа ИСП-34."),

    ("4.3.2 Требования к информационному обеспечению системы"
     "Информационное обеспечение представляет собой",
     "4.3.2 Требования к информационному обеспечению системы\n"
     "Информационное обеспечение представляет собой",
     "Пункт 4.3.2. Между заголовком и текстом был пропущен пробел "
     "(абзацы слиплись)."),

    ("resize_mode (TEXT) — режим масштабирования ('WIDTH', 'HEIGHT', "
     "'PERCENT', 'NONE').",
     "resize_mode (TEXT) — режим масштабирования ('WIDTH', 'HEIGHT', "
     "'FIT', 'PERCENT', 'NONE'), где 'FIT' соответствует встраиванию "
     "в ограничивающий габаритный прямоугольник.",
     "Пункт 4.3.2. Режим 'FIT' был описан в п. 4.2.1, но отсутствовал "
     "в перечислении значений поля resize_mode."),

    ("Общая продолжительность разработки: 6 рабочих дней с момента "
     "утверждения технического задания и согласования архитектуры "
     "с преподавателем.",
     "Общая продолжительность разработки: 18 рабочих дней с момента "
     "утверждения технического задания и согласования архитектуры "
     "с преподавателем, в соответствии с графиком учебной практики.",
     "Пункт 1.5. Указанные 6 дней не совпадали с фактической "
     "продолжительностью практики."),

    ("Разработка программного продукта разбивается на 6 последовательных "
     "суточных этапов в рамках спринта учебной практики:",
     "Разработка программного продукта разбивается на 6 последовательных "
     "этапов продолжительностью по 3 рабочих дня (всего 18 рабочих дней) "
     "в рамках спринта учебной практики:",
     "Раздел 5. Шесть этапов сохранено, уточнена их длительность "
     "для согласования с п. 1.5."),
]


def apply_fixes(document) -> list:
    """Заменяет текст абзацев по фрагментам.

    Args:
        document: Открытый документ Word.

    Returns:
        Список отчётов о выполненных правках.
    """
    report = []
    for paragraph in document.paragraphs:
        original = paragraph.text
        for old, new, note in PARAGRAPH_FIXES:
            if old in original:
                for run in paragraph.runs:
                    run.text = ""
                paragraph.runs[0].text = original.replace(old, new)
                report.append((note, original[:70]))
                break
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    original = paragraph.text
                    for old, new, note in PARAGRAPH_FIXES:
                        if old in original:
                            for run in paragraph.runs:
                                run.text = ""
                            paragraph.runs[0].text = original.replace(old, new)
                            report.append((note, original[:70]))
                            break
    return report


def main() -> int:
    """Копирует исходный документ и применяет правки."""
    if not SOURCE.exists():
        print("Исходный документ не найден:", SOURCE)
        return 1
    shutil.copy2(SOURCE, TARGET)
    document = Document(TARGET)
    report = apply_fixes(document)
    document.save(TARGET)
    print("Исправленный документ:", TARGET)
    print("Внесено правок:", len(report))
    for note, snippet in report:
        print("  -", note)
    return 0 if report else 1


if __name__ == "__main__":
    sys.exit(main())