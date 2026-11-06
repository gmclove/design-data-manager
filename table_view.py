"""The view template every table in the app starts from, and the behaviour that goes with it.

Change ``DEFAULT_TABLE_VIEW`` to change the look of all tables at once. A table of rows
(``ttk.Treeview``) gets the whole template: click a header to sort, columns sized to their
longest entry, and dragging a column's edge changes that column only. The schedule window's grid
(``OverrideTable``) takes the heading font only: a click on its headers selects the column, its
order is the Revit schedule's, and its widths are the Revit schedule's.
"""

import re
import tkinter.font as tkfont
from dataclasses import dataclass
from tkinter import ttk

SORT_ASCENDING_MARK = " ▲"
SORT_DESCENDING_MARK = " ▼"


@dataclass(frozen=True)
class TableView:
    heading_font: tuple = ("Segoe UI", 11, "bold")
    # Column widths, in pixels. A column fits its longest entry, within these limits.
    max_column_width: int = 320
    min_column_width: int = 60
    # Room around the text in a cell.
    cell_padding: int = 20
    # Room a heading's lines must leave in their column: with less, Tk draws only the first line.
    heading_margin: int = 24
    # Only the longest entries (by characters) are measured, to keep large tables quick.
    entries_measured: int = 10


DEFAULT_TABLE_VIEW = TableView()


def apply_table_style(widget, view=DEFAULT_TABLE_VIEW):
    """Set the look shared by every ``ttk.Treeview`` in the app."""
    ttk.Style(widget).configure("Treeview.Heading", font=view.heading_font)


def fitted_width(entries, heading, body_font, heading_font, view=DEFAULT_TABLE_VIEW):
    """The width that shows the longest of ``entries``, within the template's limits.

    Headings wrap, so a heading only needs room for its longest word and a sort mark.
    """
    texts = sorted({str(entry) for entry in entries if entry is not None}, key=len)[-view.entries_measured:]
    widest = max((body_font.measure(text) for text in texts), default=0)
    words = str(heading).split() or [""]
    heading_width = max(heading_font.measure(word) for word in words) + heading_font.measure(SORT_ASCENDING_MARK)
    wanted = max(widest + view.cell_padding, heading_width + view.heading_margin)
    return max(view.min_column_width, min(view.max_column_width, wanted))


def tree_body_font(tree):
    name = ttk.Style(tree).lookup("Treeview", "font") or "TkDefaultFont"
    return tkfont.Font(root=tree, font=name)


def sort_key(value):
    """Numbers by value, before text; text ignoring case, with ``Pump 2`` before ``Pump 10``."""
    text = str(value).strip()
    try:
        return (0, float(text), [])
    except ValueError:
        pass
    parts = re.split(r"(\d+)", text.casefold())
    return (1, 0.0, [int(part) if index % 2 else part for index, part in enumerate(parts)])


def sorted_rows(rows, value_of, descending=False):
    """``rows`` in order of ``value_of(row)``. Blank values go last in either direction."""
    filled = []
    blank = []
    for row in rows:
        (blank if str(value_of(row)).strip() == "" else filled).append(row)
    filled.sort(key=lambda row: sort_key(value_of(row)), reverse=descending)
    return filled + blank


def next_sort(current, column):
    """What a click on ``column``'s header does: ascending, then descending, then back to unsorted.
    A sort is ``(column, descending)``; ``None`` is the table's own order."""
    if current is None or current[0] != column:
        return (column, False)
    return (column, True) if not current[1] else None


def sort_mark(current, column):
    if current is None or current[0] != column:
        return ""
    return SORT_DESCENDING_MARK if current[1] else SORT_ASCENDING_MARK


class ColumnResizer:
    """Dragging a column's edge changes that column only.

    Tk's own drag takes the width from the neighbouring columns, so this replaces it. The table
    scrolls sideways when its columns are wider than the window.
    """

    def __init__(self, tree, view=DEFAULT_TABLE_VIEW):
        self.tree = tree
        self.view = view
        self._column = None
        self._start_x = 0
        self._start_width = 0
        for column in tree["columns"]:
            tree.column(column, stretch=False, minwidth=view.min_column_width)
        tree.bind("<Button-1>", self._on_press, add="+")
        tree.bind("<B1-Motion>", self._on_drag, add="+")
        tree.bind("<ButtonRelease-1>", self._on_release, add="+")

    def column_at_edge(self, x):
        """The column whose right edge is nearest window position ``x``."""
        tree = self.tree
        shown = tree["displaycolumns"]
        columns = tree["columns"] if not shown or shown[0] == "#all" else shown
        widths = [int(tree.column(column, "width")) for column in columns]
        scrolled = tree.xview()[0] * sum(widths)
        edge = 0
        nearest = None
        nearest_distance = None
        for column, width in zip(columns, widths):
            edge += width
            distance = abs(edge - scrolled - x)
            if nearest_distance is None or distance < nearest_distance:
                nearest, nearest_distance = column, distance
        return nearest

    def begin(self, column, x):
        self._column = column
        self._start_x = x
        self._start_width = int(self.tree.column(column, "width"))

    def drag(self, x):
        width = max(self.view.min_column_width, self._start_width + x - self._start_x)
        self.tree.column(self._column, width=width)

    def _on_press(self, event):
        if self.tree.identify_region(event.x, event.y) != "separator":
            return None
        self.begin(self.column_at_edge(event.x), event.x)
        return "break"

    def _on_drag(self, event):
        if self._column is None:
            return None
        self.drag(event.x)
        return "break"

    def _on_release(self, _event):
        if self._column is None:
            return None
        self._column = None
        return "break"
