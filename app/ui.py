"""Графический интерфейс пакетного конвертера на Tkinter."""
import queue
import sqlite3
import tkinter as tk
import tkinter.font as tkfont
import tkinter.ttk as ttk
from pathlib import Path
from tkinter import filedialog, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    DND_AVAILABLE = True
except ImportError:
    DND_FILES = None
    TkinterDnD = None
    DND_AVAILABLE = False

from PIL import Image, ImageTk

from .database import DatabaseManager
from .models import Preset, QueueItem
from .processor import ImageProcessor
from .worker import ProcessingWorker


def _resolve_base_window() -> type:
    """Выбирает окно с поддержкой Drag-and-Drop, если библиотека tkdnd загружается.

    Если пакет tkinterdnd2 отсутствует или его сборка несовместима с системным
    Tcl, приложение не прерывает запуск: открывается обычное окно Tkinter,
    а добавление файлов остаётся доступно кнопками и диалогом выбора файлов.
    """
    if not DND_AVAILABLE:
        return tk.Tk
    try:
        probe = TkinterDnD.Tk()
        probe.withdraw()
        probe.destroy()
    except (RuntimeError, tk.TclError, OSError):
        return tk.Tk
    return TkinterDnD.Tk


BaseWindow = _resolve_base_window()

# Состояния интерфейса, повторяющие макеты «Начало», «Процесс» и «Готово».
STATE_IDLE = "Начало — добавление файлов"
STATE_QUEUED = "Файлы в очереди"
STATE_RUNNING = "Процесс — обработка файлов"
STATE_DONE = "Готово — результат обработки"

FINISHED_STATES = ("Готово", "Ошибка", "Отменено")

SUPPORTED_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
    ".gif", ".ico", ".heic", ".avif",
)

COLORS = {
    # Deep Navy palette: сохраняет исходную структуру, меняет только визуальный тон.
    "page": "#080F1D",
    "card": "#0E192B",
    "card_border": "#1D2B40",
    "row_border": "#26364D",
    "row_selected": "#1B3150",
    "text": "#F1F5FC",
    "section": "#A5B3C8",
    "muted": "#8798B0",
    "hint": "#65758D",
    "purple": "#438BFF",
    "purple_hover": "#5A9BFF",
    "purple_border": "#315F9D",
    "grey_border": "#2A3A50",
    "grey_hover": "#1B2A40",
    "track": "#26354B",
    "progress": "#42B9D5",
    "thumb": "#1B2B41",
    "thumb_text": "#8DA6C7",
    "preview": "#101F33",
    "dashed": "#3F78C3",
    "status_ready": "#43D6A0",
    "status_error": "#FF6B78",
}

FONTS = {
    "title": ("Segoe UI", 13, "bold"),
    "section": ("Segoe UI", 8, "bold"),
    "value": ("Segoe UI", 10),
    "small": ("Segoe UI", 8),
    "name": ("Segoe UI", 10, "bold"),
    "status": ("Segoe UI", 9),
    "button": ("Segoe UI", 10, "bold"),
    "button_small": ("Segoe UI", 9),
    "action": ("Segoe UI", 11, "bold"),
    "accent": ("Segoe UI", 9, "bold"),
}

POSITION_LABELS = {
    "bottom-right": "Правый нижний угол",
    "top-right": "Правый верхний угол",
    "bottom-left": "Левый нижний угол",
    "top-left": "Левый верхний угол",
}

STATUS_COLORS = {
    "Готово": COLORS["status_ready"],
    "В очереди": COLORS["section"],
    "Отменено": COLORS["muted"],
    "Ошибка": COLORS["status_error"],
}


def human_size(size: int) -> str:
    """Возвращает размер файла в мегабайтах, как на макете."""
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} КБ"
    return f"{size / (1024 * 1024):.1f} МБ"


THUMB_BOX = (41, 39)
THUMB_CACHE_LIMIT = 1000
_THUMB_CACHE: dict = {}


def load_thumbnail(path, box=THUMB_BOX):
    """Возвращает PhotoImage миниатюры, кэшируя её по пути и времени изменения.

    Карточки списка пересоздаются на каждом шаге прокрутки, поэтому без кэша
    каждое движение колесом декодировало бы фотографии заново.
    """
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    photo = _THUMB_CACHE.get(key)
    if photo is not None:
        return photo
    try:
        with Image.open(path) as opened:
            opened.seek(0)
            image = opened.copy()
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
        elif image.mode != "RGB":
            image = image.convert("RGB")
        image.thumbnail(box, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
    except Exception:
        return None
    _THUMB_CACHE[key] = photo
    while len(_THUMB_CACHE) > THUMB_CACHE_LIMIT:
        _THUMB_CACHE.pop(next(iter(_THUMB_CACHE)))
    return photo


def mix_colors(color_a: str, color_b: str, factor: float) -> str:
    """Смешивает два HEX-цвета: 0.0 — первый, 1.0 — второй."""
    if factor <= 0:
        return color_a
    if factor >= 1:
        return color_b
    first = [int(color_a[index:index + 2], 16) for index in (1, 3, 5)]
    second = [int(color_b[index:index + 2], 16) for index in (1, 3, 5)]
    mixed = (round(a + (b - a) * factor) for a, b in zip(first, second))
    return "#%02X%02X%02X" % tuple(mixed)


def rounded_polygon(canvas, x1, y1, x2, y2, radius, **options):
    """Рисует на Canvas прямоугольник с дуговыми скруглениями углов."""
    import math

    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    if radius <= 0:
        return canvas.create_rectangle(x1, y1, x2, y2, **options)
    corners = (
        (x2 - radius, y1 + radius, -90, 0),
        (x2 - radius, y2 - radius, 0, 90),
        (x1 + radius, y2 - radius, 90, 180),
        (x1 + radius, y1 + radius, 180, 270),
    )
    points = []
    steps = 8
    for cx, cy, start, end in corners:
        for step in range(steps + 1):
            angle = math.radians(start + (end - start) * step / steps)
            points.extend((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return canvas.create_polygon(points, **options)


def draw_folder_icon(canvas, center_x, center_y, color):
    """Рисует иконку папки как на макете."""
    width, height = 13, 11
    left, top = center_x - width / 2, center_y - height / 2
    canvas.create_polygon(
        left, top + 2, left + 6, top, left + 6, top + 2, left + width, top + 2,
        left + width, top + height, left, top + height,
        fill="", outline=color, width=1,
    )


def draw_gradient_bar(canvas, start, end, y, color_a, color_b, thickness=10,
                      segment=14):
    """Рисует полосу с плавным переходом цвета и скруглённым правым краем."""
    canvas.create_line(start, y, end, y, fill=color_b, width=thickness,
                       capstyle="round")
    if end - start <= thickness:
        return
    body_end = end - thickness / 2
    steps = max(2, int((body_end - start) // segment))
    for index in range(steps):
        x1 = start + (body_end - start) * index / steps
        x2 = start + (body_end - start) * (index + 1) / steps
        color = mix_colors(color_a, color_b, index / max(steps - 1, 1))
        canvas.create_line(x1, y, x2, y, fill=color, width=thickness,
                           capstyle="butt")


class RoundedBox(tk.Canvas):
    """Контейнер со скруглённой рамкой для полей ввода и выпадающих списков."""

    def __init__(self, parent, fill, border_color, background, height=44,
                 radius=11, border=1, width=60, focus_border=None):
        """Создаёт рамку и запоминает вид поля."""
        super().__init__(parent, width=width, height=height, bg=background,
                         highlightthickness=0, bd=0)
        self.fill = fill
        self.border_color = border_color
        self.idle_border = border_color
        self.focus_border = focus_border
        self.border = border
        self.radius = radius
        self.child = None
        self.padx = 11
        self.bind("<Configure>", self._redraw)
        self._redraw()

    def embed(self, widget, padx=None):
        """В размещает элемент управления внутрь рамки."""
        self.child = widget
        if padx is not None:
            self.padx = padx
        widget.bind("<FocusIn>", self._focus_on, add="+")
        widget.bind("<FocusOut>", self._focus_off, add="+")
        self._place_child()

    def _focus_on(self, _event=None) -> None:
        """Подсвечивает рамку поля акцентным цветом при получении фокуса."""
        if self.focus_border is None:
            return
        self.border_color = self.focus_border
        self._redraw()

    def _focus_off(self, _event=None) -> None:
        """Возвращает рамке спокойный цвет после потери фокуса."""
        if self.focus_border is None:
            return
        self.border_color = self.idle_border
        self._redraw()

    def _place_child(self) -> None:
        """Располагает вложенный элемент по размеру рамки."""
        if self.child is None:
            return
        width = max(self.winfo_width(), 20)
        height = max(self.winfo_height(), 20)
        self.child.place(x=self.padx, y=self.border,
                         width=max(width - 2 * self.padx, 10),
                         height=max(height - 2 * self.border, 10))

    def _redraw(self, _event=None) -> None:
        """Перерисовывает рамку и позицию вложенного элемента."""
        self.delete("all")
        width = max(self.winfo_width(), 20)
        height = max(self.winfo_height(), 20)
        half = self.border / 2
        rounded_polygon(self, half, half, width - half, height - half,
                        self.radius, fill=self.fill, outline=self.border_color,
                        width=self.border)
        self._place_child()


class RoundedButton(tk.Canvas):
    """Кнопка со скруглёнными углами, полностью отрисованная на Canvas."""

    ANIM_DELAY = 16
    ANIM_STEPS = 9
    RADIUS = 12

    def __init__(self, parent, text, command, fill, foreground, border,
                 hover_fill, hover_foreground, disabled_fill, disabled_foreground,
                 font=None, padx=18, pady=12, icon=None):
        """Создаёт кнопку нужного размера под её текст."""
        self._command = command
        self._fill = fill
        self._foreground = foreground
        self._border = border
        self._hover_fill = hover_fill
        self._hover_foreground = hover_foreground
        self._disabled_fill = disabled_fill
        self._disabled_foreground = disabled_foreground
        self._text = text
        self._icon = icon
        self._padx = padx
        self._enabled = True
        self._hovered = False
        self._pressed = False
        self._hover_mix = 0.0
        self._hover_target = 0.0
        self._anim_id = None
        self._font_spec = font or FONTS["button"]
        self._measure = tkfont.Font(font=self._font_spec)
        width, height = self._required_size()
        super().__init__(parent, width=width, height=height, bg=parent.cget("bg"),
                         highlightthickness=0, bd=0, cursor="hand2", takefocus=0)
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._draw()

    def _required_size(self):
        """Вычисляет размер кнопки по тексту и иконке."""
        text_width = self._measure.measure(self._text)
        icon_width = 20 if self._icon else 0
        width = text_width + icon_width + 2 * self._padx + 4
        height = self._measure.metrics("linespace") + 22
        return int(width), int(height)

    def set_text(self, text) -> None:
        """Меняет надпись и пересчитывает ширину кнопки."""
        self._text = text
        width, height = self._required_size()
        self.configure(width=width, height=height)
        self._draw()

    def set_command(self, command) -> None:
        """Меняет действие, выполняемое при нажатии."""
        self._command = command

    def set_enabled(self, enabled) -> None:
        """Блокирует или разблокирует кнопку."""
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _press(self, _event=None) -> None:
        """Запоминает нажатие для отрисовки активного состояния."""
        if self._enabled:
            self._pressed = True
            self._draw()

    def _release(self, event) -> None:
        """Выполняет команду, если кнопка была отпущена внутри её границ."""
        inside = (0 <= event.x <= self.winfo_width()
                  and 0 <= event.y <= self.winfo_height())
        self._pressed = False
        self._draw()
        if inside and self._enabled and self._command is not None:
            self._command()

    def _enter(self, _event=None) -> None:
        """Включает плавную подсветку при наведении."""
        if not self._enabled:
            return
        self._hovered = True
        self._animate_to(1.0)

    def _leave(self, _event=None) -> None:
        """Выключает подсветку при уходе курсора."""
        self._hovered = False
        self._pressed = False
        self._animate_to(0.0)

    def _animate_to(self, target: float) -> None:
        """Планирует покадровый переход цвета к состоянию наведения."""
        self._hover_target = target
        if self._anim_id is None and self.winfo_exists():
            self._anim_id = self.after(self.ANIM_DELAY, self._animate_step)

    def _animate_step(self) -> None:
        """Следующий кадр плавного перехода кнопки."""
        self._anim_id = None
        step = 1.0 / self.ANIM_STEPS
        if self._hover_mix < self._hover_target:
            self._hover_mix = min(self._hover_target, self._hover_mix + step)
        else:
            self._hover_mix = max(self._hover_target, self._hover_mix - step)
        self._draw()
        if self._hover_mix != self._hover_target:
            self._animate_to(self._hover_target)

    def _on_destroy(self, event) -> None:
        """Останавливает анимацию при удалении кнопки из окна."""
        if event.widget is not self or self._anim_id is None:
            return
        try:
            self.after_cancel(self._anim_id)
        except tk.TclError:
            pass
        self._anim_id = None

    def _draw(self) -> None:
        """Рисует фон, иконку и надпись с учётом состояния кнопки."""
        self.delete("all")
        width = max(self.winfo_width(), 20)
        height = max(self.winfo_height(), 20)
        if not self._enabled:
            fill, foreground = self._disabled_fill, self._disabled_foreground
        else:
            mix = 1.0 if self._pressed else self._hover_mix
            fill = mix_colors(self._fill, self._hover_fill, mix)
            foreground = mix_colors(self._foreground, self._hover_foreground, mix)
        has_border = self._fill != self._border
        if has_border and not self._enabled:
            outline = COLORS["grey_border"]
        else:
            outline = self._border if has_border else ""
        rounded_polygon(self, 1, 1, width - 1, height - 1, self.RADIUS,
                        fill=fill, outline=outline, width=1)
        text_width = self._measure.measure(self._text)
        center_x = width / 2 + (10 if self._icon else 0)
        center_y = height / 2 + (1 if self._pressed else 0)
        self.create_text(center_x, center_y, text=self._text, fill=foreground,
                         font=self._font_spec)
        if self._icon:
            draw_folder_icon(self, center_x - text_width / 2 - 15, center_y,
                             foreground)


class CheckBox(tk.Frame):
    """Флажок в стиле макета: скруглённый квадрат с галочкой."""

    def __init__(self, parent, variable: tk.BooleanVar, text: str) -> None:
        """Создаёт флажок и привязывает его к переменной состояния."""
        super().__init__(parent, bg=COLORS["card"], cursor="hand2")
        self.variable = variable
        self.hovered = False
        self.box = tk.Canvas(self, width=18, height=18, bg=COLORS["card"],
                             bd=0, highlightthickness=0, cursor="hand2")
        self.box.pack(side="left")
        self.label = tk.Label(self, text=text, bg=COLORS["card"], fg=COLORS["text"],
                              font=FONTS["value"], cursor="hand2", anchor="w")
        self.label.pack(side="left", padx=(8, 0))
        for widget in (self, self.box, self.label):
            widget.bind("<Button-1>", self._toggle)
            widget.bind("<Enter>", self._hover_on)
            widget.bind("<Leave>", self._hover_off)
        self.variable.trace_add("write", lambda *_args: self._redraw())
        self._redraw()

    def _toggle(self, _event=None) -> None:
        """Переключает состояние флажка по клику."""
        self.variable.set(not self.variable.get())

    def _hover_on(self, _event=None) -> None:
        """Подсвечивает рамку флажка при наведении курсора."""
        self.hovered = True
        self._redraw()

    def _hover_off(self, _event=None) -> None:
        """Убирает подсветку флажка."""
        self.hovered = False
        self._redraw()

    def _redraw(self) -> None:
        """Перерисовывает квадрат флажка в зависимости от значения."""
        self.box.delete("all")
        if self.variable.get():
            fill = COLORS["purple_hover"] if self.hovered else COLORS["purple"]
            rounded_polygon(self.box, 1, 1, 17, 17, 6, fill=fill,
                            outline=fill)
            self.box.create_line(5, 9, 8, 12, 13, 6, fill="white", width=2,
                                 capstyle="round")
        else:
            fill = COLORS["grey_hover"] if self.hovered else COLORS["page"]
            outline = COLORS["purple_border"] if self.hovered else COLORS["grey_border"]
            rounded_polygon(self.box, 1, 1, 17, 17, 6, fill=fill,
                            outline=outline, width=1)


class QualitySlider(tk.Canvas):
    """Ползунок качества сжатия, отрисованный в стиле макета."""

    def __init__(self, parent, variable: tk.IntVar, on_change) -> None:
        """Создаёт ползунок и привязывает его к переменной качества."""
        super().__init__(parent, height=26, bg=COLORS["card"],
                         highlightthickness=0, cursor="hand2")
        self.variable = variable
        self.on_change = on_change
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Button-1>", self._set_from_pointer)
        self.bind("<B1-Motion>", self._set_from_pointer)
        self._draw()

    def _set_from_pointer(self, event) -> None:
        """Вычисляет значение качества по позиции курсора."""
        width = max(self.winfo_width(), 1)
        value = max(1, min(100, round(max(0, min(width, event.x)) / width * 100)))
        self.variable.set(value)
        self.on_change(value)
        self._draw()

    def _draw(self) -> None:
        """Рисует дорожку, заполненную часть и бегунок."""
        self.delete("all")
        width = max(self.winfo_width(), 100)
        y = 13
        value = max(1, min(100, int(self.variable.get())))
        x = width * value / 100
        self.create_line(0, y, width, y, fill=COLORS["track"], width=10, capstyle="round")
        draw_gradient_bar(self, 0, x, y, COLORS["progress"], COLORS["purple"])
        self.create_oval(x - 9, y - 9, x + 9, y + 9, fill=COLORS["purple"],
                         outline=COLORS["purple"])
        self.create_oval(x - 6, y - 6, x + 6, y + 6, fill=COLORS["text"],
                         outline=COLORS["purple"])

    def redraw(self) -> None:
        """Обновляет положение бегунка при изменении качества извне."""
        self._draw()


class ProgressBar(tk.Canvas):
    """Горизонтальный индикатор выполнения пакетной обработки."""

    def __init__(self, parent) -> None:
        """Создаёт пустой индикатор прогресса."""
        super().__init__(parent, height=12, bg=COLORS["card"],
                         highlightthickness=0)
        self.fraction = 0.0
        self.bind("<Configure>", lambda _event: self._draw())

    def set_fraction(self, fraction: float) -> None:
        """Устанавливает долю выполнения от 0 до 1 и перерисовывает полосу."""
        self.fraction = max(0.0, min(1.0, fraction))
        self._draw()

    def _draw(self) -> None:
        """Рисует серую дорожку и градиентную заполненную часть."""
        self.delete("all")
        width = max(self.winfo_width(), 1)
        y = 6
        self.create_line(0, y, width, y, fill=COLORS["track"], width=10, capstyle="round")
        filled = max(0, min(width, width * self.fraction))
        if filled > 0:
            draw_gradient_bar(self, 0, filled, y, COLORS["progress"],
                              COLORS["purple"])


class QueueRow(tk.Frame):
    """Карточка одного файла очереди: миниатюра, имя, размер, статус и удаление."""

    def __init__(self, parent, on_select, on_remove) -> None:
        """Создаёт карточку файла и сохраняет обработчики действий."""
        super().__init__(parent, bg=COLORS["card"], bd=0, highlightthickness=1,
                         highlightbackground=COLORS["row_border"], height=75)
        self.pack_propagate(False)
        self.bind("<Enter>", self._hover_on)
        self.bind("<Leave>", self._hover_off)
        self._source = None
        self._size_text = ""
        self._selected = False
        self._hovered = False
        self._thumb_photo = None
        self.on_select = on_select
        self.on_remove = on_remove

        self.thumb = tk.Frame(self, bg=COLORS["thumb"], width=51, height=49, bd=0)
        self.thumb.pack(side="left", padx=(15, 0), pady=13)
        self.thumb.pack_propagate(False)
        self.thumb_label = tk.Label(self.thumb, text="IMG", bg=COLORS["thumb"],
                                    fg=COLORS["thumb_text"], font=FONTS["small"])
        self.thumb_label.pack(expand=True)

        self.info = tk.Frame(self, bg=COLORS["card"])
        self.info.pack(side="left", fill="both", expand=True, padx=15)
        self.name = tk.Label(self.info, text="", bg=COLORS["card"], fg=COLORS["text"],
                             font=FONTS["name"], anchor="w")
        self.name.pack(fill="x")
        self.size = tk.Label(self.info, text="", bg=COLORS["card"], fg=COLORS["muted"],
                             font=FONTS["small"], anchor="w")
        self.size.pack(fill="x", pady=(3, 0))

        self.remove = tk.Label(self, text="×", bg=COLORS["card"], fg=COLORS["muted"],
                               font=("Segoe UI", 12), width=3, cursor="hand2")
        self.remove.pack(side="right", fill="y", padx=(0, 6))

        self.status = tk.Label(self, text="", bg=COLORS["card"], fg=COLORS["section"],
                               font=FONTS["status"], width=18, anchor="center")
        self.status.pack(side="right", fill="y")

        self.bind("<Button-1>", self._select)
        self.info.bind("<Button-1>", self._select)
        self.name.bind("<Button-1>", self._select)
        self.size.bind("<Button-1>", self._select)
        self.remove.bind("<Button-1>", self._remove_click)

    def _select(self, _event=None) -> None:
        """Выбирает файл для предпросмотра."""
        self.on_select(self)

    def _remove_click(self, _event=None) -> None:
        """Удаляет файл из очереди по крестику."""
        self.on_remove(self)

    def update_item(self, item: QueueItem, selected: bool) -> None:
        """Заполняет карточку данными элемента очереди."""
        if self._source != item.source:
            self._source = item.source
            try:
                self._size_text = human_size(item.source.stat().st_size)
            except OSError:
                self._size_text = "—"
            self._load_thumb(item.source)
        self.name.config(text=item.source.name)
        self.size.config(text=self._size_text)
        self.status.config(text=self._status_text(item), fg=self._status_color(item))
        self._selected = selected
        self._apply_style()

    def _load_thumb(self, path) -> None:
        """Показывает миниатюру файла вместо текстовой заглушки."""
        photo = load_thumbnail(path)
        if photo is None:
            self._thumb_photo = None
            self.thumb_label.config(image="", text="IMG")
            return
        self._thumb_photo = photo
        self.thumb_label.config(image=photo, text="")

    def _apply_style(self) -> None:
        """Обновляет цвета карточки с учётом выделения и наведения."""
        if self._selected:
            background, border = COLORS["row_selected"], COLORS["purple"]
        elif self._hovered:
            background, border = COLORS["grey_hover"], COLORS["purple_border"]
        else:
            background, border = COLORS["card"], COLORS["row_border"]
        for widget in (self, self.info, self.name, self.size, self.status,
                       self.remove):
            widget.configure(bg=background)
        self.configure(highlightbackground=border)

    @staticmethod
    def _status_text(item: QueueItem) -> str:
        """Возвращает подпись статуса с процентом для обрабатываемого файла."""
        if item.status == "В обработке":
            return f"В обработке ({item.progress}%)"
        return item.status

    @staticmethod
    def _status_color(item: QueueItem) -> str:
        """Возвращает цвет статуса в соответствии с макетом."""
        if item.status == "В обработке":
            return COLORS["progress"]
        return STATUS_COLORS.get(item.status, COLORS["section"])

    def _hover_on(self, _event=None) -> None:
        """Мягко подсвечивает карточку при наведении курсора."""
        self._hovered = True
        self._apply_style()

    def _hover_off(self, _event=None) -> None:
        """Возвращает карточку к базовому цвету."""
        self._hovered = False
        self._apply_style()


class QueueList(tk.Frame):
    """Прокручиваемый список карточек с ленительным созданием виджетов."""

    ROW_HEIGHT = 75
    ROW_GAP = 10

    def __init__(self, parent, on_select, on_remove) -> None:
        """Создаёт полосу прокрутки и область со списком карточек."""
        super().__init__(parent, bg=COLORS["card"])
        self.on_select = on_select
        self.on_remove = on_remove
        self.items: list = []
        self.selected = -1
        self._rows: dict = {}
        self._windows: dict = {}
        self._offset = 0.0
        self._content_height = 0.0
        self._bar_hover = False

        self.canvas = tk.Canvas(self, bg=COLORS["card"], bd=0, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar = tk.Canvas(self, width=10, bg=COLORS["card"], bd=0, highlightthickness=0)
        self.bar.pack(side="right", fill="y")

        self.canvas.bind("<Configure>", self.refresh)
        self.bar.bind("<Configure>", lambda _event: self._draw_bar())
        self.bar.bind("<Button-1>", self._bar_press)
        self.bar.bind("<B1-Motion>", self._bar_drag)
        self.bar.bind("<Enter>", self._bar_enter)
        self.bar.bind("<Leave>", self._bar_leave)
        self.bind_all("<MouseWheel>", self._on_wheel)

    def set_items(self, items: list, selected: int = -1) -> None:
        """Заменяет содержимое списка и сбрасывает прокрутку."""
        self.items = items
        self.selected = selected
        self._offset = 0.0
        self.refresh()

    def set_selected(self, index: int) -> None:
        """Отмечает выбранный файл и прокручивает список к нему."""
        self.selected = index
        self.refresh()

    def update_row(self, index: int) -> None:
        """Обновляет только одну видимую карточку."""
        row = self._rows.get(index)
        if row is not None and index < len(self.items):
            row.update_item(self.items[index], index == self.selected)

    def row_at(self, row: QueueRow) -> int:
        """Возвращает индекс элемента очереди по карточке."""
        for index, widget in self._rows.items():
            if widget is row:
                return index
        return -1

    def clear_rows(self) -> None:
        """Удаляет все созданные карточки списка."""
        for row in self._rows.values():
            row.destroy()
        self._rows.clear()
        self._windows.clear()

    def scroll(self, delta: float) -> None:
        """Прокручивает список на указанное количество пикселей."""
        limit = max(0.0, self._content_height - max(self.canvas.winfo_height(), 1))
        target = max(0.0, min(limit, self._offset + delta))
        if target != self._offset:
            self._offset = target
            self.refresh()

    def refresh(self, _event=None) -> None:
        """Пересоздаёт только видимые карточки по текущей прокрутке."""
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        total = len(self.items)
        step = self.ROW_HEIGHT + self.ROW_GAP
        self._content_height = total * step
        self._offset = max(0.0, min(self._offset, max(0.0, self._content_height - height)))
        first = int(self._offset // step)
        last = min(total, first + int(height // step) + 2)
        for index in list(self._rows):
            if index < first or index >= last:
                self._rows.pop(index).destroy()
                self._windows.pop(index, None)
        for index in range(first, last):
            # Карточка сдвигается на величину прокрутки, иначе список «уезжает».
            y = index * step - self._offset
            row = self._rows.get(index)
            if row is None:
                row = QueueRow(self.canvas, self.on_select, self.on_remove)
                self._windows[index] = self.canvas.create_window(
                    0, y, window=row, anchor="nw", width=max(width - 14, 1),
                    height=self.ROW_HEIGHT)
                self._rows[index] = row
            elif self._windows.get(index) is not None:
                self.canvas.itemconfigure(self._windows[index], width=max(width - 14, 1))
                self.canvas.coords(self._windows[index], 0, y)
            row.update_item(self.items[index], index == self.selected)
        self._draw_bar()

    def _draw_bar(self) -> None:
        """Рисует узкую полосу прокрутки, если список не помещается целиком."""
        self.bar.delete("all")
        height = self.bar.winfo_height()
        if height <= 1 or self._content_height <= height:
            return
        span = self._content_height - height
        thumb_height = max(30, int(height * height / self._content_height))
        top = int((height - thumb_height) * (self._offset / span))
        self.bar.create_line(5, 6, 5, height - 6, fill=COLORS["track"],
                             width=6, capstyle="round")
        color = COLORS["muted"] if self._bar_hover else COLORS["grey_border"]
        self.bar.create_line(5, top + 5, 5, top + thumb_height - 5, fill=color,
                             width=6, capstyle="round")

    def _bar_enter(self, _event=None) -> None:
        """Подсвечивает ползунок прокрутки при наведении курсора."""
        self._bar_hover = True
        self._draw_bar()

    def _bar_leave(self, _event=None) -> None:
        """Убирает подсветку ползунка прокрутки."""
        self._bar_hover = False
        self._draw_bar()

    def _offset_from_bar(self, y: int) -> float:
        """Переводит координату курсора на полосе в смещение списка."""
        height = max(self.bar.winfo_height(), 1)
        view = max(self.canvas.winfo_height(), 1)
        span = max(1.0, self._content_height - view)
        thumb_height = max(30, int(height * height / max(self._content_height, 1)))
        free = max(1, height - thumb_height)
        ratio = max(0.0, min(1.0, (y - thumb_height / 2) / free))
        return ratio * span

    def _bar_press(self, event) -> None:
        """Начинает прокрутку перетаскиванием полосы."""
        self._offset = self._offset_from_bar(event.y)
        self.refresh()

    def _bar_drag(self, event) -> None:
        """Продолжает прокрутку перетаскиванием полосы."""
        self._offset = self._offset_from_bar(event.y)
        self.refresh()

    def _on_wheel(self, event) -> None:
        """Прокручивает список колесом мыши, когда курсор находится над ним."""
        if not self.winfo_ismapped():
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        current = widget
        while current is not None and current is not self:
            current = getattr(current, "master", None)
        if current is not self:
            return
        self.scroll(-event.delta / 120 * 48)


class Preview(tk.Frame):
    """Предпросмотр выбранного изображения с увеличенным режимом До/После."""

    WIDTH = 372
    HEIGHT = 210
    THUMB = (360, 196)

    def __init__(self, parent) -> None:
        super().__init__(parent, bg=COLORS["card"])
        tk.Label(self, text="Сравнение до и после", bg=COLORS["card"],
                 fg=COLORS["section"], font=FONTS["small"], anchor="w").pack(
                     fill="x", pady=(0, 9))
        self.container = tk.Frame(self, bg=COLORS["card"])
        self.container.pack(anchor="w")
        self.before = self._panel("До обработки")
        self.after = self._panel("После обработки", accent=True)
        self.before[0].pack(side="left", padx=(0, 10))
        self.after[0].pack(side="left")
        self._photos = {}

    def _panel(self, title, accent=False):
        """Создаёт одну увеличенную панель сравнения с рамкой и подписью."""
        frame = tk.Frame(self.container, bg=COLORS["preview"], padx=10, pady=9,
                         highlightthickness=1,
                         highlightbackground=COLORS["card_border"])
        caption_color = COLORS["status_ready"] if accent else COLORS["muted"]
        tk.Label(frame, text=title, bg=COLORS["preview"], fg=caption_color,
                 font=FONTS["accent"], anchor="w").pack(fill="x", pady=(0, 7))
        box = tk.Frame(frame, bg=COLORS["page"], width=self.WIDTH,
                       height=self.HEIGHT, highlightthickness=1,
                       highlightbackground=COLORS["card_border"])
        box.pack()
        box.pack_propagate(False)
        label = tk.Label(box, text="Нет изображения", bg=COLORS["page"],
                         fg=COLORS["hint"], font=FONTS["small"])
        label.place(relx=0.5, rely=0.5, anchor="center")
        return frame, label

    def _show(self, label, key, path):
        self._photos[key] = None
        if not path:
            label.config(image="", text="Нет изображения")
            return
        try:
            with Image.open(path) as opened:
                image = opened.convert("RGB")
            image.thumbnail(self.THUMB, Image.Resampling.LANCZOS)
            self._photos[key] = ImageTk.PhotoImage(image)
            label.config(image=self._photos[key], text="")
        except Exception:
            label.config(image="", text="Нет изображения")

    def show(self, path: Path, result: Path = None) -> None:
        self._show(self.before[1], "before", path)
        self._show(self.after[1], "after", result)

    def reset(self) -> None:
        """Возвращает обе панели к заглушке «Нет изображения»."""
        self.show(None, None)


class MainWindow(BaseWindow):
    """Главное окно приложения, повторяющее макеты трёх состояний."""

    _drop_hover = False

    def __init__(self) -> None:
        """Создаёт окно и инициализирует состояние приложения."""
        super().__init__()
        self.title("Batch Image Processor")
        self.minsize(1300, 780)
        self.configure(bg=COLORS["page"])

        self.database = DatabaseManager()
        self.processor = ImageProcessor()
        self.items: list = []
        self.selected_index = -1
        self.state = STATE_IDLE
        self.worker = None
        self.active_session_id = None
        self._worker_events = queue.Queue()
        self._event_poll_id = None
        self.queue_controls = []

        self.format_var = tk.StringVar(value="WebP")
        self.width_var = tk.StringVar(value="1920")
        self.height_var = tk.StringVar(value="1080")
        self.quality_var = tk.IntVar(value=80)
        self.exif_var = tk.BooleanVar(value=True)
        self.ratio_var = tk.BooleanVar(value=True)
        self.watermark_var = tk.BooleanVar(value=True)
        self.watermark_text_var = tk.StringVar(value="Мой логотип")
        self.watermark_position_var = tk.StringVar(value=POSITION_LABELS["bottom-right"])
        self.output_var = tk.StringVar(value="C:\\Processed")
        self.preset_var = tk.StringVar(value="Текущие настройки")

        # Миниатюры кэшируются объектами ImageTk.PhotoImage, которые привязаны к
        # текущему интерпретатору Tk. При создании нового окна старые ссылки
        # недействительны, поэтому кэш очищается.
        _THUMB_CACHE.clear()

        self._build_ui()
        self._load_presets()
        self._sync_combo(self.position_combo, tuple(POSITION_LABELS.values()))
        self._set_state(STATE_IDLE)
        self.center_window()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def center_window(self) -> None:
        """Открывает окно по центру экрана в пропорциях макета."""
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(1371, screen_w - 80)
        height = min(830, screen_h - 120)
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

    @staticmethod
    def _sync_combo(combo, values) -> None:
        """Показывает в выпадающем списке значение переменной, а не пустую строку."""
        try:
            index = list(values).index(combo.get())
        except ValueError:
            combo.set(values[0])
            index = 0
        combo.current(index)

    # ------------------------------------------------------------------ каркас

    def _build_ui(self) -> None:
        """Собирает две карточки макета: очередь файлов и настройки пресета."""
        self._setup_styles()
        root = tk.Frame(self, bg=COLORS["page"])
        root.pack(fill="both", expand=True, padx=21, pady=21)
        root.grid_columnconfigure(0, weight=0)
        root.grid_columnconfigure(1, weight=1, minsize=440)
        root.grid_rowconfigure(0, weight=1)

        self._build_queue_card(root).grid(row=0, column=0, sticky="nsew", padx=(0, 11))
        self._build_settings_card(root).grid(row=0, column=1, sticky="nsew")

    def _card(self, parent):
        """Создаёт карточку с тонкой светло-фиолетовой рамкой."""
        border = tk.Frame(parent, bg=COLORS["card_border"], bd=0)
        card = tk.Frame(border, bg=COLORS["card"], bd=0)
        card.pack(fill="both", expand=True, padx=1, pady=1)
        self._register_card_drop(border)
        return border, card

    def _register_card_drop(self, widget: tk.Misc) -> None:
        """Разрешает принимать перетаскиваемые файлы в любую из карточек."""
        if DND_AVAILABLE:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)

    # ------------------------------------------------------ левая карточка

    def _build_queue_card(self, parent) -> tk.Frame:
        """Строит карточку очереди файлов с кнопками и рабочей областью."""
        border, card = self._card(parent)
        inner = tk.Frame(card, bg=COLORS["card"])
        inner.pack(fill="both", expand=True, padx=25, pady=25)

        tk.Label(inner, text="Очередь файлов для обработки", bg=COLORS["card"],
                 fg=COLORS["text"], font=FONTS["title"], anchor="w").pack(
                     fill="x", pady=(0, 16))

        toolbar = tk.Frame(inner, bg=COLORS["card"])
        toolbar.pack(fill="x", pady=(0, 20))

        add = self._button(toolbar, "+  Добавить файлы", self.add_files, primary=True,
                           side="left", padx=(0, 14))
        folder = self._button(toolbar, "Добавить папку", self.add_folder, accent=True,
                              font=FONTS["button"], icon=True, side="left", padx=(0, 14))
        clear = self._button(toolbar, "Очистить", self.clear_queue, side="left")
        self.queue_controls = [add, folder, clear]

        self.drop_zone = self._build_drop_zone(inner)
        self.queue_list = QueueList(inner, self._on_row_select, self._on_row_remove)
        self._register_card_drop(self.queue_list.canvas)
        self.preview = Preview(inner)
        self.footer = tk.Label(inner, text="После добавления файлов здесь появится очередь и предпросмотр",
                               bg=COLORS["card"], fg=COLORS["muted"],
                               font=FONTS["small"], anchor="w")
        border.configure(width=862)
        border.propagate(False)
        return border

    def _build_drop_zone(self, parent) -> tk.Canvas:
        """Создаёт пунктирную зону Drag-and-Drop из макета «Начало»."""
        canvas = tk.Canvas(parent, bg=COLORS["card"], bd=0, highlightthickness=0,
                           height=430, cursor="hand2")
        canvas.bind("<Configure>", lambda _event: self._draw_drop_zone())
        canvas.bind("<Button-1>", lambda _event: self.add_files())
        canvas.bind("<Enter>", self._drop_enter)
        canvas.bind("<Leave>", self._drop_leave)
        self._register_card_drop(canvas)
        return canvas

    def _drop_enter(self, _event=None) -> None:
        """Подсвечивает стартовую зону при наведении курсора."""
        self._drop_hover = True
        self._draw_drop_zone()

    def _drop_leave(self, _event=None) -> None:
        """Убирает подсветку стартовой зоны."""
        self._drop_hover = False
        self._draw_drop_zone()

    def _draw_drop_zone(self) -> None:
        """Рисует скруглённую пунктирную рамку, иконку и кнопку добавления."""
        canvas = self.drop_zone
        if canvas is None:
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 100)
        height = max(canvas.winfo_height(), 100)
        border = COLORS["purple"] if self._drop_hover else COLORS["dashed"]
        rounded_polygon(canvas, 2, 2, width - 2, height - 2, 18,
                        fill=COLORS["preview"], outline="")
        rounded_polygon(canvas, 2, 2, width - 2, height - 2, 18, fill="",
                        outline=border, width=2, dash=(8, 8))
        cx, cy = width / 2, height * 0.48
        icon_y = cy - 78
        canvas.create_line(cx, icon_y - 14, cx, icon_y + 6, fill=border, width=3,
                           capstyle="round")
        canvas.create_line(cx - 8, icon_y - 6, cx, icon_y - 14, cx + 8, icon_y - 6,
                           fill=border, width=3, capstyle="round", joinstyle="round")
        canvas.create_line(cx - 15, icon_y + 15, cx + 15, icon_y + 15,
                           fill=border, width=3, capstyle="round")
        canvas.create_text(cx, cy - 30, text="Перетащите изображения сюда",
                           fill=COLORS["text"], font=FONTS["title"])
        canvas.create_text(cx, cy + 2, text="или добавьте отдельные файлы / целую папку",
                           fill=COLORS["muted"], font=FONTS["value"])
        button_fill = COLORS["purple_hover"] if self._drop_hover else COLORS["purple"]
        rounded_polygon(canvas, cx - 120, cy + 35, cx + 120, cy + 85, 13,
                        fill=button_fill, outline="")
        canvas.create_text(cx, cy + 60, text="+  Добавить файлы", fill="white",
                           font=FONTS["button"])
        canvas.create_text(cx, cy + 104,
                           text="PNG · JPG · WebP · TIFF · GIF · ICO и другие",
                           fill=COLORS["hint"], font=FONTS["small"])

    # ------------------------------------------------------ правая карточка

    def _build_settings_card(self, parent) -> tk.Frame:
        """Строит карточку настроек пресета по макету."""
        border, card = self._card(parent)
        inner = tk.Frame(card, bg=COLORS["card"])
        inner.pack(fill="both", expand=True, padx=24, pady=24)

        header = tk.Frame(inner, bg=COLORS["card"])
        header.pack(fill="x", pady=(0, 16))
        tk.Label(header, text="Настройки пресета", bg=COLORS["card"],
                 fg=COLORS["text"], font=FONTS["title"], anchor="w").pack(side="left")
        # Ориентир высотой бывшей кнопки темы: блоки настроек остаются на своих местах.
        spacer_height = tkfont.Font(font=FONTS["button_small"]).metrics("linespace") + 22
        tk.Frame(header, bg=COLORS["card"], width=1, height=spacer_height).pack(
            side="right")

        self._section_label(inner, "ЦЕЛЕВОЙ ФОРМАТ")
        self._combo(inner, self.format_var,
                    ("PNG", "JPG", "WebP", "BMP", "TIFF", "GIF", "ICO", "HEIC", "AVIF"),
                    pady=(8, 5))
        self._hint(inner, "PNG · JPG · WebP · BMP · TIFF · GIF · ICO · HEIC · AVIF")

        self._section_label(inner, "РАЗМЕР ИЗОБРАЖЕНИЯ", pady=(14, 8))
        size = tk.Frame(inner, bg=COLORS["card"])
        size.pack(fill="x")
        self._entry(size, self.width_var).pack(side="left", fill="x", expand=True)
        tk.Frame(size, width=28, bg=COLORS["card"]).pack(side="left")
        self._entry(size, self.height_var).pack(side="left", fill="x", expand=True)

        self.ratio_check = CheckBox(inner, self.ratio_var, "Сохранять пропорции")
        self.ratio_check.pack(anchor="w", pady=(8, 14))

        self.quality_label = self._section_label(inner, "КАЧЕСТВО СЖАТИЯ: 80%")
        self.slider = QualitySlider(inner, self.quality_var, self._on_quality_change)
        self.slider.pack(fill="x", pady=(6, 10))

        self.exif_check = CheckBox(inner, self.exif_var,
                                   "Удалить скрытые EXIF метаданные")
        self.exif_check.pack(anchor="w")

        self._section_label(inner, "ВОДЯНОЙ ЗНАК", pady=(14, 6))
        self.watermark_check = CheckBox(inner, self.watermark_var,
                                        "Добавить водяной знак")
        self.watermark_check.pack(anchor="w", pady=(0, 9))

        watermark = tk.Frame(inner, bg=COLORS["card"])
        watermark.pack(fill="x")
        self._entry(watermark, self.watermark_text_var).pack(
            side="left", fill="x", expand=True)
        tk.Frame(watermark, width=13, bg=COLORS["card"]).pack(side="left")
        self.position_combo = self._combo(watermark, self.watermark_position_var,
                                          tuple(POSITION_LABELS.values()), width=17,
                                          side="right", expand=True)
        self.position_combo.master.config(width=191)

        self._section_label(inner, "ПАПКА СОХРАНЕНИЯ", pady=(14, 8))
        output = tk.Frame(inner, bg=COLORS["card"])
        output.pack(fill="x")
        self._entry(output, self.output_var).pack(side="left", fill="x", expand=True)
        tk.Frame(output, width=8, bg=COLORS["card"]).pack(side="left")
        self._button(output, "Выбрать", self.choose_output, accent=True,
                     font=FONTS["button_small"], pady=10, side="left")

        self.progress_bar = ProgressBar(inner)
        self.summary_title = tk.Label(inner, text="", bg=COLORS["card"],
                                      fg=COLORS["progress"], font=FONTS["accent"],
                                      anchor="w")
        self.summary_detail = tk.Label(inner, text="", bg=COLORS["card"],
                                       fg=COLORS["progress"], font=FONTS["small"],
                                       anchor="w")
        self.action_button = self._button(inner, "СТАРТ ОБРАБОТКИ",
                                          self.start_processing, primary=True,
                                          font=FONTS["action"], pady=13,
                                          fill="x", frame_pady=(20, 0))

        preset_row = tk.Frame(inner, bg=COLORS["card"])
        preset_row.pack(fill="x", pady=(18, 0))
        self.preset_combo = self._combo(preset_row, self.preset_var, (),
                                        state="normal", height=38, padx_inner=12,
                                        side="left", expand=True)
        self.preset_combo.master.config(width=250)
        self.preset_combo.bind("<<ComboboxSelected>>", self._load_selected_preset)
        self._button(preset_row, "Сохранить", self.save_preset, accent=True,
                     font=FONTS["button_small"], pady=8, side="left")
        return border

    # ------------------------------------------------------------- элементы

    def _button(self, parent, text, command, primary=False, accent=False,
                icon=None, font=None, pady=12, padx=(0, 0), frame_pady=(0, 0),
                **pack_options):
        """Создаёт скруглённую кнопку в одном из трёх стилей макета."""
        if primary:
            fill, foreground, border = COLORS["purple"], "#FFFFFF", COLORS["purple"]
            hover_fill, hover_foreground = COLORS["purple_hover"], "#FFFFFF"
            disabled_fill, disabled_foreground = COLORS["track"], COLORS["hint"]
        elif accent:
            fill, foreground, border = COLORS["page"], COLORS["purple"], COLORS["purple"]
            hover_fill, hover_foreground = COLORS["grey_hover"], COLORS["purple_hover"]
            disabled_fill, disabled_foreground = COLORS["page"], COLORS["hint"]
        else:
            fill, foreground, border = COLORS["page"], COLORS["text"], COLORS["grey_border"]
            hover_fill, hover_foreground = COLORS["grey_hover"], COLORS["text"]
            disabled_fill, disabled_foreground = COLORS["page"], COLORS["hint"]
        button = RoundedButton(
            parent, text, command, fill, foreground, border,
            hover_fill, hover_foreground, disabled_fill, disabled_foreground,
            font=font, padx=18, pady=pady, icon=icon,
        )
        button.pack(padx=padx, pady=frame_pady, **pack_options)
        return button

    def _entry(self, parent, variable, width=60):
        """Создаёт поле ввода со скруглённой рамкой как на макете."""
        box = RoundedBox(parent, COLORS["page"], COLORS["grey_border"],
                         background=parent.cget("bg"), height=44, width=width,
                         focus_border=COLORS["purple"])
        entry = tk.Entry(box, textvariable=variable, relief="flat", bd=0,
                         bg=COLORS["page"], fg=COLORS["text"],
                         insertbackground=COLORS["text"], font=FONTS["value"],
                         highlightthickness=0)
        box.embed(entry)
        return box

    def _combo(self, parent, variable, values, width=None, state="readonly",
               height=44, padx_inner=30, **pack_options):
        """Создаёт выпадающий список со скруглённой рамкой."""
        box = RoundedBox(parent, COLORS["page"], COLORS["grey_border"],
                         background=parent.cget("bg"), height=height,
                         focus_border=COLORS["purple"])
        combo = ttk.Combobox(box, textvariable=variable, values=values,
                             state=state, width=width or 18, style="App.TCombobox")
        box.embed(combo, padx=padx_inner)
        box.pack(fill="x", **pack_options)
        return combo

    def _section_label(self, parent, text, pady=(0, 0)):
        """Добавляет верхнюю подпись раздела настроек."""
        label = tk.Label(parent, text=text, bg=COLORS["card"], fg=COLORS["section"],
                         font=FONTS["section"], anchor="w")
        label.pack(fill="x", pady=pady)
        return label

    def _hint(self, parent, text):
        """Добавляет вспомогательную подпись под полем формата."""
        tk.Label(parent, text=text, bg=COLORS["card"], fg=COLORS["muted"],
                 font=FONTS["small"], anchor="w").pack(fill="x")

    def _setup_styles(self) -> None:
        """Настраивает оформление стандартных элементов Tkinter под макет."""
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "App.TCombobox",
            fieldbackground=COLORS["page"], background=COLORS["page"],
            foreground=COLORS["text"], arrowcolor=COLORS["section"],
            bordercolor=COLORS["page"], lightcolor=COLORS["page"],
            darkcolor=COLORS["page"], borderwidth=0, arrowsize=14,
            padding=(10, 8), relief="flat",
        )
        style.map(
            "App.TCombobox",
            fieldbackground=[("readonly", COLORS["page"]), ("focus", COLORS["page"])],
            background=[("readonly", COLORS["page"]), ("focus", COLORS["page"])],
            selectbackground=[("readonly", COLORS["page"])],
            selectforeground=[("readonly", COLORS["text"])],
            bordercolor=[("focus", COLORS["page"])],
        )
        # Выпадающие списки получают тёмную палитру приложения.
        self.option_add("*TCombobox*Listbox.background", COLORS["page"])
        self.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", COLORS["purple"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
        self.option_add("*TCombobox*Listbox.activeBackground", COLORS["purple_hover"])
        self.option_add("*TCombobox*Listbox.activeForeground", "#FFFFFF")

    # ------------------------------------------------------------ состояния

    def _set_state(self, state: str) -> None:
        """Переключает вид окна между состояниями макета."""
        self.state = state
        running = state == STATE_RUNNING
        done = state == STATE_DONE

        if state == STATE_IDLE:
            self.queue_list.pack_forget()
            self.preview.pack_forget()
            self.drop_zone.pack(fill="both", expand=True)
            self._draw_drop_zone()
            self.footer.pack(fill="x", pady=(20, 0))
        else:
            self.drop_zone.pack_forget()
            self.footer.pack_forget()
            self.queue_list.set_items(self.items, self.selected_index)
            self.queue_list.pack(fill="both", expand=True)
            self.preview.pack(fill="x", pady=(22, 0))

        action = self.action_button
        if running:
            action.set_text("ОТМЕНА")
            action.set_command(self.cancel_processing)
        elif done:
            action.set_text("ОБРАБОТАТЬ ЕЩЁ")
            action.set_command(self.start_over)
        else:
            action.set_text("СТАРТ ОБРАБОТКИ")
            action.set_command(self.start_processing)

        if running:
            self.summary_title.pack_forget()
            self.progress_bar.pack(fill="x", pady=(24, 0), before=self.action_button)
            self.summary_detail.pack(fill="x", pady=(14, 0), before=self.action_button)
            self._update_progress_display()
        elif done:
            self.progress_bar.pack_forget()
            self.summary_title.pack(fill="x", pady=(18, 0), before=self.action_button)
            self.summary_detail.pack(fill="x", pady=(6, 0), before=self.action_button)
        else:
            self.progress_bar.pack_forget()
            self.summary_title.pack_forget()
            self.summary_detail.pack_forget()

    def _on_quality_change(self, value: int) -> None:
        """Обновляет подпись качества при перетаскивании ползунка."""
        self.quality_label.config(text=f"КАЧЕСТВО СЖАТИЯ: {value}%")

    def _set_controls_enabled(self, enabled: bool) -> None:
        """Включает или блокирует кнопки управления очередью."""
        for control in self.queue_controls:
            control.set_enabled(enabled)

    # -------------------------------------------------------------- очередь

    def add_files(self) -> None:
        """Добавляет выбранные изображения в очередь."""
        paths = filedialog.askopenfilenames(
            title="Выберите изображения",
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp *.bmp *.tiff *.gif *.ico *.heic *.avif")],
        )
        self._append_paths(paths)

    def add_folder(self) -> None:
        """Добавляет изображения из выбранной папки."""
        folder = filedialog.askdirectory(title="Выберите папку")
        if not folder:
            return
        self._append_paths([
            str(path) for path in sorted(Path(folder).iterdir())
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ])

    def _on_drop(self, event) -> None:
        """Принимает файлы, перетащенные из файлового менеджера."""
        try:
            paths = self.tk.splitlist(event.data)
        except tk.TclError:
            paths = [event.data]
        self._append_paths(paths)

    def _append_paths(self, paths) -> None:
        """Добавляет файлы в очередь, игнорируя дубликаты и неподдерживаемые."""
        if self.state == STATE_RUNNING:
            messagebox.showwarning("Обработка выполняется",
                                   "Дождитесь завершения текущей обработки.")
            return
        known = {item.source for item in self.items}
        added = 0
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS or path in known:
                continue
            self.items.append(QueueItem(path))
            known.add(path)
            added += 1
        if not added:
            return
        if self.state in (STATE_IDLE, STATE_DONE):
            self._set_state(STATE_QUEUED)
        else:
            self.queue_list.set_items(self.items, self.selected_index)
        if self.selected_index < 0:
            self._select_item(0)
        else:
            self.queue_list.refresh()

    def clear_queue(self) -> None:
        """Очищает очередь и возвращает стартовое состояние макета."""
        if self.state == STATE_RUNNING:
            messagebox.showinfo("Обработка выполняется",
                                "Остановите обработку перед очисткой очереди.")
            return
        self.items.clear()
        self.selected_index = -1
        self.queue_list.clear_rows()
        self._reset_preview()
        self._set_state(STATE_IDLE)

    def _reset_preview(self) -> None:
        """Возвращает область предпросмотра к заглушке."""
        self.preview.reset()

    def _on_row_select(self, row: QueueRow) -> None:
        """Выбирает файл в очереди и показывает его предпросмотр."""
        self._select_item(self.queue_list.row_at(row))

    def _select_item(self, index: int) -> None:
        """Обновляет выделение карточки и область предпросмотра."""
        if not 0 <= index < len(self.items):
            return
        self.selected_index = index
        self.queue_list.set_selected(index)
        self.preview.show(self.items[index].source, self.items[index].output)

    def _on_row_remove(self, row: QueueRow) -> None:
        """Удаляет выбранный файл из очереди."""
        if self.state == STATE_RUNNING:
            messagebox.showinfo("Обработка выполняется",
                                "Остановите обработку перед удалением файлов.")
            return
        index = self.queue_list.row_at(row)
        if index < 0:
            return
        self.items.pop(index)
        self.selected_index = min(self.selected_index, len(self.items) - 1)
        if not self.items:
            self.queue_list.clear_rows()
            self._reset_preview()
            self._set_state(STATE_IDLE)
            return
        self.queue_list.set_items(self.items, self.selected_index)
        if 0 <= self.selected_index < len(self.items):
            self.preview.show(self.items[self.selected_index].source, self.items[self.selected_index].output)
        else:
            self._reset_preview()

    def choose_output(self) -> None:
        """Выбирает папку сохранения готовых файлов."""
        folder = filedialog.askdirectory(title="Папка для готовых файлов")
        if folder:
            self.output_var.set(folder)

    # --------------------------------------------------------------- пресеты

    def _build_preset(self) -> Preset:
        """Собирает значения формы в профиль настроек."""
        width = int(self.width_var.get()) if self.width_var.get().strip() else None
        height = int(self.height_var.get()) if self.height_var.get().strip() else None
        name = self.preset_var.get().strip() or "Текущие настройки"
        position = next((key for key, label in POSITION_LABELS.items()
                         if label == self.watermark_position_var.get()), "bottom-right")
        return Preset(
            name=name,
            output_format=self.format_var.get(),
            width=width,
            height=height,
            quality=int(self.quality_var.get()),
            clear_exif=self.exif_var.get(),
            keep_ratio=self.ratio_var.get(),
            output_dir=self.output_var.get().strip(),
            watermark_enabled=self.watermark_var.get(),
            watermark_text=self.watermark_text_var.get().strip(),
            watermark_position=position,
            watermark_opacity=75,
        )

    def _load_presets(self) -> None:
        """Заполняет список сохранённых профилей."""
        names = self.database.list_presets()
        self.preset_combo.configure(values=names)

    def _load_selected_preset(self, _event=None) -> None:
        """Загружает параметры выбранного профиля в форму."""
        preset = self.database.get_preset(self.preset_var.get().strip())
        if preset is None:
            return
        self.format_var.set(preset.output_format)
        self.width_var.set(str(preset.width or ""))
        self.height_var.set(str(preset.height or ""))
        self.quality_var.set(preset.quality)
        self.quality_label.config(text=f"КАЧЕСТВО СЖАТИЯ: {preset.quality}%")
        self.slider.redraw()
        self.exif_var.set(preset.clear_exif)
        self.ratio_var.set(preset.keep_ratio)
        self.watermark_var.set(preset.watermark_enabled)
        self.watermark_text_var.set(preset.watermark_text)
        positions = tuple(POSITION_LABELS.values())
        self.watermark_position_var.set(
            POSITION_LABELS.get(preset.watermark_position, POSITION_LABELS["bottom-right"])
        )
        self._sync_combo(self.position_combo, positions)
        self.output_var.set(preset.output_dir)

    def save_preset(self) -> None:
        """Сохраняет текущие настройки под введённым именем профиля."""
        try:
            preset = self._build_preset()
            self.processor._validate_preset(preset)
            if preset.name in self.database.list_presets():
                self.database.update_preset(preset)
            else:
                self.database.create_preset(preset)
            self._load_presets()
            self.preset_var.set(preset.name)
            messagebox.showinfo("Профиль сохранён", f"Настройки «{preset.name}» сохранены.")
        except (ValueError, sqlite3.Error, OSError) as exc:
            messagebox.showerror("Не удалось сохранить профиль", str(exc))

    # ------------------------------------------------------------ обработка

    def start_processing(self) -> None:
        """Запускает пакетную обработку в отдельном потоке."""
        if not self.items:
            messagebox.showwarning("Очередь пуста", "Добавьте файлы для обработки.")
            return
        try:
            preset = self._build_preset()
            self.processor._validate_preset(preset)
            if not preset.output_format:
                raise ValueError("Выберите целевой формат")
            missing = [str(item.source) for item in self.items if not item.source.is_file()]
            if missing:
                raise ValueError("Не найдены файлы: " + ", ".join(missing[:3]))
            if preset.name in self.database.list_presets():
                self.database.update_preset(preset)
            else:
                self.database.create_preset(preset)
            self.active_session_id = self.database.create_session(preset, len(self.items))
        except (ValueError, sqlite3.Error, OSError) as exc:
            messagebox.showerror("Проверьте настройки", str(exc))
            return
        for item in self.items:
            item.status, item.output, item.error, item.progress = "В очереди", None, None, 0
        self._set_controls_enabled(False)
        self.worker = ProcessingWorker(
            self.items, preset, self.processor,
            self._worker_update, self._worker_finish, self._worker_progress
        )
        self._set_state(STATE_RUNNING)
        self.worker.start()
        self._schedule_worker_events()

    def cancel_processing(self) -> None:
        """Запрашивает остановку текущей обработки."""
        if self.worker and self.worker.is_alive():
            self.worker.cancel()
            self.summary_detail.config(text="Остановка обработки…")

    def start_over(self) -> None:
        """Возвращает приложение к начальному состоянию макета."""
        self.items.clear()
        self.selected_index = -1
        self.queue_list.clear_rows()
        self._reset_preview()
        self._set_state(STATE_IDLE)

    def _worker_update(self, index: int, item: QueueItem) -> None:
        """Публикует событие обновления статуса в потокобезопасную очередь."""
        self._worker_events.put(("update", index, item))

    def _worker_progress(self, index: int, percent: int) -> None:
        """Публикует событие прогресса текущего файла."""
        self._worker_events.put(("progress", index, percent))

    def _worker_finish(self, duration: float) -> None:
        """Публикует событие завершения фоновой задачи."""
        self._worker_events.put(("finish", duration))

    def _schedule_worker_events(self) -> None:
        """Запускает опрос событий в главном потоке Tkinter."""
        if self._event_poll_id is None:
            self._event_poll_id = self.after(60, self._poll_worker_events)

    def _poll_worker_events(self) -> None:
        """Переносит события фонового потока в главный поток интерфейса."""
        self._event_poll_id = None
        while True:
            try:
                event = self._worker_events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "update":
                self.queue_list.update_row(event[1])
                # Блок «Сравнение до и после» должен показывать результат,
                # как только файл обработан, а не оставаться пустым до конца.
                if event[1] == self.selected_index and event[2].output is not None:
                    self.preview.show(event[2].source, event[2].output)
                self._update_progress_display()
            elif event[0] == "progress":
                self.queue_list.update_row(event[1])
                self._update_progress_display()
            elif event[0] == "finish":
                self._finish_ui(event[1])
        if (self.worker and self.worker.is_alive()) or not self._worker_events.empty():
            self._schedule_worker_events()

    def _update_progress_display(self) -> None:
        """Обновляет индикатор и подпись «Обработано: N из M файлов»."""
        total = len(self.items)
        finished = sum(item.status in FINISHED_STATES for item in self.items)
        current = sum(item.progress for item in self.items if item.status == "В обработке")
        percent = round((finished * 100 + current) / total) if total else 0
        self.progress_bar.set_fraction(percent / 100)
        self.summary_detail.config(
            text=f"Обработано: {finished} из {total} файлов ({percent}%)"
        )

    def _finish_ui(self, duration: float) -> None:
        """Показывает итог обработки и возвращает управление пользователю."""
        self._set_controls_enabled(True)
        if getattr(self, "active_session_id", None) is not None:
            try:
                for item in self.items:
                    self.database.log_processed_file(self.active_session_id, item)
                self.database.finish_session(self.active_session_id, duration, self.items)
            except sqlite3.Error as exc:
                messagebox.showwarning("Журналирование",
                                       f"Результаты обработаны, но журнал не сохранён: {exc}")
        self.queue_list.refresh()
        self._set_state(STATE_DONE)
        if 0 <= self.selected_index < len(self.items):
            item = self.items[self.selected_index]
            self.preview.show(item.source, item.output)

        succeeded = sum(item.status == "Готово" for item in self.items)
        failed = sum(item.status == "Ошибка" for item in self.items)
        cancelled = sum(item.status == "Отменено" for item in self.items)
        if cancelled:
            self.summary_title.config(text="Обработка отменена")
        elif failed:
            self.summary_title.config(text="Обработка завершена с ошибками")
        else:
            self.summary_title.config(text="Обработка завершена")
        total = len(self.items)
        self.summary_detail.config(text=f"Обработано: {succeeded} из {total} файлов (100%)")
        if failed:
            details = "\n".join(
                f"{item.source.name}: {item.error}" for item in self.items
                if item.status == "Ошибка" and item.error
            )
            messagebox.showwarning(
                "Обработка завершена",
                f"Успешно: {succeeded}\nОшибок: {failed}\nОтменено: {cancelled}\n\n{details[:2500]}"
            )

    def _close(self) -> None:
        """Закрывает приложение."""
        if self.worker and self.worker.is_alive():
            self.worker.cancel()
        if self._event_poll_id is not None:
            self.after_cancel(self._event_poll_id)
            self._event_poll_id = None
        self.database.close()
        self.destroy()
