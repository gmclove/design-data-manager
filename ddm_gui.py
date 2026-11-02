import importlib.util
import json
import math
import os
import pickle
import re
import tkinter.font as tkfont
import uuid
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

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

from revit_schedule_macro_generator import generate_schedule_macro_source
from revit_parameter_scheduler_export import generate_rfps_content
from revit_shared_parameter_export import generate_shared_parameter_content, parameter_guid
from revit_parameter_manager import guid_change_warning
from formula import rename_reference


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
    """Simple dataframe-first GUI for reviewing validation state and syncing to Quickbase."""

    _default_grid_column_width_in = 1.0
    _database_csv_columns = [
        "record_type", "name", "guid", "header_text", "grid_column_width", "dtype", "group_under",
        "formula", "instance_param", "default_value", "status", "validation_message", "client", "country",
        "category", "description", "family_name", "parameter_name", "group_name",
        "header_text_override", "grid_column_width_override", "override_entry", "caption",
        "parameter_names", "top_row", "bottom_row",
    ]

    _table_columns = {
        "params": ["name", "header_text", "grid_column_width", "dtype", "group_under", "formula", "instance_param", "default_value", "status", "validation_message", "guid"],
        "families": ["name", "client", "country", "category", "description", "status", "validation_message"],
        "links": ["family_name", "parameter_name"],
        "groups": ["family_name", "group_name", "parameter_name", "header_text_override", "grid_column_width_override", "override_entry", "status", "validation_message"],
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

        self.params_df = pd.DataFrame(
            [{"name": "Length", "dtype": "Length", "group_under": "Dimensions", "formula": "Width * Height", "instance_param": True, "status": "Draft", "validation_message": ""},
             {"name": "Width", "dtype": "Length", "group_under": "Dimensions", "formula": "", "instance_param": True, "status": "Approved", "validation_message": ""},
             {"name": "Height", "dtype": "Length", "group_under": "Dimensions", "formula": "", "instance_param": True, "status": "Approved", "validation_message": ""},
             {"name": "Area", "dtype": "Area", "group_under": "Dimensions", "formula": "Length * Width", "instance_param": False, "status": "Error", "validation_message": "Missing family association"},
             {"name": "Depth", "dtype": "Length", "group_under": "Dimensions", "formula": "", "instance_param": True, "status": "Draft", "validation_message": ""},
             {"name": "UValue", "dtype": "Number", "group_under": "Envelope", "formula": "", "instance_param": False, "status": "Draft", "validation_message": ""},
             {"name": "ScreenRatio", "dtype": "Number", "group_under": "Envelope", "formula": "", "instance_param": False, "status": "Draft", "validation_message": ""},
             {"name": "GlassArea", "dtype": "Area", "group_under": "Envelope", "formula": "", "instance_param": False, "status": "Draft", "validation_message": ""},
             {"name": "PowerLoad", "dtype": "Number", "group_under": "Electrical", "formula": "", "instance_param": False, "status": "Draft", "validation_message": ""},
             {"name": "FacadeRatio", "dtype": "Number", "group_under": "Envelope", "formula": "", "instance_param": False, "status": "Draft", "validation_message": ""},
             {"name": "HeadHeight", "dtype": "Length", "group_under": "Dimensions", "formula": "", "instance_param": True, "status": "Draft", "validation_message": ""},
             {"name": "Openings", "dtype": "Number", "group_under": "Openings", "formula": "", "instance_param": False, "status": "Draft", "validation_message": ""},
            ]
        )
        self.params_df["header_text"] = self.params_df["name"]
        self.params_df["grid_column_width"] = self._default_grid_column_width_in
        self.params_df["default_value"] = ""
        self.params_df["validation_message"] = self.params_df["validation_message"].fillna("").astype(str)

        self.families_df = pd.DataFrame(
            [
                {"name": "Family_A", "client": "Client A", "country": "USA", "category": "Doors", "description": "Main family", "status": "Draft", "validation_message": ""},
                {"name": "Family_B", "client": "Client B", "country": "Canada", "category": "Windows", "description": "Secondary family", "status": "Draft", "validation_message": ""},
                {"name": "Family_C", "client": "Client C", "country": "United Kingdom", "category": "Curtain Wall", "description": "Glazed facade family", "status": "Ready", "validation_message": ""},
                {"name": "Family_D", "client": "Client D", "country": "Germany", "category": "Casework", "description": "Custom cabinet family", "status": "Draft", "validation_message": ""},
                {"name": "Family_E", "client": "Client E", "country": "France", "category": "Railings", "description": "Stair guard family", "status": "Draft", "validation_message": ""},
                {"name": "Family_F", "client": "Client F", "country": "Spain", "category": "Structural Framing", "description": "Steel beam family", "status": "Draft", "validation_message": ""},
                {"name": "Family_G", "client": "Client G", "country": "Japan", "category": "Furniture", "description": "Modular joinery family", "status": "Draft", "validation_message": ""},
                {"name": "Family_H", "client": "Client H", "country": "Australia", "category": "Mechanical Equipment", "description": "Air handling unit family", "status": "Draft", "validation_message": ""},
                {"name": "Family_I", "client": "Client I", "country": "Sweden", "category": "Generic Models", "description": "Envelope panel family", "status": "Draft", "validation_message": ""},
                {"name": "Family_J", "client": "Client J", "country": "Norway", "category": "Openings", "description": "Vertical daylight opening family", "status": "Draft", "validation_message": ""},
            ]
        )
        self.families_df["validation_message"] = self.families_df["validation_message"].fillna("").astype(str)

        self.family_param_links_df = pd.DataFrame(
            [
                {"family_name": "Family_A", "parameter_name": "Length"},
                {"family_name": "Family_A", "parameter_name": "Width"},
                {"family_name": "Family_A", "parameter_name": "Area"},
                {"family_name": "Family_B", "parameter_name": "Length"},
                {"family_name": "Family_C", "parameter_name": "Length"},
                {"family_name": "Family_C", "parameter_name": "UValue"},
                {"family_name": "Family_C", "parameter_name": "GlassArea"},
                {"family_name": "Family_D", "parameter_name": "Depth"},
                {"family_name": "Family_D", "parameter_name": "Width"},
                {"family_name": "Family_E", "parameter_name": "Height"},
                {"family_name": "Family_E", "parameter_name": "RValue"},
                {"family_name": "Family_F", "parameter_name": "Length"},
                {"family_name": "Family_F", "parameter_name": "Width"},
                {"family_name": "Family_G", "parameter_name": "Depth"},
                {"family_name": "Family_G", "parameter_name": "FinishCode"},
                {"family_name": "Family_H", "parameter_name": "PowerLoad"},
                {"family_name": "Family_I", "parameter_name": "FacadeRatio"},
                {"family_name": "Family_I", "parameter_name": "GlassArea"},
                {"family_name": "Family_J", "parameter_name": "HeadHeight"},
                {"family_name": "Family_J", "parameter_name": "Openings"},
            ]
        )
        self.family_groups_df = pd.DataFrame(
            [
                {"family_name": "Family_A", "group_name": "Schedule A", "parameter_name": "Length", "override_entry": "", "status": "Ready", "validation_message": ""},
                {"family_name": "Family_A", "group_name": "Schedule A", "parameter_name": "Width", "override_entry": "Override Width", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_B", "group_name": "Schedule B", "parameter_name": "Length", "override_entry": "", "status": "Ready", "validation_message": ""},
                {"family_name": "Family_C", "group_name": "Envelope Schedule", "parameter_name": "UValue", "override_entry": "0.21", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_C", "group_name": "Envelope Schedule", "parameter_name": "GlassArea", "override_entry": "14.8", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_D", "group_name": "Casework Schedule", "parameter_name": "Depth", "override_entry": "", "status": "Ready", "validation_message": ""},
                {"family_name": "Family_E", "group_name": "Guardrail Schedule", "parameter_name": "RValue", "override_entry": "", "status": "Ready", "validation_message": ""},
                {"family_name": "Family_F", "group_name": "Structural Schedule", "parameter_name": "GrossArea", "override_entry": "35.5", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_G", "group_name": "Joinery Schedule", "parameter_name": "FinishCode", "override_entry": "J-04", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_H", "group_name": "Mechanical Schedule", "parameter_name": "PowerLoad", "override_entry": "12.4", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_I", "group_name": "Facade Review", "parameter_name": "FacadeRatio", "override_entry": "0.62", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_J", "group_name": "Opening Schedule", "parameter_name": "HeadHeight", "override_entry": "2.4", "status": "Ready", "validation_message": "Override entry recorded"},
            ]
        )
        self.family_groups_df["header_text_override"] = ""
        self.family_groups_df["grid_column_width_override"] = ""
        self._append_extended_schedule_examples()

        self.warning_text = None
        self.param_tree = None
        self.family_tree = None
        self.link_tree = None
        self.group_tree = None
        self.schedule_header_groups = {}
        self.schedule_models = {}

        self._table_columns = {
            "params": ["name", "header_text", "grid_column_width", "dtype", "group_under", "formula", "instance_param", "status", "validation_message", "guid"],
            "families": ["name", "client", "country", "category", "description", "status", "validation_message"],
            "links": ["family_name", "parameter_name"],
            "groups": ["family_name", "group_name", "parameter_name", "header_text_override", "grid_column_width_override", "override_entry", "status", "validation_message"],
        }

        self.build_ui()
        self.render_tables()
        startup_path = (
            DEFAULT_CHECKPOINT_PATH
            if DEFAULT_CHECKPOINT_PATH.exists()
            else DEMO_DATA_PATH
        )
        self.load_checkpoint(str(startup_path))
        self.checkpoint_path = DEFAULT_CHECKPOINT_PATH

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
        self.warning_text.insert(
            tk.END,
            f"\nGenerated Revit schedule macro: {output_path}",
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
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "RF Tools Export Failed",
                f"The database was saved, but the RF Tools parameter scheduler file "
                f"could not be generated:\n{exc}",
                parent=self.root,
            )
            return
        self.warning_text.insert(
            tk.END,
            f"\nGenerated RF Tools parameter scheduler file: {output_path}",
        )

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
        self.warning_text.insert(
            tk.END,
            f"\nGenerated Revit shared parameter file: {output_path}",
        )

    @staticmethod
    def _humanize_column_name(column_name: str) -> str:
        if column_name in DDMGUI._display_labels:
            return DDMGUI._display_labels[column_name]
        return column_name.replace("_", " ").title()

    def _get_table_columns(self, table_name: str):
        if hasattr(self, "_table_columns") and table_name in self._table_columns:
            return self._table_columns[table_name]
        return DDMGUI._table_columns[table_name]

    def _build_schedule_summary_df(self) -> pd.DataFrame:
        if not hasattr(self, "family_groups_df") or self.family_groups_df is None or self.family_groups_df.empty:
            return pd.DataFrame(columns=self._schedule_summary_columns)

        summary_rows = []
        for schedule_name, rows in self.family_groups_df.groupby("group_name", dropna=False):
            family_names = sorted({str(value).strip() for value in rows["family_name"].dropna().astype(str).tolist() if str(value).strip()})
            parameter_names = sorted({str(value).strip() for value in rows["parameter_name"].dropna().astype(str).tolist() if str(value).strip()})
            status_values = [str(value).strip().lower() for value in rows["status"].fillna("").astype(str).tolist() if str(value).strip()]
            status = "Error" if any(status == "error" for status in status_values) else ("Ready" if status_values else "Ready")
            validation_message = "; ".join({
                str(value).strip()
                for value in rows["validation_message"].fillna("").astype(str).tolist()
                if str(value).strip()
            })

            summary_rows.append({
                "name": str(schedule_name),
                "family_count": len(family_names),
                "parameter_count": len(parameter_names),
                "status": status,
                "validation_message": validation_message,
            })

        summary_df = pd.DataFrame(summary_rows, columns=self._schedule_summary_columns)
        return summary_df if not summary_df.empty else pd.DataFrame(columns=self._schedule_summary_columns)

    @staticmethod
    def _get_schedule_parameter_names(schedule_rows: pd.DataFrame) -> List[str]:
        return sorted({
            str(value).strip()
            for value in schedule_rows.get("parameter_name", pd.Series(dtype=str)).dropna().astype(str)
            if str(value).strip()
        })

    def _get_schedule_header_text(self, schedule_rows: pd.DataFrame, parameter_name: str) -> str:
        if "header_text_override" in schedule_rows.columns:
            overrides = schedule_rows.loc[
                schedule_rows["parameter_name"].astype(str).str.strip() == parameter_name,
                "header_text_override",
            ].dropna().astype(str).str.strip()
            overrides = overrides[overrides != ""]
            if not overrides.empty:
                return overrides.iloc[0]

        matching_params = self.params_df[
            self.params_df["name"].astype(str).str.strip() == parameter_name
        ]
        if matching_params.empty:
            return parameter_name
        default_header = str(matching_params.iloc[0].get("header_text") or "").strip()
        return default_header or parameter_name

    def _get_schedule_grid_column_width(self, schedule_rows: pd.DataFrame, parameter_name: str) -> float:
        if "grid_column_width_override" in schedule_rows.columns:
            overrides = schedule_rows.loc[
                schedule_rows["parameter_name"].astype(str).str.strip() == parameter_name,
                "grid_column_width_override",
            ].dropna().astype(str).str.strip()
            overrides = overrides[overrides != ""]
            if not overrides.empty:
                return float(overrides.iloc[0])

        matching_params = self.params_df[
            self.params_df["name"].astype(str).str.strip() == parameter_name
        ]
        if matching_params.empty:
            return self._default_grid_column_width_in
        width = matching_params.iloc[0].get("grid_column_width", self._default_grid_column_width_in)
        if width is None or pd.isna(width) or not str(width).strip():
            return self._default_grid_column_width_in
        return float(width)

    def _add_schedule_header_group(self, schedule_name: str, parameter_names: Sequence[str], caption: str):
        if not hasattr(self, "schedule_header_groups"):
            self.schedule_header_groups = {}
        if not hasattr(self, "schedule_models"):
            self.schedule_models = {}

        schedule_rows = self.family_groups_df[
            self.family_groups_df["group_name"] == schedule_name
        ].copy()
        if schedule_rows.empty:
            raise ValueError("Schedule not found: {}".format(schedule_name))

        schedule_model = self.schedule_models.get(schedule_name)
        if schedule_model is None:
            _, family_models, _, all_families_schedule = self._build_model_validation_snapshot()
            family_names = sorted({
                str(value).strip()
                for value in schedule_rows["family_name"].dropna().astype(str)
                if str(value).strip()
            })
            missing_families = [name for name in family_names if name not in family_models]
            if missing_families:
                raise ValueError("Family not found: {}".format(", ".join(missing_families)))

            schedule_overrides = {}
            schedule_width_overrides = {}
            if "header_text_override" in schedule_rows.columns:
                for parameter_name in self._get_schedule_parameter_names(schedule_rows):
                    overrides = schedule_rows.loc[
                        schedule_rows["parameter_name"].astype(str).str.strip() == parameter_name,
                        "header_text_override",
                    ].dropna().astype(str).str.strip()
                    overrides = overrides[overrides != ""]
                    if not overrides.empty:
                        schedule_overrides[parameter_name] = overrides.iloc[0]
            if "grid_column_width_override" in schedule_rows.columns:
                for parameter_name in self._get_schedule_parameter_names(schedule_rows):
                    overrides = schedule_rows.loc[
                        schedule_rows["parameter_name"].astype(str).str.strip() == parameter_name,
                        "grid_column_width_override",
                    ].dropna().astype(str).str.strip()
                    overrides = overrides[overrides != ""]
                    if not overrides.empty:
                        schedule_width_overrides[parameter_name] = float(overrides.iloc[0])

            schedule_model = type(all_families_schedule)(
                name=schedule_name,
                fams=[family_models[name] for name in family_names],
                header_text_overrides=schedule_overrides,
                grid_column_width_overrides=schedule_width_overrides,
            )
            params_by_name = {}
            for parameter in schedule_model.params:
                params_by_name.setdefault(parameter.name, parameter)
            parameter_order = self._get_schedule_parameter_names(schedule_rows)
            missing_parameters = [name for name in parameter_order if name not in params_by_name]
            if missing_parameters:
                raise ValueError(
                    "Parameters are not associated with the schedule families: {}".format(
                        ", ".join(missing_parameters)
                    )
                )
            schedule_model.params = [params_by_name[name] for name in parameter_order]
            for group in self.schedule_header_groups.get(schedule_name, []):
                schedule_model.add_header_group(
                    group["caption"],
                    group["parameter_names"],
                    top_row=group.get("top_row", 0),
                    bottom_row=group.get("bottom_row", 0),
                )
            self.schedule_models[schedule_name] = schedule_model

        group = schedule_model.add_header_group(caption, parameter_names)
        self.schedule_header_groups[schedule_name] = [
            {
                "caption": item["caption"],
                "parameter_names": list(item["parameter_names"]),
                "top_row": item["top_row"],
                "bottom_row": item["bottom_row"],
            }
            for item in schedule_model.header_groups
        ]
        return group

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
        elif table_name == "links":
            columns = self._get_table_columns("links")
            tree = ttk.Treeview(frame, columns=columns, show="headings")
            for col in columns:
                tree.heading(col, text=self._humanize_column_name(col))
                tree.column(col, width=240, anchor="w")
            self.link_tree = tree
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
        if table_name == "params":
            tree = self.param_tree
        elif table_name == "families":
            tree = self.family_tree
        elif table_name == "links":
            tree = self.link_tree
        else:
            tree = self.group_tree

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

    def _append_extended_schedule_examples(self):
        self.params_df = pd.concat(
            [
                self.params_df,
                pd.DataFrame(
                    [
                        {"name": "ClearanceHeight", "header_text": "Clearance Height", "dtype": "Length", "group_under": "Dimensions", "formula": "", "instance_param": True, "status": "Draft", "validation_message": ""},
                        {"name": "ServiceClearance", "header_text": "Service Clearance", "dtype": "Length", "group_under": "Dimensions", "formula": "", "instance_param": True, "status": "Draft", "validation_message": ""},
                        {"name": "FireRating", "header_text": "Fire Rating", "dtype": "Text", "group_under": "Compliance", "formula": "", "instance_param": False, "status": "Draft", "validation_message": ""},
                    ]
                ),
            ],
            ignore_index=True,
        )
        self.params_df["grid_column_width"] = self.params_df["grid_column_width"].fillna(
            self._default_grid_column_width_in
        )
        self.families_df = pd.concat(
            [
                self.families_df,
                pd.DataFrame(
                    [
                        {"name": "Family_K", "client": "Client K", "country": "Ireland", "category": "Doors", "description": "Rated service door", "status": "Draft", "validation_message": ""},
                        {"name": "Family_L", "client": "Client L", "country": "Netherlands", "category": "Mechanical Equipment", "description": "Plant room equipment", "status": "Draft", "validation_message": ""},
                    ]
                ),
            ],
            ignore_index=True,
        )
        self.family_param_links_df = pd.concat(
            [
                self.family_param_links_df,
                pd.DataFrame(
                    [
                        {"family_name": "Family_K", "parameter_name": "ClearanceHeight"},
                        {"family_name": "Family_K", "parameter_name": "FireRating"},
                        {"family_name": "Family_L", "parameter_name": "ServiceClearance"},
                        {"family_name": "Family_L", "parameter_name": "FireRating"},
                    ]
                ),
            ],
            ignore_index=True,
        )
        self.family_groups_df = pd.concat(
            [
                self.family_groups_df,
                pd.DataFrame(
                    [
                        {"family_name": "Family_K", "group_name": "Safety and Clearance", "parameter_name": "ClearanceHeight", "header_text_override": "", "override_entry": "2.1 m", "status": "Ready", "validation_message": "Override entry recorded"},
                        {"family_name": "Family_K", "group_name": "Safety and Clearance", "parameter_name": "FireRating", "header_text_override": "", "override_entry": "90 min", "status": "Ready", "validation_message": "Override entry recorded"},
                        {"family_name": "Family_L", "group_name": "Safety and Clearance", "parameter_name": "ServiceClearance", "header_text_override": "", "override_entry": "600 mm", "status": "Ready", "validation_message": "Override entry recorded"},
                        {"family_name": "Family_L", "group_name": "Safety and Clearance", "parameter_name": "FireRating", "header_text_override": "", "override_entry": "120 min", "status": "Ready", "validation_message": "Override entry recorded"},
                    ]
                ),
            ],
            ignore_index=True,
        )
        self.family_groups_df["grid_column_width_override"] = self.family_groups_df[
            "grid_column_width_override"
        ].fillna("")

    def render_tables(self):
        if not hasattr(self, "family_groups_df") or self.family_groups_df is None:
            self.family_groups_df = pd.DataFrame(columns=self._get_table_columns("groups"))
        if not hasattr(self, "group_tree"):
            self.group_tree = None

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

    def _load_revit_parameter_manager(self):
        module_path = Path(__file__).with_name("revit_parameter_manager.py")
        if not module_path.exists():
            return None

        spec = importlib.util.spec_from_file_location("revit_parameter_manager_model", module_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _build_model_validation_snapshot(self):
        model_module = self._load_revit_parameter_manager()
        if model_module is None:
            return {}, {}, {}, []

        Param = model_module.Param
        Fam = model_module.Fam
        Schedule = model_module.Schedule
        # Each validation pass builds a fresh catalog from the tables, so names
        # from earlier passes (or deleted rows) never leak into this one.
        catalog = model_module.Catalog()

        param_models = []
        for _, row in self.params_df.iterrows():
            name = str(row.get("name") or "").strip()
            if not name:
                continue

            dtype = str(row.get("dtype") or "")
            instance_value = row.get("instance_param", True)
            instance_param = False
            header_text = name
            grid_column_width = self._default_grid_column_width_in
            param = None
            try:
                normalized_instance = str(instance_value).strip().lower()
                if normalized_instance not in {"true", "1", "yes", "y", "false", "0", "no", "n"}:
                    raise ValueError("Instance Param must be true or false.")
                instance_param = normalized_instance in {"true", "1", "yes", "y"}
                header_text = row.get("header_text")
                if header_text is None or pd.isna(header_text) or not str(header_text).strip():
                    header_text = name
                else:
                    header_text = str(header_text).strip()
                grid_column_width = row.get(
                    "grid_column_width",
                    self._default_grid_column_width_in,
                )
                if grid_column_width is None or pd.isna(grid_column_width) or not str(grid_column_width).strip():
                    grid_column_width = self._default_grid_column_width_in
                else:
                    try:
                        grid_column_width = float(grid_column_width)
                    except (TypeError, ValueError):
                        raise ValueError("Grid column width must be a number in inches.") from None
                param = catalog.get_param(name)
                if param is None:
                    param = Param(
                        name=name, dtype=dtype, guid=parameter_guid(name, row.get("guid")),
                        group_under=row.get("group_under") or None, value=row.get("value"),
                        formula=None, instance_param=instance_param,
                        header_text=header_text,
                        grid_column_width=grid_column_width,
                        catalog=catalog,
                    )
                else:
                    param.dtype = dtype
                    param.group_under = row.get("group_under") or None
                    param.value = row.get("value")
                    param.instance_param = instance_param
                    param.header_text = header_text
                    param.grid_column_width = grid_column_width
                param_models.append(param)
            except Exception as exc:  # pragma: no cover - defensive fallback
                if param is None:
                    fallback_values = {
                        "name": name,
                        "group_under": row.get("group_under") or None,
                        "value": row.get("value"),
                        "formula": None,
                        "instance_param": instance_param,
                        "header_text": header_text,
                        "grid_column_width": self._default_grid_column_width_in,
                    }
                    try:
                        param = Param(dtype=dtype, **fallback_values)
                    except Exception:
                        param = Param(dtype="Text", **fallback_values)
                param.status = "Error"
                param.validation_message = str(exc)
                param_models.append(param)

        for _, row in self.params_df.iterrows():
            name = str(row.get("name") or "").strip()
            if not name:
                continue

            formula = str(row.get("formula") or "").strip() or None
            param = next((item for item in param_models if item.name == name), None)
            if param is None:
                continue
            if param.status == "Error":
                continue

            try:
                if formula is not None:
                    param.formula = formula
                param.validate()
            except Exception as exc:  # pragma: no cover - defensive fallback
                param.status = "Error"
                param.validation_message = str(exc)

        family_models = {}
        family_param_map = self._build_family_param_map()
        for _, row in self.families_df.iterrows():
            family_name = str(row.get("name") or "").strip()
            if not family_name:
                continue

            family_params = [
                param for param in param_models if param.name in family_param_map.get(family_name, set())
            ]
            try:
                family = Fam(
                    name=family_name,
                    client=row.get("client"),
                    country=row.get("country"),
                    description=row.get("description"),
                    category=row.get("category"),
                    params=family_params,
                    catalog=catalog,
                )
                family.validate()
                family_models[family_name] = family
            except Exception as exc:  # pragma: no cover - defensive fallback
                family = Fam(
                    name=family_name,
                    client=row.get("client"),
                    country=row.get("country"),
                    description=row.get("description"),
                    category=None,
                    params=family_params,
                )
                family.status = "Error"
                family.validation_message = str(exc)
                family_models[family_name] = family

        schedule = Schedule(fams=list(family_models.values()), catalog=catalog)
        schedule.validate()

        return param_models, family_models, family_param_map, schedule

    def validate_all(self):
        if not hasattr(self, "family_groups_df") or self.family_groups_df is None:
            self.family_groups_df = pd.DataFrame(columns=self._get_table_columns("groups"))
        if not hasattr(self, "group_tree"):
            self.group_tree = None
        if "grid_column_width" not in self.params_df.columns:
            self.params_df["grid_column_width"] = self._default_grid_column_width_in
        if "grid_column_width_override" not in self.family_groups_df.columns:
            self.family_groups_df["grid_column_width_override"] = ""
        self._ensure_param_guids()

        warnings: List[str] = []
        param_models, family_models, family_param_map, schedule = self._build_model_validation_snapshot()

        normalized_links = self.family_param_links_df.assign(
            _family_name=self.family_param_links_df["family_name"].fillna("").astype(str).str.strip(),
            _parameter_name=self.family_param_links_df["parameter_name"].fillna("").astype(str).str.strip(),
        )
        duplicate_family_links = normalized_links[
            normalized_links["_family_name"].ne("")
            & normalized_links["_parameter_name"].ne("")
            & normalized_links.duplicated(
                subset=["_family_name", "_parameter_name"],
                keep=False,
            )
        ]
        duplicate_parameters_by_family = {
            family_name: sorted(group["_parameter_name"].unique().tolist())
            for family_name, group in duplicate_family_links.groupby("_family_name")
        }

        for idx, row in self.params_df.iterrows():
            param_name = str(row.get("name") or "").strip()
            if not param_name:
                self.params_df.at[idx, "status"] = "Error"
                self.params_df.at[idx, "validation_message"] = "Parameter name is required."
                warnings.append("Parameter name is required.")
                continue
            matching = next((param for param in param_models if param.name == param_name), None)
            if matching is None:
                self.params_df.at[idx, "status"] = "Ready"
                self.params_df.at[idx, "validation_message"] = ""
                continue
            self.params_df.at[idx, "status"] = matching.status
            self.params_df.at[idx, "validation_message"] = matching.validation_message or ""
            if matching.status == "Error":
                warnings.append(f"{param_name}: {matching.validation_message}")

        for idx, row in self.families_df.iterrows():
            family_name = str(row.get("name") or "").strip()
            if not family_name:
                self.families_df.at[idx, "status"] = "Error"
                self.families_df.at[idx, "validation_message"] = "Family name is required."
                warnings.append("Family name is required.")
                continue
            matching = family_models.get(family_name)
            duplicate_parameters = duplicate_parameters_by_family.get(family_name, [])
            if matching is None:
                self.families_df.at[idx, "status"] = "Ready"
                self.families_df.at[idx, "validation_message"] = ""
            else:
                self.families_df.at[idx, "status"] = matching.status
                self.families_df.at[idx, "validation_message"] = matching.validation_message or ""

            if duplicate_parameters:
                duplicate_message = (
                    "Duplicate parameter link(s): "
                    + ", ".join(duplicate_parameters)
                    + "."
                )
                existing_message = str(
                    self.families_df.at[idx, "validation_message"] or ""
                ).strip()
                self.families_df.at[idx, "status"] = "Error"
                self.families_df.at[idx, "validation_message"] = (
                    f"{existing_message}; {duplicate_message}"
                    if existing_message
                    else duplicate_message
                )
            if str(self.families_df.at[idx, "status"]).lower() == "error":
                warnings.append(
                    f"{family_name}: {self.families_df.at[idx, 'validation_message']}"
                )

        normalized_groups = self.family_groups_df.assign(
            _family_name=self.family_groups_df["family_name"].fillna("").astype(str).str.strip(),
            _group_name=self.family_groups_df["group_name"].fillna("").astype(str).str.strip(),
            _parameter_name=self.family_groups_df["parameter_name"].fillna("").astype(str).str.strip(),
        )
        duplicate_schedule_entries = normalized_groups[
            normalized_groups["_family_name"].ne("")
            & normalized_groups["_group_name"].ne("")
            & normalized_groups["_parameter_name"].ne("")
            & normalized_groups.duplicated(
                subset=["_family_name", "_group_name", "_parameter_name"],
                keep=False,
            )
        ]
        duplicate_schedule_entry_keys = {
            (row["_family_name"], row["_group_name"], row["_parameter_name"])
            for _, row in duplicate_schedule_entries.iterrows()
        }
        for idx, row in normalized_groups.iterrows():
            override_entry = str(row.get("override_entry") or "")
            family_name = row["_family_name"]
            group_name = row["_group_name"]
            parameter_name = row["_parameter_name"]
            is_duplicate = (
                family_name,
                group_name,
                parameter_name,
            ) in duplicate_schedule_entry_keys
            messages = []
            if is_duplicate:
                messages.append(
                    f"Duplicate parameter '{parameter_name}' in schedule '{group_name}' for family '{family_name}'."
                )
            if override_entry.strip():
                messages.append("Override entry recorded")
            self.family_groups_df.at[idx, "status"] = "Error" if is_duplicate else "Ready"
            self.family_groups_df.at[idx, "validation_message"] = "; ".join(messages)
            if is_duplicate:
                warnings.append(messages[0])

        if "header_text" not in self.params_df.columns:
            self.params_df["header_text"] = self.params_df["name"]
        if "grid_column_width" not in self.params_df.columns:
            self.params_df["grid_column_width"] = self._default_grid_column_width_in
        if "default_value" not in self.params_df.columns:
            self.params_df["default_value"] = ""
        if "header_text_override" not in self.family_groups_df.columns:
            self.family_groups_df["header_text_override"] = ""
        if "grid_column_width_override" not in self.family_groups_df.columns:
            self.family_groups_df["grid_column_width_override"] = ""

        self.render_tables()
        self.warning_text.delete("1.0", tk.END)
        if warnings:
            self.warning_text.insert("1.0", "\n".join(warnings))
        else:
            self.warning_text.insert("1.0", "Validation passed. No warnings found.")

    def _ensure_param_guids(self):
        """Store a GUID on every parameter, starting from the name-based GUID earlier exports used."""
        if "guid" not in self.params_df.columns:
            self.params_df["guid"] = ""
        self.params_df["guid"] = self.params_df["guid"].astype(object)
        for idx, row in self.params_df.iterrows():
            name = str(row.get("name") or "").strip()
            if name:
                self.params_df.at[idx, "guid"] = parameter_guid(name, row.get("guid"))

    def _confirm_param_rename(self, row_index: int, new_name: str) -> bool:
        """Ask whether a rename assigns a new GUID. Returns False if the rename is cancelled."""
        self._ensure_param_guids()
        old_name = str(self.params_df.at[row_index, "name"] or "").strip()
        if not old_name or new_name == old_name:
            return True

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
            return False
        if choice:
            self.params_df.at[row_index, "guid"] = str(uuid.uuid4())
        return True

    def _rename_param_references(self, row_index: int, old_name: str, new_name: str):
        """Point links, schedule entries, header groups and formulas at a renamed parameter."""
        for df in (self.family_param_links_df, getattr(self, "family_groups_df", None)):
            if df is None or "parameter_name" not in df.columns:
                continue
            matches = df["parameter_name"].fillna("").astype(str).str.strip() == old_name
            df.loc[matches, "parameter_name"] = new_name

        for groups in getattr(self, "schedule_header_groups", {}).values():
            for group in groups:
                group["parameter_names"] = [
                    new_name if name == old_name else name
                    for name in group.get("parameter_names", [])
                ]

        if "formula" in self.params_df.columns:
            known_names = {str(name).strip() for name in self.params_df["name"].dropna()}
            for idx, formula in self.params_df["formula"].items():
                if isinstance(formula, str) and formula.strip():
                    self.params_df.at[idx, "formula"] = rename_reference(
                        formula, old_name, new_name, known_names
                    )

        # Header text left at its default follows the name; custom header text is kept.
        if "header_text" in self.params_df.columns:
            header_text = self.params_df.at[row_index, "header_text"]
            if isinstance(header_text, str) and header_text.strip() == old_name:
                self.params_df.at[row_index, "header_text"] = new_name

    def _apply_cell_value(self, table_name: str, row_index: int, column_name: str, new_value):
        if table_name == "params":
            df = self.params_df
        elif table_name == "families":
            df = self.families_df
        elif table_name == "links":
            df = self.family_param_links_df
        elif table_name == "groups":
            if not hasattr(self, "family_groups_df") or self.family_groups_df is None:
                self.family_groups_df = pd.DataFrame(columns=self._get_table_columns("groups"))
            df = self.family_groups_df
        else:
            return

        if row_index < 0 or row_index >= len(df):
            return

        if column_name in {"status", "validation_message"}:
            raise ValueError(f"{self._humanize_column_name(column_name)} is generated by validation and cannot be edited.")
        if table_name == "params" and column_name == "guid":
            raise ValueError("GUID is assigned automatically and changes only when a parameter is renamed.")

        if table_name == "params" and column_name == "name":
            new_value = "" if new_value is None else str(new_value).strip()
            if not new_value:
                raise ValueError("Parameter name is required.")
            old_name = str(df.at[row_index, "name"] or "").strip()
            other_names = {
                str(name).strip()
                for idx, name in df["name"].dropna().items()
                if idx != row_index
            }
            if new_value != old_name and new_value in other_names:
                raise ValueError(f"Parameter name '{new_value}' is already in use.")
            if not self._confirm_param_rename(row_index, new_value):
                return
            if old_name and new_value != old_name:
                self._rename_param_references(row_index, old_name, new_value)
        elif table_name == "params" and column_name == "grid_column_width":
            raw_width = "" if new_value is None else str(new_value).strip()
            if not raw_width:
                new_value = self._default_grid_column_width_in
            else:
                try:
                    new_value = float(raw_width)
                except (TypeError, ValueError):
                    raise ValueError("Grid column width must be a number in inches.")
                if not math.isfinite(new_value) or new_value <= 0:
                    raise ValueError("Grid column width must be a finite, positive number of inches.")

        if column_name == "instance_param":
            normalized = str(new_value).strip().lower()
            if normalized not in {"true", "1", "yes", "y", "false", "0", "no", "n"}:
                raise ValueError("Instance Param must be true or false.")
            df.at[row_index, column_name] = normalized in {"true", "1", "yes", "y"}
        elif table_name == "params" and column_name == "grid_column_width":
            df.at[row_index, column_name] = new_value
        else:
            df.at[row_index, column_name] = "" if new_value is None else str(new_value)

        if table_name == "groups" and column_name in {
            "header_text_override",
            "grid_column_width_override",
        }:
            schedule_name = str(df.at[row_index, "group_name"])
            parameter_name = str(df.at[row_index, "parameter_name"])
            matching_rows = (
                (df["group_name"].astype(str) == schedule_name)
                & (df["parameter_name"].astype(str) == parameter_name)
            )
            df.loc[matching_rows, column_name] = str(new_value or "").strip()

        if table_name in {"params", "families", "links", "groups"}:
            self.schedule_models = {}
            self.validate_all()

    def _build_family_param_map(self) -> dict:
        result: dict = {}
        for _, row in self.family_param_links_df.iterrows():
            family_name = str(row.get("family_name") or "")
            parameter_name = str(row.get("parameter_name") or "")
            result.setdefault(family_name, set()).add(parameter_name)
        return result

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
        summary_df = self._build_schedule_summary_df()
        if row_index < 0 or row_index >= len(summary_df):
            return
        schedule_name = str(summary_df.iloc[row_index]["name"])
        self._open_detail_window("schedule", schedule_name)

    def _open_detail_window(self, item_type: str, row_index_or_name):
        if item_type == "family":
            df = self.families_df
            columns = self._get_table_columns("families")
            title = "Family Details"
            row_index = row_index_or_name
            if row_index < 0 or row_index >= len(df):
                return
            row = df.iloc[row_index]
            entries = {}
            for col in columns:
                label = ttk.Label(self.root, text=self._humanize_column_name(col), style="Section.TLabel")
                label.pack(anchor="w", padx=12, pady=(8, 0))
            form = tk.Toplevel(self.root)
            form.title(title)
            form.transient(self.root)
            form.grab_set()
            form.geometry("700x420")
            ttk.Label(form, text=title, style="Title.TLabel").pack(anchor="w", padx=12, pady=(10, 4))
            for col in columns:
                if col in {"status", "validation_message"}:
                    current_value = "" if row.get(col) is None else str(row.get(col))
                    ttk.Label(
                        form,
                        text=f"{self._humanize_column_name(col)}: {current_value}",
                    ).pack(anchor="w", padx=12, pady=(8, 0))
                    continue
                label = ttk.Label(form, text=self._humanize_column_name(col), style="Section.TLabel")
                label.pack(anchor="w", padx=12, pady=(8, 0))
                dropdown_values = self._revit_dropdown_values(col)
                if dropdown_values:
                    combo = ttk.Combobox(form, values=dropdown_values, state="readonly", width=90)
                    combo.set("" if row.get(col) is None else str(row.get(col)))
                    entries[col] = combo
                    combo.pack(fill="x", padx=12, pady=(0, 6))
                    continue
                value = tk.StringVar(value="" if row.get(col) is None else str(row.get(col)))
                entries[col] = value
                ttk.Entry(form, textvariable=value, width=90).pack(fill="x", padx=12, pady=(0, 6))

            def save_changes():
                family_name = entries["name"].get().strip()
                if not family_name:
                    messagebox.showerror("Invalid value", "Family name is required.", parent=form)
                    return
                for col, value in entries.items():
                    current_value = value.get() if hasattr(value, "get") else value.get()
                    self.families_df.at[row_index, col] = current_value
                self.validate_all()
                form.destroy()

            ttk.Button(form, text="Save", command=save_changes, style="Action.TButton").pack(pady=(8, 12))
            return

        selected_name = str(row_index_or_name)
        summary_df = self._build_schedule_summary_df()
        summary_row = summary_df[summary_df["name"] == selected_name]
        if summary_row.empty:
            return

        schedule_rows = self.family_groups_df[self.family_groups_df["group_name"] == selected_name].copy()
        form = tk.Toplevel(self.root)
        form.title(f"Schedule Details: {selected_name}")
        form.transient(self.root)
        form.grab_set()
        form.geometry("760x480")

        ttk.Label(form, text=f"Schedule: {selected_name}", style="Title.TLabel").pack(anchor="w", padx=12, pady=(10, 4))
        ttk.Label(form, text=f"Status: {summary_row.iloc[0]['status']}", style="Section.TLabel").pack(anchor="w", padx=12, pady=(0, 6))
        ttk.Label(form, text=f"Validation: {summary_row.iloc[0]['validation_message'] or 'None'}", wraplength=700, justify="left").pack(anchor="w", padx=12, pady=(0, 8))

        content = ttk.Frame(form)
        content.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        content.grid_columnconfigure(0, weight=1, uniform="schedule_detail")
        content.grid_columnconfigure(1, weight=2, uniform="schedule_detail")
        content.grid_rowconfigure(0, weight=1)

        family_box = ttk.LabelFrame(content, text="Families", padding=8)
        family_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        family_names = sorted({
            str(value).strip()
            for value in schedule_rows["family_name"].dropna().astype(str)
            if str(value).strip()
        })
        family_list = tk.Text(family_box, height=8, width=32, wrap="word")
        family_list.insert("1.0", "\n".join(family_names) if family_names else "No families assigned")
        family_list.configure(state="disabled")
        family_list.pack(fill="both", expand=True)

        parameter_box = ttk.LabelFrame(content, text="Parameters", padding=8)
        parameter_box.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        parameter_names = self._get_schedule_parameter_names(schedule_rows)
        if parameter_names:
            def edit_schedule_header(parameter_name):
                schedule_parameter_rows = schedule_rows[
                    schedule_rows["parameter_name"].astype(str).str.strip() == parameter_name
                ]
                existing_overrides = schedule_parameter_rows.get(
                    "header_text_override", pd.Series(dtype=str)
                ).dropna().astype(str).str.strip()
                existing_overrides = existing_overrides[existing_overrides != ""]
                current_override = existing_overrides.iloc[0] if not existing_overrides.empty else ""
                existing_width_overrides = schedule_parameter_rows.get(
                    "grid_column_width_override", pd.Series(dtype=str)
                ).dropna().astype(str).str.strip()
                existing_width_overrides = existing_width_overrides[existing_width_overrides != ""]
                current_width_override = (
                    existing_width_overrides.iloc[0] if not existing_width_overrides.empty else ""
                )
                default_header = self._get_schedule_header_text(
                    schedule_parameter_rows.assign(header_text_override=""),
                    parameter_name,
                )
                default_width = self._get_schedule_grid_column_width(
                    schedule_parameter_rows.assign(grid_column_width_override=""),
                    parameter_name,
                )

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
                    width_text = width_var.get().strip()
                    if width_text:
                        try:
                            width_value = float(width_text)
                        except ValueError:
                            messagebox.showwarning(
                                "Invalid width",
                                "Enter a numeric width in inches or leave it blank to use the default.",
                                parent=editor,
                            )
                            return
                        if not math.isfinite(width_value) or width_value <= 0:
                            messagebox.showwarning(
                                "Invalid width",
                                "Width must be a finite, positive number of inches.",
                                parent=editor,
                            )
                            return
                        width_text = str(width_value)

                    first_index = schedule_parameter_rows.index[0]
                    self._apply_cell_value(
                        "groups",
                        int(first_index),
                        "header_text_override",
                        header_var.get(),
                    )
                    self._apply_cell_value(
                        "groups",
                        int(first_index),
                        "grid_column_width_override",
                        width_text,
                    )
                    refreshed_rows = self.family_groups_df[
                        self.family_groups_df["group_name"] == selected_name
                    ]
                    header_canvas.set_header_texts({
                        **header_canvas.header_texts,
                        parameter_name: self._get_schedule_header_text(refreshed_rows, parameter_name),
                    })
                    header_canvas.set_grid_column_widths([
                        self._get_schedule_grid_column_width(refreshed_rows, name)
                        for name in parameter_names
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
                {
                    parameter_name: self._get_schedule_header_text(schedule_rows, parameter_name)
                    for parameter_name in parameter_names
                },
                groups=self.schedule_header_groups.get(selected_name, []),
                on_header_double_click=edit_schedule_header,
                grid_column_widths=[
                    self._get_schedule_grid_column_width(schedule_rows, parameter_name)
                    for parameter_name in parameter_names
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
                        self._add_schedule_header_group(
                            selected_name,
                            selected_parameters,
                            caption,
                        )
                    except ValueError as exc:
                        messagebox.showwarning("Cannot group headers", str(exc), parent=editor)
                        return
                    header_canvas.set_groups(self.schedule_header_groups.get(selected_name, []))
                    editor.destroy()

                buttons = ttk.Frame(editor)
                buttons.pack(fill="x", padx=10, pady=(4, 8))
                ttk.Button(buttons, text="Group", command=save_header_group).pack(side="right")
                ttk.Button(buttons, text="Cancel", command=editor.destroy).pack(side="right", padx=(0, 6))
                caption_entry.bind("<Return>", lambda _event: save_header_group())

            ttk.Button(group_controls, text="Group Selected", command=begin_header_group).pack(side="right")
        else:
            ttk.Label(parameter_box, text="No parameters assigned").pack(anchor="w")

        ttk.Button(form, text="Close", command=form.destroy, style="Action.TButton").pack()

    def save_checkpoint(self):
        output_paths = get_database_output_paths(self.checkpoint_path)
        self.checkpoint_path = output_paths["checkpoint"]
        self._write_checkpoint(output_paths["checkpoint"])
        self._write_database_csv(output_paths["csv"])
        self._generate_revit_schedule_macro_file()
        self._generate_rfps_file()
        self._generate_shared_parameter_file()

    def save_checkpoint_as(self):
        checkpoint_path = filedialog.asksaveasfilename(
            title="Save DDM Database As",
            initialdir=str(DEFAULT_CHECKPOINT_PATH.parent),
            initialfile="test_data.ddm.pkl",
            defaultextension=".ddm.pkl",
            filetypes=[
                ("Pickle databases", "*.ddm.pkl"),
                ("CSV databases", "*.ddm.csv"),
                ("All files", "*.*"),
            ],
        )
        if not checkpoint_path:
            return
        output_paths = get_database_output_paths(checkpoint_path)
        self.checkpoint_path = output_paths["checkpoint"]
        self._write_checkpoint(output_paths["checkpoint"])
        self._write_database_csv(output_paths["csv"])
        self._generate_revit_schedule_macro_file()
        self._generate_rfps_file()
        self._generate_shared_parameter_file()

    def _write_database_csv(self, csv_path):
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
        records = []
        table_types = {
            "params": "parameter",
            "families": "family",
            "links": "link",
            "groups": "schedule_entry",
        }
        tables = {
            "params": self.params_df,
            "families": self.families_df,
            "links": self.family_param_links_df,
            "groups": self.family_groups_df,
        }
        for table_name, table in tables.items():
            for row in table.to_dict(orient="records"):
                records.append({"record_type": table_types[table_name], **row})

        for schedule_name, groups in getattr(self, "schedule_header_groups", {}).items():
            for group in groups:
                records.append({
                    "record_type": "header_group",
                    "group_name": schedule_name,
                    "caption": group.get("caption", ""),
                    "parameter_names": json.dumps(group.get("parameter_names", [])),
                    "top_row": group.get("top_row", 0),
                    "bottom_row": group.get("bottom_row", group.get("top_row", 0)),
                })

        csv_frame = pd.DataFrame(records, columns=self._database_csv_columns)
        csv_frame = csv_frame.where(pd.notna(csv_frame), "")
        csv_frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
        self.warning_text.delete("1.0", tk.END)
        self.warning_text.insert("1.0", f"Saved readable database CSV to {csv_path}")

    @staticmethod
    def _csv_bool_value(value):
        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
        return value

    def _read_database_csv(self, csv_path):
        csv_frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        if "record_type" not in csv_frame.columns:
            self.params_df = csv_frame
            self.families_df = pd.DataFrame(columns=self._get_table_columns("families"))
            self.family_param_links_df = pd.DataFrame(columns=self._get_table_columns("links"))
            self.family_groups_df = pd.DataFrame(columns=self._get_table_columns("groups"))
            self.schedule_header_groups = {}
            return

        record_types = set(csv_frame["record_type"].astype(str)) - {""}
        supported_types = {"parameter", "family", "link", "schedule_entry", "header_group"}
        unsupported_types = record_types - supported_types
        if unsupported_types:
            raise ValueError(
                "Unsupported CSV record type(s): {}".format(", ".join(sorted(unsupported_types)))
            )

        def table_for(record_type, table_name):
            rows = csv_frame[csv_frame["record_type"] == record_type]
            columns = self._get_table_columns(table_name)
            records = [
                {column: row.get(column, "") for column in columns}
                for row in rows.to_dict(orient="records")
            ]
            return pd.DataFrame(records, columns=columns)

        self.params_df = table_for("parameter", "params")
        self.families_df = table_for("family", "families")
        self.family_param_links_df = table_for("link", "links")
        self.family_groups_df = table_for("schedule_entry", "groups")

        if "header_text" not in self.params_df.columns:
            self.params_df["header_text"] = self.params_df.get("name", "")
        if "grid_column_width" not in self.params_df.columns:
            self.params_df["grid_column_width"] = self._default_grid_column_width_in
        else:
            def parse_grid_width(value):
                if not str(value).strip():
                    return self._default_grid_column_width_in
                try:
                    parsed_width = float(value)
                except (TypeError, ValueError):
                    return value
                return parsed_width if math.isfinite(parsed_width) else value

            self.params_df["grid_column_width"] = self.params_df["grid_column_width"].map(parse_grid_width)
        if "instance_param" in self.params_df.columns:
            self.params_df["instance_param"] = self.params_df["instance_param"].map(self._csv_bool_value)

        if "header_text_override" not in self.family_groups_df.columns:
            self.family_groups_df["header_text_override"] = ""
        if "grid_column_width_override" not in self.family_groups_df.columns:
            self.family_groups_df["grid_column_width_override"] = ""

        self.schedule_header_groups = {}
        header_rows = csv_frame[csv_frame["record_type"] == "header_group"]
        for row in header_rows.to_dict(orient="records"):
            try:
                parameter_names = json.loads(row.get("parameter_names", "[]"))
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid parameter list in a CSV header-group record.") from exc
            if not isinstance(parameter_names, list):
                raise ValueError("CSV header-group parameter_names must be a JSON list.")

            def parse_row_index(value, default):
                if not str(value).strip():
                    return default
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError):
                    raise ValueError("CSV header-group row indices must be whole numbers.") from None
                if not numeric_value.is_integer():
                    raise ValueError("CSV header-group row indices must be whole numbers.")
                return int(numeric_value)

            top_row = parse_row_index(row.get("top_row", ""), 0)
            bottom_row = parse_row_index(row.get("bottom_row", ""), top_row)
            self.schedule_header_groups.setdefault(row.get("group_name", ""), []).append({
                "caption": row.get("caption", ""),
                "parameter_names": parameter_names,
                "top_row": top_row,
                "bottom_row": bottom_row,
            })

    def _write_checkpoint(self, checkpoint_path):
        Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "params": self.params_df,
            "families": self.families_df,
            "family_param_links": self.family_param_links_df,
            "family_groups": self.family_groups_df,
            "schedule_header_groups": self.schedule_header_groups,
        }
        with open(checkpoint_path, "wb") as handle:
            pickle.dump(payload, handle)
        self.warning_text.delete("1.0", tk.END)
        self.warning_text.insert("1.0", f"Saved checkpoint to {checkpoint_path}")

    def load_checkpoint(self, checkpoint_path=None):
        if checkpoint_path is None:
            checkpoint_path = filedialog.askopenfilename(
                title="Load DDM Database Checkpoint",
                initialdir=str(DEFAULT_CHECKPOINT_PATH.parent),
                filetypes=[
                    ("Pickle databases", "*.ddm.pkl"),
                    ("CSV databases", "*.ddm.csv"),
                    ("All files", "*.*"),
                ],
            )
        if not checkpoint_path:
            return

        if not os.path.exists(checkpoint_path):
            messagebox.showwarning("Checkpoint missing", f"No checkpoint found at {checkpoint_path}")
            return

        is_csv = Path(checkpoint_path).suffix.lower() == ".csv"
        if is_csv:
            try:
                self._read_database_csv(checkpoint_path)
            except (OSError, pd.errors.ParserError, ValueError) as exc:
                messagebox.showerror("CSV load error", str(exc))
                return
        else:
            try:
                with open(checkpoint_path, "rb") as handle:
                    payload = pickle.load(handle)
            except (OSError, pickle.PickleError, EOFError) as exc:
                messagebox.showerror("Checkpoint load error", str(exc), parent=self.root)
                return

            self.params_df = payload.get("params", self.params_df)
            self.families_df = payload.get("families", self.families_df)
            self.family_param_links_df = payload.get("family_param_links", self.family_param_links_df)
            self.family_groups_df = payload.get("family_groups", self.family_groups_df)
            self.schedule_header_groups = payload.get("schedule_header_groups", {})

        if "header_text" not in self.params_df.columns:
            self.params_df["header_text"] = self.params_df["name"]
        if "grid_column_width" not in self.params_df.columns:
            self.params_df["grid_column_width"] = self._default_grid_column_width_in
        if "header_text_override" not in self.family_groups_df.columns:
            self.family_groups_df["header_text_override"] = ""
        if "grid_column_width_override" not in self.family_groups_df.columns:
            self.family_groups_df["grid_column_width_override"] = ""
        self._ensure_param_guids()
        self.schedule_models = {}
        self.checkpoint_path = Path(checkpoint_path)
        self.render_tables()
        if is_csv:
            self.validate_all()
            self.warning_text.insert("1.0", f"Loaded database CSV from {checkpoint_path}\n")
        else:
            self.warning_text.delete("1.0", tk.END)
            self.warning_text.insert("1.0", f"Loaded checkpoint from {checkpoint_path}")

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

        self.validate_all()
        validation_errors = sum(
            int((frame["status"].fillna("").astype(str).str.lower() == "error").sum())
            for frame in (self.params_df, self.families_df)
            if "status" in frame.columns
        )
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
            self.warning_text.delete("1.0", tk.END)
            self.warning_text.insert("1.0", "Quickbase mapping prepared. Connect real table IDs before live sync.")
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Quickbase sync error", str(exc))


def main():
    root = tk.Tk()
    app = DDMGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
