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
from revit_parameter_manager import COMMON_PARAM_NAMES, Catalog, Param, guid_change_warning
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


class ScheduleHeaderCanvas(tk.Canvas):
    def __init__(self, master, parameter_names, header_texts, groups=None, on_header_double_click=None, grid_column_widths=None):
        super().__init__(master, background="#ffffff", highlightthickness=0)
        self.parameter_names = list(parameter_names)
        self.header_texts = dict(header_texts)
        self.groups = []
        self.group_layout = []
        self.selected_indices = set()
        self.selection_anchor = None
        self.on_header_double_click = on_header_double_click
        self.column_width = 170
        self.column_widths = []
        self.column_offsets = []
        self.group_row_height = 30
        self.header_height = 58
        self.header_font = tkfont.Font(root=self, font=("Segoe UI", 10, "bold"))
        self.header_top = 0
        self.bind("<Button-1>", self._on_mouse_down)
        self.bind("<B1-Motion>", self._on_mouse_drag)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.set_grid_column_widths(grid_column_widths or [1.0] * len(self.parameter_names))
        self.set_groups(groups or [])

    def set_grid_column_widths(self, widths_in_inches):
        self.column_widths = [max(60, int(float(width) * 48)) for width in widths_in_inches]
        if len(self.column_widths) != len(self.parameter_names):
            self.column_widths = [self.column_width] * len(self.parameter_names)
        self.column_width = self.column_widths[0] if self.column_widths else 170
        self.column_offsets = []
        offset = 0
        for width in self.column_widths:
            self.column_offsets.append(offset)
            offset += width
        self._update_scroll_region()
        self._draw_grid()

    def _update_scroll_region(self):
        width = max(1, sum(self.column_widths))
        height = self.header_top + self.header_height
        self.configure(scrollregion=(0, 0, width, height))

    def _wrap_header_segment(self, text, max_width):
        return _wrap_text_segment(text, max_width, self.header_font)

    def _wrapped_header_text(self, parameter_name, max_width):
        label = self.header_texts.get(parameter_name, parameter_name)
        segments = [label] if label == parameter_name else [label, parameter_name]
        return [
            line
            for segment in segments
            for line in self._wrap_header_segment(segment, max_width)
        ]

    def set_groups(self, groups):
        self.groups = [dict(group) for group in groups]
        parameter_indices = {name: index for index, name in enumerate(self.parameter_names)}
        candidates = []
        for group in self.groups:
            indices = [parameter_indices[name] for name in group["parameter_names"] if name in parameter_indices]
            if len(indices) != len(group["parameter_names"]) or not indices:
                continue
            start_index = min(indices)
            end_index = max(indices)
            candidates.append((start_index, end_index, group))

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

        group_row_count = max(1, len(lane_ends)) if self.parameter_names else 0
        self.header_top = group_row_count * self.group_row_height
        height = self.header_top + self.header_height
        self.configure(height=height)
        self._update_scroll_region()
        self._draw_grid()

    def set_header_texts(self, header_texts):
        self.header_texts = dict(header_texts)
        self._draw_grid()

    def get_selected_parameter_names(self):
        return [
            self.parameter_names[index]
            for index in range(len(self.parameter_names))
            if index in self.selected_indices
        ]

    def _parameter_index_at(self, event):
        if not self.parameter_names or self.canvasy(event.y) < self.header_top:
            return None
        canvas_x = self.canvasx(event.x)
        for index, (left, width) in enumerate(zip(self.column_offsets, self.column_widths)):
            if left <= canvas_x < left + width:
                return index
        return None

    def _on_mouse_down(self, event):
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
        if index is not None and self.on_header_double_click is not None:
            self.on_header_double_click(self.parameter_names[index])

    def _draw_grid(self):
        self.delete("all")
        if not self.parameter_names:
            return

        wrapped_headers = [
            self._wrapped_header_text(
                parameter_name,
                max(1, self.column_widths[index] - 14),
            )
            for index, parameter_name in enumerate(self.parameter_names)
        ]
        line_height = self.header_font.metrics("linespace")
        self.header_height = max(
            58,
            max(len(lines) for lines in wrapped_headers) * line_height + 20,
        )

        group_row_count = max(1, max((lane for lane, *_ in self.group_layout), default=-1) + 1)
        self.configure(
            height=self.header_top + self.header_height,
            scrollregion=(
                0,
                0,
                max(1, sum(self.column_widths)),
                self.header_top + self.header_height,
            ),
        )
        for lane in range(group_row_count):
            top = lane * self.group_row_height
            for index in range(len(self.parameter_names)):
                left = self.column_offsets[index]
                right = left + self.column_widths[index]
                self.create_rectangle(
                    left,
                    top,
                    right,
                    top + self.group_row_height,
                    fill="#f1f5f3",
                    outline="#c8d2ce",
                )

        for lane, start_index, end_index, group in self.group_layout:
            left = self.column_offsets[start_index]
            right = self.column_offsets[end_index] + self.column_widths[end_index]
            top = lane * self.group_row_height
            self.create_rectangle(
                left,
                top,
                right,
                top + self.group_row_height,
                fill="#dce9e4",
                outline="#7a9187",
                width=2,
            )
            self.create_text(
                (left + right) / 2,
                top + self.group_row_height / 2,
                text=group["caption"],
                width=max(1, right - left - 12),
                font=("Segoe UI", 10, "bold"),
            )

        for index, (parameter_name, header_lines) in enumerate(
            zip(self.parameter_names, wrapped_headers)
        ):
            left = self.column_offsets[index]
            right = left + self.column_widths[index]
            top = self.header_top
            selected = index in self.selected_indices
            self.create_rectangle(
                left,
                top,
                right,
                top + self.header_height,
                fill="#dcefe7" if selected else "#ffffff",
                outline="#7a9187" if selected else "#c8d2ce",
                width=2 if selected else 1,
            )
            self.create_text(
                (left + right) / 2,
                top + self.header_height / 2,
                text="\n".join(header_lines),
                width=self.column_widths[index] - 14,
                justify="center",
                font=self.header_font,
            )



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
    _value_columns = ["parameter_name", "default_value", "override", "value"]
    _schedule_value_columns = ["family_name", "parameter_name", "override", "value"]

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
            self.family_tree.bind("<Double-1>", self._open_selected_family_window)
        if self.group_tree is not None:
            self.group_tree.bind("<Double-1>", self._open_selected_schedule_window)

    def _bind_table_edit_events(self, tree: ttk.Treeview, table_name: str):
        if tree is None:
            return
        if table_name in {"params"}:
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

    # --- value overrides --------------------------------------------------------

    def _connected_override_locations(self, location, param_name: str):
        """Where else, connected to ``location``, the same override can go.

        From a schedule: the other families in that schedule that show the parameter.
        From a family: the schedules that family is in that show the parameter.
        Each is a ``(location, label)`` pair.
        """
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

    def _override_value(self, location, param_name: str, new_value) -> bool:
        """Override (or, with a blank value, clear) a parameter's value at ``location``.

        ``location`` is ``(family_name, schedule_name)``, with ``None`` for the family
        everywhere. The user can pick connected places to get the same change (other
        families in the schedule, or the family's schedules) and can also make it the
        parameter's default value. Returns ``False`` if the user cancels.
        """
        value = cell_text(new_value) or None
        connected = self._connected_override_locations(location, param_name)
        param = self.catalog.get_param(param_name)

        answer = {"locations": [], "parameter": False}
        if connected or param is not None:
            answer = self._ask_override_scope(param_name, value, location, connected, param is not None)
            if answer is None:
                return False

        for target in [location, *answer["locations"]]:
            self.catalog.apply_override(target, param_name, value=value)
        if answer["parameter"]:
            param.value = value
        self.validate_all()
        return True

    def _override_questions(self, param_name: str, value, location):
        """The draft wording of the override prompt: ``(heading, list label, parameter checkbox)``."""
        family_name, schedule_name = location
        if schedule_name is None:
            where = family_name
            list_label = f"Also apply it to {family_name} in these schedules:"
        else:
            where = f"{family_name} in schedule '{schedule_name}'"
            list_label = f"Also apply it to these families in schedule '{schedule_name}':"
        if value is None:
            heading = f"Clear the override of '{param_name}' for {where}."
            parameter = f"Also clear the default value of '{param_name}'"
        else:
            heading = f"Override '{param_name}' with '{value}' for {where}."
            parameter = f"Also make '{value}' the default value of '{param_name}'"
        return heading, list_label, parameter

    def _ask_override_scope(self, param_name: str, value, location, connected, ask_parameter: bool):
        """Ask where else the override goes.

        ``connected`` is a list of ``(location, label)`` pairs to choose from.
        Returns ``{"locations": [...], "parameter": bool}``, or ``None`` to cancel.
        """
        heading, list_label, parameter_text = self._override_questions(param_name, value, location)
        dialog = tk.Toplevel(self.root)
        dialog.title("Override Value")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("480x360" if connected else "480x170")

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
        ttk.Button(buttons, text="Apply", command=apply).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 6))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.wait_window()
        return result["answer"]

    def _edit_value_dialog(self, parent, title: str, prompt: str, current_value: str, on_save):
        """A small dialog for one value. ``on_save(value)`` returns ``False`` to keep it open."""
        editor = tk.Toplevel(parent)
        editor.title(title)
        editor.transient(parent)
        editor.grab_set()
        editor.geometry("420x130")
        ttk.Label(editor, text=prompt, style="Section.TLabel", wraplength=400).pack(anchor="w", padx=10, pady=(10, 4))
        value_var = tk.StringVar(value=current_value)
        entry = ttk.Entry(editor, textvariable=value_var)
        entry.pack(fill="x", padx=10, pady=4)
        entry.focus_set()
        entry.selection_range(0, tk.END)

        def save():
            try:
                saved = on_save(value_var.get())
            except ValueError as exc:
                messagebox.showerror("Invalid value", str(exc), parent=editor)
                return
            if saved is not False:
                editor.destroy()

        buttons = ttk.Frame(editor)
        buttons.pack(fill="x", padx=10, pady=(4, 8))
        ttk.Button(buttons, text="Save", command=save).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=editor.destroy).pack(side="right", padx=(0, 6))
        entry.bind("<Return>", lambda _event: save())
        return editor

    def _family_value_rows(self, fam) -> List[dict]:
        overrides = fam.overrides
        return [
            {
                "parameter_name": param.name,
                "default_value": "" if param.value is None else param.value,
                "override": overrides.get(param.name, {}).get("value", ""),
                "value": "" if resolved.value is None else resolved.value,
            }
            for param, resolved in zip(fam.params, fam.resolved_params())
            if param.name not in COMMON_PARAM_NAMES
        ]

    def _schedule_value_rows(self, schedule) -> List[dict]:
        rows = []
        for fam in schedule.fams:
            overrides = schedule.family_overrides.get(fam.name, {})
            resolved = {param.name: param for param in schedule.resolved_family_params(fam)}
            for param_name in schedule.family_param_names(fam):
                if schedule.field_names is None and param_name in COMMON_PARAM_NAMES:
                    continue
                value = resolved[param_name].value
                rows.append({
                    "family_name": fam.name,
                    "parameter_name": param_name,
                    "override": overrides.get(param_name, {}).get("value", ""),
                    "value": "" if value is None else value,
                })
        return rows

    def _build_value_tree(self, parent, columns: Sequence[str], height: int = 8) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=list(columns), show="headings", height=height)
        labels = {"override": "Override", "value": "Value"}
        for column in columns:
            tree.heading(column, text=labels.get(column, self._humanize_column_name(column)))
            tree.column(column, width=150, anchor="w")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return tree

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
        form.geometry("760x680")
        ttk.Label(form, text=title, style="Title.TLabel").pack(anchor="w", padx=12, pady=(10, 4))

        row = self.families_df.iloc[row_index]
        entries = {}
        for col in columns:
            if col in {"status", "validation_message"}:
                ttk.Label(
                    form,
                    text=f"{self._humanize_column_name(col)}: {row.get(col)}",
                    wraplength=720,
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

        values_box = ttk.LabelFrame(form, text="Parameter Values (double-click to override)", padding=8)
        values_box.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        value_tree = self._build_value_tree(values_box, self._value_columns)

        def refresh_values():
            self._render_tree(value_tree, pd.DataFrame(self._family_value_rows(fam)), self._value_columns)

        def edit_value(event):
            row_id = value_tree.identify_row(event.y)
            if not row_id:
                return
            parameter_name = value_tree.item(row_id, "values")[0]
            current = fam.overrides.get(parameter_name, {}).get("value", "")

            def save(value):
                saved = self._override_value((fam.name, None), parameter_name, value)
                refresh_values()
                return saved

            self._edit_value_dialog(
                form,
                "Override Value",
                f"Value of '{parameter_name}' for {fam.name} (blank uses the default):",
                "" if current is None else str(current),
                save,
            )

        value_tree.bind("<Double-1>", edit_value)
        refresh_values()

    def _open_schedule_window(self, selected_name: str):
        schedule = self.catalog.get_schedule(selected_name)
        if schedule is None:
            return

        form = tk.Toplevel(self.root)
        form.title(f"Schedule Details: {selected_name}")
        form.transient(self.root)
        form.grab_set()
        form.geometry("880x700")

        ttk.Label(form, text=f"Schedule: {selected_name}", style="Title.TLabel").pack(anchor="w", padx=12, pady=(10, 4))
        ttk.Label(form, text=f"Status: {schedule.status}", style="Section.TLabel").pack(anchor="w", padx=12, pady=(0, 6))
        ttk.Label(form, text=f"Validation: {schedule.validation_message or 'None'}", wraplength=840, justify="left").pack(anchor="w", padx=12, pady=(0, 8))

        content = ttk.Frame(form)
        content.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        content.grid_columnconfigure(0, weight=1, uniform="schedule_detail")
        content.grid_columnconfigure(1, weight=2, uniform="schedule_detail")
        content.grid_rowconfigure(0, weight=1)

        family_box = ttk.LabelFrame(content, text="Families", padding=8)
        family_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        family_names = [fam.name for fam in schedule.fams]
        family_list = tk.Text(family_box, height=8, width=32, wrap="word")
        family_list.insert("1.0", "\n".join(family_names) if family_names else "No families assigned")
        family_list.configure(state="disabled")
        family_list.pack(fill="both", expand=True)

        parameter_box = ttk.LabelFrame(content, text="Parameters", padding=8)
        parameter_box.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        parameter_names = self._get_schedule_parameter_names(schedule)
        if parameter_names:
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
                ttk.Label(
                    editor,
                    text=f"Header text (blank uses '{default_header}'): ",
                    style="Section.TLabel",
                ).pack(anchor="w", padx=10, pady=(10, 4))
                header_var = tk.StringVar(value=current_override)
                header_entry = ttk.Entry(editor, textvariable=header_var)
                header_entry.pack(fill="x", padx=10, pady=4)
                ttk.Label(
                    editor,
                    text=f"Column width in inches (blank uses {default_width:g} in):",
                    style="Section.TLabel",
                ).pack(anchor="w", padx=10, pady=(8, 4))
                width_var = tk.StringVar(value=current_width_override)
                width_entry = ttk.Entry(editor, textvariable=width_var)
                width_entry.pack(fill="x", padx=10, pady=4)
                header_entry.focus_set()

                def save_header_override():
                    try:
                        self._set_schedule_column(selected_name, parameter_name, header_var.get(), width_var.get())
                    except ValueError as exc:
                        messagebox.showwarning("Invalid width", str(exc), parent=editor)
                        return
                    header_canvas.set_header_texts({
                        name: self._get_schedule_header_text(schedule, name) for name in parameter_names
                    })
                    header_canvas.set_grid_column_widths([
                        self._get_schedule_grid_column_width(schedule, name) for name in parameter_names
                    ])
                    editor.destroy()

                buttons = ttk.Frame(editor)
                buttons.pack(fill="x", padx=10, pady=(4, 8))
                ttk.Button(buttons, text="Save", command=save_header_override).pack(side="right")
                ttk.Button(buttons, text="Cancel", command=editor.destroy).pack(side="right", padx=(0, 6))
                header_entry.bind("<Return>", lambda _event: save_header_override())
                width_entry.bind("<Return>", lambda _event: save_header_override())

            header_canvas = ScheduleHeaderCanvas(
                parameter_box,
                parameter_names,
                {name: self._get_schedule_header_text(schedule, name) for name in parameter_names},
                groups=schedule.header_groups,
                on_header_double_click=edit_schedule_header,
                grid_column_widths=[
                    self._get_schedule_grid_column_width(schedule, name) for name in parameter_names
                ],
            )
            canvas_frame = ttk.Frame(parameter_box)
            canvas_frame.pack(fill="both", expand=True)
            header_canvas.pack(side="top", fill="both", expand=True)
            header_scroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=header_canvas.xview)
            header_canvas.configure(xscrollcommand=header_scroll.set)
            header_scroll.pack(side="bottom", fill="x")

            selection_box = ttk.LabelFrame(parameter_box, text="Header Groups", padding=6)
            selection_box.pack(fill="x", pady=(8, 0))
            group_controls = ttk.Frame(selection_box)
            group_controls.pack(fill="x")

            def begin_header_group():
                selected_parameters = header_canvas.get_selected_parameter_names()
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
                    header_canvas.set_groups(schedule.header_groups)
                    editor.destroy()

                buttons = ttk.Frame(editor)
                buttons.pack(fill="x", padx=10, pady=(4, 8))
                ttk.Button(buttons, text="Group", command=save_header_group).pack(side="right")
                ttk.Button(buttons, text="Cancel", command=editor.destroy).pack(side="right", padx=(0, 6))
                caption_entry.bind("<Return>", lambda _event: save_header_group())

            ttk.Button(group_controls, text="Group Selected", command=begin_header_group).pack(side="right")
        else:
            ttk.Label(parameter_box, text="No parameters assigned").pack(anchor="w")

        values_box = ttk.LabelFrame(form, text="Values in this Schedule (double-click to override)", padding=8)
        values_box.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        value_tree = self._build_value_tree(values_box, self._schedule_value_columns, height=6)

        def refresh_values():
            self._render_tree(value_tree, pd.DataFrame(self._schedule_value_rows(schedule)), self._schedule_value_columns)

        def edit_value(event):
            row_id = value_tree.identify_row(event.y)
            if not row_id:
                return
            family_name, parameter_name = value_tree.item(row_id, "values")[:2]
            current = schedule.family_overrides.get(family_name, {}).get(parameter_name, {}).get("value", "")

            def save(value):
                saved = self._override_value((family_name, selected_name), parameter_name, value)
                refresh_values()
                return saved

            self._edit_value_dialog(
                form,
                "Override Value",
                f"Value of '{parameter_name}' for {family_name} in this schedule "
                "(blank uses the family's value):",
                "" if current is None else str(current),
                save,
            )

        value_tree.bind("<Double-1>", edit_value)
        refresh_values()

        ttk.Button(form, text="Close", command=form.destroy, style="Action.TButton").pack(pady=(0, 10))

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
