"""Mouse-wheel scrolling and copy/paste for the app's tables.

Tk scrolls a Treeview, Listbox or Text with the wheel by itself, but not a Canvas: the
Schedule Builder's grid and the scrolling lists of checkboxes are canvases. One handler
on the whole app scrolls the canvas under the pointer; a canvas joins by setting
``_ddm_scrollable = True``. Shift scrolls sideways.
"""

import tkinter as tk
from tkinter import ttk

# Widgets Tk already scrolls with the wheel; the app-wide handler leaves them alone.
_SCROLLS_ITSELF = (ttk.Treeview, tk.Listbox, tk.Text, ttk.Combobox)


def install_mouse_wheel(root):
    """Scroll the scrollable canvas under the pointer, anywhere in the app."""

    def scrolled(event, sideways=False):
        try:
            widget = root.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):  # a combobox's popdown list isn't a Python widget
            return None
        while widget is not None:
            if isinstance(widget, _SCROLLS_ITSELF):
                return None
            if getattr(widget, "_ddm_scrollable", False):
                steps = -int(event.delta / 120) or (-1 if event.delta > 0 else 1)
                if sideways:
                    widget.xview_scroll(steps, "units")
                else:
                    widget.yview_scroll(steps, "units")
                return "break"
            widget = widget.master
        return None

    root.bind_all("<MouseWheel>", scrolled, add="+")
    root.bind_all("<Shift-MouseWheel>", lambda event: scrolled(event, sideways=True), add="+")
    return scrolled


def copy_text(widget, text):
    """Put ``text`` on the clipboard."""
    widget.clipboard_clear()
    widget.clipboard_append(text)
    widget.update_idletasks()  # Windows keeps the clipboard after the app closes only once it's flushed


def paste_text(widget):
    """The clipboard's text, or ``None`` when it holds no text. A single line copied from
    Excel ends in a line break, which is dropped."""
    try:
        text = widget.clipboard_get()
    except tk.TclError:
        return None
    return text[:-1] if text.endswith("\n") and text.count("\n") == 1 else text.rstrip("\r\n")


def rows_as_text(rows):
    """Rows of values as tab-separated lines, as Excel copies and pastes them."""
    return "\n".join("\t".join("" if value is None else str(value) for value in row) for row in rows)


def context_menu(widget, items):
    """A right-click menu; ``items`` is ``[(label, command or None)]`` (None greys it out)."""
    menu = tk.Menu(widget, tearoff=False)
    for label, command in items:
        menu.add_command(label=label, command=command or (lambda: None),
                         state="normal" if command else "disabled")
    return menu
