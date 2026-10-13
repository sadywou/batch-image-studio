"""Работа с локальной SQLite-базой, профилями и журналом обработки."""
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

from .models import Preset, QueueItem

APP_DATA_DIRNAME = "ImageBatchStudio"


def candidate_data_dirs() -> List[Path]:
    """Перечисляет папки, где приложение может хранить свою базу, по приоритету.

    В обычном режиме работы это папка ``data`` рядом с проектом. В собранном
    исполняемом файле — папка рядом с ``.exe``, затем пользовательская папка
    ``%LOCALAPPDATA%\\ImageBatchStudio`` и, наконец, домашняя папка.

    Returns:
        Список путей в порядке убывания приоритета.
    """
    if getattr(sys, "frozen", False):
        candidates = [Path(sys.executable).resolve().parent / "data"]
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            candidates.append(Path(local_appdata) / APP_DATA_DIRNAME)
        candidates.append(Path.home() / APP_DATA_DIRNAME)
    else:
        candidates = [Path(__file__).resolve().parent.parent / "data"]
    return candidates


def default_data_dir(candidates: Optional[List[Path]] = None) -> Path:
    """Возвращает рабочую папку приложения.

    В собранном .exe файлы программы распаковываются во временный каталог и
    удаляются при закрытии, поэтому база хранится рядом с исполняемым файлом.
    Если рядом нет прав на запись (например, Program Files), используется
    пользовательская папка %LOCALAPPDATA%\\ImageBatchStudio.

    Args:
        candidates: Список папок для проверки. По умолчанию берётся результат
            :func:`candidate_data_dirs`.

    Returns:
        Первая папка, в которой успешно создаётся и проверяется запись.

    Raises:
        RuntimeError: Ни одна из переданных папок не принимает запись.
    """
    last_error: Optional[OSError] = None
    for candidate in (candidates if candidates is not None else candidate_data_dirs()):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-test"
            probe.write_bytes(b"ok")
            probe.unlink()
            return candidate
        except OSError as error:
            last_error = error
    raise RuntimeError(f"Не удалось подготовить рабочую папку: {last_error}")


class DatabaseManager:
    """CRUD для справочников, профилей, водяных знаков и истории обработки.

    Слой доступа к данным изолирован в отдельном классе: он не зависит от
    графического интерфейса и может использоваться в тестах или в других
    программах. Все запросы к базе выполняются через параметры ``?``, поэтому
    пользовательский ввод не влияет на текст SQL.

    При первом обращении создаются пять таблиц: справочник форматов,
    профили настроек, водяные знаки, журнал сессий и журнал обработанных
    файлов. Включаются внешние ключи и режим журналирования WAL.

    Args:
        db_path: Путь к файлу базы. По умолчанию используется ``presets.db``
            в рабочей папке приложения.

    Attributes:
        data_dir: Папка, в которой хранится база.
        db_path: Полный путь к файлу базы данных.
        connection: Открытое соединение :mod:`sqlite3`.

    Raises:
        ValueError: Указано недопустимое имя объекта миграции схемы.
        RuntimeError: Рабочую папку не удалось подготовить.
    """

    # Имена таблиц и столбцов sqlite3 не принимает параметрами, поэтому имена
    # объектов миграции сверяются с белым списком: подставить произвольный
    # идентификатор через _ensure_column невозможно.
    SCHEMA_TABLES = frozenset({
        "tbl_formats", "tbl_presets", "tbl_watermarks",
        "tbl_history_sessions", "tbl_processed_files",
    })
    IDENTIFIER_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")
    DEFINITION_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?: [A-Z0-9]+)*"
                                    r"(?: DEFAULT [^,()]+)?(?: NOT NULL)?$")

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Открывает БД в рабочей папке приложения, независимо текущего каталога."""
        self.data_dir = default_data_dir()
        default_path = self.data_dir / "presets.db"
        self.db_path = Path(db_path).expanduser() if db_path else default_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path, timeout=10)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()
        self._seed_formats()

    def _create_schema(self) -> None:
        """Создаёт таблицы и безопасно расширяет БД предыдущих версий."""
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tbl_formats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS tbl_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preset_name TEXT NOT NULL UNIQUE,
                format_id INTEGER NOT NULL,
                width INTEGER CHECK(width IS NULL OR width > 0),
                height INTEGER CHECK(height IS NULL OR height > 0),
                quality INTEGER NOT NULL DEFAULT 85 CHECK(quality BETWEEN 1 AND 100),
                clear_exif INTEGER NOT NULL DEFAULT 1,
                keep_ratio INTEGER NOT NULL DEFAULT 1,
                output_dir TEXT DEFAULT '',
                FOREIGN KEY(format_id) REFERENCES tbl_formats(id)
            );
            CREATE TABLE IF NOT EXISTS tbl_watermarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preset_id INTEGER NOT NULL UNIQUE,
                watermark_text TEXT DEFAULT '',
                watermark_path TEXT,
                opacity INTEGER NOT NULL DEFAULT 75 CHECK(opacity BETWEEN 0 AND 100),
                position TEXT NOT NULL DEFAULT 'bottom-right',
                enabled INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(preset_id) REFERENCES tbl_presets(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS tbl_history_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                preset_id INTEGER,
                preset_name TEXT,
                total_files INTEGER NOT NULL DEFAULT 0,
                successful_files INTEGER NOT NULL DEFAULT 0,
                failed_files INTEGER NOT NULL DEFAULT 0,
                duration REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(preset_id) REFERENCES tbl_presets(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS tbl_processed_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                source_path TEXT NOT NULL,
                output_path TEXT,
                size_before INTEGER DEFAULT 0,
                size_after INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                error TEXT,
                FOREIGN KEY(session_id) REFERENCES tbl_history_sessions(id) ON DELETE CASCADE
            );
            """
        )
        self._ensure_column("tbl_watermarks", "enabled", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("tbl_history_sessions", "finished_at", "TEXT")
        self._ensure_column("tbl_history_sessions", "preset_name", "TEXT")
        self._ensure_column("tbl_history_sessions", "successful_files", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("tbl_history_sessions", "failed_files", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("tbl_processed_files", "error", "TEXT")
        self.connection.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        """Добавляет отсутствующий столбец, отвергая подозрительные имена.

        Миграция нужна для совместимости с базами предыдущих версий приложения.
        Имена объектов нельзя передать параметрами sqlite3, поэтому перед
        подстановкой в текст ALTER TABLE они проверяются по белому списку.
        """
        if table not in self.SCHEMA_TABLES:
            raise ValueError(f"Неизвестная таблица миграции: {table}")
        if not self.IDENTIFIER_PATTERN.match(table) or not self.IDENTIFIER_PATTERN.match(column):
            raise ValueError(f"Недопустимое имя объекта миграции: {table}.{column}")
        if not self.DEFINITION_PATTERN.match(definition):
            raise ValueError(f"Недопустимое определение столбца: {definition}")
        columns = {row[1] for row in self.connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _seed_formats(self) -> None:
        """Заполняет справочник целевых форматов."""
        self.connection.executemany(
            "INSERT OR IGNORE INTO tbl_formats(name) VALUES (?)",
            [(name,) for name in ("PNG", "JPG", "WebP", "BMP", "TIFF", "GIF", "ICO", "HEIC", "AVIF")],
        )
        self.connection.commit()

    # tbl_formats CRUD
    def list_formats(self) -> List[str]:
        """Возвращает отсортированный список доступных целевых форматов.

        Returns:
            Названия форматов, например ``["AVIF", "BMP", "GIF", ...]``.
        """
        return [row[0] for row in self.connection.execute("SELECT name FROM tbl_formats ORDER BY name")]

    def create_format(self, name: str) -> None:
        """Добавляет формат в справочник.

        Args:
            name: Название формата. Повторное добавление игнорируется.

        Raises:
            ValueError: Название пустое или уже существует.
        """
        name = name.strip()
        if not name:
            raise ValueError("Название формата не может быть пустым")
        self.connection.execute("INSERT INTO tbl_formats(name) VALUES (?)", (name,))
        self.connection.commit()

    def update_format(self, old_name: str, new_name: str) -> None:
        """Переименовывает формат в справочнике.

        Args:
            old_name: Текущее название формата.
            new_name: Новое название формата.

        Raises:
            ValueError: Новое название пустое.
        """
        if not new_name.strip():
            raise ValueError("Название формата не может быть пустым")
        self.connection.execute("UPDATE tbl_formats SET name=? WHERE name=?", (new_name.strip(), old_name))
        self.connection.commit()

    def delete_format(self, name: str) -> None:
        """Удаляет формат из справочника.

        Args:
            name: Название удаляемого формата.

        Raises:
            ValueError: Формат используется хотя бы одним сохранённым профилем.
        """
        used = self.connection.execute(
            "SELECT 1 FROM tbl_presets p JOIN tbl_formats f "
            "ON f.id=p.format_id WHERE f.name=?", (name,)).fetchone()
        if used:
            raise ValueError("Нельзя удалить формат, используемый сохранённым профилем")
        self.connection.execute("DELETE FROM tbl_formats WHERE name=?", (name,))
        self.connection.commit()

    def create_preset(self, preset: Preset) -> None:
        """Создаёт профиль и связанные настройки водяного знака.

        Args:
            preset: Профиль настроек для сохранения.

        Raises:
            ValueError: Формат профиля отсутствует в справочнике.
            sqlite3.IntegrityError: Профиль с таким именем уже существует.
        """
        format_id = self._format_id(preset.output_format)
        with self.connection:
            cursor = self.connection.execute(
                """INSERT INTO tbl_presets
                (preset_name, format_id, width, height, quality, clear_exif, keep_ratio, output_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (preset.name.strip(), format_id, preset.width, preset.height, preset.quality,
                 int(preset.clear_exif), int(preset.keep_ratio), preset.output_dir),
            )
            self._save_watermark(cursor.lastrowid, preset)

    def update_preset(self, preset: Preset, old_name: Optional[str] = None) -> None:
        """Обновляет профиль по исходному имени, включая водяной знак.

        Args:
            preset: Новое состояние профиля.
            old_name: Имя профиля до переименования. Если не задано, используется
                ``preset.name``.

        Raises:
            ValueError: Профиль не найден или формат отсутствует в справочнике.
        """
        format_id = self._format_id(preset.output_format)
        key = old_name or preset.name
        row = self.connection.execute("SELECT id FROM tbl_presets WHERE preset_name=?", (key,)).fetchone()
        if row is None:
            raise ValueError(f"Профиль «{key}» не найден")
        with self.connection:
            self.connection.execute(
                """UPDATE tbl_presets SET preset_name=?, format_id=?, width=?, height=?, quality=?,
                clear_exif=?, keep_ratio=?, output_dir=? WHERE id=?""",
                (preset.name.strip(), format_id, preset.width, preset.height, preset.quality,
                 int(preset.clear_exif), int(preset.keep_ratio), preset.output_dir, row[0]),
            )
            self._save_watermark(row[0], preset)

    def delete_preset(self, name: str) -> None:
        """Удаляет профиль вместе с его настройками водяного знака.

        Args:
            name: Название удаляемого профиля.
        """
        with self.connection:
            self.connection.execute("DELETE FROM tbl_presets WHERE preset_name=?", (name,))

    def get_preset(self, name: str) -> Optional[Preset]:
        """Читает профиль вместе с настройками водяного знака.

        Args:
            name: Название профиля.

        Returns:
            Экземпляр :class:`~app.models.Preset` или ``None``, если профиля
            с таким именем нет.
        """
        row = self.connection.execute(
            """SELECT p.id, p.preset_name, f.name, p.width, p.height, p.quality,
            p.clear_exif, p.keep_ratio, p.output_dir, w.enabled, w.watermark_text,
            w.position, w.opacity
            FROM tbl_presets p JOIN tbl_formats f ON f.id=p.format_id
            LEFT JOIN tbl_watermarks w ON w.preset_id=p.id WHERE p.preset_name=?""", (name,)
        ).fetchone()
        if not row:
            return None
        return Preset(name=row[1], output_format=row[2], width=row[3], height=row[4],
                      quality=row[5], clear_exif=bool(row[6]), keep_ratio=bool(row[7]),
                      output_dir=row[8] or "", watermark_enabled=bool(row[9]),
                      watermark_text=row[10] or "", watermark_position=row[11] or "bottom-right",
                      watermark_opacity=row[12] if row[12] is not None else 75)

    def list_presets(self) -> List[str]:
        """Возвращает отсортированный список названий сохранённых профилей."""
        return [row[0] for row in self.connection.execute("SELECT preset_name FROM tbl_presets ORDER BY preset_name")]

    def _format_id(self, name: str) -> int:
        row = self.connection.execute("SELECT id FROM tbl_formats WHERE name=?", (name,)).fetchone()
        if row is None:
            raise ValueError(f"Неизвестный формат: {name}")
        return row[0]

    def _save_watermark(self, preset_id: int, preset: Preset) -> None:
        self.connection.execute(
            """INSERT INTO tbl_watermarks(preset_id, watermark_text, opacity, position, enabled)
            VALUES (?, ?, ?, ?, ?) ON CONFLICT(preset_id) DO UPDATE SET
            watermark_text=excluded.watermark_text, opacity=excluded.opacity,
            position=excluded.position, enabled=excluded.enabled""",
            (preset_id, preset.watermark_text, preset.watermark_opacity,
             preset.watermark_position, int(preset.watermark_enabled)),
        )

    # tbl_watermarks CRUD (by profile name)
    def get_watermark(self, preset_name: str) -> Optional[dict]:
        """Читает настройки водяного знака профиля.

        Args:
            preset_name: Название профиля.

        Returns:
            Словарь с ключами ``text``, ``path``, ``opacity``, ``position``,
            ``enabled`` или ``None``, если настроек нет.
        """
        row = self.connection.execute(
            "SELECT w.watermark_text, w.watermark_path, w.opacity, w.position, w.enabled "
            "FROM tbl_watermarks w JOIN tbl_presets p ON p.id=w.preset_id WHERE p.preset_name=?",
            (preset_name,),
        ).fetchone()
        return dict(zip(("text", "path", "opacity", "position", "enabled"), row)) if row else None

    def save_watermark(self, preset_name: str, text: str, opacity: int = 75,
                       position: str = "bottom-right", enabled: bool = True,
                       image_path: Optional[str] = None) -> None:
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
        row = self.connection.execute("SELECT id FROM tbl_presets WHERE preset_name=?", (preset_name,)).fetchone()
        if not row:
            raise ValueError(f"Профиль «{preset_name}» не найден")
        with self.connection:
            self.connection.execute(
                """INSERT INTO tbl_watermarks(preset_id, watermark_text, watermark_path, opacity, position, enabled)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(preset_id) DO UPDATE SET
                watermark_text=excluded.watermark_text, watermark_path=excluded.watermark_path,
                opacity=excluded.opacity, position=excluded.position, enabled=excluded.enabled""",
                (row[0], text, image_path, opacity, position, int(enabled)),
            )

    def delete_watermark(self, preset_name: str) -> None:
        """Удаляет настройки водяного знака указанного профиля.

        Args:
            preset_name: Название профиля.
        """
        self.connection.execute(
            "DELETE FROM tbl_watermarks WHERE preset_id="
            "(SELECT id FROM tbl_presets WHERE preset_name=?)", (preset_name,))
        self.connection.commit()

    # Session/file history CRUD
    def create_session(self, preset: Preset, total_files: int) -> int:
        """Открывает новую запись в журнале сессий обработки.

        Args:
            preset: Профиль, по которому началась обработка.
            total_files: Количество файлов в очереди.

        Returns:
            Идентификатор созданной сессии.
        """
        row = self.connection.execute("SELECT id FROM tbl_presets WHERE preset_name=?", (preset.name,)).fetchone()
        cursor = self.connection.execute(
            "INSERT INTO tbl_history_sessions(preset_id, preset_name, total_files) VALUES (?, ?, ?)",
            (row[0] if row else None, preset.name, total_files),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def log_processed_file(self, session_id: int, item: QueueItem) -> None:
        """Записывает результат обработки одного файла в журнал.

        Размеры файла на диске считываются автоматически, поэтому после
        обработки в журнале остаётся полная картина: сколько файл занимал
        до обработки и сколько занимает результат.

        Args:
            session_id: Идентификатор сессии.
            item: Элемент очереди с заполненным статусом и результатом.
        """
        before = item.source.stat().st_size if item.source.exists() else 0
        after = item.output.stat().st_size if item.output and item.output.exists() else 0
        self.connection.execute(
            """INSERT INTO tbl_processed_files(session_id, source_path, output_path, size_before,
            size_after, status, error) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, str(item.source), str(item.output) if item.output else None,
             before, after, item.status, item.error),
        )
        self.connection.commit()

    def finish_session(self, session_id: int, duration: float, items: list) -> None:
        """Завершает сессию: фиксирует время, число успехов и ошибок.

        Args:
            session_id: Идентификатор сессии.
            duration: Длительность обработки в секундах.
            items: Список элементов очереди.
        """
        success = sum(item.status == "Готово" for item in items)
        failed = sum(item.status == "Ошибка" for item in items)
        with self.connection:
            self.connection.execute(
                """UPDATE tbl_history_sessions SET finished_at=CURRENT_TIMESTAMP, duration=?,
                successful_files=?, failed_files=? WHERE id=?""",
                (duration, success, failed, session_id),
            )

    def list_sessions(self, limit: int = 100) -> list:
        """Возвращает последние сессии обработки, начиная с самой новой.

        Args:
            limit: Максимальное количество записей. Значение приводится
                к диапазону от 1 до 1000.

        Returns:
            Список кортежей: идентификатор, начало, конец, имя пресета,
            всего файлов, успешно, с ошибкой, длительность.
        """
        return self.connection.execute(
            """SELECT id, started_at, finished_at, preset_name, total_files,
            successful_files, failed_files, duration FROM tbl_history_sessions
            ORDER BY id DESC LIMIT ?""", (max(1, min(int(limit), 1000)),)
        ).fetchall()

    def list_processed_files(self, session_id: int) -> list:
        """Возвращает журнал файлов по одной сессии.

        Args:
            session_id: Идентификатор сессии.

        Returns:
            Список кортежей: идентификатор, исходный путь, путь результата,
            размер до, размер после, статус, текст ошибки.
        """
        return self.connection.execute(
            "SELECT id, source_path, output_path, size_before, size_after, status, error "
            "FROM tbl_processed_files WHERE session_id=? ORDER BY id", (session_id,)
        ).fetchall()

    def update_processed_file(self, file_id: int, *, output_path: Optional[str],
                              size_after: int, status: str, error: Optional[str] = None) -> None:
        """Обновляет результат конкретного файла в журнале.

        Args:
            file_id: Идентификатор записи в журнале.
            output_path: Путь к созданному результату.
            size_after: Размер результата в байтах.
            status: Итоговый статус файла.
            error: Текст ошибки или ``None``.

        Raises:
            ValueError: Размер отрицательный или запись не найдена.
        """
        if size_after < 0:
            raise ValueError("Размер результата не может быть отрицательным")
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE tbl_processed_files SET output_path=?, size_after=?, status=?, error=? WHERE id=?",
                (output_path, size_after, status, error, file_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Запись файла {file_id} не найдена")

    def delete_processed_file(self, file_id: int) -> None:
        """Удаляет одну запись файла из журнала.

        Args:
            file_id: Идентификатор записи в журнале.
        """
        with self.connection:
            self.connection.execute("DELETE FROM tbl_processed_files WHERE id=?", (file_id,))

    def delete_session(self, session_id: int) -> None:
        """Удаляет сессию вместе со всеми записями о её файлах.

        Args:
            session_id: Идентификатор сессии.
        """
        with self.connection:
            self.connection.execute("DELETE FROM tbl_history_sessions WHERE id=?", (session_id,))

    def close(self) -> None:
        """Закрывает соединение с базой данных.

        После вызова объект использовать нельзя: следует создать новый
        экземпляр :class:`DatabaseManager`.
        """
        self.connection.close()
