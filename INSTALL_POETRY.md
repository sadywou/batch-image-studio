# Установка Poetry

Инструкция раздела 8 технического задания. Проект управляется зависимостями
через Poetry, поэтому файлы `pyproject.toml` и `poetry.lock` обязательны
для сборки и запуска.

Проверенная версия Poetry, на которой собран проект: **2.5.1**.

## 1. Быстрая установка через официальный установщик

1. Откройте в браузере `https://python-poetry.org/docs/#installation`.
2. Скопируйте команду установки для PowerShell и выполните её:

```powershell
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content |
    Invoke-Expression
```

3. Закройте и заново откройте окно терминала, чтобы применились изменения
   переменной `PATH`.
4. Проверьте, что Poetry доступна:

```powershell
poetry --version
```

Ожидаемый вывод: `Poetry (version 2.5.1)`.

> Если PowerShell блокирует запуск скриптов, разрешите их для текущего
> пользователя: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 2. Установка через pip (без прав администратора)

Если установщик недоступен, поставьте Poetry в то же окружение, где живёт проект:

```powershell
cd путь\к\проекту
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install poetry
.\.venv\Scripts\python.exe -m poetry --version
```

При таком способе команда `poetry` не появляется в `PATH`, поэтому все
дальнейшие команды вызываются как `.\.venv\Scripts\python.exe -m poetry …`.

## 3. Подготовка проекта

```powershell
cd путь\к\проекту
poetry config virtualenvs.in-project true   # окружение создаётся в .venv
poetry install                               # зависимости и инструменты разработки
```

`poetry install` читает `poetry.lock`, поэтому устанавливаются ровно те
версии, с которыми проект проходил приёмку.

### Только зависимости запуска

Без pytest, flake8, PyInstaller и Sphinx — заметно легче:

```powershell
poetry install --only prod
poetry install --extras codecs   # добавит pillow-heif и pillow-avif-plugin
```

## 4. Запуск программы и проверок

```powershell
poetry run python run_app.py
poetry run pytest
poetry run flake8 app tests tools
poetry run black --check app
```

## 5. Пересборка исполняемого файла

```powershell
poetry run pyinstaller ImageBatchStudio.spec --noconfirm --clean
```

Результат: `dist\BatchImageStudio.exe`.

## 6. Обновление зависимостей

```powershell
poetry update Pillow          # обновить одну библиотеку
poetry add pillow-heif        # добавить новую в основные зависимости
poetry add --group dev mypy  # добавить инструмент разработки
poetry lock                   # пересчитать lock-файл после ручной правки
```

После любого изменения зависимостей `poetry.lock` нужно зафиксировать в Git —
это и есть требование ТЗ о строгой фиксации версий.

## 7. Если что-то пошло не так

| Сообщение | Причина | Что делать |
|---|---|---|
| `poetry: command not found` | Не перезапущен терминал после установки | Закройте и откройте терминал заново |
| `SolverProblemError` | Несовместимые версии зависимостей | `poetry lock -vv` — покажет конфликт |
| `RuntimeError: poetry could not find a pyproject.toml` | Запуск не из папки проекта | `cd` в корень, где лежит `pyproject.toml` |
| `Unable to create virtualenv` | Не хватает прав на запись | `poetry config virtualenvs.in-project true` |
| `externally-managed-environment` при `pip install` | Системный Python защищён от установки пакетов | Ставить только внутрь `.venv`, как в разделе 2 |

Проверить, что окружение здорово:

```powershell
poetry env info
poetry check
poetry check --lock      # lock-файл соответствует pyproject.toml
```