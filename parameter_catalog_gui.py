import importlib.util
import os
import pickle
import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox

from config.revit_dtype_catalog import REVIT_DTYPE_TABLE
from config.revit_family_category_catalog import REVIT_FAMILY_CATEGORY_TABLE
from config.revit_property_pallet_catalog import REVIT_PROPERTY_PALLET_TABLE

try:
    from quickbase_integration import QuickbaseClient, QuickbaseSyncService
except ImportError:  # pragma: no cover
    QuickbaseClient = None
    QuickbaseSyncService = None


class ParameterCatalogGUI:
    """Simple dataframe-first GUI for reviewing validation state and syncing to Quickbase."""

    _table_columns = {
        "params": ["name", "dtype", "group_under", "formula", "instance_param", "status", "validation_message"],
        "families": ["name", "client", "country", "category", "description", "status", "validation_message"],
        "links": ["family_name", "parameter_name"],
        "groups": ["family_name", "group_name", "parameter_name", "override_entry", "status", "validation_message"],
    }

    _display_labels = {
        "name": "Name",
        "dtype": "Data Type",
        "group_under": "Group Under",
        "formula": "Formula",
        "instance_param": "Instance Param",
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
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Parameter Catalog Review")
        self.root.geometry("1360x820")
        self.root.minsize(1100, 700)

        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#1f2937")
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground="#374151")
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))

        self.params_df = pd.DataFrame(
            [
                {"name": "Length", "dtype": "Length", "group_under": "Dimensions", "formula": "Width * Height", "instance_param": True, "status": "Draft", "validation_message": ""},
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

        self.warning_text = None
        self.param_tree = None
        self.family_tree = None
        self.link_tree = None
        self.group_tree = None

        self._table_columns = {
            "params": ["name", "dtype", "group_under", "formula", "instance_param", "status", "validation_message"],
            "families": ["name", "client", "country", "category", "description", "status", "validation_message"],
            "links": ["family_name", "parameter_name"],
            "groups": ["family_name", "group_name", "parameter_name", "override_entry", "status", "validation_message"],
        }

        self.build_ui()
        self.render_tables()

    def build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="Parameter Catalog Review", style="Title.TLabel").grid(row=0, column=0, sticky="w")

        toolbar = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        toolbar.grid(row=1, column=0, sticky="ew")

        ttk.Button(toolbar, text="Load Demo Data", command=self.load_demo_data, style="Action.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Validate", command=self.validate_all, style="Action.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Save Checkpoint", command=self.save_checkpoint, style="Action.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Load Checkpoint", command=self.load_checkpoint, style="Action.TButton").pack(side="left", padx=(0, 8))
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

        validation_header = ttk.Label(self.root, text="Validation Output", style="Section.TLabel")
        validation_header.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 4))

        self.warning_text = tk.Text(self.root, height=8, wrap="word", padx=10, pady=8, bg="#f8fafc", borderwidth=1, relief="solid")
        self.warning_text.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=1)

    @staticmethod
    def _humanize_column_name(column_name: str) -> str:
        if column_name in ParameterCatalogGUI._display_labels:
            return ParameterCatalogGUI._display_labels[column_name]
        return column_name.replace("_", " ").title()

    def _get_table_columns(self, table_name: str):
        if hasattr(self, "_table_columns") and table_name in self._table_columns:
            return self._table_columns[table_name]
        return ParameterCatalogGUI._table_columns[table_name]

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
            columns = self._get_table_columns("groups")
            tree = ttk.Treeview(frame, columns=columns, show="headings")
            for col in columns:
                tree.heading(col, text=self._humanize_column_name(col))
                tree.column(col, width=180, anchor="w")
            self.group_tree = tree

        self._bind_table_edit_events(tree, table_name)

        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

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
                self._apply_cell_value(table_name, row_index, field_name, widget.get())
                popup.destroy()

            widget.bind("<<ComboboxSelected>>", lambda _event: commit_edit())
            widget.bind("<Return>", lambda _event: commit_edit())
            return

        value_var = tk.StringVar(value="" if current_value is None else str(current_value))
        entry = ttk.Entry(popup, textvariable=value_var)
        entry.pack(fill="x", padx=8, pady=8)
        entry.focus_set()
        entry.selection_range(0, tk.END)

        def commit_edit():
            self._apply_cell_value(table_name, row_index, field_name, value_var.get())
            popup.destroy()

        entry.bind("<Return>", lambda _event: commit_edit())
        entry.bind("<FocusOut>", lambda _event: commit_edit())

    def load_demo_data(self):
        self.params_df = pd.DataFrame(
            [
                {
                    "name": "Length",
                    "dtype": "Length",
                    "group_under": "Dimensions",
                    "formula": "Width * Height",
                    "instance_param": True,
                    "status": "Draft",
                    "validation_message": "",
                },
                {
                    "name": "Width",
                    "dtype": "Length",
                    "group_under": "Dimensions",
                    "formula": "",
                    "instance_param": True,
                    "status": "Approved",
                    "validation_message": "",
                },
                {
                    "name": "Height",
                    "dtype": "Length",
                    "group_under": "Dimensions",
                    "formula": "",
                    "instance_param": True,
                    "status": "Approved",
                    "validation_message": "",
                },
                {
                    "name": "Area",
                    "dtype": "Area",
                    "group_under": "Dimensions",
                    "formula": "Length * Width",
                    "instance_param": False,
                    "status": "Error",
                    "validation_message": "Missing family association",
                },
            ]
        )
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
                {"family_name": "Family_C", "parameter_name": "UValue"},
                {"family_name": "Family_C", "parameter_name": "GlassArea"},
                {"family_name": "Family_D", "parameter_name": "Depth"},
                {"family_name": "Family_E", "parameter_name": "RValue"},
                {"family_name": "Family_F", "parameter_name": "GrossArea"},
                {"family_name": "Family_G", "parameter_name": "FinishCode"},
                {"family_name": "Family_H", "parameter_name": "PowerLoad"},
                {"family_name": "Family_I", "parameter_name": "FacadeRatio"},
                {"family_name": "Family_J", "parameter_name": "HeadHeight"},
            ]
        )
        self.family_groups_df = pd.DataFrame(
            [
                {"family_name": "Family_A", "group_name": "Schedule A", "parameter_name": "Length", "override_entry": "", "status": "Ready", "validation_message": ""},
                {"family_name": "Family_A", "group_name": "Schedule A", "parameter_name": "Width", "override_entry": "Override Width", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_B", "group_name": "Schedule B", "parameter_name": "Length", "override_entry": "", "status": "Ready", "validation_message": ""},
                {"family_name": "Family_C", "group_name": "Envelope Schedule", "parameter_name": "UValue", "override_entry": "0.21", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_D", "group_name": "Casework Schedule", "parameter_name": "Depth", "override_entry": "", "status": "Ready", "validation_message": ""},
                {"family_name": "Family_E", "group_name": "Guardrail Schedule", "parameter_name": "RValue", "override_entry": "", "status": "Ready", "validation_message": ""},
                {"family_name": "Family_F", "group_name": "Structural Schedule", "parameter_name": "GrossArea", "override_entry": "35.5", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_G", "group_name": "Joinery Schedule", "parameter_name": "FinishCode", "override_entry": "J-04", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_H", "group_name": "Mechanical Schedule", "parameter_name": "PowerLoad", "override_entry": "12.4", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_I", "group_name": "Facade Review", "parameter_name": "FacadeRatio", "override_entry": "0.62", "status": "Ready", "validation_message": "Override entry recorded"},
                {"family_name": "Family_J", "group_name": "Opening Schedule", "parameter_name": "HeadHeight", "override_entry": "2.4", "status": "Ready", "validation_message": "Override entry recorded"},
            ]
        )
        self.render_tables()
        self.warning_text.delete("1.0", tk.END)
        self.warning_text.insert("1.0", "Loaded demo data.")

    def render_tables(self):
        if not hasattr(self, "family_groups_df") or self.family_groups_df is None:
            self.family_groups_df = pd.DataFrame(columns=self._get_table_columns("groups"))
        if not hasattr(self, "group_tree"):
            self.group_tree = None

        self._render_tree(self.param_tree, self.params_df, self._get_table_columns("params"))
        self._render_tree(self.family_tree, self.families_df, self._get_table_columns("families"))
        self._render_tree(self.group_tree, self.family_groups_df, self._get_table_columns("groups"))

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
        module_path = Path(__file__).with_name("revit-parameter-manager.py")
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

        current_param_names = set(str(name).strip() for name in self.params_df["name"].dropna().astype(str).tolist() if str(name).strip())
        existing_instances = getattr(Param, "_instances", [])
        Param._instances = [param for param in existing_instances if param.name not in current_param_names]

        param_models = []
        for _, row in self.params_df.iterrows():
            name = str(row.get("name") or "").strip()
            if not name:
                continue

            dtype = str(row.get("dtype") or "")
            instance_value = row.get("instance_param", True)
            try:
                param = next((item for item in Param._instances if item.name == name), None)
                if param is None:
                    param = Param(
                        name=name,
                        dtype=dtype,
                        group_under=row.get("group_under") or None,
                        value=row.get("value"),
                        formula=None,
                        instance_param=bool(str(instance_value).strip().lower() in {"true", "1", "yes", "y"}),
                    )
                else:
                    param.dtype = dtype
                    param.group_under = row.get("group_under") or None
                    param.value = row.get("value")
                    param.instance_param = bool(str(instance_value).strip().lower() in {"true", "1", "yes", "y"})
                param_models.append(param)
            except Exception as exc:  # pragma: no cover - defensive fallback
                param = Param(
                    name,
                    dtype,
                    group_under=row.get("group_under") or None,
                    value=row.get("value"),
                    formula=None,
                    instance_param=bool(str(instance_value).strip().lower() in {"true", "1", "yes", "y"}),
                )
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
                )
                family.validate()
                family_models[family_name] = family
            except Exception as exc:  # pragma: no cover - defensive fallback
                family = Fam(
                    name=family_name,
                    client=row.get("client"),
                    country=row.get("country"),
                    description=row.get("description"),
                    category=row.get("category"),
                    params=family_params,
                )
                family.status = "Error"
                family.validation_message = str(exc)
                family_models[family_name] = family

        schedule = Schedule(fams=list(family_models.values()))
        schedule.validate()

        return param_models, family_models, family_param_map, schedule

    def validate_all(self):
        if not hasattr(self, "family_groups_df") or self.family_groups_df is None:
            self.family_groups_df = pd.DataFrame(columns=self._get_table_columns("groups"))
        if not hasattr(self, "group_tree"):
            self.group_tree = None

        warnings: List[str] = []
        param_models, family_models, family_param_map, schedule = self._build_model_validation_snapshot()

        for idx, row in self.params_df.iterrows():
            param_name = str(row.get("name") or "").strip()
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
            matching = family_models.get(family_name)
            if matching is None:
                self.families_df.at[idx, "status"] = "Ready"
                self.families_df.at[idx, "validation_message"] = ""
                continue
            self.families_df.at[idx, "status"] = matching.status
            self.families_df.at[idx, "validation_message"] = matching.validation_message or ""
            if matching.status == "Error":
                warnings.append(f"{family_name}: {matching.validation_message}")

        # Schedule/group rows are presentation data. Integrity checks for whether a
        # parameter belongs to a family or catalog are owned by the model objects.
        for idx, row in self.family_groups_df.iterrows():
            override_entry = str(row.get("override_entry") or "")
            self.family_groups_df.at[idx, "status"] = "Ready"
            self.family_groups_df.at[idx, "validation_message"] = (
                "Override entry recorded" if override_entry.strip() else ""
            )

        self.render_tables()
        self.warning_text.delete("1.0", tk.END)
        if warnings:
            self.warning_text.insert("1.0", "\n".join(warnings))
        else:
            self.warning_text.insert("1.0", "Validation passed. No warnings found.")

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

        if column_name == "instance_param":
            normalized = str(new_value).strip().lower()
            df.at[row_index, column_name] = normalized in {"true", "1", "yes", "y"}
        else:
            df.at[row_index, column_name] = "" if new_value is None else str(new_value)

        if table_name in {"params", "families", "links", "groups"}:
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
        self._open_detail_window("schedule", row_index)

    def _open_detail_window(self, item_type: str, row_index: int):
        if item_type == "family":
            df = self.families_df
            columns = self._get_table_columns("families")
            title = "Family Details"
        else:
            df = self.family_groups_df
            columns = self._get_table_columns("groups")
            title = "Schedule Details"

        if row_index < 0 or row_index >= len(df):
            return

        form = tk.Toplevel(self.root)
        form.title(title)
        form.transient(self.root)
        form.grab_set()
        form.geometry("700x420")

        ttk.Label(form, text=title, style="Title.TLabel").pack(anchor="w", padx=12, pady=(10, 4))

        row = df.iloc[row_index]
        entries = {}
        for col in columns:
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
            for col, value in entries.items():
                current_value = value.get() if hasattr(value, "get") else value.get()
                if item_type == "family":
                    self.families_df.at[row_index, col] = current_value
                else:
                    self.family_groups_df.at[row_index, col] = current_value
            self.validate_all()
            form.destroy()

        ttk.Button(form, text="Save", command=save_changes, style="Action.TButton").pack(pady=(8, 12))

    def save_checkpoint(self):
        checkpoint_path = os.path.join(os.getcwd(), "parameter_catalog_checkpoint.pkl")
        payload = {
            "params": self.params_df,
            "families": self.families_df,
            "family_param_links": self.family_param_links_df,
            "family_groups": self.family_groups_df,
        }
        with open(checkpoint_path, "wb") as handle:
            pickle.dump(payload, handle)
        self.warning_text.delete("1.0", tk.END)
        self.warning_text.insert("1.0", f"Saved checkpoint to {checkpoint_path}")

    def load_checkpoint(self):
        checkpoint_path = os.path.join(os.getcwd(), "parameter_catalog_checkpoint.pkl")
        if not os.path.exists(checkpoint_path):
            messagebox.showwarning("Checkpoint missing", f"No checkpoint found at {checkpoint_path}")
            return

        with open(checkpoint_path, "rb") as handle:
            payload = pickle.load(handle)

        self.params_df = payload.get("params", self.params_df)
        self.families_df = payload.get("families", self.families_df)
        self.family_param_links_df = payload.get("family_param_links", self.family_param_links_df)
        self.family_groups_df = payload.get("family_groups", self.family_groups_df)
        self.render_tables()
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
    app = ParameterCatalogGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
