"""Проверки выгрузки отчёта об обработке в CSV.

Отчёт читают в Excel и LibreOffice Calc, поэтому проверяются не только
значения, но и то, как файл будет открыт: разделитель полей, кодировка
с кириллицей и отсутствие выдуманной экономии у ошибочных файлов.
"""
import csv

import pytest

from app import reporting
from app.database import DatabaseManager
from app.models import Preset, QueueItem


@pytest.fixture()
def manager(tmp_path):
    """Менеджер базы на временном файле."""
    db = DatabaseManager(str(tmp_path / "report.db"))
    try:
        yield db
    finally:
        db.close()


def _fill(manager, tmp_path, before: int = 1000, after: int = 250) -> int:
    """Заполняет журнал одной сессией: успешный и ошибочный файлы.

    Args:
        manager: Менеджер базы данных.
        tmp_path: Временный каталог для файлов.
        before: Размер исходного файла в байтах.
        after: Размер результата в байтах.

    Returns:
        Номер созданной сессии.
    """
    source = tmp_path / "src.png"
    source.write_bytes(b"x" * before)
    result = tmp_path / "out.webp"
    result.write_bytes(b"x" * after)
    session_id = manager.create_session(Preset(name="Витрина", output_format="WebP"), 2)
    manager.log_processed_file(session_id, QueueItem(
        source=source, output=result, status="Готово", progress=100))
    manager.log_processed_file(session_id, QueueItem(
        source=source, status="Ошибка", error="повреждён файл"))
    manager.finish_session(session_id, 1.5, [])
    return session_id


def _read(path):
    """Читает CSV-отчёт так, как это делает русский Excel."""
    with open(path, encoding="utf-8-sig", newline="") as source:
        return list(csv.reader(source, delimiter=reporting.DELIMITER))


def test_export_writes_file_and_reports_row_count(manager, tmp_path):
    """Выгрузка создаёт файл и сообщает, сколько строк в него записано."""
    _fill(manager, tmp_path)
    target = tmp_path / "отчёт.csv"
    assert reporting.export_from_manager(manager, target) == 3
    assert target.exists()


def test_separator_is_semicolon_for_russian_excel(manager, tmp_path):
    """Разделитель — точка с запятой: в шапке есть и запятые внутри названий."""
    assert reporting.DELIMITER == ";"
    _fill(manager, tmp_path)
    target = tmp_path / "отчёт.csv"
    reporting.export_from_manager(manager, target)
    header = target.read_text(encoding="utf-8-sig").splitlines()[0]
    assert header.split(";") == list(reporting.FILE_HEADER)
    # Запятая разделила бы строку неправильно: «Размер до, байт» содержит
    # запятую, и столбцы расползлись бы по строке.
    assert len(header.split(",")) < len(reporting.FILE_HEADER)


def test_header_is_human_readable(manager, tmp_path):
    """Шапка отчёта перечисляет понятные столбцы, а не имена полей базы."""
    target = tmp_path / "отчёт.csv"
    _fill(manager, tmp_path)
    reporting.export_from_manager(manager, target)
    assert _read(target)[0] == list(reporting.FILE_HEADER)


def test_cyrillic_survives_encoding(manager, tmp_path):
    """Кириллица читается без потерь: файл сохранён с меткой порядка байтов."""
    _fill(manager, tmp_path)
    target = tmp_path / "отчёт.csv"
    reporting.export_from_manager(manager, target)
    text = target.read_text(encoding="utf-8-sig")
    assert "Ошибка" in text and "Витрина" in text
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")


def test_saving_is_computed_only_for_success(manager, tmp_path):
    """У ошибочного файла экономия пуста, иначе было бы ложное минус сто."""
    _fill(manager, tmp_path)
    target = tmp_path / "отчёт.csv"
    reporting.export_from_manager(manager, target)
    rows = {row[-2]: row for row in _read(target)[1:]}
    assert rows["Готово"][6] == "75"
    assert rows["Ошибка"][6] == ""


def test_error_text_is_carried_into_report(manager, tmp_path):
    """Причина ошибки попадает в отчёт отдельным столбцом."""
    _fill(manager, tmp_path)
    target = tmp_path / "отчёт.csv"
    reporting.export_from_manager(manager, target)
    rows = {row[-2]: row for row in _read(target)[1:]}
    assert rows["Ошибка"][-1] == "повреждён файл"


def test_session_summary_starts_each_group(manager, tmp_path):
    """Перед файлами сессии идёт строка с итогами по сессии."""
    _fill(manager, tmp_path)
    target = tmp_path / "отчёт.csv"
    reporting.export_from_manager(manager, target)
    first = _read(target)[1]
    assert first[0].isdigit()
    assert first[6] == "1.5"
    assert first[2] == "Витрина"


def test_empty_history_produces_header_only(manager, tmp_path):
    """Пустой журнал даёт файл только с шапкой, а не пустой файл."""
    target = tmp_path / "отчёт.csv"
    assert reporting.export_from_manager(manager, target) == 0
    assert _read(target) == [list(reporting.FILE_HEADER)]


@pytest.mark.parametrize("before,after,expected", [
    (0, 100, 0),
    (100, 100, 0),
    (100, 25, 75),
    (100, 125, -25),
    (3, 1, 67),
])
def test_round_percent(before, after, expected):
    """Экономия округляется до целых процентов и может быть отрицательной."""
    assert reporting._round_percent(before, after) == expected


def test_default_file_name_has_stamp_and_extension():
    """Имя файла по умолчанию содержит дату и расширение .csv."""
    name = reporting.default_file_name()
    assert name.startswith("отчёт_обработки_") and name.endswith(".csv")
    stamp = name[len("отчёт_обработки_"):-len(".csv")]
    assert len(stamp) == 15 and stamp[8] == "_"