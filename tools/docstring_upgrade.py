"""Дополняет docstrings публичных методов app/database.py.

Скрипт используется один раз при подготовке документации Sphinx: он заменяет
однострочные docstrings на полноценные описания в формате Google Style,
которые понимает расширение sphinx.ext.napoleon.
"""
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "app" / "database.py"

REPLACEMENTS = [
    # ---------------------------------------------------------- tbl_formats
    ('''    def list_formats(self) -> List[str]:
        return [row[0] for row''',
     '''    def list_formats(self) -> List[str]:
        """Возвращает отсортированный список доступных целевых форматов.

        Returns:
            Названия форматов, например ``["AVIF", "BMP", "GIF", ...]``.
        """
        return [row[0] for row'''),

    ('''    def create_format(self, name: str) -> None:
        name = name.strip()''',
     '''    def create_format(self, name: str) -> None:
        """Добавляет формат в справочник.

        Args:
            name: Название формата. Повторное добавление игнорируется.

        Raises:
            ValueError: Название пустое или уже существует.
        """
        name = name.strip()'''),

    ('''    def update_format(self, old_name: str, new_name: str) -> None:
        if not new_name.strip()''',
     '''    def update_format(self, old_name: str, new_name: str) -> None:
        """Переименовывает формат в справочнике.

        Args:
            old_name: Текущее название формата.
            new_name: Новое название формата.

        Raises:
            ValueError: Новое название пустое.
        """
        if not new_name.strip()'''),

    ('''    def delete_format(self, name: str) -> None:
        used = self.connection.execute(''',
     '''    def delete_format(self, name: str) -> None:
        """Удаляет формат из справочника.

        Args:
            name: Название удаляемого формата.

        Raises:
            ValueError: Формат используется хотя бы одним сохранённым профилем.
        """
        used = self.connection.execute('''),

    # ---------------------------------------------------------- tbl_presets
    ('''    def create_preset(self, preset: Preset) -> None:
        """Создаёт профиль и связанные настройки водяного знака."""''',
     '''    def create_preset(self, preset: Preset) -> None:
        """Создаёт профиль и связанные настройки водяного знака.

        Args:
            preset: Профиль настроек для сохранения.

        Raises:
            ValueError: Формат профиля отсутствует в справочнике.
            sqlite3.IntegrityError: Профиль с таким именем уже существует.
        """'''),

    ('''    def update_preset(self, preset: Preset, old_name: Optional[str] = None) -> None:
        """Обновляет профиль по исходному имени, включая водяной знак."""''',
     '''    def update_preset(self, preset: Preset, old_name: Optional[str] = None) -> None:
        """Обновляет профиль по исходному имени, включая водяной знак.

        Args:
            preset: Новое состояние профиля.
            old_name: Имя профиля до переименования. Если не задано, используется
                ``preset.name``.

        Raises:
            ValueError: Профиль не найден или формат отсутствует в справочнике.
        """'''),

    ('''    def delete_preset(self, name: str) -> None:
        with self.connection:''',
     '''    def delete_preset(self, name: str) -> None:
        """Удаляет профиль вместе с его настройками водяного знака.

        Args:
            name: Название удаляемого профиля.
        """
        with self.connection:'''),

    ('''    def get_preset(self, name: str) -> Optional[Preset]:
        row = self.connection.execute(''',
     '''    def get_preset(self, name: str) -> Optional[Preset]:
        """Читает профиль вместе с настройками водяного знака.

        Args:
            name: Название профиля.

        Returns:
            Экземпляр :class:`~app.models.Preset` или ``None``, если профиля
            с таким именем нет.
        """
        row = self.connection.execute('''),

    ('''    def list_presets(self) -> List[str]:
        return [row[0] for row''',
     '''    def list_presets(self) -> List[str]:
        """Возвращает отсортированный список названий сохранённых профилей."""
        return [row[0] for row'''),

    # -------------------------------------------------------- tbl_watermarks
    ('''    def get_watermark(self, preset_name: str) -> Optional[dict]:
        row = self.connection.execute(''',
     '''    def get_watermark(self, preset_name: str) -> Optional[dict]:
        """Читает настройки водяного знака профиля.

        Args:
            preset_name: Название профиля.

        Returns:
            Словарь с ключами ``text``, ``path``, ``opacity``, ``position``,
            ``enabled`` или ``None``, если настроек нет.
        """
        row = self.connection.execute('''),

    ('''                       image_path: Optional[str] = None) -> None:
        row = self.connection.execute(''',
     '''                       image_path: Optional[str] = None) -> None:
        """Создаёт или обновляет настройки водяного знака профиля.

        Args:
            preset_name: Название профиля.
            text: Текст водяного знака.
            opacity: Прозрачность от 0 до 100.
            position: Положение на изображении.
            enabled: Включён ли водяной знак.
            image_path: Путь к файлу логотипа (зарезервировано).

        Raises:
            ValueError: Профиль с таким именем не найден.
        """
        row = self.connection.execute('''),

    ('''    def delete_watermark(self, preset_name: str) -> None:
        self.connection.execute(''',
     '''    def delete_watermark(self, preset_name: str) -> None:
        """Удаляет настройки водяного знака указанного профиля.

        Args:
            preset_name: Название профиля.
        """
        self.connection.execute('''),

    # --------------------------------------------------------- журнал сессий
    ('''    def create_session(self, preset: Preset, total_files: int) -> int:
        row = self.connection.execute(''',
     '''    def create_session(self, preset: Preset, total_files: int) -> int:
        """Открывает новую запись в журнале сессий обработки.

        Args:
            preset: Профиль, по которому началась обработка.
            total_files: Количество файлов в очереди.

        Returns:
            Идентификатор созданной сессии.
        """
        row = self.connection.execute('''),

    ('''    def log_processed_file(self, session_id: int, item: QueueItem) -> None:
        before''',
     '''    def log_processed_file(self, session_id: int, item: QueueItem) -> None:
        """Записывает результат обработки одного файла в журнал.

        Размеры файла на диске считываются автоматически, поэтому после
        обработки в журнале остаётся полная картина: сколько файл занимал
        до обработки и сколько занимает результат.

        Args:
            session_id: Идентификатор сессии.
            item: Элемент очереди с заполненным статусом и результатом.
        """
        before'''),

    ('''    def finish_session(self, session_id: int, duration: float, items: list) -> None:
        success''',
     '''    def finish_session(self, session_id: int, duration: float, items: list) -> None:
        """Завершает сессию: фиксирует время, число успехов и ошибок.

        Args:
            session_id: Идентификатор сессии.
            duration: Длительность обработки в секундах.
            items: Список элементов очереди.
        """
        success'''),

    ('''    def list_sessions(self, limit: int = 100) -> list:
        return self.connection.execute(''',
     '''    def list_sessions(self, limit: int = 100) -> list:
        """Возвращает последние сессии обработки, начиная с самой новой.

        Args:
            limit: Максимальное количество записей. Значение приводится
                к диапазону от 1 до 1000.

        Returns:
            Список кортежей: идентификатор, начало, конец, имя пресета,
            всего файлов, успешно, с ошибкой, длительность.
        """
        return self.connection.execute('''),

    ('''    def list_processed_files(self, session_id: int) -> list:
        return self.connection.execute(''',
     '''    def list_processed_files(self, session_id: int) -> list:
        """Возвращает журнал файлов по одной сессии.

        Args:
            session_id: Идентификатор сессии.

        Returns:
            Список кортежей: идентификатор, исходный путь, путь результата,
            размер до, размер после, статус, текст ошибки.
        """
        return self.connection.execute('''),

    ('''                              status: str, error: Optional[str] = None) -> None:
        """Обновляет результат конкретного файла в журнале."""''',
     '''                              status: str, error: Optional[str] = None) -> None:
        """Обновляет результат конкретного файла в журнале.

        Args:
            file_id: Идентификатор записи в журнале.
            output_path: Путь к созданному результату.
            size_after: Размер результата в байтах.
            status: Итоговый статус файла.
            error: Текст ошибки или ``None``.

        Raises:
            ValueError: Размер отрицательный или запись не найдена.
        """'''),

    ('''    def delete_processed_file(self, file_id: int) -> None:
        """Удаляет одну запись файла из журнала."""''',
     '''    def delete_processed_file(self, file_id: int) -> None:
        """Удаляет одну запись файла из журнала.

        Args:
            file_id: Идентификатор записи в журнале.
        """'''),

    ('''    def delete_session(self, session_id: int) -> None:
        with self.connection:''',
     '''    def delete_session(self, session_id: int) -> None:
        """Удаляет сессию вместе со всеми записями о её файлах.

        Args:
            session_id: Идентификатор сессии.
        """
        with self.connection:'''),

    ('''    def close(self) -> None:
        """Закрывает соединение с БД."""''',
     '''    def close(self) -> None:
        """Закрывает соединение с базой данных.

        После вызова объект использовать нельзя: следует создать новый
        экземпляр :class:`DatabaseManager`.
        """'''),
]


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    applied, missed = 0, []
    for old, new in REPLACEMENTS:
        if old not in text:
            missed.append(old.splitlines()[0].strip())
            continue
        text = text.replace(old, new, 1)
        applied += 1
    TARGET.write_text(text, encoding="utf-8")
    print(f"Обновлено docstrings: {applied} из {len(REPLACEMENTS)}")
    if missed:
        print("Не найдены фрагменты:")
        for line in missed:
            print("  -", line)
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main())
