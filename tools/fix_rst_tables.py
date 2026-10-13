"""Исправляет ширину простых таблиц reStructuredText.

Скрипт выравнивает колонки простых таблиц Sphinx по фактической длине
содержимого: длина строки-разделителя должна быть не меньше самой длинной
ячейки, иначе docutils сообщает «Malformed table».

Запуск:  python tools/fix_rst_tables.py [папка с .rst]
"""
import re
import sys
from pathlib import Path

SEPARATOR = re.compile(r"^=+( +=+)*$")
CELLS = re.compile(r"\s{2,}")


def is_separator(line: str) -> bool:
    """Проверяет, что строка состоит только из знаков «=» и пробелов."""
    return bool(SEPARATOR.match(line))


def split_row(line: str) -> list:
    """Делит строку таблицы на ячейки по двум и более пробелам."""
    return [part.strip() for part in CELLS.split(line.strip()) if part.strip()]


def separator_line(widths) -> str:
    """Собирает строку-разделитель по заданным ширинам колонок."""
    return "  ".join("=" * width for width in widths)


def data_line(cells, widths) -> str:
    """Собирает строку данных, выравнивая ячейки по колонкам."""
    parts = []
    for index, width in enumerate(widths):
        cell = cells[index] if index < len(cells) else ""
        parts.append(cell.ljust(width))
    return "  ".join(parts).rstrip()


def fix_table(lines, header_index: int, separator_index: int) -> tuple:
    """Пересобирает одну таблицу.

    Args:
        header_index: Номер строки с заголовками колонок.
        separator_index: Номер строки-разделителя под заголовками.
    """
    widths = [len(part) for part in lines[separator_index].split() if part]
    end = separator_index + 1
    rows = []
    while end < len(lines) and lines[end].strip():
        if is_separator(lines[end]):          # закрывающая строка-разделитель
            end += 1
            break
        rows.append(split_row(lines[end]))
        end += 1

    columns = len(widths)
    if columns < 2 or any(len(row) != columns for row in rows):
        return None, header_index                  # структура нестандартная — не трогаем

    header_cells = split_row(lines[header_index])
    if len(header_cells) != columns:
        return None, header_index

    for row in rows + [header_cells]:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    rebuilt = [separator_line(widths), data_line(header_cells, widths)]
    rebuilt += [data_line(row, widths) for row in rows]
    rebuilt.append(separator_line(widths))
    return rebuilt, end


def process(path: Path) -> bool:
    """Исправляет все простые таблицы в одном файле."""
    lines = path.read_text(encoding="utf-8").split("\n")
    result, index, changed = [], 0, False
    while index < len(lines):
        # Простая таблица: строка-разделитель, заголовок, такой же разделитель.
        if (is_separator(lines[index]) and index + 2 < len(lines)
                and is_separator(lines[index + 2])
                and lines[index] == lines[index + 2]):
            rebuilt, end = fix_table(lines, index + 1, index + 2)
            if rebuilt is None:
                result.append(lines[index])
                index += 1
                continue
            result.extend(rebuilt)
            index = end
            changed = True
            continue
        result.append(lines[index])
        index += 1
    if changed:
        path.write_text("\n".join(result), encoding="utf-8")
    return changed


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    total = 0
    for path in sorted(Path(folder).glob("*.rst")):
        if process(path):
            print("исправлено:", path.name)
            total += 1
    print("файлов исправлено:", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
