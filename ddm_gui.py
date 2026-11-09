import json
import os
import pickle
import threading
import tkinter.font as tkfont
import urllib.parse
import webbrowser
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from config.revit_dtype_definitions import REVIT_DTYPE_TABLE
from config.revit_family_category_definitions import REVIT_FAMILY_CATEGORY_TABLE
from config.revit_property_pallet_definitions import REVIT_PROPERTY_PALLET_TABLE
from config.app_paths import (
    APP_VERSION,
    DEFAULT_CHECKPOINT_PATH,
    FROZEN,
    NEW_ISSUE_URL,
    STARTER_DATABASE_PATH,
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
from ddm_combined import CombinedParamWindows
from ddm_sections import SectionWindows
from excel_import import import_workbook
from revit_parameter_manager import (
    CODE_KINDS, CODE_LABELS, CODED_KINDS, COMMON_PARAM_NAMES, FAMILY_NAME_TERMS, PARAM_NAME_COMPANY, PARAM_NAME_LONG_LENGTH,
    PARAM_NAME_TERMS, SCHEDULE_FILTER_PARAM, Catalog, Param, Schedule, build_param_name, guid_change_warning,
)
from revit_macro_module import (
    MACROS_ROOT, USER_SETTINGS_PATH, build_module, choose_module, chosen_module, find_macro_modules,
)
from revit_schedule_macro_generator import generate_schedule_macro_source, install_macro
from table_view import (
    DEFAULT_TABLE_VIEW,
    ColumnResizer,
    apply_table_style,
    fitted_width,
    next_sort,
    sort_mark,
    sorted_rows,
    tree_body_font,
)
from revit_parameter_scheduler_export import generate_rfps_content, generate_rfps_schedules_content
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
# The schedule table section whose rows set every family at once.
ALL_FAMILIES_SECTION = "Apply to All Families"

# Last choice in the Client and Country dropdowns; opens a dialog to add one that isn't listed.
ADD_NEW = "Add New..."

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
        "Formula, Group Under and Instance or Type: at the Parameter and Family levels only. They "
        "describe the family, so in a schedule a family's row (or the Apply to All Families rows) sets "
        "the family's own, which every schedule it's in uses. Blank uses the parameter's."
    )),
    ("Reading the Tables", (
        "Black text: set at this level.\n"
        "Gray text: inherited from the level above.\n"
        "Bold: in a schedule, the value the schedule ends up using (the family's own, or the "
        "parameter's when a family doesn't set one).\n"
        "Shaded cell: doesn't apply, for example the family doesn't have that parameter. In a "
        "schedule, an \"Add Parameter to Family\" button adds the missing parameter to the family.\n"
        "Double-click a cell to edit it in place. Enter or clicking away saves, Tab moves to the "
        "next cell, Escape cancels.\n"
        "In a schedule, the Parameter section edits the parameter itself, for every family and "
        "schedule, like the Parameters tab."
    )),
    ("The Apply to All Families Rows", (
        "In a schedule, the Apply to All Families rows are a shortcut, not another level. They set every "
        "family in the schedule that has that column:\n"
        "Default Value: becomes each family's Schedule Default Value, in this schedule only.\n"
        "Formula and Group Under: become each family's Family Default Formula or Group Under. "
        "Revit keeps these in the family, so they change the family in every schedule it's in.\n"
        "Each cell shows the shared value, \"(Varies)\" when the families differ, or blank when "
        "none is set. Leaving a \"(Varies)\" cell unchanged changes nothing."
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
    With ``hidden_names`` (a set) a Hidden Column row of checkboxes follows the
    column headers; clicking one calls ``on_hidden_toggle(parameter_name)``.
    With ``width_cells`` (one cell per column) a Column Width row follows that;
    clicking one calls ``on_width_click(column_index)``.

    Clicking a column header, or a cell in a row with ``"selects_column"``, selects
    that column; clicking a family's labels selects the family. Ctrl adds to the
    selection and Shift selects a range. Columns and families aren't selected together.

    With ``edit_on_click`` one click on an editable cell edits it (``on_cell_double_click``
    is then called on that click). A cell with ``"bold": True`` is drawn in bold.

    A section's first row with ``"family_action": text`` gets a button with that text under
    the section label; clicking it calls ``on_family_action(family)``.

    The two label columns and the header rows (group levels, column headers, Hidden Column,
    Column Width) are frozen: they stay in place while the table scrolls. Drawn items in them
    carry the tags ``frozen_x`` and ``frozen_y``, moved to follow the view after every scroll.

    Body rows are dicts: ``{"section": str, "label": str, "cells": [cell, ...]}``,
    plus any keys the caller needs back. A cell is ``{"text": str, "state": ...,
    "editable": bool}`` where state is ``"set"`` (set at this level),
    ``"inherited"`` (shown in gray, from a level above) or ``"none"`` (shaded,
    doesn't apply).
    """

    section_width = 150
    label_width = 170
    row_height = 24
    # Screen pixels per inch of Revit grid column width, and the narrowest readable column.
    pixels_per_inch = 72
    min_column_width = 110

    def __init__(self, master, parameter_names, header_texts=None, groups=None, rows=None,
                 show_header=True, on_header_double_click=None, on_cell_double_click=None,
                 grid_column_widths=None, on_cell_action=None, hidden_names=None, on_hidden_toggle=None,
                 edit_on_click=False, on_family_action=None, width_cells=None, on_width_click=None,
                 header_label="Schedule"):
        super().__init__(master, background="#ffffff", highlightthickness=0)
        # Names the header rows on the left: what they belong to.
        self.header_label = header_label
        self.parameter_names = list(parameter_names)
        self.header_texts = dict(header_texts or {})
        self.show_header = show_header
        self.rows = list(rows or [])
        self.groups = []
        self.group_layout = []
        self.selected_indices = set()
        self.selection_anchor = None
        self.selected_families = set()
        self.family_anchor = None
        self.on_header_double_click = on_header_double_click
        self.on_cell_double_click = on_cell_double_click
        self.on_cell_action = on_cell_action
        self.edit_on_click = edit_on_click
        self.on_family_action = on_family_action
        # Each family's button under its name: {family: (left, top, right, bottom)}.
        self._family_action_boxes = {}
        self.hidden_names = None if hidden_names is None else set(hidden_names)
        self.on_hidden_toggle = on_hidden_toggle
        self.width_cells = None if width_cells is None else list(width_cells)
        self.on_width_click = on_width_click
        self.column_width = 170
        self.column_widths = []
        self.column_offsets = []
        self.group_row_height = 30
        self.header_height = 58 if show_header else 0
        self.header_font = tkfont.Font(root=self, font=DEFAULT_TABLE_VIEW.heading_font)
        self.label_font = tkfont.Font(root=self, font=("Segoe UI", 9, "bold"))
        self.body_font = tkfont.Font(root=self, font=("Segoe UI", 9))
        self.body_bold_font = tkfont.Font(root=self, font=("Segoe UI", 9, "bold"))
        self.header_top = 0
        self._cell_editor = None
        # How far the frozen items are moved now, to follow the view: (x, y).
        self._frozen_offset = (0, 0)
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
    def hidden_row_top(self):
        return self.header_top + self.header_height

    @property
    def hidden_row_height(self):
        return self.row_height if self.show_header and self.hidden_names is not None else 0

    @property
    def width_row_top(self):
        return self.hidden_row_top + self.hidden_row_height

    @property
    def width_row_height(self):
        return self.row_height if self.show_header and self.width_cells is not None else 0

    @property
    def body_top(self):
        return self.width_row_top + self.width_row_height

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

    def set_hidden_names(self, hidden_names):
        self.hidden_names = set(hidden_names)
        self._draw_grid()

    def set_width_cells(self, width_cells):
        self.width_cells = list(width_cells)
        self._draw_grid()

    def get_selected_parameter_names(self):
        return [
            self.parameter_names[index]
            for index in range(len(self.parameter_names))
            if index in self.selected_indices
        ]

    def get_selected_family_names(self):
        return [name for name in self._family_names() if name in self.selected_families]

    def _family_names(self):
        """The families with rows in the table, in order."""
        return list(dict.fromkeys(row["family"] for row in self.rows if row.get("family")))

    def _cx(self, event):
        """The canvas x under the event; the frozen label columns don't scroll."""
        return event.x if event.x < self.left else self.canvasx(event.x)

    def _cy(self, event):
        """The canvas y under the event; the frozen header rows don't scroll."""
        return event.y if event.y < self.body_top else self.canvasy(event.y)

    def on_view_changed(self):
        """After a scroll: move the frozen columns and rows back into view."""
        x, y = self.canvasx(0), self.canvasy(0)
        dx, dy = x - self._frozen_offset[0], y - self._frozen_offset[1]
        if dx:
            self.move("frozen_x", dx, 0)
        if dy:
            self.move("frozen_y", 0, dy)
        self._frozen_offset = (x, y)

    def _freeze(self):
        """Tag what was just drawn in the label columns and header rows, and stack them on top."""
        for item in self.find_all():
            if self.type(item) == "window":
                continue
            coords = self.coords(item)
            in_columns = max(coords[0::2]) <= self.left
            in_rows = self.show_header and max(coords[1::2]) <= self.body_top
            if in_rows:
                self.addtag_withtag("frozen_y", item)
            if in_columns:
                self.addtag_withtag("frozen_x", item)
            if in_rows and in_columns:
                self.addtag_withtag("frozen_corner", item)
        self.tag_raise("frozen_y")
        self.tag_raise("frozen_x")
        self.tag_raise("frozen_corner")
        self._frozen_offset = (0, 0)
        self.on_view_changed()

    def _column_at(self, canvas_x):
        for index, (left, width) in enumerate(zip(self.column_offsets, self.column_widths)):
            if left <= canvas_x < left + width:
                return index
        return None

    def _parameter_index_at(self, event):
        """The column whose header was clicked, or ``None`` outside the header row."""
        canvas_y = self._cy(event)
        if not self.show_header or not self.parameter_names:
            return None
        if not self.header_top <= canvas_y < self.hidden_row_top:
            return None
        return self._column_at(self._cx(event))

    def _selectable_column_at(self, event):
        """The column whose header, or a cell in a ``"selects_column"`` row, is under the event."""
        index = self._parameter_index_at(event)
        if index is not None:
            return index
        cell = self._cell_at(event)
        if cell is not None and self.rows[cell[0]].get("selects_column"):
            return cell[1]
        return None

    def _family_at(self, event):
        """The family whose labels (left of its values) are under the event, or ``None``."""
        canvas_y = self._cy(event)
        if self._cx(event) >= self.left or canvas_y < self.body_top:
            return None
        row_index = int((canvas_y - self.body_top) // self.row_height)
        return self.rows[row_index].get("family") if row_index < len(self.rows) else None

    def _hidden_toggle_at(self, event):
        """The column whose Hidden Column checkbox is under the event, or ``None``."""
        if not self.hidden_row_height:
            return None
        if not self.hidden_row_top <= self._cy(event) < self.width_row_top:
            return None
        return self._column_at(self._cx(event))

    def _width_cell_at(self, event):
        """The column whose Column Width cell is under the event, or ``None``."""
        if not self.width_row_height:
            return None
        if not self.width_row_top <= self._cy(event) < self.body_top:
            return None
        return self._column_at(self._cx(event))

    def _cell_at(self, event):
        """``(row_index, column_index)`` of the body cell under the event, or ``None``."""
        canvas_y = self._cy(event)
        if canvas_y < self.body_top:
            return None
        row_index = int((canvas_y - self.body_top) // self.row_height)
        column_index = self._column_at(self._cx(event))
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

    def width_cell_bbox(self, column_index: int):
        """``(left, top, width, height)`` of a Column Width cell in canvas coordinates, where it
        shows now (the header rows are frozen)."""
        return (
            self.column_offsets[column_index],
            self.width_row_top + self._frozen_offset[1],
            self.column_widths[column_index],
            self.width_row_height,
        )

    def start_cell_edit(self, row_index: int, column_index: int, value: str, on_commit,
                        placeholder: str = "", choices=None, on_tab=None, bbox=None):
        """Edit one body cell in place, with a box laid over the cell.

        Enter, Tab or clicking elsewhere commits and calls ``on_commit(text)``;
        Escape cancels. Tab then calls ``on_tab()`` to move on. With ``choices`` the
        box is a drop-down whose blank first entry clears the value. ``bbox`` places
        the box over a cell outside the body.
        """
        self.finish_cell_edit(commit=True)
        left, top, width, height = bbox or self.cell_bbox(row_index, column_index)
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
        # Over a frozen header row, the box moves with it.
        tags = ("frozen_y",) if self.show_header and top - self._frozen_offset[1] < self.body_top else ()
        window = self.create_window(left, top, window=editor, anchor="nw", width=width, height=height, tags=tags)
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
        family_action = self._family_action_at(event)
        if family_action is not None:
            if self.on_family_action is not None:
                self.on_family_action(family_action)
            return
        action = self._action_at(event)
        if action is not None:
            if self.on_cell_action is not None:
                self.on_cell_action(*action)
            return
        toggle = self._hidden_toggle_at(event)
        if toggle is not None:
            if self.on_hidden_toggle is not None:
                self.on_hidden_toggle(self.parameter_names[toggle])
            return
        width_cell = self._width_cell_at(event)
        if width_cell is not None:
            if self.on_width_click is not None:
                self.on_width_click(width_cell)
            return
        family = self._family_at(event)
        if family is not None:
            self._select_family(family, event.state)
            return
        index = self._selectable_column_at(event)
        if index is not None:
            self.selected_families = set()
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
            if event.state & 0x0005:
                return  # Ctrl- and Shift-clicks only select
        if not self.edit_on_click:
            return
        cell = self._cell_at(event)
        if cell is not None and self.rows[cell[0]]["cells"][cell[1]].get("editable") and self.on_cell_double_click:
            self.on_cell_double_click(*cell)

    def _select_family(self, family, state):
        self.selected_indices = set()
        names = self._family_names()
        if state & 0x0004:
            self.selected_families ^= {family}
            self.family_anchor = family
        elif state & 0x0001 and self.family_anchor in names:
            first, last = sorted((names.index(self.family_anchor), names.index(family)))
            self.selected_families = set(names[first:last + 1])
        else:
            self.family_anchor = family
            self.selected_families = {family}
        self._draw_grid()

    def _on_mouse_drag(self, event):
        index = self._selectable_column_at(event)
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
        if self.edit_on_click:
            return  # the first click already started the edit
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

        self._draw_body(right)
        if self.show_header:
            self._draw_header(wrapped_headers)
        self._freeze()

    def _draw_header(self, wrapped_headers):
        lane_count = self.header_top // self.group_row_height
        self._label_cell(0, 0, self.section_width, self.body_top, self.header_label)
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

        if self.hidden_row_height:
            self._draw_hidden_row()
        if self.width_row_height:
            self._draw_width_row()

    def _draw_width_row(self):
        top = self.width_row_top
        height = self.width_row_height
        self._label_cell(self.section_width, top, self.label_width, height, "Column Width (in)")
        for index, cell in enumerate(self.width_cells):
            left = self.column_offsets[index]
            self.create_rectangle(left, top, left + self.column_widths[index], top + height,
                                  fill="#ffffff", outline="#c8d2ce")
            self.create_text(
                left + 6, top + height / 2, text=cell["text"], anchor="w", font=self.body_font,
                fill="#9ca3af" if cell["state"] == "inherited" else "#111827",
            )

    def _draw_hidden_row(self):
        top = self.hidden_row_top
        height = self.hidden_row_height
        self._label_cell(self.section_width, top, self.label_width, height, "Hidden Column")
        size = 14
        for index, name in enumerate(self.parameter_names):
            left = self.column_offsets[index]
            hidden = name in self.hidden_names
            self.create_rectangle(left, top, left + self.column_widths[index], top + height,
                                  fill="#f1f5f3" if hidden else "#ffffff", outline="#c8d2ce")
            box_left = left + (self.column_widths[index] - size) / 2
            box_top = top + (height - size) / 2
            self.create_rectangle(box_left, box_top, box_left + size, box_top + size,
                                  fill="#ffffff", outline="#374151")
            if hidden:
                self.create_line(
                    box_left + 3, box_top + size / 2, box_left + size / 2 - 1, box_top + size - 4,
                    box_left + size - 3, box_top + 3, fill="#111827", width=2,
                )

    def _draw_body(self, right):
        section_start = 0
        self._family_action_boxes = {}
        for row_index, row in enumerate(self.rows + [None]):
            starts_section = row is None or (row_index > 0 and row.get("section"))
            if starts_section and row_index > section_start:
                # The section label spans every row since the last section started.
                top = self.body_top + section_start * self.row_height
                height = (row_index - section_start) * self.row_height
                first = self.rows[section_start]
                if first.get("family_action"):
                    self._draw_family_section(first, top, height)
                else:
                    self._label_cell(0, top, self.section_width, height, first.get("section", ""),
                                     fill=self._label_fill(first))
                # In two parts: the one under the labels stays with them as the table scrolls.
                self.create_line(0, top, self.left, top, fill="#374151", width=2)
                self.create_line(self.left, top, right, top, fill="#374151", width=2)
                section_start = row_index
            if row is None:
                break

            top = self.body_top + row_index * self.row_height
            self._label_cell(self.section_width, top, self.label_width, self.row_height, row.get("label", ""),
                             fill=self._label_fill(row, "#f8faf9"))
            for index, cell in enumerate(row["cells"]):
                left = self.column_offsets[index]
                if cell.get("action"):
                    self._draw_action_cell(row_index, index)
                    continue
                state = cell.get("state", "set")
                if row.get("selects_column") and index in self.selected_indices:
                    fill = "#dcefe7"
                elif state == "none":
                    fill = "#e5e9e7"
                elif cell.get("editable"):
                    fill = "#ffffff"
                else:
                    fill = "#f8faf9"
                self.create_rectangle(left, top, left + self.column_widths[index], top + self.row_height,
                                      fill=fill, outline="#c8d2ce")
                if cell.get("text") and state != "none":
                    font = self.body_bold_font if cell.get("bold") else self.body_font
                    self.create_text(
                        left + 6, top + self.row_height / 2,
                        text=self._fit_text(cell["text"], self.column_widths[index] - 12, font), anchor="w",
                        font=font, fill="#9ca3af" if state == "inherited" else "#111827",
                    )

    def _draw_family_section(self, row, top, height):
        """A family's section label: its name at the top and its button underneath."""
        width = self.section_width
        self.create_rectangle(0, top, width, top + height, fill=self._label_fill(row), outline="#c8d2ce")
        self.create_text(6, top + 6, text=row.get("section", ""), anchor="nw", width=width - 10, font=self.label_font)
        box = (6, top + height - 28, width - 6, top + height - 6)
        self.create_rectangle(*box, fill="#dce9e4", outline="#7a9187")
        self.create_text((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, text=row["family_action"],
                         font=self.label_font)
        self._family_action_boxes[row["family"]] = box

    def _label_fill(self, row, fill="#f1f5f3"):
        return "#dcefe7" if row.get("family") in self.selected_families else fill

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

    def _family_action_at(self, event):
        """The family whose button (under its name) is under the event, or ``None``."""
        x, y = self._cx(event), self._cy(event)
        return next(
            (family for family, (left, top, right, bottom) in self._family_action_boxes.items()
             if left <= x <= right and top <= y <= bottom),
            None,
        )

    def _on_motion(self, event):
        clickable = any(found is not None for found in (
            self._family_action_at(event),
            self._action_at(event), self._hidden_toggle_at(event), self._family_at(event),
            self._selectable_column_at(event),
        ))
        self.configure(cursor="hand2" if clickable else "")

    def _fit_text(self, text: str, max_width: int, font=None) -> str:
        """``text`` on one line, cut short with an ellipsis if it is wider than ``max_width``."""
        font = font or self.body_font
        if font.measure(text) <= max_width:
            return text
        while text and font.measure(text + "…") > max_width:
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


class DDMGUI(SectionWindows, CombinedParamWindows):
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
        "header_text": "Default Header",
        "header_text_override": "Schedule Header Override",
        "grid_column_width": "Default Column Width (in)",
        "grid_column_width_override": "Schedule Width Override (in)",
        "dtype": "Data Type",
        "group_under": "Default Group Under",
        "formula": "Default Formula",
        "instance_param": "Instance or Type",
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
        self.root.title(f"DDM Review {APP_VERSION}")
        self.root.geometry("1360x820")
        self.root.minsize(1100, 700)

        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#1f2937")
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground="#374151")
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))
        apply_table_style(self.root)

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
            else STARTER_DATABASE_PATH
        )
        self.load_checkpoint(str(startup_path))
        self.checkpoint_path = DEFAULT_CHECKPOINT_PATH
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if startup_path == STARTER_DATABASE_PATH and FROZEN and self.warning_text is not None:
            # The bundled copy unpacks to a temporary folder; say what it is instead.
            self.warning_text.delete("1.0", "2.0")
            self.warning_text.insert(
                "1.0", f"First launch: opened the master database. Save keeps your copy in {DEFAULT_CHECKPOINT_PATH}\n"
            )

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
        ttk.Button(toolbar, text="Sync to Quickbase", command=self.sync_to_quickbase, style="Action.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(
            toolbar, text="Revit Macro Settings", command=self.open_macro_settings, style="Action.TButton",
        ).pack(side="left")
        ttk.Button(toolbar, text="Create GitHub Ticket", command=self.open_new_ticket).pack(side="right")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 8))

        self.params_tab = ttk.Frame(self.notebook)
        self.family_tab = ttk.Frame(self.notebook)
        self.schedules_tab = ttk.Frame(self.notebook)
        self.sections_tab = ttk.Frame(self.notebook)
        self.combined_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.params_tab, text="Parameters")
        self.notebook.add(self.family_tab, text="Families")
        self.notebook.add(self.schedules_tab, text="Schedules")
        self.notebook.add(self.sections_tab, text="Sections")
        self.notebook.add(self.combined_tab, text="Combined Parameters")

        self._build_data_table(self.params_tab, "params")
        self._build_data_table(self.family_tab, "families")
        self._build_data_table(self.schedules_tab, "groups")
        self._build_data_table(self.sections_tab, "sections")
        self._build_data_table(self.combined_tab, "combined")

        self._configure_detail_clicks()

        validation_header = ttk.Label(self.root, text="Messages", style="Section.TLabel")
        validation_header.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 4))

        self.warning_text = tk.Text(self.root, height=8, wrap="word", padx=10, pady=8, bg="#f8fafc", borderwidth=1, relief="solid")
        self.warning_text.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))

        self.file_actions = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        self.file_actions.grid(row=5, column=0, sticky="ew")
        self.file_actions.columnconfigure(0, weight=1)
        ttk.Button(self.file_actions, text="Load", command=self.open_database, style="Action.TButton").grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(self.file_actions, text="Save", command=self.save_checkpoint, style="Action.TButton").grid(
            row=0, column=2, padx=(0, 8)
        )
        ttk.Button(self.file_actions, text="Save As...", command=self.save_checkpoint_as, style="Action.TButton").grid(
            row=0, column=3, padx=(0, 8)
        )
        ttk.Button(
            self.file_actions, text="Import Excel...", command=self.import_excel_from_button, style="Action.TButton",
        ).grid(row=0, column=4)

    def _show_messages(self, lines: Sequence[str]):
        if self.warning_text is None:
            return
        self.warning_text.delete("1.0", tk.END)
        self.warning_text.insert("1.0", "\n".join(lines))

    def _append_message(self, line: str):
        if self.warning_text is not None:
            self.warning_text.insert(tk.END, f"\n{line}")
            self.warning_text.see(tk.END)

    # --- exports ----------------------------------------------------------------

    def _generate_revit_schedule_macro_file(self):
        """Write the schedule macro next to the save; install it in the user's macro module and build it.

        With a window, the build runs in the background so the app stays usable; a save
        made while a build is running installs its macro once that build finishes.
        """
        module = self._macro_module_for_save()
        try:
            output_path = get_database_output_paths(self.checkpoint_path)["macro"]
            source = generate_schedule_macro_source(
                self.catalog, Path(self.checkpoint_path).name,
                **({"namespace": module.namespace} if module else {}),
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(source, encoding="utf-8")
        except (OSError, ValueError) as exc:
            self._show_macro_generation_failure(exc)
            return
        self._append_message(f"Generated Revit schedule macro: {output_path}")
        if module is None:
            return
        if getattr(self, "_macro_build_thread", None) is not None:
            # Installing now would change the macro under the running build.
            self._pending_macro_install = (source, module)
            self._append_message(
                f"The {module.name} module is still building; this save's macro will be installed "
                "and built when it finishes."
            )
            return
        self._install_and_build_macro(source, module)

    def _show_macro_generation_failure(self, exc):
        messagebox.showerror(
            "Schedule Macro Generation Failed",
            f"The database was saved, but the Revit schedule macro could not be generated:\n{exc}",
            parent=getattr(self, "root", None),
        )

    def _install_and_build_macro(self, source: str, module):
        try:
            installed_path, removed_paths = install_macro(source, module.source_dir)
        except OSError as exc:
            self._show_macro_generation_failure(exc)
            return
        if installed_path is None:
            return
        for removed_path in removed_paths:
            self._append_message(f"Removed older generated macro: {removed_path}")
        root = getattr(self, "root", None)
        if root is None:
            # No window (tests, scripts): build here and now.
            self._append_message(f"Installed the schedule macro in {installed_path}. Building {module.name}...")
            self._finish_macro_build(module, *build_module(module))
            return

        self._append_message(
            f"Installed the schedule macro in {installed_path}. Building {module.name} in the background; "
            "keep working, and its messages will show here when it's done."
        )
        outcome = {}

        def build():
            try:
                outcome["result"] = build_module(module)
            except Exception as exc:  # noqa: BLE001 - reported in Messages rather than lost in the thread
                outcome["result"] = (False, [f"The {module.name} module couldn't be built: {exc}"])

        thread = threading.Thread(target=build, name="macro-build", daemon=True)
        self._macro_build_thread = thread
        thread.start()

        def check():
            # Tk isn't thread-safe: the window only hears about the build from its own thread.
            if thread.is_alive():
                root.after(self._macro_build_poll_ms, check)
                return
            self._macro_build_thread = None
            self._finish_macro_build(module, *outcome["result"])

        root.after(self._macro_build_poll_ms, check)

    _macro_build_poll_ms = 250

    def _finish_macro_build(self, module, succeeded: bool, build_messages: Sequence[str]):
        for line in build_messages:
            self._append_message(line)
        if not succeeded:
            self._show_macro_build_failure(module, build_messages)
        pending = getattr(self, "_pending_macro_install", None)
        if pending is not None:
            self._pending_macro_install = None
            self._install_and_build_macro(*pending)
        elif getattr(self, "_close_when_built", False):
            self.root.destroy()

    def _macro_module_for_save(self):
        """The macro module Save installs into, or ``None`` (with a message saying why).

        The user's choice is remembered; with only one module on the machine it is used,
        and with several the user is asked once.
        """
        modules = find_macro_modules(MACROS_ROOT)
        module = chosen_module(modules, USER_SETTINGS_PATH)
        if module is not None:
            return module
        if not modules:
            self._append_message(
                "No Revit 2025 (or later) application macro module was found, so the schedule macro "
                "wasn't installed. Create one in Revit (Manage > Macro Manager > Application > Module, "
                "C#), then save again."
            )
            return None
        if len(modules) == 1:
            choose_module(modules[0], USER_SETTINGS_PATH)
            self._append_message(f"Using {modules[0].label} for the schedule macro (the only macro module found).")
            return modules[0]
        if getattr(self, "root", None) is not None:
            module = self.open_macro_settings(modules)
            if module is not None:
                return module
        self._append_message(
            "The schedule macro wasn't installed: choose a macro module with Revit Macro Settings, then save again."
        )
        return None

    def open_macro_settings(self, modules=None):
        """Ask which macro module gets the schedule macro. Returns the chosen module, or ``None``."""
        if modules is None:
            modules = find_macro_modules(MACROS_ROOT)
        root = getattr(self, "root", None)
        if not modules:
            messagebox.showinfo(
                "Revit Macro Settings",
                "No Revit 2025 (or later) application macro module was found.\n\nCreate one in Revit: "
                "Manage > Macro Manager > Application > Module (C#). Then open these settings again.",
                parent=root,
            )
            return None
        current = chosen_module(modules, USER_SETTINGS_PATH)

        dialog = tk.Toplevel(root)
        dialog.title("Revit Macro Settings")
        dialog.transient(root)
        dialog.geometry("520x220")
        ttk.Label(dialog, text="Install the Schedule Macro In", style="Section.TLabel").pack(anchor="w", padx=10, pady=(10, 4))
        ttk.Label(
            dialog, wraplength=490, justify="left",
            text="Save writes CreateSchedulesFromDatabase into this Revit application macro module "
                 "and builds it, so it appears in Revit's Macro Manager.",
        ).pack(anchor="w", padx=10)
        labels = [module.label for module in modules]
        combo = ttk.Combobox(dialog, values=labels, state="readonly")
        combo.set(current.label if current else labels[0])
        combo.pack(fill="x", padx=10, pady=10)
        result = {"module": None}

        def use():
            module = modules[labels.index(combo.get())]
            choose_module(module, USER_SETTINGS_PATH)
            result["module"] = module
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", side="bottom", padx=10, pady=8)
        ttk.Button(buttons, text="Use This Module", command=use).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 6))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.grab_set()
        dialog.wait_window()
        if result["module"] is not None:
            self._append_message(f"The schedule macro will be installed in {result['module'].label}.")
        return result["module"]

    # Most build errors a pop-up lists; the rest are only in Messages.
    _max_popup_build_errors = 10

    def _show_macro_build_failure(self, module, build_messages: Sequence[str]):
        """Pop up the build errors, so a failed build isn't missed among the save messages."""
        details = list(build_messages[:-1])
        shown = details[:self._max_popup_build_errors]
        if len(details) > len(shown):
            shown.append(f"... and {len(details) - len(shown)} more (see Messages).")
        messagebox.showerror(
            "Macro Build Failed",
            f"The database was saved, but the {module.name} module didn't build, so Revit's Macro "
            "Manager still has the previous build of CreateSchedulesFromDatabase.\n\n"
            + "\n".join(shown or build_messages),
            parent=getattr(self, "root", None),
        )

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
            # The older export, one template per schedule, kept beside it.
            schedules_path = output_paths["rfps_schedules"]
            schedules_content = generate_rfps_schedules_content(
                [(schedule.name, [param.name for param in schedule.params]) for schedule in self.catalog.schedules],
                self.params_df,
                shared_parameter_file_name=output_paths["shared_parameters"].name,
            )
            schedules_path.write_text(schedules_content, encoding="utf-8", newline="")
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "RF Tools Export Failed",
                f"The database was saved, but the RF Tools parameter scheduler file "
                f"could not be generated:\n{exc}",
                parent=getattr(self, "root", None),
            )
            return
        self._append_message(f"Generated RF Tools parameter scheduler file (families): {output_path}")
        self._append_message(f"Generated RF Tools parameter scheduler file (schedules): {schedules_path}")

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

    def open_new_ticket(self):
        """Open a new GitHub issue in the browser, with the app version filled in."""
        url = NEW_ISSUE_URL + "?" + urllib.parse.urlencode({"body": f"App Version: {APP_VERSION}\n\n"})
        if not webbrowser.open(url):
            messagebox.showinfo("Create GitHub Ticket", f"Couldn't open a browser. Create the ticket here:\n{NEW_ISSUE_URL}")

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
        self._build_search_bar(parent, table_name)
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

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
        elif table_name == "sections":
            columns = self._section_summary_columns
            tree = ttk.Treeview(frame, columns=columns, show="headings")
            for col in columns:
                tree.heading(col, text=self._humanize_column_name(col))
                tree.column(col, width=180 if col in ("name", "caption") else 120, anchor="w")
            self.section_tree = tree
        elif table_name == "combined":
            columns = self._combined_summary_columns
            tree = ttk.Treeview(frame, columns=columns, show="headings")
            for col in columns:
                tree.heading(col, text=self._humanize_column_name(col))
                tree.column(col, width=360 if col == "pattern" else 160 if col in ("name", "header") else 110, anchor="w")
            self.combined_tree = tree
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
        tree._ddm_sort = None
        for col in columns:
            tree.heading(col, command=lambda table=tree, column=col: self._sort_table(table, column))
        # Last, so the handlers above still run before it ends a drag's default handling.
        tree._ddm_resizer = ColumnResizer(tree)
        self._update_table_heading_wrap(tree)

        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

    def _build_search_bar(self, parent: ttk.Frame, table_name: str):
        """A Search box over a main table: rows show only when they contain every word typed."""
        if not hasattr(self, "_search_vars"):
            self._search_vars = {}
            self._search_counts = {}
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(bar, text="Search:").pack(side="left", padx=(0, 6))
        search_var = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=search_var, width=40)
        entry.pack(side="left")
        entry.bind("<Escape>", lambda _event: search_var.set(""))
        ttk.Button(bar, text="Clear", command=lambda: search_var.set("")).pack(side="left", padx=(6, 0))
        count = ttk.Label(bar, text="")
        count.pack(side="left", padx=(12, 0))
        if table_name == "params":
            ttk.Button(bar, text="Add Parameter...", command=self._open_param_name_builder).pack(side="right")
        elif table_name == "sections":
            ttk.Button(bar, text="Add Section...", command=self.open_section_window).pack(side="right")
        elif table_name == "combined":
            ttk.Button(bar, text="Add Combined Parameter...", command=self.open_combined_window).pack(side="right")
        elif table_name == "groups":
            ttk.Button(bar, text="Duplicate Schedule...", command=self._duplicate_selected_schedule).pack(side="right")
        self._search_vars[table_name] = search_var
        self._search_counts[table_name] = count
        search_var.trace_add("write", lambda *_args: self.render_tables())

    def _search_text(self, table_name: str) -> str:
        search_var = getattr(self, "_search_vars", {}).get(table_name)
        return search_var.get() if search_var is not None else ""

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
            label = self._humanize_column_name(column) + sort_mark(getattr(tree, "_ddm_sort", None), column)
            width = max(1, int(tree.column(column, "width")) - DEFAULT_TABLE_VIEW.heading_margin)
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
            # One click edits a cell in place; on a name it opens the Family Name Builder.
            self.family_tree.bind("<Button-1>", lambda event: self._on_tree_click(event, "families"), add="+")
        if self.group_tree is not None:
            self.group_tree.bind("<Double-1>", self._open_selected_schedule_window)
        if self.section_tree is not None:
            self.section_tree.bind("<Double-1>", self._open_selected_section_window)
        if self.combined_tree is not None:
            self.combined_tree.bind("<Double-1>", self._open_selected_combined_window)

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
        if column_name == "instance_param":
            return ["Instance", "Type"]
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

        row_index = int(row_id)
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
        params = self.params_df
        # Shown as on the schedule window: Instance or Type, not true / false.
        params["instance_param"] = params["instance_param"].map(lambda value: self._attribute_text("instance_param", value))
        tables = (
            ("params", self.param_tree, params, self._get_table_columns("params")),
            ("families", self.family_tree, self.families_df, self._get_table_columns("families")),
            ("groups", self.group_tree, self._build_schedule_summary_df(), self._schedule_summary_columns),
            ("sections", self.section_tree, self._build_section_summary_df(), self._section_summary_columns),
            ("combined", self.combined_tree, self._build_combined_summary_df(), self._combined_summary_columns),
        )
        for table_name, tree, df, columns in tables:
            shown = self._render_tree(tree, df, columns, self._search_text(table_name))
            count = getattr(self, "_search_counts", {}).get(table_name)
            if count is not None:
                count.configure(text=f"Showing {shown} of {len(df)}" if self._search_text(table_name).strip() else "")
            self._fit_table_columns(tree, df, columns)

    def _fit_table_columns(self, tree, df, columns):
        """Size columns to their entries, once per database: after that, a dragged width stays."""
        if tree is None or getattr(tree, "_ddm_fitted_catalog", None) is self.catalog:
            return
        tree._ddm_fitted_catalog = self.catalog
        body_font = tree_body_font(tree)
        for column in columns:
            entries = df[column].tolist() if column in df.columns else []
            label = self._humanize_column_name(column)
            tree.column(column, width=fitted_width(entries, label, body_font, tree._ddm_heading_font))
        self._update_table_heading_wrap(tree)

    def _sort_table(self, tree, column):
        """A click on a column's header: sort by it, the other way, then back to the table's own order."""
        tree._ddm_sort = next_sort(tree._ddm_sort, column)
        self.render_tables()
        self._update_table_heading_wrap(tree)

    @staticmethod
    def _render_tree(tree: ttk.Treeview, df: pd.DataFrame, columns: Sequence[str], search: str = "") -> int:
        """Fill the table with the rows matching ``search``; returns how many are shown.

        Each row's item ID is its position in ``df``, so edits reach the right item while filtered.
        """
        if tree is None:
            return 0

        for row in tree.get_children():
            tree.delete(row)

        words = search.casefold().split()
        rows = []
        for position, (_, row) in enumerate(df.iterrows()):
            values = ["" if value is None else value for value in (row.get(col, "") for col in columns)]
            text = " ".join(str(value) for value in values).casefold()
            if all(word in text for word in words):
                rows.append((position, values))
        sort = getattr(tree, "_ddm_sort", None)
        if sort is not None and sort[0] in columns:
            index = list(columns).index(sort[0])
            rows = sorted_rows(rows, lambda item: item[1][index], descending=sort[1])
        for position, values in rows:
            tree.insert("", "end", iid=str(position), values=values)
        return len(rows)

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
        elif column_name in {"client", "country", "category_1", "category_2", "description"}:
            setattr(fam, column_name, value or None)
        elif column_name.endswith("_code") and column_name[:-len("_code")] in CODED_KINDS:
            # The code belongs to the client (country, category, ...), so every family with it changes.
            kind = column_name[:-len("_code")]
            if not getattr(fam, kind):
                raise ValueError(f"Choose a {CODE_LABELS[kind].lower()} before setting its code.")
            self.catalog.set_code(kind, getattr(fam, kind), value)
        else:
            raise ValueError(f"{self._humanize_column_name(column_name)} can't be edited.")

    # --- clients and countries --------------------------------------------------

    def _dropdown_values(self, column_name: str):
        """Choices for a column's dropdown, or ``None`` for a free-text column."""
        if column_name in CODE_KINDS:
            return self.catalog.names(column_name) + [ADD_NEW]
        return self._revit_dropdown_values(column_name)

    def _ask_new_code_entry(self, kind: str, parent=None):
        """Ask for a new client (country, Category 1 or 2) name and code and add it. Returns the name, or ``None``."""
        label = CODE_LABELS[kind]
        owner = (parent or self.root).winfo_toplevel()
        dialog = tk.Toplevel(owner)
        dialog.title(f"Add New {label}")
        dialog.transient(owner)
        dialog.geometry("420x200")
        previous_grab = owner.grab_current()

        ttk.Label(dialog, text=f"Add New {label}", style="Section.TLabel").pack(anchor="w", padx=10, pady=(10, 6))
        fields = ttk.Frame(dialog)
        fields.pack(fill="x", padx=10)
        fields.columnconfigure(1, weight=1)
        examples = {"client": ("Client Name", "Abbreviation, e.g. ACME"),
                    "country": ("e.g. United States", "Abbreviation, e.g. USA"),
                    "category_1": ("e.g. Equipment", "Abbreviation, e.g. EQUIP"),
                    "category_2": ("e.g. Air Handling Unit", "Abbreviation, e.g. AHU")}
        name_hint, code_hint = examples[kind]
        ttk.Label(fields, text=f"{label} =").grid(row=0, column=0, sticky="w", pady=4)
        name_entry = PlaceholderEntry(fields, placeholder=name_hint)
        name_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=4)
        ttk.Label(fields, text=f"{label} Code =").grid(row=1, column=0, sticky="w", pady=4)
        code_entry = PlaceholderEntry(fields, placeholder=code_hint)
        code_entry.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=4)
        name_entry.focus_set()

        result = {"name": None}

        def close():
            dialog.destroy()
            if previous_grab is not None and previous_grab.winfo_exists():
                previous_grab.grab_set()

        def add():
            name = name_entry.get().strip()
            if name in self.catalog.codes[kind] or name in self.catalog.names(kind):
                messagebox.showerror("Already Listed", f"{label} '{name}' is already listed.", parent=dialog)
                return
            try:
                self.catalog.set_code(kind, name, code_entry.get())
            except ValueError as exc:
                messagebox.showerror("Invalid value", str(exc), parent=dialog)
                return
            result["name"] = name
            close()

        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", side="bottom", padx=10, pady=8)
        ttk.Button(buttons, text="Add", command=add).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=close).pack(side="right", padx=(0, 6))
        dialog.bind("<Return>", lambda _event: add())
        dialog.bind("<Escape>", lambda _event: close())
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.grab_set()
        dialog.wait_window()
        return result["name"]

    # --- family and parameter names ---------------------------------------------

    def _build_name_terms_table(self, parent, parts, labels, value_heading, value_widget, on_change):
        """The Use / Term / Value / Prefix / Suffix / Order table both name builders share.

        ``value_widget(parent, term)`` makes a term's Value cell, and ``on_change()`` runs after
        any change to ``parts``. Returns ``move(index, step)``.
        """
        def move(index, step):
            target = index + step
            if 0 <= target < len(parts):
                parts[index], parts[target] = parts[target], parts[index]
                draw_terms()

        def draw_terms():
            for child in parent.winfo_children():
                child.destroy()
            for column, heading in enumerate(("Use", "Term", value_heading, "Prefix", "Suffix", "Order")):
                ttk.Label(parent, text=heading, style="Section.TLabel").grid(row=0, column=column, sticky="w", padx=4)
            parent.columnconfigure(2, weight=1)
            for index, part in enumerate(parts, start=1):
                use_var = tk.BooleanVar(value=part["use"])
                prefix_var = tk.StringVar(value=part["prefix"])
                suffix_var = tk.StringVar(value=part["suffix"])

                def update(*_args, part=part, use_var=use_var, prefix_var=prefix_var, suffix_var=suffix_var):
                    part.update(use=use_var.get(), prefix=prefix_var.get(), suffix=suffix_var.get())
                    on_change()

                ttk.Checkbutton(parent, variable=use_var).grid(row=index, column=0, padx=4)
                ttk.Label(parent, text=labels[part["term"]]).grid(row=index, column=1, sticky="w", padx=4)
                value_widget(parent, part["term"]).grid(row=index, column=2, sticky="ew", padx=4, pady=1)
                ttk.Entry(parent, textvariable=prefix_var, width=8).grid(row=index, column=3, padx=4, pady=1)
                ttk.Entry(parent, textvariable=suffix_var, width=8).grid(row=index, column=4, padx=4, pady=1)
                order = ttk.Frame(parent)
                order.grid(row=index, column=5, padx=4)
                ttk.Button(order, text="\u25b2", width=3, command=lambda i=index - 1: move(i, -1)).pack(side="left")
                ttk.Button(order, text="\u25bc", width=3, command=lambda i=index - 1: move(i, 1)).pack(side="left")
                for var in (use_var, prefix_var, suffix_var):
                    var.trace_add("write", update)
            on_change()

        draw_terms()
        return move


    def _open_family_name_builder(self, row_index: int):
        """The Family Name Builder: build a family's name from its codes, categories and description.

        Each term can be used or not, and has a prefix and suffix; a blank term is left
        out with them, and the first term in a name has no prefix. The order, prefixes and suffixes are one format shared by every
        family, saved when a family is renamed with it.
        """
        if not 0 <= row_index < len(self.catalog.families):
            return None
        fam = self.catalog.families[row_index]
        labels = dict(FAMILY_NAME_TERMS)
        parts = [dict(part) for part in self.catalog.family_name_format]

        window = tk.Toplevel(self.root)
        window.title("Family Name Builder")
        window.transient(self.root)
        window.grab_set()
        window.geometry("720x480")

        ttk.Label(window, text=f"Family: {fam.name}", style="Section.TLabel").pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(
            window,
            text="Each used term adds Prefix + Value + Suffix. A blank value is left out with its prefix and "
                 "suffix, and the first term in the name has no prefix. The order, prefixes and suffixes are "
                 "shared by every family.",
            wraplength=690, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        terms_frame = ttk.Frame(window)
        terms_frame.pack(fill="x", padx=12)
        name_var = tk.StringVar()

        def built_name():
            return self.catalog.build_family_name(fam, parts)

        def refresh_name(*_args):
            name_var.set(built_name())

        def value_label(parent, term):
            value = str(getattr(fam, term) or "")
            return ttk.Label(parent, text=value or "(blank)", foreground="#111827" if value else "#9ca3af")

        move = self._build_name_terms_table(
            terms_frame, parts, labels, "Value (This Family)", value_label, refresh_name,
        )

        name_box = ttk.Frame(window)
        name_box.pack(fill="x", padx=12, pady=(12, 4))
        ttk.Label(name_box, text="New Name:", style="Section.TLabel").pack(side="left")
        ttk.Entry(name_box, textvariable=name_var, font=("Segoe UI", 11)).pack(side="left", fill="x", expand=True, padx=(8, 0))
        ttk.Label(window, text="Edit the New Name before renaming to use something else for this family.",
                  foreground="#6b7280").pack(anchor="w", padx=12)

        def rename_this():
            new_name = cell_text(name_var.get())
            old_name = fam.name
            try:
                if new_name != old_name:
                    self._set_family_field(fam, "name", new_name)
            except ValueError as exc:
                messagebox.showerror("Invalid Name", str(exc), parent=window)
                return
            self.catalog.set_family_name_format(parts)
            self.validate_all()
            if new_name != old_name:
                self._append_message(f"Renamed family '{old_name}' to '{new_name}'.")
            window.destroy()

        def rename_all():
            renames, skipped = self._family_renames(parts)
            if not renames and not skipped:
                messagebox.showinfo("Rename All Families", "Every family's name already matches.", parent=window)
                return
            shown = [f"{old} \u2192 {new}" for old, new in renames[:15]]
            if len(renames) > len(shown):
                shown.append(f"...and {len(renames) - len(shown)} more")
            message = f"Rename {len(renames)} famil{'y' if len(renames) == 1 else 'ies'} to match this format?\n\n" + "\n".join(shown)
            if skipped:
                message += (f"\n\n{len(skipped)} left as they are: their new names would be blank or the "
                            "same as another family's (see Messages).")
            message += "\n\nOnly names in this database change; families in Revit aren't renamed."
            if not messagebox.askyesno("Rename All Families", message, parent=window):
                return
            self.catalog.set_family_name_format(parts)
            for old, new in renames:
                try:
                    self.catalog.get_family(old).name = new
                except ValueError as exc:  # e.g. two families swapping names
                    skipped.append(f"'{old}' ({exc})")
                    renames = [pair for pair in renames if pair[0] != old]
            self.validate_all()
            self._show_messages(
                [f"Renamed {len(renames)} famil{'y' if len(renames) == 1 else 'ies'} to match the name format."]
                + [f"Not renamed: {reason}" for reason in skipped]
            )
            window.destroy()

        buttons = ttk.Frame(window)
        buttons.pack(fill="x", side="bottom", padx=12, pady=10)
        ttk.Button(buttons, text="Rename This Family", command=rename_this, style="Action.TButton").pack(side="right")
        ttk.Button(buttons, text="Rename All Families to Match...", command=rename_all).pack(side="right", padx=(0, 6))
        ttk.Button(buttons, text="Cancel", command=window.destroy).pack(side="left")
        # For tests.
        window.parts, window.name_var, window.move = parts, name_var, move
        window.rename_this, window.rename_all = rename_this, rename_all
        return window

    # --- parameter names --------------------------------------------------------

    # Terms picked from the values already in use (or typed, to add a new one); the rest are typed.
    _param_term_dropdowns = ("company_code", "parent_category", "child_category", "units")

    def _open_param_name_builder(self, row_index: Optional[int] = None):
        """The Parameter Name Builder: build a parameter's name from its terms, as the Family Name Builder does.

        Each term can be used or not, and has a prefix and suffix; a blank term is left out with
        them, and the first term in a name has no prefix. The order, prefixes and suffixes are one
        format shared by every parameter, saved when a parameter is saved here. With ``row_index``
        it renames that parameter; without it, it adds a new one. A parameter without recorded
        terms keeps its name until a term, the format or the New Name is changed.
        """
        param = None
        if row_index is not None:
            if not 0 <= row_index < len(self.catalog.params):
                return None
            param = self.catalog.params[row_index]
        labels = dict(PARAM_NAME_TERMS)
        parts = [dict(part) for part in self.catalog.param_name_format]

        window = tk.Toplevel(self.root)
        window.title("Parameter Name Builder")
        window.transient(self.root)
        window.grab_set()
        window.geometry("720x480" if param is None else "720x400")

        heading = "New Parameter" if param is None else f"Parameter: {param.name}"
        ttk.Label(window, text=heading, style="Section.TLabel").pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(
            window,
            text="Each used term adds Prefix + Value + Suffix. A blank value is left out with its prefix and "
                 "suffix, and the first term in the name has no prefix. The order, prefixes and suffixes are "
                 "shared by every parameter.",
            wraplength=690, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        if param is None:
            terms = {term: "" for term, _label in PARAM_NAME_TERMS}
            terms["company_code"] = PARAM_NAME_COMPANY
            first_name = ""
        else:
            terms = param.name_terms
            first_name = build_param_name(terms, parts) if param.has_name_terms else param.name
        term_vars = {term: tk.StringVar(value=terms[term]) for term, _label in PARAM_NAME_TERMS}
        name_var = tk.StringVar(value=first_name)
        long_name = tk.StringVar()
        state = {"changed": False}

        def current_terms():
            return {term: var.get() for term, var in term_vars.items()}

        def rebuild_name(*_args):
            if state["changed"]:
                name_var.set(build_param_name(current_terms(), parts))

        def value_field(parent, term):
            if term in self._param_term_dropdowns:
                return ttk.Combobox(parent, textvariable=term_vars[term], values=self.catalog.param_term_values(term))
            return ttk.Entry(parent, textvariable=term_vars[term])

        terms_frame = ttk.Frame(window)
        terms_frame.pack(fill="x", padx=12)
        move = self._build_name_terms_table(
            terms_frame, parts, labels, "Value (This Parameter)", value_field, rebuild_name,
        )
        state["changed"] = True  # from here on, every change rebuilds the name

        def check_length(*_args):
            too_long = len(name_var.get()) > PARAM_NAME_LONG_LENGTH
            long_name.set(f"Long Name Detected (Over {PARAM_NAME_LONG_LENGTH} Characters), Consider Shortening"
                          if too_long else "")

        for var in term_vars.values():
            var.trace_add("write", rebuild_name)
        name_var.trace_add("write", check_length)
        check_length()

        name_box = ttk.Frame(window)
        name_box.pack(fill="x", padx=12, pady=(12, 4))
        ttk.Label(name_box, text="New Name:", style="Section.TLabel").pack(side="left")
        ttk.Entry(name_box, textvariable=name_var, font=("Segoe UI", 11)).pack(side="left", fill="x", expand=True, padx=(8, 0))
        ttk.Label(window, text="Edit the New Name before renaming to use something else for this parameter.",
                  foreground="#6b7280").pack(anchor="w", padx=12)
        ttk.Label(window, textvariable=long_name, foreground="#b45309").pack(anchor="w", padx=12)
        if param is not None:
            note = None
            if not param.has_name_terms:
                note = ("Terms Guessed From The Name; Correct Them If Needed." if any(
                    value for term, value in terms.items() if term != "company_code")
                    else "This Name Doesn't Follow The Format.")
            elif first_name != param.name:
                note = "The Format Builds A Different Name; Renaming Asks About The GUID."
            if note:
                ttk.Label(window, text=note, foreground="#6b7280").pack(anchor="w", padx=12)

        new_fields = {}
        if param is None:
            details = ttk.Frame(window)
            details.pack(fill="x", padx=12, pady=(10, 0))
            details.columnconfigure(1, weight=1)
            choices = (
                ("dtype", "Data Type", "Text", self._revit_dropdown_values("dtype")),
                ("group_under", "Default Group Under", "", self._revit_dropdown_values("group_under")),
                ("instance_param", "Instance or Type", "Instance", ["Instance", "Type"]),
            )
            for row, (field, label, default, values) in enumerate(choices):
                new_fields[field] = tk.StringVar(value=default)
                ttk.Label(details, text=f"{label} =").grid(row=row, column=0, sticky="w", pady=2)
                ttk.Combobox(details, textvariable=new_fields[field], values=values, state="readonly").grid(
                    row=row, column=1, sticky="ew", padx=(6, 0), pady=2)

        def save():
            new_name = cell_text(name_var.get())
            try:
                if param is None:
                    added = self._add_param_from_builder(new_name, current_terms(), new_fields, parts)
                    window.destroy()
                    self._show_new_param(added)
                    return
                old_name = param.name
                self._rename_param(param, new_name)
            except ValueError as exc:
                messagebox.showerror("Invalid Name", str(exc), parent=window)
                return
            if param.name != new_name:
                return  # the rename was cancelled at the GUID question
            self.catalog.set_param_name_format(parts)
            param.set_name_terms(current_terms())
            self.validate_all()
            if new_name != old_name:
                self._append_message(f"Renamed parameter '{old_name}' to '{new_name}'.")
            window.destroy()

        buttons = ttk.Frame(window)
        buttons.pack(fill="x", side="bottom", padx=12, pady=10)
        ttk.Button(buttons, text="Add Parameter" if param is None else "Rename This Parameter", command=save,
                   style="Action.TButton").pack(side="right")
        ttk.Button(buttons, text="Cancel", command=window.destroy).pack(side="left")
        # For tests.
        window.parts, window.move = parts, move
        window.term_vars, window.name_var, window.long_name, window.new_fields = term_vars, name_var, long_name, new_fields
        window.save = save
        return window

    def _add_param_from_builder(self, name: str, terms: dict, fields: dict, name_format):
        """Add the parameter the builder describes. Raises ``ValueError`` if the name can't be used."""
        if not name:
            raise ValueError("Parameter name is required.")
        if self.catalog.get_param(name) is not None or name in COMMON_PARAM_NAMES:
            raise ValueError(f"Parameter name '{name}' is already in use.")
        param = self.catalog.add_param(
            name,
            fields["dtype"].get(),
            group_under=fields["group_under"].get() or None,
            instance_param=parse_bool(fields["instance_param"].get()),
        )
        self.catalog.set_param_name_format(name_format)
        param.set_name_terms(terms)
        return param

    def _show_new_param(self, param):
        """Bring a just-added parameter into view: it could be hidden by the search."""
        search_var = getattr(self, "_search_vars", {}).get("params")
        if search_var is not None:
            search_var.set("")
        self.validate_all()
        self._append_message(f"Added parameter '{param.name}'.")
        row_id = str(self.catalog.params.index(param))
        if self.param_tree is not None and self.param_tree.exists(row_id):
            self.param_tree.selection_set(row_id)
            self.param_tree.see(row_id)

    def _family_renames(self, name_format):
        """Families whose name differs from ``name_format``'s: ``([(old, new), ...], [reason, ...])``.

        A family is left out if its new name is blank or another family has (or would get) it.
        """
        wanted = {fam.name: self.catalog.build_family_name(fam, name_format) for fam in self.catalog.families}
        counts = {}
        for new in wanted.values():
            counts[new] = counts.get(new, 0) + 1
        renames, skipped = [], []
        for old, new in wanted.items():
            if new == old:
                continue
            if not new:
                skipped.append(f"'{old}' (its new name would be blank)")
            elif counts[new] > 1 or (new in wanted and wanted[new] == new):
                skipped.append(f"'{old}' (another family has or would get '{new}')")
            else:
                renames.append((old, new))
        # A rename onto a name another family gives up: do that family first.
        order = {old: index for index, (old, _new) in enumerate(renames)}
        renames.sort(key=lambda pair: (pair[1] in order, order[pair[0]]))
        return renames, skipped

    # --- default value overrides ------------------------------------------------

    # What can be overridden, in table order, with its style-guide term and row label.
    _override_attributes = (
        ("value", "Default Value", "Default Value"),
        ("formula", "Default Formula", "Default Formula"),
        ("group_under", "Default Group Under", "Default Group Under"),
        ("instance_param", "Instance or Type", "Instance or Type"),
    )
    # Belong to the family, yet editable on a schedule's family rows (where they set the family).
    _family_level_attributes = ("formula", "group_under", "instance_param")

    @staticmethod
    def _attribute_text(attribute: str, value):
        """How a cell shows ``attribute``'s value: Instance or Type for ``instance_param``."""
        if attribute == "instance_param" and isinstance(value, bool):
            return "Instance" if value else "Type"
        return value

    @staticmethod
    def _attribute_value(attribute: str, text):
        """The value a cell's text stores; ``None`` for blank."""
        value = cell_text(text) or None
        if attribute == "instance_param" and value is not None:
            if value not in ("Instance", "Type"):
                raise ValueError("Instance or Type must be Instance or Type.")
            return value == "Instance"
        return value

    def _asks_parameter(self, param, attribute: str, value) -> bool:
        """Offer the Parameter checkbox? A parameter is always Instance or Type, so never to clear it."""
        return param is not None and not (attribute == "instance_param" and value is None)

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
        value = self._attribute_value(attribute, new_value)
        connected = self._connected_override_locations(location, param_name, attribute)
        param = self.catalog.get_param(param_name)
        ask_parameter = self._asks_parameter(param, attribute, value)

        answer = {"locations": [], "parameter": False}
        if connected or ask_parameter:
            answer = self._ask_override_scope(param_name, value, location, connected, ask_parameter, attribute)
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
        shown = "(no value)" if value is None else self._attribute_text(attribute, value)
        if attribute == "group_under":
            assignment = f"{param_name} Group Under = {shown}"
        else:
            assignment = f"{param_name} = {shown}"
        if family_name == ALL_FAMILIES and attribute != "value":
            heading = (
                f"{verb} Family {term}\nEvery Family in {schedule_name} (in Every Schedule They're In)"
                f"\n{assignment}"
            )
            list_label = ""  # every family is already covered; there's no list to pick from
        elif schedule_name is None:
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

    # Parameter section rows and the parameter field each one edits.
    _parameter_row_fields = {
        "value": "default_value", "formula": "formula", "group_under": "group_under",
        "instance_param": "instance_param",
    }

    def _parameter_table_rows(self, parameter_names: Sequence[str], families, schedule_window: bool = False) -> List[dict]:
        """The Parameter section: each column's name and Parameter Default values.

        In the schedule window (``schedule_window``) Default Header (the parameter's own
        header text, in gray when it's just the name) and Default Column Width rows follow
        the name, and the cells edit the parameter itself; elsewhere they're read-only.
        """
        definitions = [
            self.catalog.get_column(name)
            or next((param for fam in families for param in fam.params if param.name == name), None)
            for name in parameter_names
        ]

        def editable(param):
            # Only catalog parameters: a family-only parameter is edited in its family.
            return schedule_window and param is not None and self.catalog.get_param(param.name) is param

        rows = [{
            "section": "Parameter", "label": "Name", "selects_column": True, "param_field": "name",
            "cells": [self._table_cell(name, editable=editable(param)) for name, param in zip(parameter_names, definitions)],
        }]
        if schedule_window:
            rows.append({
                "section": "",
                "label": "Default Header",
                "param_field": "header_text",
                "cells": [
                    self._table_cell(None) if param is None else self._table_cell(
                        param.header_text, "set" if param._header_text is not None else "inherited", editable(param)
                    )
                    for param in definitions
                ],
            })
            rows.append({
                "section": "",
                "label": self._display_labels["grid_column_width"],
                "param_field": "grid_column_width",
                "cells": [
                    self._table_cell(None) if param is None else self._table_cell(
                        f"{param.grid_column_width:g}", editable=editable(param)
                    )
                    for param in definitions
                ],
            })
        def attribute_text(param, attribute):
            if param is None:
                return None
            if getattr(param, "is_combined", False):
                # A combined column has no value of its own: Revit joins its parts.
                return param.pattern() if attribute == "formula" else None
            return self._attribute_text(attribute, getattr(param, attribute))

        for attribute, _term, label in self._override_attributes:
            rows.append({
                "section": "",
                "label": label,
                "param_field": self._parameter_row_fields[attribute],
                "cells": [
                    self._table_cell(attribute_text(param, attribute), editable=editable(param))
                    for param in definitions
                ],
            })
        return rows

    def _set_param_from_table(self, param_name: str, field: str, text):
        """Edit a parameter from the schedule window's Parameter section; it changes everywhere."""
        param = self.catalog.get_param(param_name)
        if param is None:
            raise ValueError(f"Parameter not found: {param_name}")
        if field == "instance_param":
            value = self._attribute_value("instance_param", text)
            if value is None:
                raise ValueError("A parameter is always Instance or Type; pick one.")
            param.instance_param = value
        else:
            self._set_param_field(param, field, text)
        self.validate_all()

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
            editable = (
                schedule is None or attribute in Schedule.FAMILY_OVERRIDABLE_ATTRIBUTES
                or attribute in self._family_level_attributes
            )
            set_here = fam.overrides if attribute in self._family_level_attributes else own_overrides
            cells = []
            for name in parameter_names:
                param = resolved.get(name)
                combined = self.catalog.get_combined_param(name)
                if param is None and combined is not None:
                    values = {part: resolved[part].value for part in combined.parameter_names if part in resolved}
                    sample = combined.sample(values) if attribute == "value" else None
                    cells.append(self._table_cell(sample, "inherited" if sample else "none"))
                    continue
                if param is None:
                    cell = self._table_cell(None, "none")
                    if self.catalog.get_param(name) is not None:
                        cell["action"] = "Add Parameter to Family"
                    cells.append(cell)
                    continue
                is_set = editable and attribute in set_here.get(name, {})
                cells.append(self._table_cell(
                    self._attribute_text(attribute, getattr(param, attribute)), "set" if is_set else "inherited", editable
                ))
            rows.append({
                "section": "" if rows else fam.name,
                "label": label,
                "cells": cells,
                "family": fam.name,
                "attribute": attribute,
            })
        if schedule is not None and any(cell.get("action") for cell in rows[0]["cells"]):
            rows[0]["family_action"] = "Add All Parameters"
        return rows

    def _add_all_parameters_to_family(self, table: "OverrideTable", rows_builder, family_name: str):
        """The "Add All Parameters" button: give the family every schedule column it lacks."""
        fam = self.catalog.get_family(family_name)
        have = {param.name for param in fam.params}
        missing = [
            self.catalog.get_param(name) for name in table.parameter_names
            if name not in have and self.catalog.get_param(name) is not None
        ]
        for param in missing:
            fam.add_param(param)
        self.validate_all()
        self._append_message(f"Added {len(missing)} parameter(s) to family '{family_name}'.")
        table.set_rows(rows_builder())

    def _all_families_rows(self, schedule, parameter_names: Sequence[str]) -> List[dict]:
        """The Apply to All Families rows: shortcuts that set every family in the schedule at once.

        Default Value sets each family's Schedule Default Value. Formula and Group
        Under belong to the family itself (Revit keeps them in the family), so they
        set each family's Family Default, which every schedule the family is in uses.
        A cell shows the shared value when every family with that column agrees,
        "(Varies)" when they differ, and blank when none has one.
        """
        rows = []
        for attribute, _term, label in self._override_attributes:
            cells = []
            for name in parameter_names:
                families = [fam for fam in schedule.fams if name in schedule.family_param_names(fam)]
                if not families:
                    cells.append(self._table_cell(None, "none"))
                    continue
                values = {
                    self._attribute_text(attribute, (
                        schedule.family_overrides.get(fam.name, {}) if attribute == "value" else fam.overrides
                    ).get(name, {}).get(attribute))
                    for fam in families
                }
                if len(values) > 1:
                    cells.append(self._table_cell("(Varies)", "inherited", True))
                else:
                    value = values.pop()
                    cells.append(self._table_cell(value, "inherited" if value is None else "set", True))
            rows.append({
                "section": "" if rows else ALL_FAMILIES_SECTION,
                "label": label,
                "cells": cells,
                "family": None,
                "attribute": attribute,
                "all_families": True,
            })
        return rows

    def _override_all_families(self, schedule_name: str, param_name: str, new_value, attribute: str = "value") -> bool:
        """Set (or clear) ``attribute`` for every family in the schedule with the column.

        A Default Value goes to each family's Schedule Default Value; a Formula or
        Group Under to each family's Family Default. The prompt only offers the
        Parameter default, since every family is already covered. Returns ``False``
        if the user cancels.
        """
        value = self._attribute_value(attribute, new_value)
        schedule = self._get_schedule(schedule_name)
        targets = [
            (fam.name, schedule_name if attribute == "value" else None) for fam in schedule.fams
            if param_name in schedule.family_param_names(fam)
        ]
        param = self.catalog.get_param(param_name)
        answer = {"locations": [], "parameter": False}
        if self._asks_parameter(param, attribute, value):
            answer = self._ask_override_scope(
                param_name, value, (ALL_FAMILIES, schedule_name), [], True, attribute
            )
            if answer is None:
                return False
        for target in targets:
            self.catalog.apply_override(target, param_name, **{attribute: value})
        if answer["parameter"]:
            setattr(param, attribute, value)
        self.validate_all()
        return True

    def _schedule_table_rows(self, schedule) -> List[dict]:
        parameter_names = self._get_schedule_parameter_names(schedule)
        rows = self._parameter_table_rows(parameter_names, schedule.fams, schedule_window=True)
        rows.extend(self._all_families_rows(schedule, parameter_names))
        for fam in schedule.fams:
            rows.extend(self._family_table_rows(fam, parameter_names, schedule))
        self._mark_used_values(schedule, parameter_names, rows)
        return rows

    @staticmethod
    def _value_source(schedule, fam, param_name: str, attribute: str) -> str:
        """Where the value ``fam`` gets in ``schedule`` comes from: "schedule", "family" or "parameter"."""
        if attribute == "value":
            if param_name == SCHEDULE_FILTER_PARAM:
                return "schedule"  # the schedule filter sets it
            if "value" in schedule.family_overrides.get(fam.name, {}).get(param_name, {}):
                return "schedule"
        return "family" if attribute in fam.overrides.get(param_name, {}) else "parameter"

    def _mark_used_values(self, schedule, parameter_names: Sequence[str], rows: List[dict]):
        """Bold the cells holding the values the schedule ends up using.

        A family's cell is bold when the schedule or the family sets its own value; the
        Parameter cell when a family falls back to the parameter's (or no family has the
        column). The Default Header and Default Column Width are bold unless the schedule
        overrides them.
        """
        families_with = {
            name: [fam for fam in schedule.fams if name in schedule.family_param_names(fam)]
            for name in parameter_names
        }
        for row in rows:
            field = row.get("param_field")
            for index, cell in enumerate(row["cells"]):
                name = parameter_names[index]
                if cell["state"] == "none":
                    continue
                if field == "header_text":
                    cell["bold"] = name not in schedule.header_text_overrides
                elif field == "grid_column_width":
                    cell["bold"] = name not in schedule.grid_column_width_overrides
                elif field and field != "name":
                    attribute = next(a for a, f in self._parameter_row_fields.items() if f == field)
                    families = families_with[name]
                    cell["bold"] = not families or any(
                        self._value_source(schedule, fam, name, attribute) == "parameter" for fam in families
                    )
                elif row.get("family") and not row.get("all_families"):
                    fam = self.catalog.get_family(row["family"])
                    cell["bold"] = self._value_source(schedule, fam, name, row["attribute"]) != "parameter"

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

    def _edit_table_cell(self, table: "OverrideTable", rows_builder, schedule_name, row_index: int, column_index: int,
                         on_columns_changed=None):
        """Edit one table cell in place; on commit, run the override prompt and refresh.

        Tab moves on to the next editable cell in the row. A Parameter section cell
        edits the parameter itself; a change to its name, Default Header or Default Column
        Width calls ``on_columns_changed()`` (the columns need redrawing) instead.
        """
        row = table.rows[row_index]
        if not row["cells"][column_index].get("editable"):
            return None
        param_name = table.parameter_names[column_index]
        if row.get("param_field"):
            return self._edit_parameter_cell(table, rows_builder, schedule_name, row_index, column_index, on_columns_changed)
        attribute = row["attribute"]
        family_name = row["family"]
        all_families = row.get("all_families", False)
        if all_families:
            cell = row["cells"][column_index]
            own = {attribute: cell["text"]} if cell["state"] == "set" else {}
            if cell["text"] == "(Varies)":
                placeholder = "Varies: Type a Value to Set Every Family"
            elif attribute == "value":
                placeholder = "Blank Uses Each Family Default Value"
            else:
                placeholder = f"Blank Uses Parameter {self._attribute_term(attribute)}"
        elif schedule_name is None:
            own = self.catalog.get_family(family_name).overrides.get(param_name, {})
            placeholder = f"Blank Uses Parameter {self._attribute_term(attribute)}"
        elif attribute in self._family_level_attributes:
            own = self.catalog.get_family(family_name).overrides.get(param_name, {})
            placeholder = f"Blank Uses Parameter {self._attribute_term(attribute)}"
        else:
            own = self._get_schedule(schedule_name).family_overrides.get(family_name, {}).get(param_name, {})
            placeholder = f"Blank Uses Family {self._attribute_term(attribute)}"
        current = self._attribute_text(attribute, own.get(attribute))
        current = "" if current is None else str(current)
        # A family-level setting on a schedule's family row sets the family itself.
        location_schedule = None if attribute in self._family_level_attributes else schedule_name

        def commit(text):
            if cell_text(text) == current:
                return
            try:
                if all_families:
                    self._override_all_families(schedule_name, param_name, text, attribute)
                else:
                    self._override_value((family_name, location_schedule), param_name, text, attribute)
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
            choices=(
                self._revit_dropdown_values("group_under") if attribute == "group_under"
                else ["Instance", "Type"] if attribute == "instance_param" else None
            ),
            on_tab=edit_next,
        )

    def _edit_parameter_cell(self, table, rows_builder, schedule_name, row_index, column_index, on_columns_changed):
        """Edit a Parameter section cell in place: it sets the parameter for every family and schedule."""
        row = table.rows[row_index]
        field = row["param_field"]
        param = self.catalog.get_param(table.parameter_names[column_index])
        if field == "header_text":
            current = param._header_text or ""
        elif field == "name":
            current = param.name
        else:
            current = row["cells"][column_index]["text"]

        def commit(text):
            if cell_text(text) == current:
                return
            try:
                self._set_param_from_table(param.name, field, text)
            except ValueError as exc:
                messagebox.showerror("Invalid value", str(exc), parent=table.winfo_toplevel())
                return
            if field in ("name", "header_text", "grid_column_width") and on_columns_changed is not None:
                on_columns_changed()
            else:
                table.set_rows(rows_builder())

        def edit_next():
            cells = table.rows[row_index]["cells"]
            next_column = next(
                (index for index in range(column_index + 1, len(cells)) if cells[index].get("editable")),
                None,
            )
            if next_column is not None:
                self._edit_table_cell(table, rows_builder, schedule_name, row_index, next_column, on_columns_changed)

        choices = None
        if field == "group_under":
            choices = self._revit_dropdown_values("group_under")
        elif field == "instance_param":
            choices = ["Instance", "Type"]
        return table.start_cell_edit(
            row_index,
            column_index,
            current,
            commit,
            placeholder="Blank Uses the Parameter Name" if field == "header_text"
            else "Sets the Parameter for Every Family and Schedule",
            choices=choices,
            on_tab=edit_next,
        )

    def _build_override_table(self, parent, parameter_names, rows, **kwargs) -> "OverrideTable":
        """An ``OverrideTable`` with scroll bars, packed into ``parent``."""
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        table = OverrideTable(frame, parameter_names, rows=rows, **kwargs)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=table.xview)
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
        table.configure(
            xscrollcommand=lambda *view: (x_scroll.set(*view), table.on_view_changed()),
            yscrollcommand=lambda *view: (y_scroll.set(*view), table.on_view_changed()),
        )
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

    def _set_schedule_column(self, schedule_name: str, parameter_name: str, header_text: str, width_text: str,
                             hidden: Optional[bool] = None):
        """Set or clear a schedule's header text and column width overrides for one column.

        ``hidden`` hides the column in the finished Revit schedule; ``None`` leaves it as is.
        """
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
        if hidden is not None:
            schedule.set_field_hidden(parameter_name, hidden)
        self.validate_all()

    def _schedule_width_cells(self, schedule, parameter_names: Sequence[str]) -> List[dict]:
        """The Column Width row: each column's width here, in gray when it's the parameter's."""
        return [
            self._table_cell(
                f"{self._get_schedule_grid_column_width(schedule, name):g}",
                "set" if name in schedule.grid_column_width_overrides else "inherited",
                True,
            )
            for name in parameter_names
        ]

    def _edit_schedule_width(self, table: "OverrideTable", schedule, column_index: int, on_changed):
        """Edit a column's width in this schedule in place. Blank goes back to the parameter's."""
        parameter_name = table.parameter_names[column_index]
        override = schedule.grid_column_width_overrides.get(parameter_name)
        current = "" if override is None else f"{override:g}"

        def commit(text):
            if cell_text(text) == current:
                return
            try:
                self._set_schedule_column(
                    schedule.name, parameter_name, schedule.header_text_overrides.get(parameter_name, ""), text,
                )
            except ValueError as exc:
                messagebox.showerror("Invalid value", str(exc), parent=table.winfo_toplevel())
                return
            on_changed()

        def edit_next():
            if column_index + 1 < len(table.parameter_names):
                self._edit_schedule_width(table, schedule, column_index + 1, on_changed)

        return table.start_cell_edit(
            None,
            column_index,
            current,
            commit,
            placeholder="Blank Uses Parameter Default Column Width",
            on_tab=edit_next,
            bbox=table.width_cell_bbox(column_index),
        )

    def _set_schedule_column_hidden(self, schedule_name: str, parameter_name: str, hidden: bool):
        """Hide a column in the finished Revit schedule; the working schedule still shows it."""
        self._get_schedule(schedule_name).set_field_hidden(parameter_name, hidden)
        self.validate_all()

    def _set_schedule_settings(self, schedule_name: str, filter_value: str, itemize: bool, view_template: str):
        """Set a schedule's filter value (blank means its name), itemizing and view template."""
        schedule = self._get_schedule(schedule_name)
        filter_value = cell_text(filter_value)
        schedule.filter_value = None if not filter_value or filter_value == schedule.name else filter_value
        schedule.itemize = bool(itemize)
        schedule.view_template = cell_text(view_template) or None
        self.validate_all()

    def _build_schedule_settings(self, parent, schedule):
        """The Schedule Settings box: filter value, Itemize Every Instance and view template.

        Each change is saved as soon as the box loses focus, Enter is pressed or the
        checkbox is clicked.
        """
        box = ttk.LabelFrame(parent, text="Schedule Settings", padding=8)
        box.columnconfigure(2, weight=1)

        ttk.Label(box, text="Schedule Filter", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(box, text=f"{SCHEDULE_FILTER_PARAM} =").grid(row=0, column=1, sticky="w", padx=(12, 6))
        filter_entry = PlaceholderEntry(box, placeholder=f"{schedule.name} (Overrides Every Family in the Schedule)")
        if schedule.filter_value:
            filter_entry.insert(0, schedule.filter_value)
        filter_entry.grid(row=0, column=2, sticky="ew", pady=2)

        itemize_var = tk.BooleanVar(value=schedule.itemize)
        ttk.Checkbutton(box, text="Itemize Every Instance", variable=itemize_var).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=2
        )

        ttk.Label(box, text="View Template", style="Section.TLabel").grid(row=2, column=0, sticky="w")
        template_entry = PlaceholderEntry(box, placeholder="None (Name of a Revit Schedule View Template)")
        if schedule.view_template:
            template_entry.insert(0, schedule.view_template)
        template_entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=2)

        def save(_event=None):
            current = (schedule.filter_value or "", schedule.itemize, schedule.view_template or "")
            wanted = (filter_entry.get().strip(), itemize_var.get(), template_entry.get().strip())
            if wanted[0] == schedule.name:
                wanted = ("",) + wanted[1:]
            if wanted != current:
                self._set_schedule_settings(schedule.name, *wanted)

        for entry in (filter_entry, template_entry):
            entry.bind("<Return>", save, add="+")
            entry.bind("<FocusOut>", save, add="+")
        itemize_var.trace_add("write", lambda *_args: save())
        box.save = save  # for tests
        return box

    @staticmethod
    def _fit_window_width(window, row, margin=24):
        """Widen ``window`` so every widget in ``row`` (a button row) shows, as far as the screen allows,
        and keep it from being made narrower than that."""
        window.update_idletasks()
        needed = min(row.winfo_reqwidth() + margin, window.winfo_screenwidth())
        size, _, position = window.geometry().partition("+")
        width, height = (int(value) for value in size.split("x"))
        window.minsize(needed, 0)
        if width < needed:
            window.geometry(f"{needed}x{height}" + (f"+{position}" if position else ""))

    def _duplicate_selected_schedule(self):
        """Duplicate Schedule...: copy the schedule selected on the Schedules tab."""
        selection = self.group_tree.selection() if self.group_tree is not None else ()
        if len(selection) != 1:
            messagebox.showwarning(
                "Select a Schedule", "Select one schedule on the Schedules tab to duplicate.",
                parent=getattr(self, "root", None),
            )
            return None
        return self.ask_duplicate_schedule(self.catalog.schedules[int(selection[0])].name)

    def ask_duplicate_schedule(self, schedule_name: str):
        """The Duplicate Schedule box: name the copy; Duplicate makes it and opens it in the Schedule Builder."""
        parent = getattr(self, "root", None)
        dialog = tk.Toplevel(parent)
        dialog.title("Duplicate Schedule")
        dialog.transient(parent)
        dialog.grab_set()
        dialog.geometry("420x150")
        ttk.Label(dialog, text=f"Copy of: {schedule_name}").pack(anchor="w", padx=10, pady=(10, 2))
        ttk.Label(dialog, text="New Schedule Name:", style="Section.TLabel").pack(anchor="w", padx=10, pady=(4, 4))
        name_var = tk.StringVar(dialog, value=self.catalog.copy_name(schedule_name))
        entry = ttk.Entry(dialog, textvariable=name_var)
        entry.pack(fill="x", padx=10, pady=4)
        entry.focus_set()
        entry.select_range(0, "end")

        def duplicate():
            try:
                copy = self._duplicate_schedule(schedule_name, name_var.get())
            except ValueError as exc:
                messagebox.showwarning("Cannot Duplicate Schedule", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._open_detail_window("schedule", copy.name)

        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", padx=10, pady=(4, 8))
        ttk.Button(buttons, text="Duplicate", command=duplicate, style="Action.TButton").pack(side="right")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 6))
        entry.bind("<Return>", lambda _event: duplicate())
        dialog.name_var, dialog.duplicate = name_var, duplicate  # for tests
        return dialog

    def _duplicate_schedule(self, schedule_name: str, new_name: str):
        copy = self.catalog.duplicate_schedule(schedule_name, cell_text(new_name))
        self.validate_all()
        self.render_tables()
        self._append_message(f"Duplicated schedule '{schedule_name}' as '{copy.name}'.")
        return copy

    def _rename_schedule(self, schedule_name: str, new_name: str):
        """Rename a schedule; raises ``ValueError`` for a blank or taken name."""
        self._get_schedule(schedule_name).name = cell_text(new_name)
        self.validate_all()

    def _build_schedule_name_entry(self, parent, form, schedule):
        """The schedule window's title as an editable name: Enter or clicking away renames, Escape undoes.

        A rename reopens the window under the new name.
        """
        name_var = tk.StringVar(value=schedule.name)
        entry = ttk.Entry(parent, textvariable=name_var, font=("Segoe UI", 18, "bold"))
        renaming = False

        def rename(_event=None):
            nonlocal renaming
            new_name = name_var.get().strip()
            if renaming or new_name == schedule.name:
                return
            renaming = True
            old_name = schedule.name
            try:
                self._rename_schedule(old_name, new_name)
            except ValueError as exc:
                messagebox.showwarning("Rename Schedule", str(exc), parent=form)
                name_var.set(old_name)
                renaming = False
                return
            self._show_messages([f"Renamed schedule '{old_name}' to '{new_name}'."])
            form.destroy()
            self._open_schedule_window(new_name)

        entry.bind("<Return>", rename)
        entry.bind("<FocusOut>", rename)
        entry.bind("<Escape>", lambda _event: name_var.set(schedule.name))
        entry.rename = rename  # for tests
        return entry

    def _link_schedule_families(self, schedule_name: str, family_names: Sequence[str]):
        """Add families to a schedule; ones already in it are left as they are."""
        schedule = self._get_schedule(schedule_name)
        for family_name in family_names:
            fam = self.catalog.get_family(family_name)
            if fam is None:
                raise ValueError("Family not found: {}".format(family_name))
            if schedule.get_family(family_name) is None:
                schedule.add_family(fam)
        self.validate_all()

    def _unlink_schedule_family(self, schedule_name: str, family_name: str):
        """Take a family out of a schedule, with its Schedule Default Values for that family."""
        self._get_schedule(schedule_name).remove_family(family_name)
        self.validate_all()

    def _add_schedule_parameters(self, schedule_name: str, parameter_names: Sequence[str], after=None):
        """Add catalog parameters as schedule columns, after column ``after`` or at the end."""
        self._get_schedule(schedule_name).add_columns(parameter_names, after=after)
        self.validate_all()

    def _remove_schedule_parameters(self, schedule_name: str, parameter_names: Sequence[str]):
        """Take columns out of a schedule, with their settings and Schedule Default Values."""
        self._get_schedule(schedule_name).remove_columns(parameter_names)
        self.validate_all()

    def _move_schedule_parameters(self, schedule_name: str, parameter_names: Sequence[str], step: int) -> bool:
        """Move columns one place left (-1) or right (+1); ``False`` if they're already at that end."""
        moved = self._get_schedule(schedule_name).move_columns(parameter_names, step)
        if moved:
            self.validate_all()
        return moved

    def _build_schedule_edit_buttons(self, parent, schedule, get_table, on_change):
        """Add Parameter..., Remove Parameter, Move Left, Move Right, Add Family..., Remove Family
        and Add Section..., with a label naming the sections the schedule uses.

        The Remove and Move buttons act on the columns or families selected in the
        table (``get_table()``, which may be ``None`` when the schedule has no columns).
        ``on_change(selected_parameters=())`` runs after a change.
        """
        bar = ttk.Frame(parent)

        def selected(kind):
            table = get_table()
            if table is None:
                return []
            return table.get_selected_parameter_names() if kind == "parameter" else table.get_selected_family_names()

        def add_parameters():
            columns = {param.name for param in schedule.params}
            choices = [
                (combined.name, f"{combined.name} Combined {combined.header_text} {combined.pattern()}")
                for combined in self.catalog.combined_params if combined.name not in columns
            ] + [
                (param.name, f"{param.name} {param.header_text or ''} {param.group_under or ''}")
                for param in self.catalog.params if param.name not in columns
            ]
            after = (selected("parameter") or [None])[-1]

            def add(names):
                try:
                    self._add_schedule_parameters(schedule.name, names, after=after)
                except ValueError as exc:
                    messagebox.showwarning("Add Parameters", str(exc), parent=bar)
                    return
                on_change()

            hint = (
                f"Added to the right of {after}." if after
                else "Added at the right end (select a column first to add to its right)."
            )
            return self._pick_names(bar.winfo_toplevel(), f"Add Parameters to {schedule.name}", choices, add, hint)

        def remove_parameters():
            names = selected("parameter")
            if not names:
                messagebox.showinfo(
                    "Remove Parameters", "Select the columns to remove first: click their headers or names.",
                    parent=bar,
                )
                return
            if not messagebox.askyesno(
                "Remove Parameters",
                "Remove these columns from the schedule? Their column settings and Schedule Default "
                "Values go with them:\n\n" + "\n".join(names),
                parent=bar,
            ):
                return
            self._remove_schedule_parameters(schedule.name, names)
            on_change()

        def move(step):
            names = selected("parameter")
            if not names:
                messagebox.showinfo(
                    "Move Parameters", "Select the columns to move first: click their headers or names.",
                    parent=bar,
                )
                return
            try:
                moved = self._move_schedule_parameters(schedule.name, names, step)
            except ValueError as exc:
                messagebox.showwarning("Move Parameters", str(exc), parent=bar)
                return
            if moved:
                on_change(names)

        def add_families():
            linked = {fam.name for fam in schedule.fams}
            choices = [
                (fam.name, f"{fam.name} {fam.category or ''} {fam.description or ''}")
                for fam in self.catalog.families if fam.name not in linked
            ]

            def add(names):
                self._link_schedule_families(schedule.name, names)
                on_change()

            return self._pick_names(bar.winfo_toplevel(), f"Add Families to {schedule.name}", choices, add)

        def remove_families():
            names = selected("family")
            if not names:
                messagebox.showinfo(
                    "Remove Families", "Select the families to remove first: click their names on the left.",
                    parent=bar,
                )
                return
            message = "Remove these families from the schedule?\n\n" + "\n".join(names)
            if any(schedule.family_overrides.get(name) for name in names):
                message += "\n\nTheir Schedule Default Values in this schedule are deleted with them."
            if not messagebox.askyesno("Remove Families", message, parent=bar):
                return
            for name in names:
                self._unlink_schedule_family(schedule.name, name)
            on_change()

        def add_section():
            after = (selected("parameter") or [None])[-1]
            return self._add_section_to_schedule(bar.winfo_toplevel(), schedule, after, on_change)

        for text, command in (
            ("Add Parameter...", add_parameters), ("Remove Parameter", remove_parameters),
            ("◀ Move Left", lambda: move(-1)), ("Move Right ▶", lambda: move(1)),
            ("Add Family...", add_families), ("Remove Family", remove_families),
            ("Add Section...", add_section),
        ):
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=(0, 6))
        used_sections = [section.name for section, _use in schedule._used_sections()]
        if used_sections:
            ttk.Label(bar, text="Sections: " + ", ".join(used_sections)).pack(side="left", padx=(6, 0))
        # For tests.
        bar.add_parameters, bar.remove_parameters = add_parameters, remove_parameters
        bar.add_families, bar.remove_families = add_families, remove_families
        bar.add_section = add_section
        bar.move = move
        return bar

    def _pick_names(self, parent, title: str, choices, on_pick, hint: str = ""):
        """A searchable, multi-select list of ``choices`` (``(name, search text)`` pairs).

        Add calls ``on_pick(names)`` with the selected names; double-click adds one.
        """
        picker = tk.Toplevel(parent)
        picker.title(title)
        picker.transient(parent)
        picker.grab_set()
        picker.geometry("560x520")

        search_bar = ttk.Frame(picker)
        search_bar.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(search_bar, text="Search:").pack(side="left", padx=(0, 6))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_bar, textvariable=search_var)
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.focus_set()

        list_frame = ttk.Frame(picker)
        list_frame.pack(fill="both", expand=True, padx=10, pady=4)
        listbox = tk.Listbox(list_frame, selectmode="extended", exportselection=False)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        help_text = " ".join(filter(None, [hint, "Ctrl-click or Shift-click to select several; double-click adds one."]))
        ttk.Label(picker, text=help_text, wraplength=530).pack(anchor="w", padx=10)

        shown = []

        def refresh(*_args):
            words = search_var.get().casefold().split()
            shown[:] = [name for name, text in choices if all(word in text.casefold() for word in words)]
            listbox.delete(0, "end")
            for name in shown:
                listbox.insert("end", name)

        def add(_event=None):
            names = [shown[index] for index in listbox.curselection()]
            if not names:
                messagebox.showinfo(title, "Select one or more first.", parent=picker)
                return
            picker.destroy()
            on_pick(names)

        search_var.trace_add("write", refresh)
        listbox.bind("<Double-1>", add)
        refresh()

        buttons = ttk.Frame(picker)
        buttons.pack(fill="x", padx=10, pady=(4, 10))
        ttk.Button(buttons, text="Add", command=add, style="Action.TButton").pack(side="right")
        ttk.Button(buttons, text="Cancel", command=picker.destroy).pack(side="right", padx=(0, 6))
        picker.search_var = search_var  # for tests
        picker.listbox = listbox
        picker.add = add
        return picker

    def _add_schedule_header_group(self, schedule_name: str, parameter_names: Sequence[str], caption: str):
        group = self._get_schedule(schedule_name).add_header_group(caption, parameter_names)
        self.validate_all()
        return group

    def _remove_schedule_header_group(self, schedule_name: str, parameter_names: Sequence[str]):
        group = self._get_schedule(schedule_name).remove_header_group(parameter_names)
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
        if table_name == "families":
            # No double-click on the Families tab, so there's nothing to wait for.
            if self._get_table_columns("families")[cell[1]] == "name":
                self._finish_tree_cell_edit(True)
                self._open_family_name_builder(int(cell[0]))
            else:
                self._start_tree_cell_edit(tree, table_name, *cell)
            return
        if self._get_table_columns("params")[cell[1]] == "name":
            self._finish_tree_cell_edit(True)
            self._open_param_name_builder(int(cell[0]))
            return

        def start():
            self._pending_tree_edit = None
            self._start_tree_cell_edit(tree, table_name, *cell)

        # Wait in case this is the first click of a double-click.
        self._pending_tree_edit = self.root.after(self._single_click_delay_ms, start)

    def _start_tree_cell_edit(self, tree: ttk.Treeview, table_name: str, row_id: str, column_number: int):
        """Edit one cell of a main table in place: Enter or clicking away saves, Escape cancels."""
        self._finish_tree_cell_edit(False)
        field_name = self._get_table_columns(table_name)[column_number]
        if field_name in {"status", "validation_message", "guid"} or not tree.exists(row_id):
            return
        bbox = tree.bbox(row_id, f"#{column_number + 1}")
        if not bbox:
            return
        row_index = int(row_id)
        values = tree.item(row_id, "values")
        current_value = str(values[column_number]) if column_number < len(values) else ""

        dropdown_values = self._dropdown_values(field_name)
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
            if new_value == ADD_NEW:
                new_value = (self._ask_new_code_entry(field_name, tree) if save else None) or current_value
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
        row_index = int(row_id)
        self._open_detail_window("family", row_index)

    def _open_selected_schedule_window(self, event):
        if self.group_tree is None:
            return
        row_id = self.group_tree.identify_row(event.y)
        if not row_id:
            return
        row_index = int(row_id)
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
            dropdown_values = self._dropdown_values(col)
            if dropdown_values:
                combo = ttk.Combobox(form, values=dropdown_values, state="readonly", width=90)
                combo.set(str(row.get(col)))
                entries[col] = combo
                combo.pack(fill="x", padx=12, pady=(0, 4))
                if col in CODE_KINDS:
                    combo.bind("<<ComboboxSelected>>", lambda _event, kind=col: choose_code_entry(kind))
                continue
            value = tk.StringVar(value=str(row.get(col)))
            entries[col] = value
            ttk.Entry(form, textvariable=value, width=90).pack(fill="x", padx=12, pady=(0, 4))

        chosen = {kind: str(row.get(kind)) for kind in CODE_KINDS}

        def choose_code_entry(kind):
            """Handle Add New, and show the chosen client's (or country's) code."""
            combo = entries[kind]
            if combo.get() == ADD_NEW:
                name = self._ask_new_code_entry(kind, form)
                combo.configure(values=self._dropdown_values(kind))
                combo.set(name if name is not None else chosen[kind])
            chosen[kind] = combo.get()
            entries[f"{kind}_code"].set(self.catalog.code(kind, combo.get()))

        def save_changes():
            try:
                # Name first, so a rejected name leaves the other fields untouched.
                self._set_family_field(fam, "name", entries["name"].get())
                for col, widget in entries.items():
                    if col == "name":
                        continue
                    kind = col[:-len("_code")] if col.endswith("_code") else None
                    if kind is not None and widget.get() == self.catalog.code(kind, getattr(fam, kind)):
                        continue  # unchanged; don't touch the shared code
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

    def _open_schedule_window(self, selected_name: str, view=None):
        """The schedule window. ``view`` (from a reopen) restores its place, size, scrolling
        and selected columns: ``{"geometry", "xview", "yview", "selected"}``."""
        schedule = self.catalog.get_schedule(selected_name)
        if schedule is None:
            return

        form = tk.Toplevel(self.root)
        form.title(f"Schedule Builder: {selected_name}")
        form.transient(self.root)
        form.grab_set()
        form.geometry(view["geometry"] if view else "1040x840")

        title_bar = ttk.Frame(form)
        title_bar.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(title_bar, text="Schedule:", style="Title.TLabel").pack(side="left")
        self._info_button(title_bar).pack(side="right")
        self._build_schedule_name_entry(title_bar, form, schedule).pack(
            side="left", fill="x", expand=True, padx=(8, 12)
        )
        ttk.Label(form, text=f"Status: {schedule.status}", style="Section.TLabel").pack(anchor="w", padx=12, pady=(0, 6))
        ttk.Label(form, text=f"Validation: {schedule.validation_message or 'None'}", wraplength=1000, justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        self._build_schedule_settings(form, schedule).pack(fill="x", padx=12, pady=(0, 8))

        def reopen(selected_parameters=()):
            # Adding, removing or moving columns and families rebuilds the table, in the same place.
            reopened_view = {"geometry": form.geometry(), "selected": list(selected_parameters)}
            if table is not None:
                reopened_view.update(xview=table.xview()[0], yview=table.yview()[0])
            form.destroy()
            self._open_schedule_window(selected_name, reopened_view)

        table = None

        # Header grouping sits above the table; the column and family buttons stay under it.
        header_controls = ttk.Frame(form)
        table_box = ttk.LabelFrame(
            form,
            text="Schedule Default Values (click a value to edit it; bold is the value the schedule uses; "
                 "double-click a header for column settings; click headers or family names to select them)",
            padding=8,
        )
        parameter_names = self._get_schedule_parameter_names(schedule)
        if parameter_names:
            header_controls.pack(fill="x", padx=12, pady=(0, 6))
        table_box.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        if not parameter_names:
            ttk.Label(table_box, text="No Parameters Yet: Add Parameter... Adds Columns").pack(anchor="w")
            edit_buttons = self._build_schedule_edit_buttons(form, schedule, lambda: table, reopen)
            edit_buttons.pack(fill="x", padx=12)
            ttk.Button(form, text="Close", command=form.destroy, style="Action.TButton").pack(pady=(8, 10))
            self._fit_window_width(form, edit_buttons, margin=24)
            return

        def edit_schedule_header(parameter_name):
            current_override = schedule.header_text_overrides.get(parameter_name, "")
            width_override = schedule.grid_column_width_overrides.get(parameter_name)
            current_width_override = "" if width_override is None else f"{width_override:g}"
            # The column's default: its family's version, or the catalog's when no family has it.
            default_param = next(
                (param for fam in schedule.fams for param in fam.resolved_params() if param.name == parameter_name),
                None,
            ) or self.catalog.get_column(parameter_name)
            default_header = default_param.header_text
            default_width = default_param.grid_column_width

            editor = tk.Toplevel(form)
            editor.title("Schedule Column Settings")
            editor.transient(form)
            editor.grab_set()
            editor.geometry("420x250")
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
            hidden_var = tk.BooleanVar(value=parameter_name in schedule.hidden_field_names)
            ttk.Checkbutton(
                editor, text="Hidden Column (Shown Only in the Working Schedule)", variable=hidden_var,
            ).pack(anchor="w", padx=10, pady=(6, 0))
            header_entry.focus_set()

            def save_header_override():
                try:
                    self._set_schedule_column(
                        selected_name, parameter_name, header_entry.get(), width_entry.get(), hidden_var.get()
                    )
                except ValueError as exc:
                    messagebox.showwarning("Invalid width", str(exc), parent=editor)
                    return
                table.set_header_texts(header_texts())
                table.set_hidden_names(schedule.hidden_field_names)
                refresh_widths()
                editor.destroy()

            buttons = ttk.Frame(editor)
            buttons.pack(fill="x", padx=10, pady=(4, 8))
            ttk.Button(buttons, text="Save", command=save_header_override).pack(side="right")
            ttk.Button(buttons, text="Cancel", command=editor.destroy).pack(side="right", padx=(0, 6))
            header_entry.bind("<Return>", lambda _event: save_header_override())
            width_entry.bind("<Return>", lambda _event: save_header_override())

        def header_texts():
            return {name: self._get_schedule_header_text(schedule, name) for name in parameter_names}

        def refresh_widths():
            table.width_cells = self._schedule_width_cells(schedule, parameter_names)
            table.set_rows(rows_builder())  # the Default Column Width's bold follows the override
            table.set_grid_column_widths([
                self._get_schedule_grid_column_width(schedule, name) for name in parameter_names
            ])

        def toggle_hidden(parameter_name):
            self._set_schedule_column_hidden(
                selected_name, parameter_name, parameter_name not in schedule.hidden_field_names
            )
            table.set_hidden_names(schedule.hidden_field_names)

        rows_builder = lambda: self._schedule_table_rows(schedule)  # noqa: E731 - rebuilt after each edit
        table = self._build_override_table(
            table_box,
            parameter_names,
            rows_builder(),
            header_texts=header_texts(),
            groups=schedule.header_groups,
            on_header_double_click=edit_schedule_header,
            hidden_names=schedule.hidden_field_names,
            on_hidden_toggle=toggle_hidden,
            width_cells=self._schedule_width_cells(schedule, parameter_names),
            on_width_click=lambda column_index: self._edit_schedule_width(table, schedule, column_index, refresh_widths),
            edit_on_click=True,
            on_cell_double_click=lambda row_index, column_index: self._edit_table_cell(
                table, rows_builder, selected_name, row_index, column_index,
                on_columns_changed=lambda: reopen(table.get_selected_parameter_names()),
            ),
            on_cell_action=lambda row_index, column_index: self._add_parameter_from_table(
                table, rows_builder, row_index, column_index
            ),
            on_family_action=lambda family_name: self._add_all_parameters_to_family(table, rows_builder, family_name),
            grid_column_widths=[
                self._get_schedule_grid_column_width(schedule, name) for name in parameter_names
            ],
        )

        if view:
            table.selected_indices = {
                index for index, name in enumerate(parameter_names) if name in view["selected"]
            }
            table._draw_grid()
            form.update_idletasks()
            table.xview_moveto(view.get("xview", 0))
            table.yview_moveto(view.get("yview", 0))

        group_controls = ttk.Frame(form)
        group_controls.pack(fill="x", padx=12)
        self._build_schedule_edit_buttons(group_controls, schedule, lambda: table, reopen).pack(side="left")

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

        def ungroup_headers():
            try:
                self._remove_schedule_header_group(selected_name, table.get_selected_parameter_names())
            except ValueError as exc:
                messagebox.showwarning("Cannot Ungroup Headers", str(exc), parent=form)
                return
            table.set_groups(schedule.header_groups)

        ttk.Label(header_controls, text="Header Groups:").pack(side="left", padx=(0, 6))
        ttk.Button(header_controls, text="Group Selected Headers", command=begin_header_group).pack(side="left")
        ttk.Button(header_controls, text="Ungroup Selected Headers", command=ungroup_headers).pack(side="left", padx=(6, 0))
        self._fit_window_width(form, group_controls, margin=24)
        ttk.Button(form, text="Close", command=form.destroy, style="Action.TButton").pack(pady=(8, 10))

    # --- files ------------------------------------------------------------------

    def save_checkpoint(self):
        return self._save_to(self.checkpoint_path)

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
            return False
        return self._save_to(checkpoint_path)

    def _save_to(self, database_path) -> bool:
        """Save the catalog as JSON, plus a readable CSV and the Revit exports alongside.
        Returns ``False`` if the database couldn't be written."""
        output_paths = get_database_output_paths(database_path)
        self.checkpoint_path = output_paths["checkpoint"]
        try:
            self._write_checkpoint(output_paths["checkpoint"])
            write_database_csv(self.catalog, output_paths["csv"])
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=getattr(self, "root", None))
            return False
        self._mark_saved()
        self._append_message(f"Saved readable database CSV to {output_paths['csv']}")
        self._generate_rfps_file()
        self._generate_shared_parameter_file()
        # Last: the macro module's build is the slow part (in the background with a window).
        self._generate_revit_schedule_macro_file()
        return True

    # --- unsaved changes ----------------------------------------------------------

    def _catalog_state(self) -> str:
        return json.dumps(self.catalog.to_dict(), sort_keys=True, default=str)

    def _mark_saved(self):
        """Remember the database as saved (or as loaded): later edits are unsaved changes."""
        self._saved_state = self._catalog_state()

    def has_unsaved_changes(self) -> bool:
        saved = getattr(self, "_saved_state", None)
        return saved is not None and saved != self._catalog_state()

    def _confirm_unsaved_changes(self, action: str) -> bool:
        """Before ``action`` ("closing", ...), offer to save unsaved changes.

        Returns ``True`` to go ahead (saved, discarded or nothing to save), ``False`` to stop.
        """
        if not self.has_unsaved_changes():
            return True
        choice = self._ask_save_discard_cancel(action)
        if choice == "save":
            return self.save_checkpoint()
        return choice == "discard"

    def _ask_save_discard_cancel(self, action: str):
        """The Unsaved Changes window: ``"save"``, ``"discard"`` or ``None`` (cancel)."""
        root = self.root
        dialog = tk.Toplevel(root)
        dialog.title("Unsaved Changes")
        dialog.transient(root)
        dialog.resizable(False, False)
        ttk.Label(dialog, text="Unsaved Changes", style="Section.TLabel").pack(anchor="w", padx=14, pady=(12, 4))
        ttk.Label(
            dialog,
            text=f"The database has changes that aren't saved to {Path(self.checkpoint_path).name}. "
                 f"Save them before {action}?",
            wraplength=380, justify="left",
        ).pack(anchor="w", padx=14)
        result = {"choice": None}

        def choose(choice):
            result["choice"] = choice
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", padx=14, pady=12)
        cancel = ttk.Button(buttons, text="Cancel", command=lambda: choose(None))
        cancel.pack(side="right")
        ttk.Button(buttons, text="Discard", command=lambda: choose("discard")).pack(side="right", padx=(0, 6))
        save = ttk.Button(buttons, text="Save", command=lambda: choose("save"), style="Action.TButton")
        save.pack(side="right", padx=(0, 6))
        dialog.bind("<Escape>", lambda _event: choose(None))
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(None))
        save.focus_set()
        dialog.grab_set()
        dialog.wait_window()
        return result["choice"]

    def open_database(self):
        """The Load button: ask about unsaved changes, then pick a database to open."""
        if self._confirm_unsaved_changes("opening another database"):
            self.load_checkpoint()

    def import_excel_from_button(self):
        """The Import Excel... button: ask about unsaved changes, then import."""
        if self._confirm_unsaved_changes("importing"):
            self.import_excel_workbook(confirm=False)

    def close(self):
        """Closing the window: ask about unsaved changes, and let a running macro build finish."""
        if not self._confirm_unsaved_changes("closing"):
            return
        if getattr(self, "_macro_build_thread", None) is not None:
            # Quitting now would stop the build part-way.
            self._close_when_built = True
            self._append_message("Closing once the schedule macro has finished building...")
            return
        self.root.destroy()

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
        self._mark_saved()
        lines = [f"Loaded database from {checkpoint_path}"]
        if issues:
            lines.append(f"{len(issues)} problem(s) in the file were fixed or skipped while loading:")
            lines.extend(f"  {issue}" for issue in issues)
        if self.warning_text is not None:
            self.warning_text.insert("1.0", "\n".join(lines) + "\n\n")

    def import_excel_workbook(self, workbook_path=None, confirm=True):
        """Replace the open database with the Excel master workbook's contents.

        Nothing is saved: the import is open like a loaded database, and Save keeps it.
        """
        root = getattr(self, "root", None)
        if workbook_path is None:
            workbook_path = filedialog.askopenfilename(
                title="Import Excel Master Workbook",
                filetypes=[("Excel workbooks", "*.xlsm *.xlsx"), ("All files", "*.*")],
            )
        if not workbook_path:
            return
        if confirm and not messagebox.askyesno(
            "Replace the Open Database?",
            "Importing replaces the open database with the workbook's parameters, families and "
            "schedules. Nothing is saved until you click Save.\n\nImport the Workbook?",
            parent=root,
        ):
            return

        if root is not None:
            root.configure(cursor="watch")
            root.update_idletasks()
        try:
            result = import_workbook(workbook_path)
        except ImportError:
            messagebox.showerror(
                "Import Failed", "Reading Excel workbooks needs the openpyxl package.", parent=root,
            )
            return
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("Import Failed", f"The workbook couldn't be imported:\n{exc}", parent=root)
            return
        finally:
            if root is not None:
                root.configure(cursor="")

        self.catalog = result.catalog
        self.load_issues = result.issues
        self.validate_all()
        lines = list(result.summary)
        lines.extend(f"  {correction}" for correction in result.corrections)
        if result.issues:
            lines.append(f"{len(result.issues)} thing(s) in the workbook were fixed or skipped:")
            lines.extend(f"  {issue}" for issue in result.issues)
        lines.append("Click Save to keep the imported database.")
        if self.warning_text is not None:
            self.warning_text.insert("1.0", "\n".join(lines) + "\n\n")
        return result

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
