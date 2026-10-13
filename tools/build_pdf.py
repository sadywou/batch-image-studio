"""Сборка PDF-версии документации.

Sphinx 9 вынес построитель ``latexpdf`` в отдельный пакет, поэтому PDF
собирается в два шага: сначала единый HTML-файл сборкой ``singlehtml``,
затем печать в PDF headless-браузером. Такой способ не требует установки
дистрибутива TeX и даёт книгу со всеми разделами и закладками.

Запуск:  python tools/build_pdf.py
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "source"
SINGLE = ROOT / "docs" / "_build" / "single"
PDF = ROOT / "docs" / "_build" / "ImageBatchStudio_документация.pdf"

#: Браузеры, которыми печатается PDF, в порядке предпочтения.
BROWSERS = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


def find_browser() -> Path:
    """Ищет установленный браузер для печати.

    Returns:
        Путь к исполняемому файлу браузера.

    Raises:
        FileNotFoundError: Ни один поддерживаемый браузер не найден.
    """
    for candidate in BROWSERS:
        if candidate.is_file():
            return candidate
    found = shutil.which("chrome") or shutil.which("msedge")
    if found:
        return Path(found)
    raise FileNotFoundError(
        "Не найден Chrome или Edge для печати PDF. Укажите браузер "
        "в списке BROWSERS в начале скрипта.")


def build_single_html(python: Path) -> None:
    """Собирает все разделы документации в один HTML-файл.

    Args:
        python: Исполняемый файл Python проекта.
    """
    subprocess.run(
        [str(python), "-m", "sphinx", "-b", "singlehtml",
         str(SOURCE), str(SINGLE)],
        check=True, cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace",
    )


def print_pdf(browser: Path, source_html: Path, target: Path) -> None:
    """Печатает HTML-страницу в PDF.

    Args:
        browser: Исполняемый файл браузера.
        source_html: HTML-файл с полной документацией.
        target: Путь создаваемого PDF.
    """
    target.unlink(missing_ok=True)
    subprocess.run(
        [str(browser), "--headless=new", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer", f"--print-to-pdf={target}",
         source_html.resolve().as_uri()],
        check=False, cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", timeout=300,
    )
    # Браузер возвращает управление до завершения записи файла.
    for _ in range(30):
        if target.is_file() and target.stat().st_size > 0:
            time.sleep(1.0)
            return
        time.sleep(1.0)
    raise RuntimeError(f"Браузер не создал файл {target}")


def count_pages(python: Path, target: Path) -> int:
    """Подсчитывает страницы готового PDF.

    Args:
        python: Исполняемый файл Python проекта.
        target: Путь к PDF-файлу.

    Returns:
        Количество страниц или 0, если подсчёт недоступен.
    """
    try:
        import pypdfium2
    except ImportError:
        return 0
    return len(pypdfium2.PdfDocument(str(target)))


def main() -> int:
    """Собирает единый HTML и печатает его в PDF."""
    python = Path(sys.executable)
    browser = find_browser()
    print("Браузер:", browser)
    print("Сборка единого HTML...")
    build_single_html(python)
    print("Печать в PDF...")
    print_pdf(browser, SINGLE / "index.html", PDF)
    pages = count_pages(python, PDF)
    print(f"PDF собран: {PDF}")
    print(f"Размер: {PDF.stat().st_size / 1024 / 1024:.2f} МБ, страниц: {pages}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())