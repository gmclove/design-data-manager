"""The Sections tab's windows: define a section, pick its schedules and preview what changes."""
import tkinter as tk
from tkinter import messagebox, ttk

import pandas as pd

from revit_parameter_manager import ScheduleSection
from table_view import DEFAULT_TABLE_VIEW

_WHITE = "#ffffff"
_BODY_FONT = ("Segoe UI", 9)
_TITLE_FONT = ("Segoe UI", 11, "bold")


class SectionRow:
    """One schedule in a preview. ``kind`` is add, update or stop (stop using the section)."""

    def __init__(self, schedule, change, kind, through=False):
        self.schedule = schedule
        self.change = change
        self.kind = kind
        # Reached through a section that includes the one being edited.
        self.through = kind == "update" and through
        self.accepted = True
        self.clear_headers = []


def change_summary(change):
    """What a change does, as lines for a preview."""
    parts = (
        ("Added", change.added), ("Removed", change.removed), ("Moved", change.moved),
        ("Now Hidden", change.hidden_now), ("Now Shown", change.shown_now),
        ("Header Groups Replaced", change.replaced), ("Header Groups Trimmed", change.trimmed),
        ("Header Groups Dropped", change.dropped),
        ("Sections It Takes Over", [section.name for section in change.absorbs]),
    )
    return [f"{label}: {', '.join(names)}" for label, names in parts if names]


class SectionWindows:
    """Mixed into ``DDMGUI``, which supplies the catalog, the root window and the message area."""

    section_tree = None
    _section_summary_columns = ["name", "caption", "includes", "column_count", "schedules_using"]

    def _build_section_summary_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "name": section.name,
                    "caption": section.caption or "",
                    "includes": ", ".join(included.name for included in section.included_sections()),
                    "column_count": len(section.parameter_names),
                    "schedules_using": len(self.catalog.schedules_using(section)),
                }
                for section in self.catalog.sections
            ],
            columns=self._section_summary_columns,
        )

    def _open_selected_section_window(self, event):
        row_id = self.section_tree.identify_row(event.y)
        if not row_id:
            return None
        return self.open_section_window(self.catalog.sections[int(row_id)])

    # --- planning ---------------------------------------------------------------

    def _plan_section_rows(self, section, proposed, picked, only_existing):
        """Compare the schedules with ``proposed``. Returns ``(rows, unchanged, problems)``.

        ``section`` is ``None`` for a new section. Schedules using it through a section that
        includes it get a row whatever is ticked: the edit reaches them. ``unchanged`` holds the
        changes of schedules that stay linked with nothing to review. Raises ``ValueError`` if
        the proposal can't work for a schedule already using the section.
        """
        rows, unchanged, problems = [], [], []
        using = set()
        if section is None:
            self.catalog._check_section_name_free(proposed.name)
            with self.catalog.proposing(proposed):
                self.catalog._check_section_definition(proposed)
        else:
            for change in self.catalog.plan_section_update(section, proposed):
                using.add(change.schedule.name)
                direct = change.section.guid == section.guid
                if direct and change.schedule.name not in picked:
                    rows.append(SectionRow(change.schedule, change, "stop"))
                elif change.changes_anything:
                    rows.append(SectionRow(change.schedule, change, "update", through=not direct))
                else:
                    unchanged.append(change)
        with self.catalog.proposing(proposed):
            names = set(proposed.parameter_names)
            for schedule in self.catalog.schedules:
                if schedule.name in using or schedule.name not in picked:
                    continue
                current = {param.name for param in schedule.params}
                excluded = []
                if only_existing and current & names:
                    # A combined column counts as had when the schedule has all its parts.
                    excluded = [
                        name for name in proposed.parameter_names if not self.catalog.column_present(name, current)
                    ]
                try:
                    rows.append(SectionRow(schedule, schedule.plan_section(proposed, excluded=excluded), "add"))
                except ValueError as exc:
                    problems.append(str(exc))
        return rows, unchanged, problems

    def _commit_section(self, section, proposed, rows, unchanged):
        """Save the section and apply the accepted rows. Returns the section."""
        kept = list(unchanged)
        clear_headers = {}
        for row in rows:
            if row.kind == "update" and row.accepted:
                kept.append(row.change)
                clear_headers[row.schedule.name] = row.clear_headers
            elif row.kind == "stop" and not row.accepted:
                # Not accepting "stop using it" keeps the schedule linked, so the edit reaches it.
                kept.append(row.change)
        if section is None:
            section = self.catalog.add_section(
                proposed.name, proposed.members, caption=proposed.caption,
                hidden_parameter_names=proposed.own_hidden, guid=proposed.guid,
                header_groups=proposed.header_groups,
            )
        else:
            self.catalog.commit_section_update(section, proposed, kept, clear_headers)
        added = [row for row in rows if row.kind == "add" and row.accepted]
        for row in added:
            row.schedule.apply_section_change(row.change, row.clear_headers)
        lines = [f"Saved section '{section.name}'."]
        if added:
            lines.append(f"Added it to: {', '.join(row.schedule.name for row in added)}.")
        updated = [row for row in rows if row.kind == "update" and row.accepted]
        if updated:
            lines.append(f"Updated: {', '.join(row.schedule.name for row in updated)}.")
        stopped = [row for row in rows if row.accepted and row.kind == "stop"]
        stopped += [row for row in rows if not row.accepted and row.kind == "update"]
        if stopped:
            lines.append(f"Stopped using it, keeping their columns: {', '.join(row.schedule.name for row in stopped)}.")
        self._show_messages(lines)
        self.validate_all()
        return section

    # --- section window ---------------------------------------------------------

    def open_section_window(self, section=None):
        """Define a section (``None`` for a new one) and pick the schedules that use it."""
        window = tk.Toplevel(getattr(self, "root", None))
        window.title(f"Section: {section.name}" if section else "Add Section")
        window.geometry("1320x820")
        members = list(section.members) if section else []
        hidden = set(section.own_hidden) if section else set()

        def member_id(member):
            return f"section:{member['section']}" if isinstance(member, dict) else member

        def resolved_names():
            names = []
            for member in members:
                if isinstance(member, dict):
                    names.extend(self.catalog.get_section_by_guid(member["section"]).parameter_names)
                else:
                    names.append(member)
            return names

        fields = ttk.Frame(window)
        fields.pack(fill="x", padx=12, pady=(12, 6))
        name_var = tk.StringVar(window, value=section.name if section else "")
        caption_var = tk.StringVar(window, value=(section.caption or "") if section else "")
        ttk.Label(fields, text="Section Name:").pack(side="left", padx=(0, 6))
        ttk.Entry(fields, textvariable=name_var, width=32).pack(side="left")
        ttk.Label(fields, text="Header Group Over All Columns:").pack(side="left", padx=(16, 6))
        ttk.Entry(fields, textvariable=caption_var, width=32).pack(side="left")
        caption_var.trace_add("write", lambda *_args: render_columns())

        bottom = ttk.Frame(window)
        bottom.pack(side="bottom", fill="x", padx=12, pady=(6, 12))
        panes = ttk.Frame(window)
        panes.pack(fill="both", expand=True, padx=12)
        panes.columnconfigure(0, weight=3, uniform="panes")
        panes.columnconfigure(1, weight=1, uniform="panes")
        panes.rowconfigure(0, weight=1)

        # Left: the section's columns, laid out like the Schedule Builder.
        left = ttk.LabelFrame(
            panes, text="Columns, in Order (click headers to select them; click Hidden Column to hide one)",
        )
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left_buttons = ttk.Frame(left)
        left_buttons.pack(side="bottom", fill="x", padx=6, pady=6)
        table_box = ttk.Frame(left)
        table_box.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        # Its own header groups, inside the caption.
        own_groups = [
            {"caption": group["caption"], "parameter_names": list(group["parameter_names"])}
            for group in section.header_groups
        ] if section else []
        view = {"table": None}

        def origins():
            """The included section each column comes from, by column name."""
            found = {}
            for member in members:
                if isinstance(member, dict):
                    included = self.catalog.get_section_by_guid(member["section"])
                    for name in included.parameter_names:
                        found[name] = included.name
            return found

        def draft():
            """The section as it stands in the window, or ``None`` while it can't be built."""
            try:
                drafted = ScheduleSection(
                    name_var.get().strip() or "Section", list(members), caption=caption_var.get().strip() or None,
                    hidden_parameter_names=set(hidden), header_groups=own_groups,
                    guid=section.guid if section else None,
                )
            except ValueError:
                return None
            drafted.catalog = self.catalog
            return drafted

        def selected_names():
            table = view["table"]
            return table.get_selected_parameter_names() if table is not None else []

        def selected_members():
            names = set(selected_names())
            picked = []
            for member in members:
                if isinstance(member, dict):
                    included = self.catalog.get_section_by_guid(member["section"])
                    if names & set(included.parameter_names):
                        picked.append(member)
                elif member in names:
                    picked.append(member)
            return picked

        def header_text(name):
            column = self.catalog.get_column(name)
            return column.header_text if column is not None else name

        def column_width(name):
            column = self.catalog.get_column(name)
            return column.grid_column_width if column is not None else 1.0

        def render_columns(selection=None):
            if selection is None:
                selection = selected_names()
            for child in table_box.winfo_children():
                child.destroy()
            view["table"] = None
            names = resolved_names()
            if not names:
                ttk.Label(table_box, text="No Columns Yet: Add Parameter... or Add Section... Adds Them").pack(anchor="w")
                refresh_counts()
                return
            drafted = draft()
            groups = [
                {"caption": caption, "parameter_names": list(columns)} for caption, columns in drafted.bands()
            ] if drafted is not None else []
            found = origins()
            rows = [{
                "section": "Section",
                "label": "Included From",
                "cells": [
                    self._table_cell(found.get(name, ""), "inherited" if name in found else "set") for name in names
                ],
            }]
            for row in self._parameter_table_rows(names, [], schedule_window=True):
                for cell in row["cells"]:
                    cell["editable"] = False
                rows.append(row)
            table = self._build_override_table(
                table_box, names, rows,
                header_texts={name: header_text(name) for name in names},
                groups=groups,
                hidden_names=drafted.hidden_parameter_names if drafted is not None else set(hidden),
                on_hidden_toggle=toggle_hidden_column,
                grid_column_widths=[column_width(name) for name in names],
                header_label="Section",
            )
            table.selected_indices = {index for index, name in enumerate(names) if name in set(selection)}
            table._draw_grid()
            view["table"] = table
            refresh_counts()

        def insert_members(picked):
            chosen = selected_members()
            position = members.index(chosen[-1]) + 1 if chosen else len(members)
            members[position:position] = picked
            render_columns([
                name for member in picked
                for name in (
                    self.catalog.get_section_by_guid(member["section"]).parameter_names
                    if isinstance(member, dict) else [member]
                )
            ])

        def add_parameters():
            present = set(resolved_names())
            choices = [
                (combined.name, f"{combined.name} Combined {combined.header_text} {combined.pattern()}")
                for combined in self.catalog.combined_params if combined.name not in present
            ] + [
                (param.name, f"{param.name} {param.header_text or ''} {param.group_under or ''}")
                for param in self.catalog.params if param.name not in present
            ]
            return self._pick_names(window, "Add Parameters to Section", choices, insert_members)

        def add_section():
            listed = {member["section"] for member in members if isinstance(member, dict)}
            including = {other.guid for other in self.catalog.sections_including(section)} if section else set()
            choices = [
                (other.name, f"{other.name} {other.caption or ''} {' '.join(other.parameter_names)}")
                for other in self.catalog.sections
                if other.guid not in listed and other.guid not in including and (not section or other.guid != section.guid)
            ]

            def add(picked):
                insert_members([{"section": self.catalog.get_section(name).guid} for name in picked])

            hint = "A section can't include one that already includes it."
            return self._pick_names(window, "Include Sections", choices, add, hint)

        def remove_parameters():
            chosen = selected_members()
            if not chosen:
                messagebox.showinfo("Remove", "Select the columns to remove first: click their headers.", parent=window)
                return
            for member in chosen:
                members.remove(member)
                if not isinstance(member, dict):
                    hidden.discard(member)
            remaining = set(resolved_names())
            for group in own_groups:
                group["parameter_names"] = [name for name in group["parameter_names"] if name in remaining]
            own_groups[:] = [group for group in own_groups if group["parameter_names"]]
            render_columns([])

        def move(step):
            chosen = selected_members()
            selection = selected_names()
            indices = [index for index, member in enumerate(members) if member in chosen]
            if not indices or (step < 0 and indices[0] == 0) or (step > 0 and indices[-1] == len(members) - 1):
                return
            for index in (indices if step < 0 else reversed(indices)):
                if members[index + step] not in chosen:
                    members[index], members[index + step] = members[index + step], members[index]
            render_columns(selection)

        def toggle_hidden_column(name):
            if name not in members:
                messagebox.showinfo(
                    "Hidden Column", f"{name} comes from section '{origins().get(name, '')}'; hide it there.",
                    parent=window,
                )
                return
            hidden.symmetric_difference_update({name})
            render_columns()

        def toggle_hidden():
            selection = selected_names()
            # An included section says which of its own columns are hidden.
            hidden.symmetric_difference_update(name for name in selection if name in members)
            render_columns(selection)

        def group_selected(caption=None):
            """Group the selected headers under ``caption``; without one, ask for it."""
            names = selected_names()
            if not names:
                messagebox.showwarning("Select Headers", "Select the headers to group first.", parent=window)
                return None
            if caption is None:
                return self._ask_group_caption(window, lambda text: group_selected(text))
            if set(names) == set(resolved_names()):
                # Over every column: that is the section's caption.
                caption_var.set(caption)
                return None
            own_groups.append({"caption": caption, "parameter_names": list(names)})
            drafted = draft()
            issue = drafted.band_issue() if drafted is not None else None
            if issue:
                own_groups.pop()
                messagebox.showwarning("Cannot Group Headers", issue, parent=window)
                return None
            render_columns(names)
            return None

        def ungroup_selected():
            """Remove the innermost header group around the selected headers."""
            names = set(selected_names())
            if not names:
                messagebox.showwarning("Select Headers", "Select a header in the group to remove first.", parent=window)
                return
            around = [group for group in own_groups if names <= set(group["parameter_names"])]
            if around:
                own_groups.remove(min(around, key=lambda group: len(group["parameter_names"])))
            elif caption_var.get().strip():
                caption_var.set("")
                return
            else:
                drafted = draft()
                source = next(
                    (
                        origins().get(next(iter(names)), "")
                        for caption, columns in (drafted.bands() if drafted is not None else [])
                        if names <= set(columns)
                    ),
                    None,
                )
                if source:
                    messagebox.showinfo(
                        "Ungroup Headers", f"That header group comes from section '{source}'; change it there.",
                        parent=window,
                    )
                return
            render_columns(sorted(names, key=resolved_names().index))

        for text, command in (
            ("Add Parameter...", add_parameters), ("Add Section...", add_section), ("Remove", remove_parameters),
            ("◀ Move Left", lambda: move(-1)), ("Move Right ▶", lambda: move(1)),
            ("Group Selected Headers", group_selected), ("Ungroup Selected Headers", ungroup_selected),
        ):
            ttk.Button(left_buttons, text=text, command=command).pack(side="left", padx=(0, 6))

        # Right: the schedules, those with the most of its columns first.
        right = ttk.LabelFrame(panes, text="Schedules Using This Section")
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        only_existing_var = tk.BooleanVar(window, value=True)
        ttk.Checkbutton(
            right, variable=only_existing_var, text="Only Add Columns a Schedule Already Has",
        ).pack(anchor="w", padx=6, pady=(6, 2))
        picks = ttk.Frame(right)
        picks.pack(fill="x", padx=6, pady=(0, 2))
        canvas, rows = self._scrolling_rows(right, window)
        canvas.master.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        schedule_vars = {}
        count_labels = {}

        def has_count(schedule):
            current = {param.name for param in schedule.params}
            return sum(self.catalog.column_present(name, current) for name in resolved_names())

        def set_all(value):
            for var in schedule_vars.values():
                var.set(value)

        ttk.Button(picks, text="Select All", command=lambda: set_all(True)).pack(side="left")
        ttk.Button(picks, text="Deselect All", command=lambda: set_all(False)).pack(side="left", padx=(6, 0))

        def build_schedule_rows():
            def order(schedule):
                using = section is not None and bool(schedule.sections_through(section))
                return (not using, -has_count(schedule))

            ordered = sorted(self.catalog.schedules, key=order)
            for row, schedule in enumerate(ordered):
                through = schedule.sections_through(section) if section is not None else []
                direct = section is not None and schedule._section_use(section.guid) is not None
                var = tk.BooleanVar(window, value=bool(through))
                schedule_vars[schedule.name] = var
                # Using it through another section: that section is where to change it.
                tk.Checkbutton(
                    rows, variable=var, text=schedule.name, anchor="w", background=_WHITE, activebackground=_WHITE,
                    font=_BODY_FONT, state="disabled" if through and not direct else "normal",
                ).grid(row=row, column=0, sticky="w")
                count = tk.Label(rows, background=_WHITE, foreground="#6b7280", font=_BODY_FONT)
                count.grid(row=row, column=1, sticky="w", padx=(8, 0))
                if through and not direct:
                    count.configure(text="Through " + ", ".join(used.name for used in through))
                else:
                    count_labels[schedule.name] = (count, schedule)

        def refresh_counts():
            for count, schedule in count_labels.values():
                total = len(resolved_names())
                count.configure(text=f"Has {has_count(schedule)} of {total}" if total else "")

        build_schedule_rows()
        render_columns()

        def proposal():
            changes = dict(
                name=name_var.get(), members=list(members), caption=caption_var.get().strip() or None,
                hidden_parameter_names=set(hidden),
                header_groups=[dict(group, parameter_names=list(group["parameter_names"])) for group in own_groups],
            )
            if section is not None:
                return section.edited(**changes)
            proposed = ScheduleSection(**changes)
            proposed.catalog = self.catalog
            return proposed

        def preview():
            try:
                proposed = proposal()
                picked = {name for name, var in schedule_vars.items() if var.get()}
                plan_rows, unchanged, problems = self._plan_section_rows(section, proposed, picked, only_existing_var.get())
            except ValueError as exc:
                messagebox.showwarning("Section", str(exc), parent=window)
                return None

            def commit():
                self._commit_section(section, proposed, plan_rows, unchanged)
                window.destroy()

            if not plan_rows and not problems:
                commit()
                return None
            return self._open_section_preview(window, f"Preview Section: {proposed.name}", plan_rows, problems, commit)

        def delete():
            count = len(self.catalog.schedules_using(section))
            including = self.catalog.sections_including(section)
            message = (
                f"Delete section '{section.name}'? The {count} schedules using it keep its columns."
            )
            if including:
                message += " " + ", ".join(other.name for other in including) + " will list its columns directly."
            if not messagebox.askyesno("Delete Section", message, parent=window):
                return
            self.catalog.remove_section(section.name)
            window.destroy()
            self._show_messages([f"Deleted section '{section.name}'."])
            self.validate_all()

        if section is not None:
            ttk.Button(bottom, text="Delete Section", command=delete).pack(side="left")
        ttk.Button(bottom, text="Preview Changes...", command=preview, style="Action.TButton").pack(side="right")
        ttk.Button(bottom, text="Cancel", command=window.destroy).pack(side="right", padx=(0, 6))

        # For tests.
        window.name_var, window.caption_var = name_var, caption_var
        window.names, window.hidden = members, hidden
        window.schedule_vars = schedule_vars
        window.only_existing_var = only_existing_var
        window.preview, window.delete = preview, delete
        window.add_parameters, window.move, window.toggle_hidden = add_parameters, move, toggle_hidden
        window.add_section = add_section
        window.render_columns = render_columns
        window.header_groups = own_groups
        window.group_selected, window.ungroup_selected = group_selected, ungroup_selected
        window.table = lambda: view["table"]

        def select(names):
            render_columns(list(names))

        window.select = select
        return window

    @staticmethod
    def _ask_group_caption(parent, on_caption):
        """The Schedule Builder's Name Header Group box; Group calls ``on_caption(text)``."""
        editor = tk.Toplevel(parent)
        editor.title("Name Header Group")
        editor.transient(parent)
        editor.grab_set()
        editor.geometry("360x130")
        ttk.Label(editor, text="Group name:", style="Section.TLabel").pack(anchor="w", padx=10, pady=(10, 4))
        caption_var = tk.StringVar(editor)
        entry = ttk.Entry(editor, textvariable=caption_var)
        entry.pack(fill="x", padx=10, pady=4)
        entry.focus_set()

        def save():
            caption = caption_var.get().strip()
            if not caption:
                messagebox.showwarning("Group Name Required", "Enter a name for this header group.", parent=editor)
                return
            editor.destroy()
            on_caption(caption)

        buttons = ttk.Frame(editor)
        buttons.pack(fill="x", padx=10, pady=(4, 8))
        ttk.Button(buttons, text="Group", command=save).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=editor.destroy).pack(side="right", padx=(0, 6))
        entry.bind("<Return>", lambda _event: save())
        editor.caption_var, editor.save = caption_var, save
        return editor

    @staticmethod
    def _scrolling_rows(parent, window):
        """A scrolling white area. Returns ``(canvas, frame to fill)``; pack ``canvas.master``."""
        body = ttk.Frame(parent)
        canvas = tk.Canvas(body, highlightthickness=0, background=_WHITE)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        rows = tk.Frame(canvas, background=_WHITE)
        rows_id = canvas.create_window((0, 0), window=rows, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(rows_id, width=event.width))
        rows.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))

        def scrolled(event):
            if canvas.winfo_exists():
                canvas.yview_scroll(-int(event.delta / 120), "units")

        window.bind("<MouseWheel>", scrolled)
        return canvas, rows

    # --- preview ----------------------------------------------------------------

    def _open_section_preview(self, parent, title, rows, problems, on_apply):
        """Each schedule's columns side by side, now and after, with a box to accept it."""
        window = tk.Toplevel(parent)
        window.title(title)
        window.geometry("1100x660")
        window.transient(parent)

        top = ttk.Frame(window)
        top.pack(fill="x", padx=10, pady=(10, 6))
        bottom = ttk.Frame(window)
        bottom.pack(side="bottom", fill="x", padx=10, pady=(6, 10))
        canvas, grid = self._scrolling_rows(window, window)
        canvas.master.pack(fill="both", expand=True, padx=10)
        grid.columnconfigure(1, weight=1, uniform="values")
        grid.columnconfigure(2, weight=1, uniform="values")

        accepted_vars = []
        header_vars = []

        def cell(row, column, text, background=_WHITE, foreground="#111827", font=_BODY_FONT, **options):
            label = tk.Label(
                grid, text=text, background=background, foreground=foreground, anchor="nw", justify="left",
                font=font, padx=6, pady=3, wraplength=460,
            )
            label.grid(row=row, column=column, sticky="nsew", padx=1, pady=1, **options)
            return label

        def column_lines(names, hidden_names):
            return "\n".join(name + (" (Hidden)" if name in hidden_names else "") for name in names)

        row_number = 0
        for row in rows:
            change = row.change
            var = tk.BooleanVar(window, value=True)
            accepted_vars.append((row, var))
            tk.Checkbutton(grid, variable=var, background=_WHITE, activebackground=_WHITE).grid(
                row=row_number, column=0, sticky="nw",
            )
            through = f" (Through {change.section.name})" if row.through else ""
            cell(row_number, 1, row.schedule.name + through, font=_TITLE_FONT, columnspan=2)
            row_number += 1
            if row.kind == "stop":
                cell(row_number, 1, "Stops using this section and keeps its columns as ordinary ones.", columnspan=2)
                row_number += 1
                continue
            cell(row_number, 1, "Now", background="#e5e7eb", font=DEFAULT_TABLE_VIEW.heading_font)
            cell(row_number, 2, f"After: {', '.join(change.captions)}" if change.captions else "After",
                 background="#e5e7eb", font=DEFAULT_TABLE_VIEW.heading_font)
            row_number += 1
            cell(row_number, 1, column_lines(change.before, row.schedule.hidden_field_names), background="#f3f4f6")
            cell(row_number, 2, column_lines(change.block, change.hidden), background="#e0f2fe")
            row_number += 1
            summary = change_summary(change)
            if row.kind == "update":
                summary.append(f"If not accepted: keeps its columns and stops using {change.section.name}.")
            if summary:
                cell(row_number, 1, "\n".join(summary), foreground="#4b5563", columnspan=2)
                row_number += 1
            for name, local, standard in change.local_headers:
                header_var = tk.BooleanVar(window, value=False)
                header_vars.append((row, name, header_var))
                tk.Checkbutton(
                    grid, variable=header_var, background="#fef3c7", activebackground="#fef3c7", font=_BODY_FONT,
                    anchor="w", text=f"Use the Parameter's Header for {name}: this schedule shows '{local}', "
                    f"the parameter says '{standard or ''}'",
                ).grid(row=row_number, column=1, columnspan=2, sticky="ew", padx=1, pady=1)
                row_number += 1
        if problems:
            cell(row_number, 1, f"Can't Be Added ({len(problems)})", font=_TITLE_FONT, columnspan=2)
            row_number += 1
            cell(row_number, 1, "\n".join(problems), foreground="#b91c1c", columnspan=2)

        count_label = ttk.Label(top)
        apply_button = ttk.Button(bottom, command=lambda: apply(), style="Action.TButton")

        def update_count(*_args):
            selected = sum(var.get() for _row, var in accepted_vars)
            count_label.configure(text=f"{selected} of {len(accepted_vars)} Selected")
            apply_button.configure(text=f"Apply Selected ({selected})")

        def set_all(value):
            for _row, var in accepted_vars:
                var.set(value)

        def apply():
            for row, var in accepted_vars:
                row.accepted = var.get()
                row.clear_headers = [name for other, name, header_var in header_vars if other is row and header_var.get()]
            window.destroy()
            on_apply()

        for _row, var in accepted_vars:
            var.trace_add("write", update_count)
        ttk.Button(top, text="Select All", command=lambda: set_all(True)).pack(side="left")
        ttk.Button(top, text="Deselect All", command=lambda: set_all(False)).pack(side="left", padx=(6, 12))
        count_label.pack(side="left")
        apply_button.pack(side="right")
        ttk.Button(bottom, text="Cancel", command=window.destroy).pack(side="right", padx=(0, 6))
        update_count()

        # For tests.
        window.accepted_vars, window.header_vars, window.problems = accepted_vars, header_vars, problems
        window.apply, window.set_all = apply, set_all
        return window

    # --- schedule builder -------------------------------------------------------

    def _add_section_to_schedule(self, parent, schedule, after, on_done):
        """The Schedule Builder's Add Section...: pick a section, preview it on this schedule."""
        used = set()
        for section, _use in schedule._used_sections():
            used |= {section.guid} | section.included_guids()
        choices = [
            (section.name, f"{section.name} {section.caption or ''} {' '.join(section.parameter_names)}")
            for section in self.catalog.sections if section.guid not in used
        ]
        if not choices:
            messagebox.showinfo(
                "Add Section", "There's no section left to add. Make sections on the Sections tab.", parent=parent,
            )
            return None

        def pick(names):
            for name in names:
                section = self.catalog.get_section(name)
                try:
                    change = schedule.plan_section(section, excluded=[], after=after)
                except ValueError as exc:
                    messagebox.showwarning("Add Section", str(exc), parent=parent)
                    continue
                row = SectionRow(schedule, change, "add")

                def apply(row=row, section=section):
                    if row.accepted:
                        schedule.apply_section_change(row.change, row.clear_headers)
                        self._show_messages([f"Added section '{section.name}' to '{schedule.name}'."])
                        self.validate_all()
                        on_done()

                parent.preview_window = self._open_section_preview(
                    parent, f"Preview Section: {section.name}", [row], [], apply,
                )

        return self._pick_names(parent, f"Add Sections to {schedule.name}", choices, pick)
