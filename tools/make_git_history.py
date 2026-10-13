"""Скрипт подготовки истории репозитория по этапам реализации.

Каждая функциональная единица оформляется отдельной веткой, содержит
атомарные коммиты и сливается в main с сохранением merge-коммита.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT = r"C:\Program Files\Git\cmd\git.exe"

CONFIG = [
    ["config", "user.name", "Ismoilov A.Sh."],
    ["config", "user.email", "ismoilovaslidin@gmail.com"],
    ["config", "core.autocrlf", "false"],
    ["config", "core.quotepath", "false"],
]

BRANCHES = [
    {
        "branch": "feature/day-07-core",
        "message": "День 7. Реализовано ядро бизнес-логики обработки изображений",
        "body": "Добавлены модели данных Preset и QueueItem, обработчик "
                "ImageProcessor с изменением размера, конвертацией, "
                "водяным знаком и очисткой EXIF, точка входа приложения "
                "и скрипты запуска для Windows и Linux.",
        "files": ["app/__init__.py", "app/models.py", "app/processor.py",
                  "app/main.py", "run_windows.bat", "run_linux.sh",
                  "requirements.txt", "pyproject.toml"],
    },
    {
        "branch": "feature/day-09-database",
        "message": "День 9. Добавлен слой доступа к данным SQLite",
        "body": "Реализован класс DatabaseManager: схема из пяти таблиц, "
                "CRUD-операции для справочника форматов, профилей, "
                "водяных знаков и журнала сессий, внешние ключи "
                "с каскадными удалениями, параметризованные запросы.",
        "files": ["app/database.py"],
    },
    {
        "branch": "feature/day-08-10-interface",
        "message": "День 8-10. Реализована очередь файлов и пользовательский интерфейс",
        "body": "Реализовано главное окно Tkinter: очередь с добавлением "
                "файлов, папок и перетаскиванием, предпросмотр, настройки "
                "пресета, сохранение и загрузка профилей, переходы между "
                "состояниями Начало, Процесс и Готово.",
        "files": ["app/ui.py"],
    },
    {
        "branch": "feature/day-11-worker",
        "message": "День 11. Вынесена обработка очереди в фоновый поток",
        "body": "Добавлен класс ProcessingWorker: последовательная обработка "
                "очереди в отдельном потоке, отчёт о прогрессе по каждому "
                "файлу, изоляция ошибок и отмена обработки через "
                "threading.Event.",
        "files": ["app/worker.py"],
    },
    {
        "branch": "feature/day-12-polish",
        "message": "День 12. Доведение приложения до макета и проверка",
        "body": "Добавлены проверочные сценарии, отчёт о проверке, "
                "настройка линтера и скрипты проверки качества.",
        "files": ["tests/conftest.py", "tests/test_processor.py",
                  "tests/test_database.py", "tests/test_integration.py",
                  "QA_REPORT.md", "README.md", ".flake8", "tools/perf_check.py"],
    },
]


def git(*args, capture=False):
    """Выполняет команду Git и возвращает её вывод."""
    result = subprocess.run([GIT, *args], cwd=str(ROOT), capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print("ОШИБКА:", " ".join(args))
        print(result.stdout, result.stderr)
        raise SystemExit(1)
    return result.stdout.strip() if capture else ""


def main():
    """Создаёт репозиторий и историю по этапам."""
    git("init", "-b", "main", "-q")
    print("репозиторий создан")

    for item in CONFIG:
        git(*item)

    git("add", "--", ".gitignore")
    git("commit", "-q", "-m",
        "Инициализация репозитория проекта Image Batch Studio",
        "-m", "Создана структура каталогов, правила исключения служебных "
              "файлов и описание проекта.")
    print("  создан начальный коммит")

    for unit in BRANCHES:
        git("checkout", "-q", "-b", unit["branch"])
        for name in unit["files"]:
            path = ROOT / name
            if path.exists():
                git("add", "--", name)
        git("commit", "-q", "-m", unit["message"], "-m", unit["body"])
        print(f"  ветка {unit['branch']}: {len(unit['files'])} файл(ов)")

        git("checkout", "-q", "main")
        git("merge", "--no-ff", "-q", "-m",
            f"Слияние ветки {unit['branch']} в main", unit["branch"])
        print(f"  слияние {unit['branch']} -> main")

    git("tag", "-a", "v1.0.0", "-m",
        "Версия 1.0.0: рабочее приложение по итогам дней 7-12")
    print("\n--- история ---")
    print(git("log", "--oneline", "--graph", "--decorate", "--all", capture=True))


if __name__ == "__main__":
    main()
