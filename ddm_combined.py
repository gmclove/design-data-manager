"""The Combined Parameters tab and its window: define a column that joins several parameters,
as Revit's combined parameters do, such as TAG from the tag terms."""
import tkinter as tk
from tkinter import messagebox, ttk

import pandas as pd


class CombinedParamWindows:
    """Mixed into ``DDMGUI``, which supplies the catalog, the root window and the message area."""

    combined_tree = None
    _combined_summary_columns = ["name", "header", "pattern", "schedules_using", "sections_using", "status"]

    def _build_combined_summary_df(self) -> pd.DataFrame:
        rows = []
        for combined in self.catalog.combined_params:
            combined.validate()
            rows.append({
                "name": combined.name,
                "header": combined.header_text,
                "pattern": combined.pattern(),
                "schedules_using": len(self.catalog.schedules_with_column(combined.name)),
                "sections_using": len([
                    section for section in self.catalog.sections if combined.name in section.parameter_names
                ]),
                "status": combined.validation_message or combined.status,
            })
        return pd.DataFrame(rows, columns=self._combined_summary_columns)

    def _open_selected_combined_window(self, event):
        row_id = self.combined_tree.identify_row(event.y)
        if not row_id:
            return None
        return self.open_combined_window(self.catalog.combined_params[int(row_id)])

    def open_combined_window(self, combined=None):
        """Define a combined parameter (``None`` for a new one): its name, header and parts.
        Add it to schedules from the Schedule Builder or through a section."""
        window = tk.Toplevel(getattr(self, "root", None))
        window.title(f"Combined Parameter: {combined.name}" if combined else "Add Combined Parameter")
        window.geometry("820x560")
        parts = [dict(part) for part in combined.parts] if combined else []

        fields = ttk.Frame(window)
        fields.pack(fill="x", padx=12, pady=(12, 6))
        name_var = tk.StringVar(window, value=combined.name if combined else "")
        header_var = tk.StringVar(window, value=(combined._header_text or "") if combined else "")
        width_var = tk.StringVar(window, value=f"{combined.grid_column_width:g}" if combined else "1")
        for label, var, width in (
            ("Name:", name_var, 24), ("Column Header:", header_var, 24), ("Column Width (in):", width_var, 8),
        ):
            ttk.Label(fields, text=label).pack(side="left", padx=(0 if label == "Name:" else 14, 6))
            ttk.Entry(fields, textvariable=var, width=width).pack(side="left")

        pattern_var = tk.StringVar(window)
        ttk.Label(window, textvariable=pattern_var, wraplength=780, justify="left").pack(
            anchor="w", padx=12, pady=(0, 6)
        )

        bottom = ttk.Frame(window)
        bottom.pack(side="bottom", fill="x", padx=12, pady=(6, 12))

        box = ttk.LabelFrame(window, text="Parameters Combined, in Order")
        box.pack(fill="both", expand=True, padx=12)
        columns = ("prefix", "parameter", "suffix", "separator")
        tree = ttk.Treeview(box, columns=columns, show="headings", selectmode="extended", height=8)
        for column, label, width in (
            ("prefix", "Prefix", 90), ("parameter", "Parameter", 320), ("suffix", "Suffix", 90),
            ("separator", "Separator (Before the Next)", 180),
        ):
            tree.heading(column, text=label)
            tree.column(column, width=width, anchor="w")
        edit_row = ttk.Frame(box)
        edit_row.pack(side="bottom", fill="x", padx=6, pady=(0, 6))
        buttons = ttk.Frame(box)
        buttons.pack(side="bottom", fill="x", padx=6, pady=6)
        tree.pack(fill="both", expand=True, padx=6, pady=(6, 0))

        # Prefix, suffix and separator of the selected parts; spaces count.
        edit_vars = {key: tk.StringVar(window) for key in ("prefix", "suffix", "separator")}
        loading = {"busy": False}
        for key, label in (("prefix", "Prefix:"), ("suffix", "Suffix:"), ("separator", "Separator:")):
            ttk.Label(edit_row, text=label).pack(side="left", padx=(0 if key == "prefix" else 14, 6))
            ttk.Entry(edit_row, textvariable=edit_vars[key], width=10).pack(side="left")
        ttk.Label(edit_row, text="Applies to the selected rows.", foreground="#6b7280").pack(side="left", padx=(14, 0))

        def shown(value):
            # Spaces would be invisible in the table.
            return value.replace(" ", "␣")

        def render(selection=()):
            tree.delete(*tree.get_children())
            for index, part in enumerate(parts):
                tree.insert("", "end", iid=str(index), values=(
                    shown(part["prefix"]), part["parameter"], shown(part["suffix"]),
                    "" if index == len(parts) - 1 and not part["separator"] else shown(part["separator"]),
                ))
            tree.selection_set([str(index) for index in selection if index < len(parts)])
            preview = self._combined_preview(parts)
            pattern_var.set(f"Pattern: {preview}" if parts else "Pattern: Add the parameters to combine.")

        def selected():
            return [int(item) for item in tree.selection()]

        def on_select(_event=None):
            rows = selected()
            loading["busy"] = True
            for key, var in edit_vars.items():
                values = {parts[index][key] for index in rows}
                var.set(values.pop() if len(values) == 1 else "")
            loading["busy"] = False

        def on_edit(key):
            if loading["busy"]:
                return
            rows = selected()
            for index in rows:
                parts[index][key] = edit_vars[key].get()
            render(rows)

        tree.bind("<<TreeviewSelect>>", on_select)
        for key, var in edit_vars.items():
            var.trace_add("write", lambda *_args, key=key: on_edit(key))

        def add_parameters():
            choices = [
                (param.name, f"{param.name} {param.header_text or ''} {param.group_under or ''}")
                for param in self.catalog.params
            ]
            rows = selected()
            position = rows[-1] + 1 if rows else len(parts)

            def add(names):
                parts[position:position] = [
                    {"parameter": name, "prefix": "", "suffix": "", "separator": ""} for name in names
                ]
                render(range(position, position + len(names)))

            return self._pick_names(window, "Add Parameters to Combine", choices, add)

        def remove():
            for index in sorted(selected(), reverse=True):
                del parts[index]
            render()

        def move(step):
            rows = selected()
            if not rows or (step < 0 and rows[0] == 0) or (step > 0 and rows[-1] == len(parts) - 1):
                return
            for index in (rows if step < 0 else reversed(rows)):
                parts[index], parts[index + step] = parts[index + step], parts[index]
            render([index + step for index in rows])

        for text, command in (
            ("Add Parameter...", add_parameters), ("Remove", remove),
            ("▲ Move Up", lambda: move(-1)), ("Move Down ▼", lambda: move(1)),
        ):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=(0, 6))

        def save():
            try:
                saved = self._save_combined_param(
                    combined, name_var.get(), parts, header_var.get(), width_var.get(),
                )
            except ValueError as exc:
                messagebox.showwarning("Combined Parameter", str(exc), parent=window)
                return None
            window.destroy()
            return saved

        def delete():
            schedules = self.catalog.schedules_with_column(combined.name)
            sections = [section for section in self.catalog.sections if combined.name in section.parameter_names]
            message = f"Delete combined parameter '{combined.name}'?"
            if schedules or sections:
                message += (
                    f" It leaves the {len(schedules)} schedule(s) and {len(sections)} section(s) listing it."
                )
            if not messagebox.askyesno("Delete Combined Parameter", message, parent=window):
                return
            self.catalog.remove_combined_param(combined.name)
            window.destroy()
            self._show_messages([f"Deleted combined parameter '{combined.name}'."])
            self.validate_all()

        if combined is not None:
            ttk.Button(bottom, text="Delete Combined Parameter", command=delete).pack(side="left")
        ttk.Label(
            bottom, text="Add it to schedules with Add Parameter... in the Schedule Builder, or in a section.",
            foreground="#6b7280",
        ).pack(side="left", padx=(12, 0))
        ttk.Button(bottom, text="Save", command=save, style="Action.TButton").pack(side="right")
        ttk.Button(bottom, text="Cancel", command=window.destroy).pack(side="right", padx=(0, 6))
        render()

        # For tests.
        window.name_var, window.header_var, window.width_var = name_var, header_var, width_var
        window.parts, window.tree, window.edit_vars = parts, tree, edit_vars
        window.save, window.render, window.add_parameters = save, render, add_parameters
        window.pattern_var = pattern_var
        return window

    @staticmethod
    def _combined_preview(parts):
        text = ""
        for index, part in enumerate(parts):
            text += f"{part['prefix']}[{part['parameter']}]{part['suffix']}"
            if index < len(parts) - 1:
                text += part["separator"]
        return text

    def _save_combined_param(self, combined, name, parts, header_text, width_text):
        """Create (``combined`` is ``None``) or change a combined parameter. Raises ``ValueError``."""
        width_text = str(width_text).strip()
        try:
            width = float(width_text) if width_text else 1.0
        except ValueError:
            raise ValueError("Column Width must be a number of inches.") from None
        if width <= 0:
            raise ValueError("Column Width must be more than 0 inches.")
        if combined is not None:
            # Check everything first, so a refused edit changes nothing.
            self.catalog._check_column_name_free(name, ignore=combined)
            self.catalog._check_combined_parts(name, parts)
        if combined is None:
            combined = self.catalog.add_combined_param(
                name, parts, header_text=header_text or None, grid_column_width=width,
            )
            message = f"Added combined parameter '{combined.name}'."
        else:
            combined.set_parts(parts)
            combined.grid_column_width = width
            combined.header_text = header_text or None
            combined.name = name
            message = f"Saved combined parameter '{combined.name}'."
        for schedule in self.catalog.schedules_with_column(combined.name):
            schedule.refresh_params()
        self._show_messages([message])
        self.validate_all()
        return combined
