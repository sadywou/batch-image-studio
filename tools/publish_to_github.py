"""Выкладка репозитория на GitHub.

Скрипт добавляет удалённый адрес и отправляет ветку main вместе
с тегами. Перед первым запуском нужно создать пустой репозиторий
на GitHub без файлов README и .gitignore, иначе возникнет конфликт.

Запуск:
    python tools/publish_to_github.py <ваш_логин_на_github>

Пример:
    python tools/publish_to_github.py student-isp34
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT = Path(r"C:\Program Files\Git\cmd\git.exe")
REPO_NAME = "batch-image-studio"


def run(*arguments: str) -> str:
    """Выполняет команду Git в папке проекта и возвращает вывод.

    Args:
        *arguments: Аргументы команды Git.

    Returns:
        Вывод команды.
    """
    result = subprocess.run([str(GIT), "-C", str(ROOT), *arguments],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    return (result.stdout or "") + (result.stderr or "")


def main() -> int:
    """Настраивает удалённый репозиторий и отправляет ветку с тегами."""
    if len(sys.argv) < 2:
        print("Укажите логин GitHub, например:")
        print("  python tools/publish_to_github.py student-isp34")
        return 1
    login = sys.argv[1].strip().strip("/")
    url = f"https://github.com/{login}/{REPO_NAME}.git"

    existing = run("remote", "get-url", "origin").strip()
    if existing:
        if existing == url:
            print(f"Удалённый адрес уже настроен: {url}")
        else:
            print(f"Обновляю адрес: {existing} -> {url}")
            run("remote", "set-url", "origin", url)
    else:
        run("remote", "add", "origin", url)
        print(f"Добавлен удалённый адрес: {url}")

    print()
    print("Отправляю ветку main...")
    output = run("push", "-u", "origin", "main")
    print(output.strip())
    if "error" in output.lower() and "fatal" not in output.lower():
        print("Возможно, требуется авторизация.")
    if "Everything up-to-date" in output or "branch 'main'" in output:
        print()
        print("Отправляю теги...")
        print(run("push", "origin", "--tags").strip())
        print()
        print("Готово. Репозиторий доступен по адресу:")
        print(f"  https://github.com/{login}/{REPO_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())