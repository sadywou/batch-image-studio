Руководство разработчика
========================

Документ предназначен для инженера, который подхватывает проект:
настраивает окружение, запускает тесты, собирает исполняемый файл
и вносит изменения в код.

1. Настройка среды разработки
-----------------------------

**1.1. Требования**

* Python 3.10 или новее (проверено на 3.14);
* ОС: Windows 10/11, Linux или macOS с графическим окружением;
* Git для контроля версий.

**1.2. Создание окружения**

.. code-block:: bash

   git clone <адрес репозитория>
   cd image_batch_studio
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   source .venv/bin/activate       # Linux/macOS
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   python -m pip install pytest pytest-cov flake8 psutil pyinstaller

Зависимости зафиксированы в ``requirements.txt``:

============================  ==============================================
Пакет                         Назначение
Pillow                        Декодирование, изменение размера, кодирование
tkinterdnd2                   Перетаскивание файлов в окно
pytest                        Автоматические тесты
black                         Форматирование кода
flake8                        Статический анализ
============================  ==============================================

Для разработки дополнительно ставятся ``pytest-cov`` (отчёт о покрытии),
``psutil`` (измерение памяти), ``pyinstaller`` (сборка) и
``sphinx`` (документация).

**1.3. Запуск**

.. code-block:: bash

   python -m app.main        # обычный запуск
   python run_app.py         # запуск в виде скрипта
   run_windows.bat           # тот же запуск, Windows
   ./run_linux.sh            # тот же запуск, Linux/macOS

2. Структура проекта
--------------------

.. code-block:: text

   app/
     __init__.py
     main.py         точка входа: python -m app.main
     models.py       Preset, QueueItem
     processor.py    ImageProcessor — обработка изображений
     database.py     DatabaseManager — SQLite
     worker.py       ProcessingWorker — фоновый поток
     ui.py           MainWindow и виджеты Tkinter
   tests/
     conftest.py              отключает tkinterdnd2 для стабильных тестов
     test_processor.py        40 модульных тестов обработки
     test_database.py         28 модульных тестов слоя данных
     test_integration.py      11 интеграционных тестов
     test_ui.py               30 системных тестов окна
     test_security.py         27 тестов безопасности
     test_deployment.py       7 тестов размещения базы
   tools/
     perf_check.py            измерение производительности и памяти
     profile_stages.py        профилирование этапов обработки
     make_icon.py             генерация иконки
     check_exe.py             проверка готового файла
     make_report.py           сборка отчёта по практике
     screenshot_ui.py         снимки состояний окна
   docs/
     source/                  исходники документации Sphinx
     screenshots/             изображения для отчёта и презентации

3. Принципы работы с кодом
--------------------------

**3.1. Слои не должны пересекаться**

``app/processor.py`` не импортирует ``app/ui.py`` и ``tkinter``:
бизнес-логика должна быть проверяема без графики. Если обработчику
изображений понадобится значение из формы, передавайте объект ``Preset``,
а не ссылку на окно.

**3.2. Обращения к базе — только через параметры**

Запросы выполняются исключительно с плейсхолдерами ``?``:

.. code-block:: python

   self.connection.execute(
       "SELECT * FROM tbl_presets WHERE preset_name=?", (name,))

Сборка SQL конкатенацией запрещена. Единственное исключение — миграция схемы
``_ensure_column``, где имена объектов сверяются с белым списком
``SCHEMA_TABLES`` и регулярными выражениями. За соблюдением правила следит
автоматический тест в ``tests/test_security.py``.

**3.3. Обработка не должна падать на одном файле**

Любое исключение внутри цикла обработки перехватывается, а элемент
получает статус «Ошибка» с текстом сообщения. Продолжается обработка
очереди.

**3.4. Фоновый поток не трогает виджеты**

Поток ``ProcessingWorker`` только публикует события в ``queue.Queue``.
Обновление карточек и индикаторов выполняется в главном потоке
в методе ``_poll_worker_events``.

4. Запуск тестов
----------------

.. code-block:: bash

   pytest -q                                        # все тесты
   pytest tests/test_processor.py -v                 # один модуль
   pytest -k "watermark"                            # выборка по имени
   pytest --cov=app --cov=tests --cov-report=html   # с отчётом
   pytest --cov=app --cov-report=term-missing       # строки без покрытия

Ожидаемый результат: **143 теста пройдены** без предупреждений.

Отдельные группы тестов:

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Команда
     - Назначение
   * - ``pytest tests/test_processor.py``
     - Обработка изображений и граничные случаи
   * - ``pytest tests/test_database.py``
     - CRUD базы, ограничения, каскады
   * - ``pytest tests/test_integration.py``
     - Worker, обработчик и база вместе
   * - ``pytest tests/test_ui.py``
     - Реальное окно, полный пользовательский сценарий
   * - ``pytest tests/test_security.py``
     - SQL-инъекции и статический анализ запросов
   * - ``pytest tests/test_deployment.py``
     - Размещение базы в исходниках и в .exe

.. note::

   ``tests/conftest.py`` отключает ``tkinterdnd2`` перед импортом
   ``app.ui``. Drag-and-Drop зависит от оконного окружения, и без этого
   прогон был бы нестабильным. Такой прогон заодно проверяет ветку отката
   на обычный Tkinter.

5. Сборка исполняемого файла
----------------------------

.. code-block:: bash

   build_windows.bat            # Windows
   sh build_linux.sh           # Linux/macOS

Скрипт выполняет пять шагов: создаёт окружение, ставит зависимости,
запускает ``flake8`` и ``pytest``, создаёт иконку и собирает файл.
Если тесты не пройдены, исполняемый файл не создаётся.

Ручная сборка:

.. code-block:: bash

   python tools/make_icon.py
   pyinstaller ImageBatchStudio.spec --noconfirm --clean

Проверка результата:

.. code-block:: bash

   python tools/check_exe.py      # запуск и создание базы
   python tools/screenshot_exe.py # снимок окна собранного файла

Результат: ``dist/ImageBatchStudio.exe`` размером около 34 МБ.

.. important::

   Спецификация сборки указывает на ``run_app.py``, а не на ``app/main.py``:
   модуль с относительными импортами нельзя выполнять как самостоятельный
   скрипт.

6. Документация
---------------

.. code-block:: bash

   pip install sphinx sphinx-rtd-theme
   sphinx-build -b html docs/source docs/_build/html
   sphinx-build -b latexpdf docs/source docs/_build/pdf

Раздел ``docs/source/api.rst`` формируется из docstrings автоматически.
Поэтому описание нового метода достаточно написать в коде в формате
Google Style (Args, Returns, Raises) и пересобрать документацию.

Пример оформления:

.. code-block:: python

   def process(self, source, preset, progress=None):
       """Обрабатывает один файл и возвращает путь к результату.

       Args:
           source: Путь к исходному изображению.
           preset: Профиль настроек обработки.
           progress: Обработчик прогресса от 0 до 100.

       Returns:
           Путь к созданному файлу.

       Raises:
           FileNotFoundError: Исходный файл не найден.
       """

7. Сборка документации и отчётов
--------------------------------

.. code-block:: bash

   python tools/perf_check.py      # замеры производительности → build/perf
   python tools/profile_stages.py  # профилирование этапов
   python tools/screenshot_ui.py   # снимки состояний окна
   python tools/make_report.py     # docs/Отчёт_день_13-14.docx

8. Проверка качества перед коммитом
-----------------------------------

.. code-block:: bash

   flake8 app tests        # стиль и потенциальные ошибки
   pytest -q               # поведение
   black --check app tests # форматирование (если используется black)

Все три команды должны завершаться без ошибок.

9. Известные ограничения
------------------------

* Анимированные изображения обрабатываются как первый кадр.
* Для ICO создаётся один файл с тремя размерами; увеличение исходника
  не создаётся.
* Текстовый водяной знак поддерживает четыре положения; логотип-файл
  в интерфейсе пока не выбирается.
* Drag-and-Drop зависит от ``tkinterdnd2`` и оконного окружения.
* Тесты интерфейса требуют графического окружения: на сервере без дисплея
  их следует пропускать.
* Замеры производительности сделаны на одной конфигурации; на других
  компьютерах значения будут отличаться.

10. Передача проекта новому разработчику
----------------------------------------

1. Открыть ``README.md`` — краткое описание и команды запуска.
2. Выполнить раздел 1 — окружение за 5 минут.
3. Выполнить ``pytest -q`` — убедиться, что базовая проверка проходит.
4. Прочитать ``docs/_build/html/architecture.rst`` и ``api.rst`` —
   понять слои и интерфейсы.
5. Создать ветку от ``main`` и внести изменения по одному атомарному
   коммиту на задачу.
6. Перед отправкой прогнать ``flake8`` и ``pytest``.
