"""Column Widths From Revit: review each parameter's typical width in Revit and take the ones wanted.

The widths come from the files the macro's ``ExportScheduleWidths`` writes (see ``revit_widths``).
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from config.app_paths import get_revit_widths_folder
from revit_widths import apply_typical_widths, load_width_exports, typical_widths

CHECKED, UNCHECKED = "☑", "☐"


def _inches(value):
    return "" if value is None else f"{value:g}"


class WidthReviewWindows:
    """Mixin for ``DDMGUI``: the Column Widths From Revit window."""

    def _revit_widths_folder(self):
        return get_revit_widths_folder(Path(self.checkpoint_path).resolve())

    def open_width_review(self, folder=None):
        """Column Widths From Revit...: read the exports in ``folder`` (by default the
        ``revit-widths`` folder next to the database) and open the review."""
        parent = getattr(self, "root", None)
        folder = Path(folder) if folder else self._revit_widths_folder()
        if not folder.is_dir() or not any(folder.glob("*.widths.json")):
            if not messagebox.askyesno(
                "Column Widths From Revit",
                f"No column width exports in:\n{folder}\n\n"
                "To make them: Save here (it installs the macro), then in each Revit project run "
                "ExportScheduleWidths from the Macro Manager.\n\nChoose another folder?",
                parent=parent,
            ):
                return None
            chosen = filedialog.askdirectory(parent=parent, title="Folder With Column Width Exports")
            if not chosen:
                return None
            folder = Path(chosen)
        exports, problems = load_width_exports(folder)
        if problems:
            messagebox.showwarning(
                "Column Widths From Revit",
                "Couldn't read:\n" + "\n".join(f"{path.name}: {error}" for path, error in problems),
                parent=parent,
            )
        if not exports:
            return None
        return self._width_review_window(exports, folder)

    def _width_review_window(self, exports, folder):
        parent = getattr(self, "root", None)
        window = tk.Toplevel(parent)
        window.title("Column Widths From Revit")
        window.transient(parent)
        rows = [row for row in typical_widths(self.catalog, exports) if row["typical"] is not None]
        accepted = set()

        projects = sorted({data.get("project") or path.stem for path, data in exports})
        top = ttk.Frame(window)
        top.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(top, text="Typical Column Widths in Revit", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            top, wraplength=900, justify="left",
            text=(f"From {len(projects)} project(s) in {folder}: {', '.join(projects)}.\n"
                  "Typical is the most common width among columns someone adjusted; columns still at Revit's "
                  "default width and hidden columns don't count. Accepting makes it the parameter's Default "
                  "Column Width: schedules without their own width follow it, and a schedule's own width "
                  "that equals it is cleared."),
        ).pack(anchor="w", pady=(2, 0))

        bottom = ttk.Frame(window)
        bottom.pack(side="bottom", fill="x", padx=12, pady=(6, 12))
        controls = ttk.Frame(window)
        controls.pack(fill="x", padx=12, pady=(4, 4))
        show_unchanged = tk.BooleanVar(window, value=False)
        count = ttk.Label(controls, text="")

        box = ttk.Frame(window)
        box.pack(fill="both", expand=True, padx=12)
        columns = ("accept", "parameter", "current", "typical", "agree", "projects", "others")
        headings = ("Accept", "Parameter", "Current Default (in)", "Typical (in)", "Agree",
                    "Projects", "Other Widths (in × uses)")
        tree = ttk.Treeview(box, columns=columns, show="headings", selectmode="extended")
        for column, heading, width in zip(columns, headings, (60, 300, 130, 100, 90, 70, 260)):
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="center" if column != "parameter" and column != "others" else "w")
        scroll = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        def shown_rows():
            return [row for row in rows
                    if show_unchanged.get() or row["typical"] != row["current_default"]]

        def refresh():
            tree.delete(*tree.get_children())
            for row in shown_rows():
                tree.insert("", "end", iid=row["parameter"], values=(
                    CHECKED if row["parameter"] in accepted else UNCHECKED,
                    row["parameter"],
                    _inches(row["current_default"]),
                    _inches(row["typical"]),
                    f"{row['agree']} of {row['adjusted_uses']}",
                    len(row["projects"]),
                    ", ".join(f"{_inches(width)} × {uses}" for width, uses in row["spread"][1:]),
                ))
            count.configure(text=f"{len(accepted)} selected of {len(shown_rows())} shown")
            accept_button.configure(state="normal" if accepted else "disabled")

        def toggle(names):
            names = list(names)
            if all(name in accepted for name in names):
                accepted.difference_update(names)
            else:
                accepted.update(names)
            refresh()

        def on_click(event):
            if tree.identify_region(event.x, event.y) == "cell" and tree.identify_column(event.x) == "#1":
                row = tree.identify_row(event.y)
                if row:
                    toggle([row])
                    return "break"
            return None

        def select_all():
            accepted.update(row["parameter"] for row in shown_rows())
            refresh()

        def deselect_all():
            accepted.clear()
            refresh()

        def accept():
            choices = {row["parameter"]: row["typical"] for row in rows if row["parameter"] in accepted}
            if not choices:
                return None
            summary = apply_typical_widths(self.catalog, choices)
            self.validate_all()
            self.render_tables()
            self._append_message(
                f"Took the typical Revit width for {len(summary['parameters'])} parameter(s); "
                f"{len(summary['schedules_changed'])} schedule(s) follow the new widths; "
                f"cleared {summary['overrides_cleared']} schedule width(s) equal to them. Save to keep them."
            )
            window.destroy()
            return summary

        tree.bind("<Button-1>", on_click)
        tree.bind("<space>", lambda _event: (toggle(tree.selection()) if tree.selection() else None, "break")[1])
        ttk.Checkbutton(controls, text="Show Unchanged", variable=show_unchanged, command=refresh).pack(side="left")
        ttk.Button(controls, text="Select All", command=select_all).pack(side="left", padx=(12, 0))
        ttk.Button(controls, text="Deselect All", command=deselect_all).pack(side="left", padx=(6, 0))
        count.pack(side="left", padx=(12, 0))
        accept_button = ttk.Button(bottom, text="Accept Selected", command=accept, style="Action.TButton")
        accept_button.pack(side="right")
        ttk.Button(bottom, text="Close", command=window.destroy).pack(side="right", padx=(0, 6))
        window.bind("<Escape>", lambda _event: window.destroy())
        refresh()
        self._fit_window(window, bottom, "1100x640", margin=24)

        # For tests.
        window.tree, window.rows, window.accepted = tree, rows, accepted
        window.toggle, window.select_all, window.deselect_all, window.accept = toggle, select_all, deselect_all, accept
        window.show_unchanged, window.refresh = show_unchanged, refresh
        return window
