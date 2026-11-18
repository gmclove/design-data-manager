"""Review Revit Changes: take schedule changes made in Revit back into the database.

The add-in (or the ``SendSchedulesToDatabase`` macro) writes a snapshot of a Revit project's
schedules; ``revit_sync`` compares it with the database, and this window lets the user accept
changes one by one.
"""

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from config.app_paths import get_revit_sync_path
from revit_sync import SyncFileError, apply_differences, read_sync_file, schedule_differences
from table_view import DEFAULT_TABLE_VIEW


# How often the app checks for Revit asking for a review (ms).
REVIEW_POLL_MS = 2000


class RevitSyncWindows:
    """Mixin for ``DDMGUI``: the Review Revit Changes window."""

    def open_revit_changes(self):
        """Show how the schedules Revit sent differ from the database, to take changes back."""
        root = getattr(self, "root", None)
        path = get_revit_sync_path(self.checkpoint_path)
        if not Path(path).exists():
            messagebox.showinfo(
                "Review Revit Changes",
                f"Nothing has been sent from Revit yet.\n\nIn Revit, click Design Data Manager on the Design Data "
                f"tab (or run the SendSchedulesToDatabase macro). It writes:\n{path}",
                parent=root,
            )
            return None
        try:
            data = read_sync_file(path)
            differences = schedule_differences(self.catalog, data)
        except (SyncFileError, KeyError, TypeError) as exc:
            messagebox.showwarning("Review Revit Changes", f"Couldn't read {path}:\n{exc}", parent=root)
            return None
        if not differences:
            messagebox.showinfo(
                "Review Revit Changes",
                f"The schedules in {data.get('project', 'the project')} match the database.",
                parent=root,
            )
            return None

        return self._build_revit_changes_window(data, differences)

    def _build_revit_changes_window(self, data, differences):
        """Each change side by side, Database against Revit, with a box to accept it."""
        window = tk.Toplevel(getattr(self, "root", None))
        window.title("Review Revit Changes")
        window.geometry("1100x640")

        changes = [difference for difference in differences if difference.can_apply]
        information = [difference for difference in differences if not difference.can_apply]
        checks = []

        ttk.Label(
            window, style="Section.TLabel",
            text=f"From {data.get('project', 'Revit')}, Sent {data.get('sent_at', '')}",
        ).pack(anchor="w", padx=10, pady=(10, 2))
        top = ttk.Frame(window)
        top.pack(fill="x", padx=10, pady=(4, 6))
        bottom = ttk.Frame(window)
        bottom.pack(side="bottom", fill="x", padx=10, pady=(6, 10))

        body = ttk.Frame(window)
        body.pack(fill="both", expand=True, padx=10)
        canvas = tk.Canvas(body, highlightthickness=0, background="#ffffff")
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        rows = tk.Frame(canvas, background="#ffffff")
        rows_id = canvas.create_window((0, 0), window=rows, anchor="nw")

        # The two value columns stay the same width, so they read side by side.
        rows.columnconfigure(1, minsize=260)
        rows.columnconfigure(2, weight=1, uniform="values")
        rows.columnconfigure(3, weight=1, uniform="values")
        value_labels = []
        wide_labels = []

        def cell(row, column, text, background="#ffffff", foreground="#111827", font=None, track=None, **grid):
            label = tk.Label(
                rows, text=text, background=background, foreground=foreground, anchor="nw", justify="left",
                font=font or ("Segoe UI", 9), padx=6, pady=3,
            )
            label.grid(row=row, column=column, sticky="nsew", padx=1, pady=1, **grid)
            if track is not None:
                track.append(label)
            return label

        def resized(event):
            canvas.itemconfigure(rows_id, width=event.width)
            value_width = max(120, (event.width - 340) // 2 - 16)
            for label in value_labels:
                label.configure(wraplength=value_width)
            for label in wide_labels:
                label.configure(wraplength=max(240, event.width - 40))

        canvas.bind("<Configure>", resized)
        rows.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        window.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))

        count_label = ttk.Label(top)
        accept_button = ttk.Button(bottom, style="Action.TButton")

        def update_count(*_args):
            selected = sum(var.get() for _difference, var in checks)
            count_label.configure(text=f"{selected} of {len(checks)} Selected")
            accept_button.configure(
                text=f"Accept Selected ({selected})",
                state="normal" if selected else "disabled",
            )

        def set_all(value):
            for _difference, var in checks:
                var.set(value)

        def accept():
            accepted = [difference for difference, var in checks if var.get()]
            applied, problems = apply_differences(self.catalog, accepted)
            window.destroy()
            self._after_revit_changes(applied, problems)

        row = 0
        by_schedule = {}
        for difference in changes:
            by_schedule.setdefault(difference.schedule_name, []).append(difference)
        for schedule_name, schedule_changes in by_schedule.items():
            cell(row, 0, schedule_name, font=("Segoe UI", 11, "bold"), columnspan=4, track=wide_labels)
            row += 1
            for column, heading in enumerate(("Accept", "Change", "Database Value", "Revit Value")):
                cell(row, column, heading, background="#e5e7eb", font=DEFAULT_TABLE_VIEW.heading_font)
            row += 1
            for difference in schedule_changes:
                var = tk.BooleanVar(window, value=False)
                var.trace_add("write", update_count)
                checks.append((difference, var))
                tk.Checkbutton(rows, variable=var, background="#ffffff", activebackground="#ffffff").grid(
                    row=row, column=0, sticky="n", pady=1,
                )
                cell(row, 1, difference.change).configure(wraplength=250)
                cell(row, 2, difference.database_value, background="#f3f4f6", track=value_labels)
                cell(row, 3, difference.revit_value, background="#e0f2fe", track=value_labels)
                row += 1
                if difference.note:
                    cell(row, 2, difference.note, foreground="#6b7280", columnspan=2, track=wide_labels)
                    row += 1

        # Grouped by what they say: one project can have many schedules that aren't linked.
        by_note = {}
        for difference in information:
            name = difference.schedule_name
            by_note.setdefault(difference.note, []).append(
                f"{name}: {difference.parameter}" if difference.parameter else name
            )
        if by_note:
            cell(row, 0, f"For Information ({len(information)})", font=("Segoe UI", 11, "bold"), columnspan=4, track=wide_labels)
            row += 1
            for note, names in by_note.items():
                cell(row, 0, note, font=("Segoe UI", 9, "bold"), columnspan=4, track=wide_labels)
                row += 1
                cell(row, 0, ", ".join(names), foreground="#4b5563", columnspan=4, track=wide_labels)
                row += 1

        state = "normal" if checks else "disabled"
        ttk.Button(top, text="Select All", command=lambda: set_all(True), state=state).pack(side="left")
        ttk.Button(top, text="Deselect All", command=lambda: set_all(False), state=state).pack(side="left", padx=(6, 12))
        count_label.pack(side="left")
        accept_button.configure(command=accept)
        accept_button.pack(side="right")
        ttk.Button(bottom, text="Cancel", command=window.destroy).pack(side="right", padx=(0, 6))
        update_count()
        window.checks = checks  # for tests
        window.information = by_note  # for tests
        return window

    def _after_revit_changes(self, applied, problems):
        messages = [f"Took from Revit: {message}" for message in applied]
        messages += [f"Couldn't take from Revit: {message}" for message in problems]
        if messages:
            self._show_messages(messages)
        if applied:
            # Refreshes the main tables, and leaves the changes unsaved.
            self.validate_all()

    # --- opened from Revit: review straight away ----------------------------------

    def start_revit_review_watch(self):
        """Watch for Revit asking for a review: the add-in's Design Data Manager button sends a
        snapshot marked ``"review": true``, then opens this app (or leaves it to notice)."""
        self._revit_snapshot_seen = None
        self._poll_revit_snapshot()

    def _poll_revit_snapshot(self):
        try:
            self.check_revit_review_request()
        finally:
            root = getattr(self, "root", None)
            if root is not None:
                root.after(REVIEW_POLL_MS, self._poll_revit_snapshot)

    def check_revit_review_request(self):
        """Open Review Revit Changes if a snapshot asks for it and hasn't been reviewed yet.
        Each snapshot opens the review once. Returns whether it opened."""
        path = Path(get_revit_sync_path(self.checkpoint_path))
        try:
            modified = path.stat().st_mtime
        except OSError:
            return False
        if modified == getattr(self, "_revit_snapshot_seen", None):
            return False
        self._revit_snapshot_seen = modified
        try:
            data = read_sync_file(path)
        except SyncFileError:
            return False
        sent_at = f"{data.get('project', '')} {data.get('sent_at', '')}"
        if not data.get("review") or sent_at == self._addin_setting("revit_review_handled"):
            return False
        self._record_for_revit_addin(revit_review_handled=sent_at)
        root = getattr(self, "root", None)
        if root is not None:
            # Come to the front: Revit is where the user clicked.
            root.deiconify()
            root.lift()
            root.attributes("-topmost", True)
            root.after(300, lambda: root.attributes("-topmost", False))
            root.focus_force()
        self.open_revit_changes()
        return True
