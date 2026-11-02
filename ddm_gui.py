import json
import os
import pickle
import tkinter.font as tkfont
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from config.revit_dtype_definitions import REVIT_DTYPE_TABLE
from config.revit_family_category_definitions import REVIT_FAMILY_CATEGORY_TABLE
from config.revit_property_pallet_definitions import REVIT_PROPERTY_PALLET_TABLE
from config.app_paths import (
    DEFAULT_CHECKPOINT_PATH,
    DEMO_DATA_PATH,
    get_database_output_paths,
)

try:
    from quickbase_integration import QuickbaseClient, QuickbaseSyncService
except ImportError:  # pragma: no cover
    QuickbaseClient = None
    QuickbaseSyncService = None

from ddm_tables import (
    DEFAULT_GRID_COLUMN_WIDTH_IN,
    FAMILY_COLUMNS,
    PARAM_COLUMNS,
    catalog_from_tables,
    entries_table,
    families_table,
    header_groups_by_schedule,
    links_table,
    params_table,
    parse_bool,
    parse_width,
    read_database_csv,
    tables_from_legacy_pickle,
    text as cell_text,
    write_database_csv,
)
from revit_parameter_manager import COMMON_PARAM_NAMES, Catalog, Param, Schedule, guid_change_warning
from revit_schedule_macro_generator import generate_schedule_macro_source
from revit_parameter_scheduler_export import generate_rfps_content
from revit_shared_parameter_export import generate_shared_parameter_content




def _wrap_text_segment(text, max_width, font):
    remaining = str(text)
    lines = []
    while remaining:
        if font.measure(remaining) <= max_width:
            lines.append(remaining)
            break

        end = 0
        for index in range(1, len(remaining) + 1):
            if font.measure(remaining[:index]) > max_width:
                break
            end = index
        end = max(1, end)

        break_at = max(
            remaining.rfind(" ", 0, end),
            remaining.rfind("_", 0, end) + 1,
            max(
                (
                    index
                    for index in range(1, end)
                    if remaining[index].isupper()
                    and remaining[index - 1].islower()
                ),
                default=0,
            ),
        )
        if break_at <= 0:
            break_at = end
        lines.append(remaining[:break_at].rstrip())
        remaining = remaining[break_at:].lstrip()
    return lines or [""]


# Label of the schedule table row that sets every family's Schedule Default Value at once.
ALL_FAMILIES = "All Families"

# Shown by the Info button on the override windows. Keep in step with the README's
# "Overriding Default Values" section.
OVERRIDE_RULES = (
    ("Three Levels of Default Value", (
        "Parameter Default Value: set on the parameter itself. Every family and schedule uses it "
        "unless something more specific overrides it.\n"
        "Family Default Value: set for one family. It replaces the Parameter Default Value for that "
        "family, in every schedule the family is in.\n"
        "Schedule Default Value: set for one family in one schedule. It replaces the Family and "
        "Parameter Default Values in that schedule only."
    )),
    ("Which Value Wins", (
        "The most specific level wins: Schedule Default Value, then Family Default Value, then "
        "Parameter Default Value. Clearing an override (delete the value and save) lets the level "
        "above show through again."
    )),
    ("What Can Be Overridden", (
        "Default Value: at all three levels.\n"
        "Formula and Group Under: at the Parameter and Family levels only. They describe the family, "
        "so a schedule shows them read-only."
    )),
    ("Reading the Tables", (
        "Black text: set at this level.\n"
        "Gray text: inherited from the level above.\n"
        "Shaded cell: doesn't apply, for example the family doesn't have that parameter. In a "
        "schedule, an \"Add Parameter to Family\" button adds the missing parameter to the family.\n"
        "Double-click a cell to edit it in place. Enter or clicking away saves, Tab moves to the "
        "next cell, Escape cancels."
    )),
    ("The All Families Row", (
        "In a schedule, the All Families row is a shortcut, not another level. A value set there "
        "becomes the Schedule Default Value of every family in the schedule that has that column. "
        "It shows the shared value, \"(Varies)\" when the families differ, or blank when none is "
        "set. Leaving a \"(Varies)\" cell unchanged changes nothing."
    )),
    ("Where Else to Override", (
        "After you change a Family or Schedule Default Value you're asked where else it should go:\n"
        "From a schedule: pick other families in the same schedule to get the same value.\n"
        "From a family: pick the schedules that family is in to get the same value.\n"
        "Tick \"Override Parameter Default Value?\" to make the value the parameter's default for "
        "everything that doesn't override it.\n"
        "Formula and Group Under changes only offer the parameter checkbox, since schedules can't "
        "hold them."
    )),
    ("Renames", (
        "Overrides follow parameter and family renames, including parameter names used inside "
        "formula overrides."
    )),
)


class OverrideTable(tk.Canvas):
    """A grid of default values: header rows, then labelled rows of cells.

    Columns are parameters. Two label columns on the left name each section
    (Schedule, Parameter, a family) and each row. With ``show_header`` the top
    rows are the schedule's header groups (Group Level N ... 1) and column headers.

    Body rows are dicts: ``{"section": str, "label": str, "cells": [cell, ...]}``,
    plus any keys the caller needs back. A cell is ``{"text": str, "state": ...,
    "editable": bool}`` where state is ``"set"`` (set at this level),
    ``"inherited"`` (shown in gray, from a level above) or ``"none"`` (shaded,
    doesn't apply).
    """

    section_width = 110
    label_width = 110
    row_height = 24
    # Screen pixels per inch of Revit grid column width, and the narrowest readable column.
    pixels_per_inch = 72
    min_column_width = 110

    def __init__(self, master, parameter_names, header_texts=None, groups=None, rows=None,
                 show_header=True, on_header_double_click=None, on_cell_double_click=None,
                 grid_column_widths=None, on_cell_action=None):
        super().__init__(master, background="#ffffff", highlightthickness=0)
        self.parameter_names = list(parameter_names)
        self.header_texts = dict(header_texts or {})
        self.show_header = show_header
        self.rows = list(rows or [])
        self.groups = []
        self.group_layout = []
        self.selected_indices = set()
        self.selection_anchor = None
        self.on_header_double_click = on_header_double_click
        self.on_cell_double_click = on_cell_double_click
        self.on_cell_action = on_cell_action
        self.column_width = 170
        self.column_widths = []
        self.column_offsets = []
        self.group_row_height = 30
        self.header_height = 58 if show_header else 0
        self.header_font = tkfont.Font(root=self, font=("Segoe UI", 10, "bold"))
        self.label_font = tkfont.Font(root=self, font=("Segoe UI", 9, "bold"))
        self.body_font = tkfont.Font(root=self, font=("Segoe UI", 9))
        self.header_top = 0
        self._cell_editor = None
        self.bind("<Button-1>", self._on_mouse_down)
        self.bind("<B1-Motion>", self._on_mouse_drag)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Motion>", self._on_motion)
        self.set_grid_column_widths(grid_column_widths or [1.0] * len(self.parameter_names))
        self.set_groups(groups or [])

    @property
    def left(self):
        return self.section_width + self.label_width

    @property
    def body_top(self):
        return self.header_top + self.header_height

    def set_grid_column_widths(self, widths_in_inches):
        self.column_widths = [
            max(self.min_column_width, int(float(width) * self.pixels_per_inch)) for width in widths_in_inches
        ]
        if len(self.column_widths) != len(self.parameter_names):
            self.column_widths = [self.column_width] * len(self.parameter_names)
        self.column_width = self.column_widths[0] if self.column_widths else 170
        self.column_offsets = []
        offset = self.left
        for width in self.column_widths:
            self.column_offsets.append(offset)
            offset += width
        self._draw_grid()

    def _wrap_header_segment(self, text, max_width):
        return _wrap_text_segment(text, max_width, self.header_font)

    def _wrapped_header_text(self, parameter_name, max_width):
        return self._wrap_header_segment(self.header_texts.get(parameter_name, parameter_name), max_width)

    def set_groups(self, groups):
        self.groups = [dict(group) for group in groups]
        parameter_indices = {name: index for index, name in enumerate(self.parameter_names)}
        candidates = []
        for group in self.groups:
            indices = [parameter_indices[name] for name in group["parameter_names"] if name in parameter_indices]
            if len(indices) != len(group["parameter_names"]) or not indices:
                continue
            candidates.append((min(indices), max(indices), group))

        candidates.sort(key=lambda item: (item[0], -item[1]))
        lane_ends = []
        self.group_layout = []
        for start_index, end_index, group in candidates:
            lane = next((index for index, end in enumerate(lane_ends) if end < start_index), len(lane_ends))
            if lane == len(lane_ends):
                lane_ends.append(end_index)
            else:
                lane_ends[lane] = end_index
            self.group_layout.append((lane, start_index, end_index, group))

        if self.show_header and self.parameter_names:
            self.header_top = max(1, len(lane_ends)) * self.group_row_height
        else:
            self.header_top = 0
        self._draw_grid()

    def set_header_texts(self, header_texts):
        self.header_texts = dict(header_texts)
        self._draw_grid()

    def set_rows(self, rows):
        self.rows = list(rows)
        self._draw_grid()

    def get_selected_parameter_names(self):
        return [
            self.parameter_names[index]
            for index in range(len(self.parameter_names))
            if index in self.selected_indices
        ]

    def _column_at(self, canvas_x):
        for index, (left, width) in enumerate(zip(self.column_offsets, self.column_widths)):
            if left <= canvas_x < left + width:
                return index
        return None

    def _parameter_index_at(self, event):
        """The column whose header was clicked, or ``None`` outside the header row."""
        canvas_y = self.canvasy(event.y)
        if not self.show_header or not self.parameter_names:
            return None
        if not self.header_top <= canvas_y < self.body_top:
            return None
        return self._column_at(self.canvasx(event.x))

    def _cell_at(self, event):
        """``(row_index, column_index)`` of the body cell under the event, or ``None``."""
        canvas_y = self.canvasy(event.y)
        if canvas_y < self.body_top:
            return None
        row_index = int((canvas_y - self.body_top) // self.row_height)
        column_index = self._column_at(self.canvasx(event.x))
        if row_index >= len(self.rows) or column_index is None:
            return None
        return row_index, column_index

    def cell_bbox(self, row_index: int, column_index: int):
        """``(left, top, width, height)`` of a body cell in canvas coordinates."""
        return (
            self.column_offsets[column_index],
            self.body_top + row_index * self.row_height,
            self.column_widths[column_index],
            self.row_height,
        )

    def start_cell_edit(self, row_index: int, column_index: int, value: str, on_commit,
                        placeholder: str = "", choices=None, on_tab=None):
        """Edit one body cell in place, with a box laid over the cell.

        Enter, Tab or clicking elsewhere commits and calls ``on_commit(text)``;
        Escape cancels. Tab then calls ``on_tab()`` to move on. With ``choices`` the
        box is a drop-down whose blank first entry clears the value.
        """
        self.finish_cell_edit(commit=True)
        left, top, width, height = self.cell_bbox(row_index, column_index)
        if choices is not None:
            editor = ttk.Combobox(self, values=["", *choices], state="readonly")
            editor.set(value)
            editor.bind("<<ComboboxSelected>>", lambda _event: finish(True), add="+")
        else:
            editor = PlaceholderEntry(self, placeholder=placeholder)
            if value:
                editor.insert(0, value)
                editor.selection_range(0, tk.END)
            # A drop-down list takes focus while open, so only a text box commits on focus loss.
            editor.bind("<FocusOut>", lambda _event: finish(True), add="+")
        window = self.create_window(left, top, window=editor, anchor="nw", width=width, height=height)
        done = False

        def finish(commit, then=None):
            nonlocal done
            if done:
                return "break"
            done = True
            text = editor.get()
            self._cell_editor = None
            self.delete(window)
            editor.destroy()
            if commit:
                on_commit(text)
            if then is not None:
                then()
            return "break"

        editor.bind("<Return>", lambda _event: finish(True), add="+")
        editor.bind("<KP_Enter>", lambda _event: finish(True), add="+")
        editor.bind("<Escape>", lambda _event: finish(False), add="+")
        editor.bind("<Tab>", lambda _event: finish(True, on_tab), add="+")
        editor.focus_set()
        self._cell_editor = (editor, finish)
        return editor

    def finish_cell_edit(self, commit: bool = True):
        """Commit (or cancel) the cell being edited, if any."""
        if self._cell_editor is not None:
            self._cell_editor[1](commit)

    def _on_mouse_down(self, event):
        self.finish_cell_edit(commit=True)
        action = self._action_at(event)
        if action is not None:
            if self.on_cell_action is not None:
                self.on_cell_action(*action)
            return
        index = self._parameter_index_at(event)
        if index is None:
            return
        if event.state & 0x0004:
            if index in self.selected_indices:
                self.selected_indices.remove(index)
            else:
                self.selected_indices.add(index)
            self.selection_anchor = index
        elif event.state & 0x0001 and self.selection_anchor is not None:
            self._select_range(self.selection_anchor, index)
        else:
            self.selection_anchor = index
            self.selected_indices = {index}
        self._draw_grid()

    def _on_mouse_drag(self, event):
        index = self._parameter_index_at(event)
        if index is None or self.selection_anchor is None:
            return
        self._select_range(self.selection_anchor, index)
        self._draw_grid()

    def _select_range(self, start_index, end_index):
        first_index, last_index = sorted((start_index, end_index))
        self.selected_indices = set(range(first_index, last_index + 1))

    def _on_double_click(self, event):
        index = self._parameter_index_at(event)
        if index is not None:
            if self.on_header_double_click is not None:
                self.on_header_double_click(self.parameter_names[index])
            return
        cell = self._cell_at(event)
        if cell is not None and self.on_cell_double_click is not None:
            self.on_cell_double_click(*cell)

    def _label_cell(self, x, y, width, height, text, fill="#f1f5f3", font=None):
        self.create_rectangle(x, y, x + width, y + height, fill=fill, outline="#c8d2ce")
        if text:
            self.create_text(
                x + 6, y + height / 2, text=text, anchor="w",
                width=max(1, width - 10), font=font or self.label_font,
            )

    def _draw_grid(self):
        self.delete("all")
        if not self.parameter_names:
            return

        if self.show_header:
            wrapped_headers = [
                self._wrapped_header_text(name, max(1, self.column_widths[index] - 14))
                for index, name in enumerate(self.parameter_names)
            ]
            line_height = self.header_font.metrics("linespace")
            self.header_height = max(58, max(len(lines) for lines in wrapped_headers) * line_height + 20)
        else:
            wrapped_headers = []
            self.header_height = 0

        right = self.column_offsets[-1] + self.column_widths[-1]
        total_height = self.body_top + len(self.rows) * self.row_height
        self.configure(height=min(max(total_height, 1), 480), scrollregion=(0, 0, right, total_height))

        if self.show_header:
            self._draw_header(wrapped_headers)
        self._draw_body(right)

    def _draw_header(self, wrapped_headers):
        lane_count = self.header_top // self.group_row_height
        self._label_cell(0, 0, self.section_width, self.body_top, "Schedule")
        for lane in range(lane_count):
            top = lane * self.group_row_height
            self._label_cell(self.section_width, top, self.label_width, self.group_row_height,
                             f"Group Level {lane_count - lane}")
            for index in range(len(self.parameter_names)):
                left = self.column_offsets[index]
                self.create_rectangle(
                    left, top, left + self.column_widths[index], top + self.group_row_height,
                    fill="#f1f5f3", outline="#c8d2ce",
                )
        self._label_cell(self.section_width, self.header_top, self.label_width, self.header_height, "Column Header")

        for lane, start_index, end_index, group in self.group_layout:
            left = self.column_offsets[start_index]
            right = self.column_offsets[end_index] + self.column_widths[end_index]
            top = lane * self.group_row_height
            self.create_rectangle(left, top, right, top + self.group_row_height, fill="#dce9e4", outline="#7a9187", width=2)
            self.create_text(
                (left + right) / 2, top + self.group_row_height / 2,
                text=group["caption"], width=max(1, right - left - 12), font=("Segoe UI", 10, "bold"),
            )

        for index, header_lines in enumerate(wrapped_headers):
            left = self.column_offsets[index]
            right = left + self.column_widths[index]
            selected = index in self.selected_indices
            self.create_rectangle(
                left, self.header_top, right, self.body_top,
                fill="#dcefe7" if selected else "#ffffff",
                outline="#7a9187" if selected else "#c8d2ce",
                width=2 if selected else 1,
            )
            self.create_text(
                (left + right) / 2, self.header_top + self.header_height / 2,
                text="\n".join(header_lines), width=self.column_widths[index] - 14,
                justify="center", font=self.header_font,
            )

    def _draw_body(self, right):
        section_start = 0
        for row_index, row in enumerate(self.rows + [None]):
            starts_section = row is None or (row_index > 0 and row.get("section"))
            if starts_section and row_index > section_start:
                # The section label spans every row since the last section started.
                top = self.body_top + section_start * self.row_height
                height = (row_index - section_start) * self.row_height
                self._label_cell(0, top, self.section_width, height, self.rows[section_start].get("section", ""))
                self.create_line(0, top, right, top, fill="#374151", width=2)
                section_start = row_index
            if row is None:
                break

            top = self.body_top + row_index * self.row_height
            self._label_cell(self.section_width, top, self.label_width, self.row_height, row.get("label", ""), fill="#f8faf9")
            for index, cell in enumerate(row["cells"]):
                left = self.column_offsets[index]
                if cell.get("action"):
                    self._draw_action_cell(row_index, index)
                    continue
                state = cell.get("state", "set")
                if state == "none":
                    fill = "#e5e9e7"
                elif cell.get("editable"):
                    fill = "#ffffff"
                else:
                    fill = "#f8faf9"
                self.create_rectangle(left, top, left + self.column_widths[index], top + self.row_height,
                                      fill=fill, outline="#c8d2ce")
                if cell.get("text") and state != "none":
                    self.create_text(
                        left + 6, top + self.row_height / 2,
                        text=self._fit_text(cell["text"], self.column_widths[index] - 12), anchor="w",
                        font=self.body_font, fill="#9ca3af" if state == "inherited" else "#111827",
                    )

    def _action_span(self, row_index: int, column_index: int):
        """The first row and row count of the action button covering this cell.

        Consecutive rows of the same family with the same action in a column merge
        into one button.
        """
        def same(index):
            row = self.rows[index]
            return (
                row.get("family") == self.rows[row_index].get("family")
                and row["cells"][column_index].get("action") == self.rows[row_index]["cells"][column_index]["action"]
            )

        first = row_index
        while first > 0 and same(first - 1):
            first -= 1
        last = row_index
        while last + 1 < len(self.rows) and same(last + 1):
            last += 1
        return first, last - first + 1

    def _draw_action_cell(self, row_index: int, column_index: int):
        first, count = self._action_span(row_index, column_index)
        if first != row_index:
            return
        left, top, width, _height = self.cell_bbox(row_index, column_index)
        height = count * self.row_height
        self.create_rectangle(left, top, left + width, top + height, fill="#e5e9e7", outline="#c8d2ce")
        self.create_rectangle(
            left + 6, top + 6, left + width - 6, top + height - 6,
            fill="#dce9e4", outline="#7a9187",
        )
        self.create_text(
            left + width / 2, top + height / 2,
            text=self.rows[row_index]["cells"][column_index]["action"],
            width=max(1, width - 20), justify="center", font=self.label_font,
        )

    def _action_at(self, event):
        """``(row_index, column_index)`` of the action button under the event, or ``None``."""
        cell = self._cell_at(event)
        if cell is None or not self.rows[cell[0]]["cells"][cell[1]].get("action"):
            return None
        return cell

    def _on_motion(self, event):
        self.configure(cursor="hand2" if self._action_at(event) else "")

    def _fit_text(self, text: str, max_width: int) -> str:
        """``text`` on one line, cut short with an ellipsis if it is wider than ``max_width``."""
        if self.body_font.measure(text) <= max_width:
            return text
        while text and self.body_font.measure(text + "…") > max_width:
            text = text[:-1]
        return text + "…"


class PlaceholderEntry(ttk.Entry):
    """A ``ttk.Entry`` that shows gray instructions while it is empty.

    The placeholder clears when the user starts typing (not on focus, so a focused
    box still shows it) and comes back when the box is emptied. ``get()`` returns
    ``""`` while the placeholder is showing.
    """

    _style_name = "Placeholder.TEntry"

    def __init__(self, master, placeholder: str = "", **kwargs):
        super().__init__(master, **kwargs)
        self.placeholder = placeholder
        self._normal_style = kwargs.get("style", "TEntry")
        self._showing = False
        ttk.Style(self).configure(self._style_name, foreground="#9ca3af")
        self.bind("<KeyPress>", self._on_key, add="+")
        self.bind("<KeyRelease>", lambda _event: self._show_if_empty(), add="+")
        self.bind("<FocusIn>", lambda _event: self._park_cursor(), add="+")
        self.bind("<ButtonRelease-1>", lambda _event: self._park_cursor(), add="+")
        self.bind("<FocusOut>", lambda _event: self._show_if_empty(), add="+")
        self._show_if_empty()

    def get(self):
        return "" if self._showing else super().get()

    def insert(self, index, string):
        self._hide()
        super().insert(index, string)

    def _show_if_empty(self):
        if self._showing or not self.placeholder or super().get():
            return
        super().insert(0, self.placeholder)
        self.configure(style=self._style_name)
        self._showing = True
        self._park_cursor()

    def _hide(self):
        if not self._showing:
            return
        super().delete(0, tk.END)
        self.configure(style=self._normal_style)
        self._showing = False

    def _park_cursor(self):
        if self._showing:
            self.selection_clear()
            self.icursor(0)

    def _on_key(self, event):
        if not self._showing:
            return None
        if event.keysym in {"BackSpace", "Delete", "Left", "Right", "Home", "End"}:
            return "break"
        if event.char and event.char.isprintable():
            self._hide()
        return None


class DDMGUI:
    """Tkinter review/edit GUI over a parameter ``Catalog``.

    The catalog is the source of truth. The tables are views rebuilt from it after
    every change, and edits go through model methods, so an invalid edit is
    rejected with an error instead of being stored.
    """

    _default_grid_column_width_in = DEFAULT_GRID_COLUMN_WIDTH_IN

    _table_columns = {
        "params": list(PARAM_COLUMNS),
        "families": list(FAMILY_COLUMNS),
    }

    _display_labels = {
        "name": "Name",
        "header_text": "Default Header Text",
        "header_text_override": "Schedule Header Override",
        "grid_column_width": "Grid Column Width (in)",
        "grid_column_width_override": "Schedule Width Override (in)",
        "dtype": "Data Type",
        "group_under": "Group Under",
        "formula": "Formula",
        "instance_param": "Instance Param",
        "default_value": "Default Value",
        "status": "Status",
        "validation_message": "Validation Message",
        "client": "Client",
        "country": "Country",
        "category": "Category",
        "description": "Description",
        "family_name": "Family Name",
        "parameter_name": "Parameter Name",
        "group_name": "Group Name",
        "override_entry": "Override Entry",
        "family_count": "Family Count",
        "parameter_count": "Parameter Count",
        "guid": "GUID",
    }

    _schedule_summary_columns = ["name", "family_count", "parameter_count", "status", "validation_message"]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DDM Review")
        self.root.geometry("1360x820")
        self.root.minsize(1100, 700)

        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#1f2937")
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground="#374151")
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))

        self.catalog = Catalog()
        self.load_issues: List[str] = []
        self.warning_text = None
        self.param_tree = None
        self.family_tree = None
        self.group_tree = None
        self.checkpoint_path = DEFAULT_CHECKPOINT_PATH

        self.build_ui()
        self.render_tables()
        startup_path = (
            DEFAULT_CHECKPOINT_PATH
            if DEFAULT_CHECKPOINT_PATH.exists()
            else DEMO_DATA_PATH
        )
        self.load_checkpoint(str(startup_path))
        self.checkpoint_path = DEFAULT_CHECKPOINT_PATH

    # --- views on the catalog -------------------------------------------------

    @property
    def params_df(self) -> pd.DataFrame:
        return params_table(self.catalog)

    @property
    def families_df(self) -> pd.DataFrame:
        return families_table(self.catalog)

    @property
    def family_param_links_df(self) -> pd.DataFrame:
        return links_table(self.catalog)

    @property
    def family_groups_df(self) -> pd.DataFrame:
        return entries_table(self.catalog)

    @property
    def schedule_header_groups(self) -> dict:
        return header_groups_by_schedule(self.catalog)

    # --- layout -----------------------------------------------------------------

    def build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        header = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="DDM Review", style="Title.TLabel").grid(row=0, column=0, sticky="w")

        toolbar = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        toolbar.grid(row=1, column=0, sticky="ew")

        ttk.Button(toolbar, text="Validate", command=self.validate_all, style="Action.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Sync to Quickbase", command=self.sync_to_quickbase, style="Action.TButton").pack(side="left")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 8))

        self.params_tab = ttk.Frame(self.notebook)
        self.family_tab = ttk.Frame(self.notebook)
        self.schedules_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.params_tab, text="Parameters")
        self.notebook.add(self.family_tab, text="Families")
        self.notebook.add(self.schedules_tab, text="Schedules")

        self._build_data_table(self.params_tab, "params")
        self._build_data_table(self.family_tab, "families")
        self._build_data_table(self.schedules_tab, "groups")

        self._configure_detail_clicks()

        validation_header = ttk.Label(self.root, text="Messages", style="Section.TLabel")
        validation_header.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 4))

        self.warning_text = tk.Text(self.root, height=8, wrap="word", padx=10, pady=8, bg="#f8fafc", borderwidth=1, relief="solid")
        self.warning_text.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))

        self.file_actions = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        self.file_actions.grid(row=5, column=0, sticky="ew")
        self.file_actions.columnconfigure(0, weight=1)
        ttk.Button(self.file_actions, text="Load", command=self.load_checkpoint, style="Action.TButton").grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(self.file_actions, text="Save", command=self.save_checkpoint, style="Action.TButton").grid(
            row=0, column=2, padx=(0, 8)
        )
        ttk.Button(self.file_actions, text="Save As...", command=self.save_checkpoint_as, style="Action.TButton").grid(
            row=0, column=3
        )

    def _show_messages(self, lines: Sequence[str]):
        if self.warning_text is None:
            return
        self.warning_text.delete("1.0", tk.END)
        self.warning_text.insert("1.0", "\n".join(lines))

    def _append_message(self, line: str):
        if self.warning_text is not None:
            self.warning_text.insert(tk.END, f"\n{line}")

    # --- exports ----------------------------------------------------------------

    def _generate_revit_schedule_macro_file(self):
        try:
            output_path = get_database_output_paths(self.checkpoint_path)["macro"]
            source = generate_schedule_macro_source(
                self.family_groups_df,
                self.families_df,
                self.params_df,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(source, encoding="utf-8")
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Schedule Macro Generation Failed",
                f"The database was saved, but the Revit schedule macro could not be generated:\n{exc}",
                parent=getattr(self, "root", None),
            )
            return
        self._append_message(f"Generated Revit schedule macro: {output_path}")

    def _generate_rfps_file(self):
        try:
            output_paths = get_database_output_paths(self.checkpoint_path)
            output_path = output_paths["rfps"]
            content = generate_rfps_content(
                self.families_df,
                self.family_param_links_df,
                self.params_df,
                shared_parameter_file_name=output_paths["shared_parameters"].name,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                content,
                encoding="utf-8",
                newline="",
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "RF Tools Export Failed",
                f"The database was saved, but the RF Tools parameter scheduler file "
                f"could not be generated:\n{exc}",
                parent=getattr(self, "root", None),
            )
            return
        self._append_message(f"Generated RF Tools parameter scheduler file: {output_path}")

    def _generate_shared_parameter_file(self):
        try:
            output_path = get_database_output_paths(self.checkpoint_path)["shared_parameters"]
            content = generate_shared_parameter_content(self.params_df)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-16", newline="")
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Shared Parameter Export Failed",
                f"The database was saved, but the Revit shared parameter file "
                f"could not be generated:\n{exc}",
                parent=getattr(self, "root", None),
            )
            return
        self._append_message(f"Generated Revit shared parameter file: {output_path}")

    # --- tables -----------------------------------------------------------------

    @staticmethod
    def _humanize_column_name(column_name: str) -> str:
        if column_name in DDMGUI._display_labels:
            return DDMGUI._display_labels[column_name]
        return column_name.replace("_", " ").title()

    def _get_table_columns(self, table_name: str):
        return DDMGUI._table_columns[table_name]

    def _build_schedule_summary_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "name": schedule.name,
                    "family_count": len(schedule.fams),
                    "parameter_count": len(schedule.params),
                    "status": schedule.status,
                    "validation_message": schedule.validation_message,
                }
                for schedule in self.catalog.schedules
            ],
            columns=self._schedule_summary_columns,
        )

    def _build_data_table(self, parent: ttk.Frame, table_name: str):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        if table_name == "params":
            columns = self._get_table_columns("params")
            tree = ttk.Treeview(frame, columns=columns, show="headings")
            for col in columns:
                tree.heading(col, text=self._humanize_column_name(col))
                tree.column(col, width=150, anchor="w")
            self.param_tree = tree
        elif table_name == "families":
            columns = self._get_table_columns("families")
            tree = ttk.Treeview(frame, columns=columns, show="headings")
            for col in columns:
                tree.heading(col, text=self._humanize_column_name(col))
                tree.column(col, width=170, anchor="w")
            self.family_tree = tree
        else:
            columns = self._schedule_summary_columns
            tree = ttk.Treeview(frame, columns=columns, show="headings")
            for col in columns:
                tree.heading(col, text=self._humanize_column_name(col))
                width = 180 if col == "name" else 120
                tree.column(col, width=width, anchor="w")
            self.group_tree = tree

        self._bind_table_edit_events(tree, table_name)

        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        tree._ddm_heading_font = tkfont.Font(
            root=self.root,
            font=ttk.Style(self.root).lookup("Treeview.Heading", "font"),
        )
        tree._ddm_heading_columns = list(columns)
        tree._ddm_heading_line_count = 1
        if not hasattr(self, "_table_heading_trees"):
            self._table_heading_trees = []
        self._table_heading_trees.append(tree)
        tree.bind(
            "<ButtonRelease-1>",
            lambda _event, table=tree: self._update_table_heading_wrap(table),
            add="+",
        )
        tree.bind(
            "<B1-Motion>",
            lambda event, table=tree: self._schedule_table_heading_wrap(table, event),
            add="+",
        )
        self._update_table_heading_wrap(tree)

        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

    def _schedule_table_heading_wrap(self, tree: ttk.Treeview, event):
        if tree.identify_region(event.x, event.y) == "separator":
            tree.after_idle(lambda: self._update_table_heading_wrap(tree))

    def _update_table_heading_wrap(self, tree: ttk.Treeview):
        font = getattr(tree, "_ddm_heading_font", None)
        columns = getattr(tree, "_ddm_heading_columns", ())
        if font is None:
            return
        max_line_count = 1
        for column in columns:
            label = self._humanize_column_name(column)
            width = max(1, int(tree.column(column, "width")) - 16)
            lines = _wrap_text_segment(label, width, font)
            max_line_count = max(max_line_count, len(lines))
            wrapped_label = "\n".join(lines)
            tree.heading(column, text=wrapped_label, anchor="n")
        tree._ddm_heading_line_count = max_line_count

        if not hasattr(self, "_table_heading_style"):
            self._table_heading_style = ttk.Style(self.root)
        heading_line_count = max(
            (
                getattr(table, "_ddm_heading_line_count", 1)
                for table in getattr(self, "_table_heading_trees", [])
            ),
            default=max_line_count,
        )
        line_height = font.metrics("linespace")
        top_padding = 2
        bottom_padding = top_padding + (heading_line_count - 1) * line_height
        self._table_heading_style.configure(
            "Treeview.Heading",
            padding=(6, top_padding, 6, bottom_padding),
        )
        tree.update_idletasks()

    def _configure_detail_clicks(self):
        if self.family_tree is not None:
            # One click edits the cell in place; two clicks open the family window.
            self.family_tree.bind("<Button-1>", lambda event: self._on_tree_click(event, "families"), add="+")
            self.family_tree.bind("<Double-1>", self._on_family_tree_double_click)
        if self.group_tree is not None:
            self.group_tree.bind("<Double-1>", self._open_selected_schedule_window)

    def _bind_table_edit_events(self, tree: ttk.Treeview, table_name: str):
        if tree is None:
            return
        if table_name in {"params"}:
            # One click edits the cell in place; two clicks open the edit pop-up.
            tree.bind("<Button-1>", lambda event, name=table_name: self._on_tree_click(event, name), add="+")
            tree.bind("<Double-1>", lambda event, name=table_name: self._on_tree_double_click(event, name))

    @staticmethod
    def _revit_dropdown_values(column_name: str):
        if column_name == "dtype":
            return sorted({str(value) for value in REVIT_DTYPE_TABLE["Data Types"].dropna().tolist()})
        if column_name == "group_under":
            return sorted({str(value) for value in REVIT_PROPERTY_PALLET_TABLE["Property Palette Display Name"].dropna().tolist()})
        if column_name == "category":
            return sorted({str(value) for value in REVIT_FAMILY_CATEGORY_TABLE["Category"].dropna().tolist()})
        return None

    def _on_tree_double_click(self, event, table_name: str):
        self._cancel_pending_tree_edit()
        self._finish_tree_cell_edit(False)
        tree = self.param_tree if table_name == "params" else self.family_tree
        if tree is None:
            return

        row_id = tree.identify_row(event.y)
        if not row_id:
            return

        column_index = tree.identify_column(event.x)
        if not column_index:
            return

        try:
            column_number = int(column_index.replace("#", "")) - 1
        except ValueError:
            return

        columns = self._get_table_columns(table_name)
        if column_number < 0 or column_number >= len(columns):
            return

        row_index = tree.index(row_id)
        current_value = tree.item(row_id, "values")[column_number] if column_number < len(tree.item(row_id, "values")) else ""
        field_name = columns[column_number]
        if field_name in {"status", "validation_message", "guid"}:
            return
        dropdown_values = self._revit_dropdown_values(field_name)

        popup = tk.Toplevel(self.root)
        popup.title(f"Edit {self._humanize_column_name(field_name)}")
        popup.transient(self.root)
        popup.grab_set()
        popup.geometry("360x110")

        ttk.Label(popup, text=f"{self._humanize_column_name(field_name)}:", style="Section.TLabel").pack(anchor="w", padx=10, pady=(10, 4))

        if dropdown_values:
            widget = ttk.Combobox(popup, values=dropdown_values, state="readonly", width=40)
            widget.set("" if current_value is None else str(current_value))
            widget.pack(fill="x", padx=8, pady=8)
            widget.focus_set()

            def commit_edit():
                try:
                    self._apply_cell_value(table_name, row_index, field_name, widget.get())
                except ValueError as exc:
                    messagebox.showerror("Invalid value", str(exc), parent=popup)
                    return
                popup.destroy()

            widget.bind("<<ComboboxSelected>>", lambda _event: commit_edit())
            widget.bind("<Return>", lambda _event: commit_edit())
            return

        value_var = tk.StringVar(value="" if current_value is None else str(current_value))
        entry = ttk.Entry(popup, textvariable=value_var)
        entry.pack(fill="x", padx=8, pady=8)
        entry.focus_set()
        entry.selection_range(0, tk.END)

        # A rename opens a GUID prompt, which takes focus and fires <FocusOut>.
        committing = False

        def commit_edit():
            nonlocal committing
            if committing:
                return
            committing = True
            try:
                self._apply_cell_value(table_name, row_index, field_name, value_var.get())
            except ValueError as exc:
                messagebox.showerror("Invalid value", str(exc), parent=popup)
                committing = False
                return
            popup.destroy()

        entry.bind("<Return>", lambda _event: commit_edit())
        entry.bind("<FocusOut>", lambda _event: commit_edit())

    def render_tables(self):
        self._render_tree(self.param_tree, self.params_df, self._get_table_columns("params"))
        self._render_tree(self.family_tree, self.families_df, self._get_table_columns("families"))
        self._render_tree(self.group_tree, self._build_schedule_summary_df(), self._schedule_summary_columns)

    @staticmethod
    def _render_tree(tree: ttk.Treeview, df: pd.DataFrame, columns: Sequence[str]):
        if tree is None:
            return

        for row in tree.get_children():
            tree.delete(row)

        if df.empty:
            return

        for _, row in df.iterrows():
            values = [row.get(col, "") for col in columns]
            tree.insert("", "end", values=["" if value is None else value for value in values])

    # --- validation -------------------------------------------------------------

    def validate_all(self):
        """Validate the catalog, refresh the tables and list any errors."""
        for schedule in self.catalog.schedules:
            schedule.refresh_params()
        issues = self.catalog.validate()
        self.render_tables()
        self._show_messages(
            [f"{name}: {message}" for _kind, name, message in issues]
            or ["Validation passed. No warnings found."]
        )
        return issues

    # --- editing ----------------------------------------------------------------

    def _apply_cell_value(self, table_name: str, row_index: int, column_name: str, new_value):
        """Apply a table edit through the model. Raises ``ValueError`` for an invalid edit."""
        if column_name in {"status", "validation_message"}:
            raise ValueError(f"{self._humanize_column_name(column_name)} is generated by validation and cannot be edited.")

        if table_name == "params":
            items = self.catalog.params
        elif table_name == "families":
            items = self.catalog.families
        else:
            raise ValueError(f"The {table_name} table can't be edited directly.")
        if row_index < 0 or row_index >= len(items):
            return

        if table_name == "params":
            self._set_param_field(items[row_index], column_name, new_value)
        else:
            self._set_family_field(items[row_index], column_name, new_value)
        self.validate_all()

    def _set_param_field(self, param, column_name: str, new_value):
        value = cell_text(new_value)
        if column_name == "guid":
            raise ValueError("GUID is assigned automatically and changes only when a parameter is renamed.")
        if column_name == "name":
            self._rename_param(param, value)
        elif column_name == "header_text":
            # The name itself means "use the default", so the header keeps following renames.
            param.header_text = None if value == param.name else value
        elif column_name == "grid_column_width":
            param.grid_column_width = parse_width(value)
        elif column_name == "dtype":
            param.dtype = value
        elif column_name == "group_under":
            param.group_under = value or None
        elif column_name == "formula":
            param.formula = value or None
        elif column_name == "instance_param":
            param.instance_param = parse_bool(value)
        elif column_name == "default_value":
            param.value = value or None
        else:
            raise ValueError(f"{self._humanize_column_name(column_name)} can't be edited.")

    def _rename_param(self, param, new_name: str):
        if not new_name:
            raise ValueError("Parameter name is required.")
        if new_name == param.name:
            return
        if self.catalog.get_param(new_name) is not None or new_name in COMMON_PARAM_NAMES:
            raise ValueError(f"Parameter name '{new_name}' is already in use.")
        keep_guid = self._confirm_param_rename(param.name, new_name)
        if keep_guid is None:
            return
        self.catalog.rename_param(param.name, new_name, keep_guid=keep_guid)

    def _confirm_param_rename(self, old_name: str, new_name: str) -> Optional[bool]:
        """Ask whether a rename keeps the GUID. Returns ``keep_guid``, or ``None`` to cancel."""
        choice = messagebox.askyesnocancel(
            "Parameter GUID will change",
            guid_change_warning(old_name, new_name)
            + "\n\nYes: assign a new GUID (default)"
            + "\nNo: keep the current GUID"
            + "\nCancel: don't rename",
            icon=messagebox.WARNING,
            default=messagebox.YES,
            parent=getattr(self, "root", None),
        )
        if choice is None:
            return None
        return not choice

    def _set_family_field(self, fam, column_name: str, new_value):
        value = cell_text(new_value)
        if column_name == "name":
            if not value:
                raise ValueError("Family name is required.")
            fam.name = value
        elif column_name == "category":
            fam.set_category(value or None)
        elif column_name in {"client", "country", "description"}:
            setattr(fam, column_name, value or None)
        else:
            raise ValueError(f"{self._humanize_column_name(column_name)} can't be edited.")

    # --- default value overrides ------------------------------------------------

    # What can be overridden, in table order, with its style-guide term and row label.
    _override_attributes = (
        ("value", "Default Value", "Default Value"),
        ("formula", "Default Formula", "Formula"),
        ("group_under", "Default Group Under", "Group Under"),
    )

    @classmethod
    def _attribute_term(cls, attribute: str) -> str:
        return next(term for name, term, _label in cls._override_attributes if name == attribute)

    def _connected_override_locations(self, location, param_name: str, attribute: str = "value"):
        """Where else, connected to ``location``, the same override can go.

        From a schedule: the other families in that schedule that show the parameter.
        From a family: the schedules that family is in that show the parameter.
        Schedules only hold values, so other attributes have nowhere connected to go.
        Each is a ``(location, label)`` pair.
        """
        if attribute not in Schedule.FAMILY_OVERRIDABLE_ATTRIBUTES:
            return []
        family_name, schedule_name = location
        if schedule_name is not None:
            schedule = self._get_schedule(schedule_name)
            return [
                ((fam.name, schedule_name), fam.name)
                for fam in schedule.fams
                if fam.name != family_name and param_name in schedule.family_param_names(fam)
            ]
        fam = self.catalog.get_family(family_name)
        return [
            ((family_name, schedule.name), schedule.name)
            for schedule in self.catalog.schedules
            if fam in schedule.fams and param_name in schedule.family_param_names(fam)
        ]

    def _override_value(self, location, param_name: str, new_value, attribute: str = "value") -> bool:
        """Override (or, with a blank value, clear) ``attribute`` of a parameter at ``location``.

        ``location`` is ``(family_name, schedule_name)``, with ``None`` for the family
        everywhere. The user can pick connected places to get the same change (other
        families in the schedule, or the family's schedules) and can also make it the
        parameter's default. Returns ``False`` if the user cancels.
        """
        value = cell_text(new_value) or None
        connected = self._connected_override_locations(location, param_name, attribute)
        param = self.catalog.get_param(param_name)

        answer = {"locations": [], "parameter": False}
        if connected or param is not None:
            answer = self._ask_override_scope(param_name, value, location, connected, param is not None, attribute)
            if answer is None:
                return False

        for target in [location, *answer["locations"]]:
            self.catalog.apply_override(target, param_name, **{attribute: value})
        if answer["parameter"]:
            setattr(param, attribute, value)
        self.validate_all()
        return True

    def _override_questions(self, param_name: str, value, location, attribute: str = "value"):
        """The wording of the override prompt: ``(heading, list label, parameter checkbox)``.

        The three levels are always named the same way: Parameter, Family and
        Schedule, followed by the attribute's term (Default Value, Default Formula,
        Default Group Under).
        """
        family_name, schedule_name = location
        verb = "Clear" if value is None else "Override"
        term = self._attribute_term(attribute)
        shown = "(no value)" if value is None else value
        if attribute == "group_under":
            assignment = f"{param_name} Group Under = {shown}"
        else:
            assignment = f"{param_name} = {shown}"
        if schedule_name is None:
            heading = f"{verb} Family {term}\n{family_name}\n{assignment}"
            list_label = f"{verb} Schedule {term} in These Schedules?"
        else:
            heading = f"{verb} Schedule {term}\n{schedule_name}: {family_name}\n{assignment}"
            list_label = f"{verb} Schedule {term} for These Families?"
        parameter = f"{verb} Parameter {term}?\n{assignment}"
        return heading, list_label, parameter

    def _ask_override_scope(self, param_name: str, value, location, connected, ask_parameter: bool,
                            attribute: str = "value"):
        """Ask where else the override goes.

        ``connected`` is a list of ``(location, label)`` pairs to choose from.
        Returns ``{"locations": [...], "parameter": bool}``, or ``None`` to cancel.
        """
        heading, list_label, parameter_text = self._override_questions(param_name, value, location, attribute)
        dialog = tk.Toplevel(self.root)
        dialog.title("Override Default Value")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("480x420" if connected else "480x220")

        ttk.Label(dialog, text=heading, wraplength=450, justify="left", style="Section.TLabel").pack(
            anchor="w", padx=10, pady=(10, 6)
        )

        listbox = None
        if connected:
            ttk.Label(dialog, text=list_label, wraplength=450, justify="left").pack(anchor="w", padx=10)
            list_frame = ttk.Frame(dialog)
            list_frame.pack(fill="both", expand=True, padx=10, pady=(2, 0))
            listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, exportselection=False, height=6)
            for _location, label in connected:
                listbox.insert(tk.END, label)
            scroll = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
            listbox.configure(yscrollcommand=scroll.set)
            listbox.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")
            list_buttons = ttk.Frame(dialog)
            list_buttons.pack(fill="x", padx=10, pady=(2, 4))
            ttk.Button(list_buttons, text="Select All", command=lambda: listbox.selection_set(0, tk.END)).pack(side="left")
            ttk.Button(list_buttons, text="Clear", command=lambda: listbox.selection_clear(0, tk.END)).pack(side="left", padx=(6, 0))

        parameter_var = tk.BooleanVar(value=False)
        if ask_parameter:
            ttk.Checkbutton(dialog, text=parameter_text, variable=parameter_var).pack(anchor="w", padx=10, pady=4)

        result = {"answer": None}

        def apply():
            chosen = [] if listbox is None else [connected[index][0] for index in listbox.curselection()]
            result["answer"] = {"locations": chosen, "parameter": parameter_var.get()}
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", side="bottom", padx=10, pady=8)
        self._info_button(buttons).pack(side="left")
        ttk.Button(buttons, text="Apply", command=apply).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 6))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.wait_window()
        return result["answer"]

    def _info_button(self, parent):
        return ttk.Button(parent, text="ⓘ Override Rules", command=lambda: self._show_override_rules(parent))

    def _show_override_rules(self, parent):
        """A read-only window explaining how default value overrides work."""
        owner = parent.winfo_toplevel()
        info = tk.Toplevel(owner)
        info.title("Override Rules")
        info.transient(owner)
        info.geometry("620x560")

        frame = ttk.Frame(info)
        frame.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        text = tk.Text(frame, wrap="word", relief="flat", padx=8, pady=6, font=("Segoe UI", 10),
                       background="#ffffff", spacing3=2)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.tag_configure("heading", font=("Segoe UI", 11, "bold"), foreground="#1f2937", spacing1=8)
        for heading, body in OVERRIDE_RULES:
            text.insert(tk.END, heading + "\n", "heading")
            text.insert(tk.END, body + "\n")
        text.configure(state="disabled")
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # The override windows are modal; hand the grab over and back.
        previous_grab = owner.grab_current()

        def close():
            info.destroy()
            if previous_grab is not None and previous_grab.winfo_exists():
                previous_grab.grab_set()

        ttk.Button(info, text="Close", command=close).pack(side="right", padx=10, pady=8)
        info.protocol("WM_DELETE_WINDOW", close)
        info.grab_set()
        return info

    # --- default value tables -----------------------------------------------------

    @staticmethod
    def _table_cell(text, state: str = "set", editable: bool = False) -> dict:
        return {"text": "" if text is None else str(text), "state": state, "editable": editable}

    def _parameter_table_rows(self, parameter_names: Sequence[str], families) -> List[dict]:
        """The Parameter section: each column's name and Parameter Default values (read-only)."""
        definitions = [
            self.catalog.get_param(name)
            or next((param for fam in families for param in fam.params if param.name == name), None)
            for name in parameter_names
        ]
        rows = [{"section": "Parameter", "label": "Name", "cells": [self._table_cell(name) for name in parameter_names]}]
        for attribute, _term, label in self._override_attributes:
            rows.append({
                "section": "",
                "label": label,
                "cells": [
                    self._table_cell(None if param is None else getattr(param, attribute))
                    for param in definitions
                ],
            })
        return rows

    def _family_table_rows(self, fam, parameter_names: Sequence[str], schedule=None) -> List[dict]:
        """One row per attribute for ``fam``: its Family Default values, or with
        ``schedule`` its Schedule Default values (only the value is editable there).

        A value set at this level is ``"set"``; one that comes from a level above is
        ``"inherited"``; a column the family doesn't have is ``"none"``, with an
        "Add Parameter to Family" action when the parameter can be added.
        """
        if schedule is None:
            resolved = {param.name: param for param in fam.resolved_params()}
            own_overrides = fam.overrides
        else:
            resolved = {param.name: param for param in schedule.resolved_family_params(fam)}
            own_overrides = schedule.family_overrides.get(fam.name, {})

        rows = []
        for attribute, _term, label in self._override_attributes:
            editable = schedule is None or attribute in Schedule.FAMILY_OVERRIDABLE_ATTRIBUTES
            cells = []
            for name in parameter_names:
                param = resolved.get(name)
                if param is None:
                    cell = self._table_cell(None, "none")
                    if self.catalog.get_param(name) is not None:
                        cell["action"] = "Add Parameter to Family"
                    cells.append(cell)
                    continue
                is_set = editable and attribute in own_overrides.get(name, {})
                cells.append(self._table_cell(getattr(param, attribute), "set" if is_set else "inherited", editable))
            rows.append({
                "section": "" if rows else fam.name,
                "label": label,
                "cells": cells,
                "family": fam.name,
                "attribute": attribute,
            })
        return rows

    def _all_families_row(self, schedule, parameter_names: Sequence[str]) -> dict:
        """The All Families row: a shortcut that sets every family's Schedule Default Value.

        A cell shows the shared value when every family with that column agrees,
        "(Varies)" when they differ, and blank when none has one.
        """
        cells = []
        for name in parameter_names:
            families = [fam for fam in schedule.fams if name in schedule.family_param_names(fam)]
            if not families:
                cells.append(self._table_cell(None, "none"))
                continue
            values = {
                schedule.family_overrides.get(fam.name, {}).get(name, {}).get("value")
                for fam in families
            }
            if len(values) > 1:
                cells.append(self._table_cell("(Varies)", "inherited", True))
            else:
                value = values.pop()
                cells.append(self._table_cell(value, "inherited" if value is None else "set", True))
        return {
            "section": ALL_FAMILIES,
            "label": "Default Value",
            "cells": cells,
            "family": None,
            "attribute": "value",
            "all_families": True,
        }

    def _override_all_families(self, schedule_name: str, param_name: str, new_value) -> bool:
        """Set (or clear) the Schedule Default Value of every family in the schedule with the column.

        The prompt only offers the Parameter Default Value, since every family is
        already covered. Returns ``False`` if the user cancels.
        """
        value = cell_text(new_value) or None
        schedule = self._get_schedule(schedule_name)
        targets = [
            (fam.name, schedule_name) for fam in schedule.fams
            if param_name in schedule.family_param_names(fam)
        ]
        param = self.catalog.get_param(param_name)
        answer = {"locations": [], "parameter": False}
        if param is not None:
            answer = self._ask_override_scope(param_name, value, (ALL_FAMILIES, schedule_name), [], True)
            if answer is None:
                return False
        for target in targets:
            self.catalog.apply_override(target, param_name, value=value)
        if answer["parameter"]:
            param.value = value
        self.validate_all()
        return True

    def _schedule_table_rows(self, schedule) -> List[dict]:
        parameter_names = self._get_schedule_parameter_names(schedule)
        rows = self._parameter_table_rows(parameter_names, schedule.fams)
        rows.append(self._all_families_row(schedule, parameter_names))
        for fam in schedule.fams:
            rows.extend(self._family_table_rows(fam, parameter_names, schedule))
        return rows

    def _family_window_rows(self, fam) -> List[dict]:
        parameter_names = [param.name for param in fam.custom_params]
        return self._parameter_table_rows(parameter_names, [fam]) + self._family_table_rows(fam, parameter_names)

    def _add_parameter_from_table(self, table: "OverrideTable", rows_builder, row_index: int, column_index: int):
        """The "Add Parameter to Family" button: link the column's parameter to the row's family."""
        fam = self.catalog.get_family(table.rows[row_index]["family"])
        param = self.catalog.get_param(table.parameter_names[column_index])
        try:
            fam.add_param(param)
        except ValueError as exc:
            messagebox.showerror("Cannot add parameter", str(exc), parent=table.winfo_toplevel())
            return
        self.validate_all()
        table.set_rows(rows_builder())

    def _edit_table_cell(self, table: "OverrideTable", rows_builder, schedule_name, row_index: int, column_index: int):
        """Edit one table cell in place; on commit, run the override prompt and refresh.

        Tab moves on to the next editable cell in the row.
        """
        row = table.rows[row_index]
        if not row["cells"][column_index].get("editable"):
            return None
        param_name = table.parameter_names[column_index]
        attribute = row["attribute"]
        family_name = row["family"]
        all_families = row.get("all_families", False)
        if all_families:
            cell = row["cells"][column_index]
            own = {attribute: cell["text"]} if cell["state"] == "set" else {}
            if cell["text"] == "(Varies)":
                placeholder = "Varies: Type a Value to Set Every Family"
            else:
                placeholder = "Blank Uses Each Family Default Value"
        elif schedule_name is None:
            own = self.catalog.get_family(family_name).overrides.get(param_name, {})
            placeholder = f"Blank Uses Parameter {self._attribute_term(attribute)}"
        else:
            own = self._get_schedule(schedule_name).family_overrides.get(family_name, {}).get(param_name, {})
            placeholder = f"Blank Uses Family {self._attribute_term(attribute)}"
        current = own.get(attribute)
        current = "" if current is None else str(current)

        def commit(text):
            if cell_text(text) == current:
                return
            try:
                if all_families:
                    self._override_all_families(schedule_name, param_name, text)
                else:
                    self._override_value((family_name, schedule_name), param_name, text, attribute)
            except ValueError as exc:
                messagebox.showerror("Invalid value", str(exc), parent=table.winfo_toplevel())
            table.set_rows(rows_builder())

        def edit_next():
            cells = table.rows[row_index]["cells"]
            next_column = next(
                (index for index in range(column_index + 1, len(cells)) if cells[index].get("editable")),
                None,
            )
            if next_column is not None:
                self._edit_table_cell(table, rows_builder, schedule_name, row_index, next_column)

        return table.start_cell_edit(
            row_index,
            column_index,
            current,
            commit,
            placeholder=placeholder,
            choices=self._revit_dropdown_values("group_under") if attribute == "group_under" else None,
            on_tab=edit_next,
        )

    def _build_override_table(self, parent, parameter_names, rows, **kwargs) -> "OverrideTable":
        """An ``OverrideTable`` with scroll bars, packed into ``parent``."""
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        table = OverrideTable(frame, parameter_names, rows=rows, **kwargs)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=table.xview)
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
        table.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        return table

    # --- schedules --------------------------------------------------------------

    def _get_schedule(self, schedule_name: str):
        schedule = self.catalog.get_schedule(schedule_name)
        if schedule is None:
            raise ValueError("Schedule not found: {}".format(schedule_name))
        return schedule

    @staticmethod
    def _get_schedule_parameter_names(schedule) -> List[str]:
        return [param.name for param in schedule.params]

    @staticmethod
    def _get_schedule_header_text(schedule, parameter_name: str) -> str:
        param = next((param for param in schedule.params if param.name == parameter_name), None)
        return parameter_name if param is None else param.header_text

    def _get_schedule_grid_column_width(self, schedule, parameter_name: str) -> float:
        param = next((param for param in schedule.params if param.name == parameter_name), None)
        return self._default_grid_column_width_in if param is None else param.grid_column_width

    def _set_schedule_column(self, schedule_name: str, parameter_name: str, header_text: str, width_text: str):
        """Set or clear a schedule's header text and column width overrides for one column."""
        width_text = cell_text(width_text)
        width = None
        if width_text:
            try:
                width = Param._coerce_grid_column_width(width_text)
            except ValueError:
                raise ValueError("Width must be a finite, positive number of inches.") from None
        schedule = self._get_schedule(schedule_name)
        schedule.override_param(
            parameter_name,
            header_text=cell_text(header_text),
            grid_column_width=width,
        )
        self.validate_all()

    def _add_schedule_header_group(self, schedule_name: str, parameter_names: Sequence[str], caption: str):
        group = self._get_schedule(schedule_name).add_header_group(caption, parameter_names)
        self.validate_all()
        return group

    # --- detail windows ---------------------------------------------------------

    # Long enough to tell a single click from the first click of a double-click.
    _single_click_delay_ms = 300

    def _tree_cell_at(self, tree: ttk.Treeview, table_name: str, event):
        """``(row_id, column_number)`` of the body cell under the event, or ``None``."""
        if tree.identify_region(event.x, event.y) != "cell":
            return None
        row_id = tree.identify_row(event.y)
        try:
            column_number = int(tree.identify_column(event.x).replace("#", "")) - 1
        except ValueError:
            return None
        if not row_id or not 0 <= column_number < len(self._get_table_columns(table_name)):
            return None
        return row_id, column_number

    def _cancel_pending_tree_edit(self):
        pending = getattr(self, "_pending_tree_edit", None)
        if pending is not None:
            self.root.after_cancel(pending)
            self._pending_tree_edit = None

    def _on_tree_click(self, event, table_name: str):
        self._cancel_pending_tree_edit()
        tree = self.param_tree if table_name == "params" else self.family_tree
        cell = self._tree_cell_at(tree, table_name, event)
        if cell is None:
            return

        def start():
            self._pending_tree_edit = None
            self._start_tree_cell_edit(tree, table_name, *cell)

        # Wait in case this is the first click of a double-click.
        self._pending_tree_edit = self.root.after(self._single_click_delay_ms, start)

    def _on_family_tree_double_click(self, event):
        self._cancel_pending_tree_edit()
        self._finish_tree_cell_edit(False)
        self._open_selected_family_window(event)

    def _start_tree_cell_edit(self, tree: ttk.Treeview, table_name: str, row_id: str, column_number: int):
        """Edit one cell of a main table in place: Enter or clicking away saves, Escape cancels."""
        self._finish_tree_cell_edit(False)
        field_name = self._get_table_columns(table_name)[column_number]
        if field_name in {"status", "validation_message", "guid"} or not tree.exists(row_id):
            return
        bbox = tree.bbox(row_id, f"#{column_number + 1}")
        if not bbox:
            return
        row_index = tree.index(row_id)
        values = tree.item(row_id, "values")
        current_value = str(values[column_number]) if column_number < len(values) else ""

        dropdown_values = self._revit_dropdown_values(field_name)
        if dropdown_values:
            editor = ttk.Combobox(tree, values=[""] + dropdown_values, state="readonly")
            editor.set(current_value)
        else:
            editor = ttk.Entry(tree)
            editor.insert(0, current_value)
            editor.selection_range(0, tk.END)
        x, y, width, height = bbox
        editor.place(x=x, y=y, width=width, height=height)
        editor.focus_set()

        finishing = False

        def finish(save: bool):
            nonlocal finishing
            if finishing or not editor.winfo_exists():
                return
            finishing = True
            new_value = editor.get()
            if save and new_value != current_value:
                try:
                    self._apply_cell_value(table_name, row_index, field_name, new_value)
                except ValueError as exc:
                    messagebox.showerror("Invalid value", str(exc), parent=self.root)
                    finishing = False
                    if editor.winfo_exists():
                        editor.focus_set()
                    return
            self._tree_cell_editor = None
            editor.destroy()

        self._tree_cell_editor = (editor, finish)
        editor.bind("<Return>", lambda _event: finish(True))
        editor.bind("<KP_Enter>", lambda _event: finish(True))
        editor.bind("<Escape>", lambda _event: finish(False))

        def focus_out(_event):
            # Opening the dropdown list moves focus into the combobox's own popdown.
            def check():
                if editor.winfo_exists() and not str(editor.tk.call("focus")).startswith(str(editor)):
                    finish(True)
            editor.after_idle(check)

        editor.bind("<FocusOut>", focus_out)
        if dropdown_values:
            editor.bind("<<ComboboxSelected>>", lambda _event: finish(True))

    def _finish_tree_cell_edit(self, save: bool):
        cell_editor = getattr(self, "_tree_cell_editor", None)
        if cell_editor is not None:
            cell_editor[1](save)

    def _open_selected_family_window(self, event):
        if self.family_tree is None:
            return
        row_id = self.family_tree.identify_row(event.y)
        if not row_id:
            return
        row_index = self.family_tree.index(row_id)
        self._open_detail_window("family", row_index)

    def _open_selected_schedule_window(self, event):
        if self.group_tree is None:
            return
        row_id = self.group_tree.identify_row(event.y)
        if not row_id:
            return
        row_index = self.group_tree.index(row_id)
        if row_index < 0 or row_index >= len(self.catalog.schedules):
            return
        self._open_detail_window("schedule", self.catalog.schedules[row_index].name)

    def _open_detail_window(self, item_type: str, row_index_or_name):
        if item_type == "family":
            self._open_family_window(row_index_or_name)
        else:
            self._open_schedule_window(str(row_index_or_name))

    def _open_family_window(self, row_index: int):
        if row_index < 0 or row_index >= len(self.catalog.families):
            return
        fam = self.catalog.families[row_index]
        columns = self._get_table_columns("families")
        title = "Family Details"

        form = tk.Toplevel(self.root)
        form.title(title)
        form.transient(self.root)
        form.grab_set()
        form.geometry("960x760")
        title_bar = ttk.Frame(form)
        title_bar.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(title_bar, text=title, style="Title.TLabel").pack(side="left")
        self._info_button(title_bar).pack(side="right")

        row = self.families_df.iloc[row_index]
        entries = {}
        for col in columns:
            if col in {"status", "validation_message"}:
                ttk.Label(
                    form,
                    text=f"{self._humanize_column_name(col)}: {row.get(col)}",
                    wraplength=920,
                    justify="left",
                ).pack(anchor="w", padx=12, pady=(6, 0))
                continue
            ttk.Label(form, text=self._humanize_column_name(col), style="Section.TLabel").pack(anchor="w", padx=12, pady=(6, 0))
            dropdown_values = self._revit_dropdown_values(col)
            if dropdown_values:
                combo = ttk.Combobox(form, values=dropdown_values, state="readonly", width=90)
                combo.set(str(row.get(col)))
                entries[col] = combo
                combo.pack(fill="x", padx=12, pady=(0, 4))
                continue
            value = tk.StringVar(value=str(row.get(col)))
            entries[col] = value
            ttk.Entry(form, textvariable=value, width=90).pack(fill="x", padx=12, pady=(0, 4))

        def save_changes():
            try:
                # Name first, so a rejected name leaves the other fields untouched.
                self._set_family_field(fam, "name", entries["name"].get())
                for col, widget in entries.items():
                    if col != "name":
                        self._set_family_field(fam, col, widget.get())
            except ValueError as exc:
                messagebox.showerror("Invalid value", str(exc), parent=form)
                return
            self.validate_all()
            form.destroy()

        ttk.Button(form, text="Save", command=save_changes, style="Action.TButton").pack(pady=(8, 4))

        values_box = ttk.LabelFrame(form, text="Family Default Values (double-click a value to edit it)", padding=8)
        values_box.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        rows_builder = lambda: self._family_window_rows(fam)  # noqa: E731 - rebuilt after each edit
        table = self._build_override_table(
            values_box,
            [param.name for param in fam.custom_params],
            rows_builder(),
            show_header=False,
            on_cell_double_click=lambda row_index, column_index: self._edit_table_cell(
                table, rows_builder, None, row_index, column_index
            ),
        )

    def _open_schedule_window(self, selected_name: str):
        schedule = self.catalog.get_schedule(selected_name)
        if schedule is None:
            return

        form = tk.Toplevel(self.root)
        form.title(f"Schedule Details: {selected_name}")
        form.transient(self.root)
        form.grab_set()
        form.geometry("1040x760")

        title_bar = ttk.Frame(form)
        title_bar.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(title_bar, text=f"Schedule: {selected_name}", style="Title.TLabel").pack(side="left")
        self._info_button(title_bar).pack(side="right")
        ttk.Label(form, text=f"Status: {schedule.status}", style="Section.TLabel").pack(anchor="w", padx=12, pady=(0, 6))
        ttk.Label(form, text=f"Validation: {schedule.validation_message or 'None'}", wraplength=1000, justify="left").pack(anchor="w", padx=12, pady=(0, 8))

        table_box = ttk.LabelFrame(
            form,
            text="Schedule Default Values (double-click a value to edit it, a header for column settings)",
            padding=8,
        )
        table_box.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        parameter_names = self._get_schedule_parameter_names(schedule)
        if not parameter_names:
            ttk.Label(table_box, text="No parameters assigned").pack(anchor="w")
            ttk.Button(form, text="Close", command=form.destroy, style="Action.TButton").pack(pady=(0, 10))
            return

        def edit_schedule_header(parameter_name):
            current_override = schedule.header_text_overrides.get(parameter_name, "")
            width_override = schedule.grid_column_width_overrides.get(parameter_name)
            current_width_override = "" if width_override is None else f"{width_override:g}"
            default_param = next(
                param for fam in schedule.fams for param in fam.resolved_params()
                if param.name == parameter_name
            )
            default_header = default_param.header_text
            default_width = default_param.grid_column_width

            editor = tk.Toplevel(form)
            editor.title("Schedule Column Settings")
            editor.transient(form)
            editor.grab_set()
            editor.geometry("420x210")
            ttk.Label(editor, text="Schedule Header Text", style="Section.TLabel").pack(
                anchor="w", padx=10, pady=(10, 4)
            )
            header_entry = PlaceholderEntry(editor, placeholder=default_header)
            if current_override:
                header_entry.insert(0, current_override)
            header_entry.pack(fill="x", padx=10, pady=4)
            ttk.Label(editor, text="Schedule Column Width (in)", style="Section.TLabel").pack(
                anchor="w", padx=10, pady=(8, 4)
            )
            width_entry = PlaceholderEntry(editor, placeholder=f"{default_width:g}")
            if current_width_override:
                width_entry.insert(0, current_width_override)
            width_entry.pack(fill="x", padx=10, pady=4)
            header_entry.focus_set()

            def save_header_override():
                try:
                    self._set_schedule_column(selected_name, parameter_name, header_entry.get(), width_entry.get())
                except ValueError as exc:
                    messagebox.showwarning("Invalid width", str(exc), parent=editor)
                    return
                table.set_header_texts({
                    name: self._get_schedule_header_text(schedule, name) for name in parameter_names
                })
                table.set_grid_column_widths([
                    self._get_schedule_grid_column_width(schedule, name) for name in parameter_names
                ])
                editor.destroy()

            buttons = ttk.Frame(editor)
            buttons.pack(fill="x", padx=10, pady=(4, 8))
            ttk.Button(buttons, text="Save", command=save_header_override).pack(side="right")
            ttk.Button(buttons, text="Cancel", command=editor.destroy).pack(side="right", padx=(0, 6))
            header_entry.bind("<Return>", lambda _event: save_header_override())
            width_entry.bind("<Return>", lambda _event: save_header_override())

        rows_builder = lambda: self._schedule_table_rows(schedule)  # noqa: E731 - rebuilt after each edit
        table = self._build_override_table(
            table_box,
            parameter_names,
            rows_builder(),
            header_texts={name: self._get_schedule_header_text(schedule, name) for name in parameter_names},
            groups=schedule.header_groups,
            on_header_double_click=edit_schedule_header,
            on_cell_double_click=lambda row_index, column_index: self._edit_table_cell(
                table, rows_builder, selected_name, row_index, column_index
            ),
            on_cell_action=lambda row_index, column_index: self._add_parameter_from_table(
                table, rows_builder, row_index, column_index
            ),
            grid_column_widths=[
                self._get_schedule_grid_column_width(schedule, name) for name in parameter_names
            ],
        )

        group_controls = ttk.Frame(form)
        group_controls.pack(fill="x", padx=12)

        def begin_header_group():
            selected_parameters = table.get_selected_parameter_names()
            if len(selected_parameters) < 2:
                messagebox.showwarning(
                    "Select headers",
                    "Select at least two adjacent parameter headers to group.",
                    parent=form,
                )
                return

            editor = tk.Toplevel(form)
            editor.title("Name Header Group")
            editor.transient(form)
            editor.grab_set()
            editor.geometry("360x130")
            ttk.Label(editor, text="Group name:", style="Section.TLabel").pack(
                anchor="w", padx=10, pady=(10, 4)
            )
            caption_var = tk.StringVar()
            caption_entry = ttk.Entry(editor, textvariable=caption_var)
            caption_entry.pack(fill="x", padx=10, pady=4)
            caption_entry.focus_set()

            def save_header_group():
                caption = caption_var.get().strip()
                if not caption:
                    messagebox.showwarning(
                        "Group name required",
                        "Enter a name for this header group.",
                        parent=editor,
                    )
                    return
                try:
                    self._add_schedule_header_group(selected_name, selected_parameters, caption)
                except ValueError as exc:
                    messagebox.showwarning("Cannot group headers", str(exc), parent=editor)
                    return
                table.set_groups(schedule.header_groups)
                editor.destroy()

            buttons = ttk.Frame(editor)
            buttons.pack(fill="x", padx=10, pady=(4, 8))
            ttk.Button(buttons, text="Group", command=save_header_group).pack(side="right")
            ttk.Button(buttons, text="Cancel", command=editor.destroy).pack(side="right", padx=(0, 6))
            caption_entry.bind("<Return>", lambda _event: save_header_group())

        ttk.Button(group_controls, text="Group Selected Headers", command=begin_header_group).pack(side="left")
        ttk.Button(form, text="Close", command=form.destroy, style="Action.TButton").pack(pady=(8, 10))

    # --- files ------------------------------------------------------------------

    def save_checkpoint(self):
        self._save_to(self.checkpoint_path)

    def save_checkpoint_as(self):
        checkpoint_path = filedialog.asksaveasfilename(
            title="Save DDM Database As",
            initialdir=str(DEFAULT_CHECKPOINT_PATH.parent),
            initialfile=DEFAULT_CHECKPOINT_PATH.name,
            defaultextension=".ddm.json",
            filetypes=[
                ("DDM databases", "*.ddm.json"),
                ("CSV databases", "*.ddm.csv"),
                ("All files", "*.*"),
            ],
        )
        if not checkpoint_path:
            return
        self._save_to(checkpoint_path)

    def _save_to(self, database_path):
        """Save the catalog as JSON, plus a readable CSV and the Revit exports alongside."""
        output_paths = get_database_output_paths(database_path)
        self.checkpoint_path = output_paths["checkpoint"]
        try:
            self._write_checkpoint(output_paths["checkpoint"])
            write_database_csv(self.catalog, output_paths["csv"])
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=getattr(self, "root", None))
            return
        self._append_message(f"Saved readable database CSV to {output_paths['csv']}")
        self._generate_revit_schedule_macro_file()
        self._generate_rfps_file()
        self._generate_shared_parameter_file()

    def _write_checkpoint(self, checkpoint_path):
        self.catalog.save(str(checkpoint_path))
        self._show_messages([f"Saved database to {checkpoint_path}"])

    def load_checkpoint(self, checkpoint_path=None):
        if checkpoint_path is None:
            checkpoint_path = filedialog.askopenfilename(
                title="Load DDM Database",
                initialdir=str(DEFAULT_CHECKPOINT_PATH.parent),
                filetypes=[
                    ("DDM databases", "*.ddm.json"),
                    ("CSV databases", "*.ddm.csv"),
                    ("Older pickle databases", "*.ddm.pkl"),
                    ("All files", "*.*"),
                ],
            )
        if not checkpoint_path:
            return

        if not os.path.exists(checkpoint_path):
            messagebox.showwarning("Database missing", f"No database found at {checkpoint_path}")
            return

        try:
            catalog, issues = self._read_database(checkpoint_path)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
                pd.errors.ParserError, pickle.UnpicklingError, EOFError) as exc:
            messagebox.showerror("Load error", str(exc), parent=getattr(self, "root", None))
            return

        self.catalog = catalog
        self.load_issues = issues
        self.checkpoint_path = Path(checkpoint_path)
        self.validate_all()
        lines = [f"Loaded database from {checkpoint_path}"]
        if issues:
            lines.append(f"{len(issues)} problem(s) in the file were fixed or skipped while loading:")
            lines.extend(f"  {issue}" for issue in issues)
        if self.warning_text is not None:
            self.warning_text.insert("1.0", "\n".join(lines) + "\n\n")

    @staticmethod
    def _read_database(path):
        """Read a JSON, CSV or older pickle database. Returns ``(catalog, issues)``."""
        suffix = str(path).lower()
        if suffix.endswith(".json"):
            catalog, _extra = Catalog.load(path)
            return catalog, []
        if suffix.endswith(".csv"):
            tables, header_groups = read_database_csv(path)
        else:
            with open(path, "rb") as handle:
                payload = pickle.load(handle)
            tables, header_groups = tables_from_legacy_pickle(payload)
        return catalog_from_tables(header_groups=header_groups, **tables)

    # --- Quickbase --------------------------------------------------------------

    def sync_to_quickbase(self):
        if QuickbaseClient is None or QuickbaseSyncService is None:
            messagebox.showwarning(
                "Quickbase not available",
                "The Quickbase sync classes were not imported. Confirm that quickbase_integration.py is available.",
            )
            return

        app_id = os.getenv("QB_APP_ID")
        user_token = os.getenv("QB_USER_TOKEN")
        if not app_id or not user_token:
            messagebox.showwarning(
                "Quickbase configuration missing",
                "Set QB_APP_ID and QB_USER_TOKEN in your environment before syncing.",
            )
            return

        validation_errors = len(self.validate_all())
        if validation_errors:
            messagebox.showwarning(
                "Validation failed",
                f"Resolve {validation_errors} validation error(s) before syncing. See Messages for details.",
            )
            return

        try:
            client = QuickbaseClient(app_id=app_id, user_token=user_token, app_token=os.getenv("QB_APP_TOKEN"))
            sync = QuickbaseSyncService(client)
            for _, row in self.params_df.iterrows():
                sync.map_param_record(row.to_dict())
            for _, row in self.families_df.iterrows():
                sync.map_family_record(row.to_dict())
            self._show_messages(["Quickbase mapping prepared. Connect real table IDs before live sync."])
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Quickbase sync error", str(exc))


def main():
    root = tk.Tk()
    app = DDMGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
