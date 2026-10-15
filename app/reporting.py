"""Экспорт результатов пакетной обработки в таблицу CSV.

Модуль собирает данные журнала сессий и обработанных файлов в файл,
который можно открыть в Excel или LibreOffice Calc без дополнительной
подготовки. Разделителем выбирается точка с запятой, потому что
русская версия Excel по умолчанию разделяет поля именно ей.

Формирование файла вынесено отдельно от интерфейса, поэтому его
можно проверить в автоматических тестах без запуска окна.
"""
import csv
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

#: Разделитель полей, который читает русская версия Excel.
DELIMITER = ";"

#: Кодировка файла: bom добавляется, чтобы Excel не ломал кириллицу.
ENCODING = "utf-8-sig"

#: Заголовок таблицы сессий.
SESSION_HEADER = ("Номер сессии", "Дата и время", "Профиль настроек",
                  "Всего файлов", "Успешно", "Ошибок", "Длительность, с")

#: Заголовок таблицы файлов.
FILE_HEADER = ("Номер сессии", "Дата и время", "Исходный файл",
               "Результат", "Размер до, байт", "Размер после, байт",
               "Экономия, %", "Статус", "Ошибка")

#: Значения статуса в базе и соответствующие подписи для пользователя.
STATUS_LABELS = {"SUCCESS": "Готово", "ERROR": "Ошибка"}


#: Порядок столбцов, который возвращает list_processed_files.
FILE_COLUMNS = ("id", "source_path", "result_path", "file_size_before",
                "file_size_after", "status", "error")

#: Порядок столбцов, который возвращает list_sessions.
SESSION_COLUMNS = ("id", "session_date", "finished_at", "preset_name",
                   "total_files", "successful_files", "failed_files",
                   "duration_sec")


def _field(entry: Sequence, columns: Sequence[str], column: str, default=None):
    """Возвращает значение столбца по его имени.

    Обращение по имени, а не по номеру, избавляет от ошибок при
    изменении состава запроса в слое данных.

    Args:
        entry: Строка результата запроса.
        columns: Имена столбцов в порядке запроса.
        column: Имя нужного столбца.
        default: Значение при отсутствии столбца или значения.

    Returns:
        Значение столбца либо значение по умолчанию.
    """
    if column not in columns:
        return default
    index = list(columns).index(column)
    if index >= len(entry):
        return default
    value = entry[index]
    return default if value is None else value


def _round_percent(before: int, after: int) -> int:
    """Считает экономию размера в процентах.

    Args:
        before: Размер исходного файла в байтах.
        after: Размер результата в байтах.

    Returns:
        Экономия в целых процентах; отрицательное значение означает
        увеличение размера. При нулевом исходном файле возвращается 0.
    """
    if not before:
        return 0
    return round((before - after) / before * 100)


def build_rows(sessions: Sequence[Sequence], files_by_session: dict) -> List[List]:
    """Готовит строки отчёта по всем данным журнала.

    Args:
        sessions: Список сессий из журнала запусков.
        files_by_session: Словарь ``{номер сессии: список файлов}``.

    Returns:
        Список строк отчёта, каждая строка — список значений.
    """
    rows: List[List] = []
    for session in sessions:
        session_id = _field(session, SESSION_COLUMNS, "id", "")
        date = _field(session, SESSION_COLUMNS, "session_date", "")
        profile = _field(session, SESSION_COLUMNS, "preset_name", "")
        total = _field(session, SESSION_COLUMNS, "total_files", 0)
        ok = _field(session, SESSION_COLUMNS, "successful_files", 0)
        failed = _field(session, SESSION_COLUMNS, "failed_files", 0)
        duration = _field(session, SESSION_COLUMNS, "duration_sec", 0)
        rows.append([session_id, date, profile, total, ok, failed,
                     round(float(duration or 0), 2)])
        for entry in files_by_session.get(session_id, []):
            before = int(_field(entry, FILE_COLUMNS, "file_size_before", 0) or 0)
            after = int(_field(entry, FILE_COLUMNS, "file_size_after", 0) or 0)
            status = _field(entry, FILE_COLUMNS, "status", "")
            error = _field(entry, FILE_COLUMNS, "error", "")
            # Экономия считается только для успешно обработанных
            # файлов: у ошибочных результата нет, и нулевой размер
            # дал бы в отчёте ложное сокращение в 100 процентов.
            saving = (_round_percent(before, after)
                      if status == "SUCCESS" else "")
            rows.append([
                session_id, date,
                _field(entry, FILE_COLUMNS, "source_path", ""),
                _field(entry, FILE_COLUMNS, "result_path", ""),
                before, after if status == "SUCCESS" else "", saving,
                STATUS_LABELS.get(status, status or ""),
                error or "",
            ])
    return rows


def write_csv(path, sessions: Sequence[Sequence], files_by_session: dict) -> int:
    """Записывает отчёт в файл CSV.

    Args:
        path: Путь создаваемого файла.
        sessions: Список сессий из журнала запусков.
        files_by_session: Словарь ``{номер сессии: список файлов}``.

    Returns:
        Количество записанных строк данных.
    """
    rows = build_rows(sessions, files_by_session)
    with open(path, "w", encoding=ENCODING, newline="") as target:
        writer = csv.writer(target, delimiter=DELIMITER)
        writer.writerow(FILE_HEADER)
        writer.writerows(rows)
    return len(rows)


def export_from_manager(manager, path, limit: int = 200) -> int:
    """Собирает отчёт из объекта менеджера базы и сохраняет его.

    Args:
        manager: Экземпляр менеджера базы данных.
        path: Путь создаваемого файла.
        limit: Сколько последних сессий включить в отчёт.

    Returns:
        Количество записанных строк данных.
    """
    sessions = manager.list_sessions(limit)
    files = {row[0]: manager.list_processed_files(row[0]) for row in sessions}
    return write_csv(path, sessions, files)


def default_file_name() -> str:
    """Возвращает имя файла отчёта с датой и временем.

    Returns:
        Имя файла вида ``отчёт_обработки_20261015_143000.csv``.
    """
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"отчёт_обработки_{stamp}.csv"


def main(argv: Iterable[str] | None = None) -> int:
    """Экспортирует журнал последних сессий в файл CSV.

    Args:
        argv: Аргументы командной строки; по умолчанию — из sys.argv.

    Returns:
        Код возврата: 0 при успехе.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.database import DatabaseManager

    args = list(argv if argv is not None else sys.argv[1:])
    target = Path(args[0]) if args else Path(default_file_name())
    manager = DatabaseManager()
    try:
        count = export_from_manager(manager, target)
    finally:
        manager.close()
    print(f"Отчёт сохранён: {target}")
    print(f"Записано строк: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
