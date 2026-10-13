Справочник API
==============

Этот раздел формируется автоматически расширением ``sphinx.ext.autodoc``
из docstrings исходного кода. Правка описаний в файлах ``app/*.py`` сразу
отражается здесь после пересборки документации.

Модели данных
-------------

.. automodule:: app.models
   :members:
   :undoc-members:
   :show-inheritance:

Обработка изображений
---------------------

.. automodule:: app.processor
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Фоновый поток
--------------

.. automodule:: app.worker
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Доступ к данным
---------------

.. automodule:: app.database
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Точка входа
-----------

.. automodule:: app.main
   :members:
   :undoc-members:

Примеры вызовов
---------------

Обработка одного файла с отчётом о прогрессе
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from pathlib import Path

   from app.models import Preset
   from app.processor import ImageProcessor

   def show_progress(percent: int) -> None:
       print(f"Готово на {percent} %")

   preset = Preset(name="Печать", output_format="JPG", width=1200, height=900,
                   quality=92, output_dir="C:/Печать")

   ImageProcessor().process(Path("C:/Фото DSC_0001.JPG"), preset, show_progress)

Сохранение и чтение профиля
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from app.database import DatabaseManager

   database = DatabaseManager()          # data/presets.db в рабочей папке
   database.create_preset(preset)
   same = database.get_preset("Печать")
   print(same.quality, same.watermark_position)
   database.close()

Журнал сессии
~~~~~~~~~~~~~

.. code-block:: python

   session_id = database.create_session(preset, total_files=2)
   for item in items:
       database.log_processed_file(session_id, item)
   database.finish_session(session_id, duration, items)

   for row in database.list_sessions(limit=10):
       print(row[3], row[4], row[5], row[6], row[7])

Обработка ошибок
----------------

.. code-block:: python

   from app.processor import ImageProcessor

   try:
       result = ImageProcessor().process(source, preset)
   except FileNotFoundError:
       print("Исходный файл не найден")
   except ValueError as error:
       print("Некорректные параметры:", error)
   except RuntimeError as error:
       print("Не удалось обработать файл:", error)
