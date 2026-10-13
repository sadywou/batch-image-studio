#!/usr/bin/env sh
# ==========================================================================
#  Сборка исполняемого файла Image Batch Studio (Linux/macOS)
#
#  Порядок действий:
#    1. создаётся виртуальное окружение .venv;
#    2. устанавливаются зависимости и PyInstaller;
#    3. прогоняются автотесты и статический анализ;
#    4. создаётся иконка;
#    5. собирается один файл dist/ImageBatchStudio.
# ==========================================================================
set -eu
cd "$(dirname "$0")"

echo
echo "[1/5] Создание виртуального окружения .venv"
if [ ! -x ".venv/bin/python" ]; then
    python3 -m venv .venv
else
    echo "     Окружение уже существует, используется повторно."
fi
PY=".venv/bin/python"

echo "[2/5] Установка зависимостей"
"$PY" -m pip install --upgrade pip -q
"$PY" -m pip install -r requirements.txt -q
"$PY" -m pip install pytest pytest-cov psutil pyinstaller -q

echo "[3/5] Проверки качества: flake8 и pytest"
"$PY" -m flake8 app tests
"$PY" -m pytest -q

echo "[4/5] Создание иконки приложения"
"$PY" tools/make_icon.py

echo "[5/5] Сборка исполняемого файла"
rm -rf build/ImageBatchStudio dist/ImageBatchStudio dist/ImageBatchStudio.spec.bak 2>/dev/null || true
"$PY" -m PyInstaller ImageBatchStudio.spec --noconfirm --clean --log-level WARN

test -f dist/ImageBatchStudio || {
    echo "!!! Исполняемый файл не создан" >&2
    exit 1
}

echo
echo "=========================================================================="
echo " Готово: dist/ImageBatchStudio"
ls -lh dist/ImageBatchStudio
echo " Запуск: dist/ImageBatchStudio"
echo "=========================================================================="