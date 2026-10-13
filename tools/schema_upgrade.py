"""Переводит запросы слоя данных на колонки из технического задания.

Скрипт используется один раз при приведении базы к схеме раздела 4.3.2 ТЗ.
"""
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "app" / "database.py"

REPLACEMENTS = [
    # ---------------------------------------------------------- tbl_formats
    ('"INSERT OR IGNORE INTO tbl_formats(name) VALUES (?)"',
     '"INSERT OR IGNORE INTO tbl_formats(format_name) VALUES (?)"'),
    ('"SELECT name FROM tbl_formats ORDER BY name"',
     '"SELECT format_name FROM tbl_formats ORDER BY format_name"'),
    ('"INSERT INTO tbl_formats(name) VALUES (?)"',
     '"INSERT INTO tbl_formats(format_name) VALUES (?)"'),
    ('"UPDATE tbl_formats SET name=? WHERE name=?"',
     '"UPDATE tbl_formats SET format_name=? WHERE format_name=?"'),
    ('"ON f.id=p.format_id WHERE f.name=?"',
     '"ON f.id=p.format_id WHERE f.format_name=?"'),
    ('"DELETE FROM tbl_formats WHERE name=?"',
     '"DELETE FROM tbl_formats WHERE format_name=?"'),
    # ---------------------------------------------------------- tbl_presets
    ('''                """INSERT INTO tbl_presets
                (preset_name, format_id, width, height, quality, clear_exif, keep_ratio, output_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (preset.name.strip(), format_id, preset.width, preset.height, preset.quality,
                 int(preset.clear_exif), int(preset.keep_ratio), preset.output_dir),''',
     '''                """INSERT INTO tbl_presets
                (preset_name, format_id, resize_mode, resize_value,
                 compression_quality, strip_metadata, keep_ratio, output_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (preset.name.strip(), format_id, preset.resize_mode,
                 preset.resize_value, preset.quality,
                 int(preset.clear_exif), int(preset.keep_ratio), preset.output_dir),'''),
    ('''                """UPDATE tbl_presets SET preset_name=?, format_id=?, width=?, height=?, quality=?,
                clear_exif=?, keep_ratio=?, output_dir=? WHERE id=?""",
                (preset.name.strip(), format_id, preset.width, preset.height, preset.quality,
                 int(preset.clear_exif), int(preset.keep_ratio), preset.output_dir, row[0]),''',
     '''                """UPDATE tbl_presets SET preset_name=?, format_id=?, resize_mode=?,
                resize_value=?, compression_quality=?, strip_metadata=?,
                keep_ratio=?, output_dir=? WHERE id=?""",
                (preset.name.strip(), format_id, preset.resize_mode,
                 preset.resize_value, preset.quality,
                 int(preset.clear_exif), int(preset.keep_ratio), preset.output_dir, row[0]),'''),
    ('"SELECT id FROM tbl_formats WHERE name=?"', '"SELECT id FROM tbl_formats WHERE format_name=?"'),
]

# Блок чтения профиля и сохранения водяного знака переписывается целиком,
# потому что состав колонок изменился.
BLOCK_REPLACEMENTS = [
    ('''            """SELECT p.id, p.preset_name, f.name, p.width, p.height, p.quality,
            p.clear_exif, p.keep_ratio, p.output_dir, w.enabled, w.watermark_text,
            w.position, w.opacity
            FROM tbl_presets p JOIN tbl_formats f ON f.id=p.format_id
            LEFT JOIN tbl_watermarks w ON w.preset_id=p.id WHERE p.preset_name=?"""''',
     '''            """SELECT p.id, p.preset_name, f.format_name, p.resize_mode,
            p.resize_value, p.compression_quality, p.strip_metadata,
            p.keep_ratio, p.output_dir, w.enabled, w.wm_type, w.wm_content,
            w.wm_position, w.wm_opacity, w.wm_size, w.wm_color
            FROM tbl_presets p JOIN tbl_formats f ON f.id=p.format_id
            LEFT JOIN tbl_watermarks w ON w.preset_id=p.id WHERE p.preset_name=?"""'''),
    ('''        return Preset(name=row[1], output_format=row[2], width=row[3], height=row[4],
                      quality=row[5], clear_exif=bool(row[6]), keep_ratio=bool(row[7]),
                      output_dir=row[8] or "", watermark_enabled=bool(row[9]),
                      watermark_text=row[10] or "", watermark_position=row[11] or "bottom-right",
                      watermark_opacity=row[12] if row[12] is not None else 75)''',
     '''        opacity = row[13]
        return Preset(
            name=row[1], output_format=row[2],
            resize_mode=row[3] or "WIDTH", resize_value=row[4] or "1920",
            quality=row[5], clear_exif=bool(row[6]), keep_ratio=bool(row[7]),
            output_dir=row[8] or "", watermark_enabled=bool(row[9]),
            watermark_type=row[10] or "TEXT",
            watermark_text=(row[11] or "") if (row[10] or "TEXT") == "TEXT" else "",
            watermark_image=(row[11] or "") if row[10] == "IMAGE" else "",
            watermark_position=row[12] or "bottom-right",
            watermark_opacity=round(float(opacity) * 100) if opacity is not None else 75,
            watermark_size=row[15] or 4, watermark_color=row[16] or "#FFFFFF")'''),
    ('''            """INSERT INTO tbl_watermarks(preset_id, watermark_text, opacity, position, enabled)
            VALUES (?, ?, ?, ?, ?) ON CONFLICT(preset_id) DO UPDATE SET
            watermark_text=excluded.watermark_text, opacity=excluded.opacity,
            position=excluded.position, enabled=excluded.enabled""",
            (preset_id, preset.watermark_text, preset.watermark_opacity,
             preset.watermark_position, int(preset.watermark_enabled)),''',
     '''            """INSERT INTO tbl_watermarks
            (preset_id, wm_type, wm_content, wm_opacity, wm_position,
             wm_size, wm_color, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(preset_id) DO UPDATE SET
            wm_type=excluded.wm_type, wm_content=excluded.wm_content,
            wm_opacity=excluded.wm_opacity, wm_position=excluded.wm_position,
            wm_size=excluded.wm_size, wm_color=excluded.wm_color,
            enabled=excluded.enabled""",
            (preset_id, preset.watermark_type,
             preset.watermark_image if preset.watermark_type == "IMAGE"
             else preset.watermark_text,
             round(preset.watermark_opacity / 100, 2), preset.watermark_position,
             preset.watermark_size, preset.watermark_color,
             int(preset.watermark_enabled)),'''),
    ('''            "SELECT w.watermark_text, w.watermark_path, w.opacity, w.position, w.enabled "
            "FROM tbl_watermarks w JOIN tbl_presets p ON p.id=w.preset_id WHERE p.preset_name=?",''',
     '''            "SELECT w.wm_type, w.wm_content, w.wm_opacity, w.wm_position, w.enabled "
            "FROM tbl_watermarks w JOIN tbl_presets p ON p.id=w.preset_id "
            "WHERE p.preset_name=?",'''),
    ('return dict(zip(("text", "path", "opacity", "position", "enabled"), row)) if row else None',
     'return dict(zip(("type", "content", "opacity", "position", "enabled"), row)) if row else None'),
    ('''                """INSERT INTO tbl_watermarks(preset_id, watermark_text, watermark_path, opacity, position, enabled)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(preset_id) DO UPDATE SET
                watermark_text=excluded.watermark_text, watermark_path=excluded.watermark_path,
                opacity=excluded.opacity, position=excluded.position, enabled=excluded.enabled""",
                (row[0], text, image_path, opacity, position, int(enabled)),''',
     '''                """INSERT INTO tbl_watermarks
                (preset_id, wm_type, wm_content, wm_opacity, wm_position, enabled)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(preset_id) DO UPDATE SET
                wm_type=excluded.wm_type, wm_content=excluded.wm_content,
                wm_opacity=excluded.wm_opacity, wm_position=excluded.wm_position,
                enabled=excluded.enabled""",
                (row[0], "IMAGE" if image_path else "TEXT",
                 image_path or text, round(opacity / 100, 2), position, int(enabled)),'''),
    ('''            """UPDATE tbl_history_sessions SET finished_at=CURRENT_TIMESTAMP, duration=?,''',
     '''            """UPDATE tbl_history_sessions SET finished_at=CURRENT_TIMESTAMP, duration_sec=?,'''),
    ('''            """SELECT id, started_at, finished_at, preset_name, total_files,''',
     '''            """SELECT id, session_date, finished_at, preset_name, total_files,'''),
    ('''            "SELECT id, source_path, output_path, size_before, size_after, status, error "
            "FROM tbl_processed_files WHERE session_id=? ORDER BY id"''',
     '''            "SELECT id, source_path, result_path, file_size_before, file_size_after, "
            "status, error FROM tbl_processed_files WHERE session_id=? ORDER BY id"'''),
    ('''            """INSERT INTO tbl_processed_files(session_id, source_path, output_path, size_before,
            size_after, status, error) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, str(item.source), str(item.output) if item.output else None,
             before, after, item.status, item.error),''',
     '''            """INSERT INTO tbl_processed_files(session_id, source_path, result_path,
            file_size_before, file_size_after, status, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, str(item.source), str(item.output) if item.output else None,
             before, after, self.STATUS_IN_DB.get(item.status, "ERROR"), item.error),'''),
    ('''                "UPDATE tbl_processed_files SET output_path=?, size_after=?, status=?, error=? WHERE id=?",''',
     '''                "UPDATE tbl_processed_files SET result_path=?, file_size_after=?, "
                "status=?, error=? WHERE id=?",'''),
    ('''            (output_path, size_after, status, error, file_id),''',
     '''            (output_path, size_after, self.STATUS_IN_DB.get(status, status), error, file_id),'''),
]

STATUS_CONST = '''    #: Соответствие статусов интерфейса значениям из технического задания.
    STATUS_IN_DB = {"Готово": "SUCCESS", "Ошибка": "ERROR", "Отменено": "ERROR"}

'''


def main() -> int:
    """Применяет замены в модуле database.py."""
    text = TARGET.read_text(encoding="utf-8")
    applied, missed = 0, []
    for old, new in REPLACEMENTS + BLOCK_REPLACEMENTS:
        if old not in text:
            missed.append(old.strip().splitlines()[0][:70])
            continue
        text = text.replace(old, new, 1)
        applied += 1
    if STATUS_CONST not in text:
        anchor = "    def _create_schema(self) -> None:"
        text = text.replace(anchor, STATUS_CONST + anchor, 1)
    TARGET.write_text(text, encoding="utf-8")
    print(f"Замен выполнено: {applied}")
    if missed:
        print("Не найдены фрагменты:")
        for line in missed:
            print("  -", line)
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main())
