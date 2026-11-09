"""The Formula Builder: the window that opens wherever a formula is entered.

It checks the formula as it's typed, with the same checks validation uses
(``Catalog.formula_issues``), and only saves a valid one.
"""

import tkinter as tk
from tkinter import ttk

# Functions offered in the builder, as inserted. The cursor goes after the "(".
FORMULA_FUNCTION_TEMPLATES = [
    ("if(Test, Then, Else)", "if("),
    ("and(A, B)", "and("),
    ("or(A, B)", "or("),
    ("not(A)", "not("),
    ("round(X)", "round("),
    ("roundup(X)", "roundup("),
    ("rounddown(X)", "rounddown("),
    ("abs(X)", "abs("),
    ("sqrt(X)", "sqrt("),
    ("min(A, B)", "min("),
    ("max(A, B)", "max("),
    ("pi()", "pi()"),
    ("sin(X)", "sin("),
    ("cos(X)", "cos("),
    ("tan(X)", "tan("),
    ("exp(X)", "exp("),
    ("ln(X)", "ln("),
    ("log(X)", "log("),
]
FORMULA_OPERATORS = ["+", "-", "*", "/", "^", "=", "<", ">", "&", "(", ")", ","]


class FormulaBuilderWindows:
    """Mixin for ``DDMGUI``: the Formula Builder window."""

    def open_formula_builder(self, current, on_save, param_name=None, families=(), context="", parent=None):
        """Open the Formula Builder on ``current``. Save calls ``on_save(formula)`` with a valid
        formula, or ``""`` to clear it; Cancel changes nothing.

        ``param_name`` is the parameter the formula belongs to; ``families`` are the families it
        must work in (their parameters are the ones offered); ``context`` says where it goes.
        """
        parent = parent or getattr(self, "root", None)
        window = tk.Toplevel(parent)
        window.title(f"Formula Builder: {param_name}" if param_name else "Formula Builder")
        window.transient(parent)
        window.grab_set()
        families = list(families)

        top = ttk.Frame(window)
        top.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(top, text=f"{param_name} =" if param_name else "Formula", style="Title.TLabel").pack(anchor="w")
        if context:
            ttk.Label(top, text=context, wraplength=760, justify="left").pack(anchor="w", pady=(2, 0))

        # Laid out first, at the bottom, so they always show.
        bottom = ttk.Frame(window)
        bottom.pack(side="bottom", fill="x", padx=12, pady=(6, 12))
        status = tk.Text(window, height=4, wrap="word", relief="flat", background=window.cget("background"),
                         font=("Segoe UI", 9))
        status.pack(side="bottom", fill="x", padx=12)

        text = tk.Text(window, height=5, wrap="word", font=("Consolas", 11), undo=True)
        text.pack(fill="x", padx=12, pady=(4, 6))
        text.insert("1.0", current or "")
        text.focus_set()

        operators = ttk.Frame(window)
        operators.pack(fill="x", padx=12, pady=(0, 6))
        ttk.Label(operators, text="Insert:").pack(side="left", padx=(0, 6))
        for operator in FORMULA_OPERATORS:
            ttk.Button(operators, text=operator, width=3,
                       command=lambda op=operator: insert(f" {op} " if op not in "()," else op)).pack(side="left")
        ttk.Button(operators, text='"Text"', command=lambda: insert('""', back=1)).pack(side="left", padx=(6, 0))

        lists = ttk.Frame(window)
        lists.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        lists.columnconfigure(0, weight=3)
        lists.columnconfigure(1, weight=2)
        lists.rowconfigure(1, weight=1)

        # Parameters: the families' own when there are families, else every parameter.
        if families:
            names = sorted({param.name for fam in families for param in fam.params} - {param_name}, key=str.lower)
            label = "Parameters in " + (f"Family {families[0].name}" if len(families) == 1 else f"All {len(families)} Families")
        else:
            names = sorted({param.name for param in self.catalog.params} - {param_name}, key=str.lower)
            label = "Parameters"
        param_box = ttk.Frame(lists)
        param_box.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 6))
        ttk.Label(param_box, text=f"{label} (double-click to insert)", style="Section.TLabel").pack(anchor="w")
        search_var = tk.StringVar(window)
        ttk.Entry(param_box, textvariable=search_var).pack(fill="x", pady=(2, 2))
        param_list = tk.Listbox(param_box, height=10, exportselection=False)
        param_list.pack(fill="both", expand=True)

        def refresh_params(*_args):
            words = search_var.get().casefold().split()
            param_list.delete(0, "end")
            for name in names:
                if all(word in name.casefold() for word in words):
                    param_list.insert("end", name)

        search_var.trace_add("write", refresh_params)
        refresh_params()

        function_box = ttk.Frame(lists)
        function_box.grid(row=0, column=1, rowspan=2, sticky="nsew")
        ttk.Label(function_box, text="Functions (double-click to insert)", style="Section.TLabel").pack(anchor="w")
        function_list = tk.Listbox(function_box, height=10, exportselection=False)
        function_list.pack(fill="both", expand=True, pady=(2, 0))
        for shown, _inserted in FORMULA_FUNCTION_TEMPLATES:
            function_list.insert("end", shown)

        def insert(snippet, back=0):
            if text.tag_ranges("sel"):
                text.delete("sel.first", "sel.last")
            text.insert("insert", snippet)
            if back:
                text.mark_set("insert", f"insert - {back} chars")
            text.focus_set()
            check()

        def insert_param(_event=None):
            selection = param_list.curselection()
            if selection:
                insert(param_list.get(selection[0]))

        def insert_function(_event=None):
            selection = function_list.curselection()
            if selection:
                insert(FORMULA_FUNCTION_TEMPLATES[selection[0]][1])

        param_list.bind("<Double-Button-1>", insert_param)
        param_list.bind("<Return>", insert_param)
        function_list.bind("<Double-Button-1>", insert_function)
        function_list.bind("<Return>", insert_function)

        def formula():
            # Revit formulas are one line.
            return " ".join(text.get("1.0", "end").split())

        def issues():
            return self.catalog.formula_issues(formula(), param_name, families)

        def check(_event=None):
            found = issues()
            status.configure(state="normal")
            status.delete("1.0", "end")
            if not formula():
                status.insert("1.0", "No formula: Save clears it, so the value is typed in instead.")
                status.configure(foreground="#4b5563")
            elif found:
                status.insert("1.0", "Not valid yet:\n" + "\n".join(f"• {issue}" for issue in found))
                status.configure(foreground="#b42318")
            else:
                status.insert("1.0", "Valid formula.")
                status.configure(foreground="#067647")
            status.configure(state="disabled")
            save_button.configure(state="disabled" if found else "normal")
            return found

        def save(_event=None):
            if check():
                return "break"
            value = formula()
            window.destroy()
            on_save(value)
            return "break"

        save_button = ttk.Button(bottom, text="Save", command=save, style="Action.TButton")
        save_button.pack(side="right")
        ttk.Button(bottom, text="Cancel", command=window.destroy).pack(side="right", padx=(0, 6))
        ttk.Button(bottom, text="Clear", command=lambda: (text.delete("1.0", "end"), check())).pack(side="left")
        text.bind("<KeyRelease>", check)
        text.bind("<Return>", save)  # one line: Enter saves, as in the other editors
        text.bind("<KP_Enter>", save)
        window.bind("<Escape>", lambda _event: window.destroy())
        check()
        self._fit_window(window, bottom, "800x560", margin=24)

        # For tests.
        window.text, window.status, window.save, window.check = text, status, save, check
        window.formula, window.param_list, window.search_var = formula, param_list, search_var
        window.function_list, window.insert = function_list, insert
        window.insert_param, window.insert_function, window.save_button = insert_param, insert_function, save_button
        return window
