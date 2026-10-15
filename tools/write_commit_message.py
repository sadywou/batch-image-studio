"""Записывает текст сообщения коммита в файл без BOM.

Скрипт нужен потому, что PowerShell в Windows PowerShell 5 записывает
файл в кодировке UTF-8 с меткой порядка байтов, и она попадает
в первое слово сообщения коммита.

Запуск:  python tools/write_commit_message.py <файл> <текст>
"""
import sys
from pathlib import Path


def main() -> int:
    """Записывает сообщение коммита в переданный или временный файл.

    Args:
        sys.argv: Путь к файлу и текст сообщения; путь по умолчанию —
            ``COMMIT_EDITMSG.txt``.

    Returns:
        Код возврата: 0 при успехе.
    """
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("COMMIT_EDITMSG.txt")
    message = sys.argv[2] if len(sys.argv) > 2 else ""
    target.write_text(message, encoding="utf-8", newline="\n")
    print("сообщение записано:", target, "| символов:", len(message))
    print("первые байты:", target.read_bytes()[:4])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())