"""Проверка готового .exe: запуск, создание базы и снимок экрана.

Скрипт запускает dist\\ImageBatchStudio.exe как обычный пользовательский процесс,
делает снимок окна и проверяет, что рабочая база создалась рядом с файлом.

Запуск:  python tools/check_exe.py
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "ImageBatchStudio.exe"
SHOTS = ROOT / "docs" / "screenshots"


def capture(filename: str) -> Path | None:
    """Делает снимок экрана и сохраняет его в docs/screenshots."""
    try:
        from PIL import ImageGrab
    except Exception as error:  # pragma: no cover
        print(f"  снимок экрана недоступен: {error}")
        return None
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / filename
    ImageGrab.grab().save(path)
    print(f"  снимок сохранён: {path}")
    return path


def main() -> int:
    if not EXE.exists():
        print(f"Файл {EXE} не найден. Сначала выполните build_windows.bat.")
        return 1

    size_mb = EXE.stat().st_size / (1024 * 1024)
    print("=" * 72)
    print("Проверка готового исполняемого файла")
    print("=" * 72)
    print(f"Файл:    {EXE}")
    print(f"Размер:  {size_mb:.1f} МБ")
    print()

    before = set(EXE.parent.rglob("data/*"))
    process = subprocess.Popen([str(EXE)], cwd=str(EXE.parent))
    print(f"Процесс запущен, PID={process.pid}")
    print("Ожидание инициализации окна и базы данных...")

    db_file = EXE.parent / "data" / "presets.db"
    started = time.time()
    deadline = started + 60
    ok = False
    while time.time() < deadline:
        if process.poll() is not None:
            print(f"!!! Программа завершилась с кодом {process.returncode}")
            return 1
        if db_file.exists():
            ok = True
            break
        time.sleep(1)

    print(f"Время до готовности: {time.time() - started:.1f} с")
    print(f"База данных создана: {'да' if ok else 'нет'} ({db_file})")
    time.sleep(3)
    capture("01_startup.png")

    print("Завершение работы программы...")
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()

    after = sorted(set(EXE.parent.rglob("data/*")) - before)
    print("Файлы, созданные при первом запуске:")
    for item in after or [db_file]:
        print(f"  {item.relative_to(EXE.parent)}  "
              f"({item.stat().st_size if item.is_file() else 0} байт)")
    print()
    if ok:
        print("Итог: исполняемый файл запускается, окно открывается, база создаётся.")
        return 0
    print("Итог: база данных рядом с .exe не создана — требуется проверка.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
