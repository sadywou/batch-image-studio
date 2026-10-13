@echo off
REM ==========================================================================
REM  Сборка исполняемого файла Image Batch Studio (Windows)
REM
REM  Порядок действий:
REM    1. создаётся виртуальное окружение .venv;
REM    2. устанавливаются зависимости и PyInstaller;
REM    3. прогоняются автотесты и статический анализ;
REM    4. создаётся иконка;
REM    5. собирается один файл dist\ImageBatchStudio.exe.
REM ==========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Сборка Image Batch Studio

echo.
echo [1/5] Создание виртуального окружения .venv
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv || goto :error
) else (
    echo      Окружение уже существует, используется повторно.
)

set PY=".venv\Scripts\python.exe"

echo [2/5] Установка зависимостей
%PY% -m pip install --upgrade pip -q || goto :error
%PY% -m pip install -r requirements.txt -q || goto :error
%PY% -m pip install pytest pytest-cov psutil pyinstaller -q || goto :error

echo [3/5] Проверки качества: flake8 и pytest
%PY% -m flake8 app tests || goto :error
%PY% -m pytest -q || goto :error

echo [4/5] Создание иконки приложения
%PY% tools\make_icon.py || goto :error

echo [5/5] Сборка исполняемого файла
if exist "build\ImageBatchStudio" rmdir /s /q "build\ImageBatchStudio"
if exist "dist\ImageBatchStudio.exe" del /q "dist\ImageBatchStudio.exe"
%PY% -m PyInstaller ImageBatchStudio.spec --noconfirm --clean --log-level WARN || goto :error

if not exist "dist\ImageBatchStudio.exe" goto :error

echo.
echo ==========================================================================
echo  Готово: dist\ImageBatchStudio.exe
for %%F in ("dist\ImageBatchStudio.exe") do echo  Размер: %%~zF байт
echo  Запуск: dist\ImageBatchStudio.exe
echo ==========================================================================
endlocal
exit /b 0

:error
echo.
echo !!! Сборка прервана из-за ошибки. Смотрите сообщения выше.
endlocal
exit /b 1