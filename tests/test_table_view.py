import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from ddm_gui import DDMGUI, OverrideTable
from table_view import (
    DEFAULT_TABLE_VIEW,
    SORT_ASCENDING_MARK,
    SORT_DESCENDING_MARK,
    ColumnResizer,
    fitted_width,
    next_sort,
    sorted_rows,
    tree_body_font,
)


class FixedFont:
    """Every character is 10 pixels wide."""

    @staticmethod
    def measure(text):
        return len(text) * 10


def fitted(entries, heading="Name"):
    return fitted_width(entries, heading, FixedFont, FixedFont)


def test_a_column_fits_its_longest_entry():
    padding = DEFAULT_TABLE_VIEW.cell_padding
    assert fitted(["short", "a longer entry"]) == 140 + padding


def test_a_columns_width_is_capped_and_has_a_minimum():
    assert fitted(["x" * 200]) == DEFAULT_TABLE_VIEW.max_column_width
    assert fitted([""], heading="") >= DEFAULT_TABLE_VIEW.min_column_width


def test_a_heading_needs_room_for_its_longest_word_only():
    mark = len(SORT_ASCENDING_MARK) * 10
    assert fitted([], heading="Very Long Heading") == 70 + mark + DEFAULT_TABLE_VIEW.heading_margin


def test_sorting_numbers_text_and_blanks():
    rows = ["Pump 10", "", "pump 2", "3", "12", "Alpha", "  "]
    assert sorted_rows(rows, str) == ["3", "12", "Alpha", "pump 2", "Pump 10", "", "  "]
    assert sorted_rows(rows, str, descending=True) == ["Pump 10", "pump 2", "Alpha", "12", "3", "", "  "]


def test_header_clicks_go_ascending_descending_then_back_to_the_tables_order():
    assert next_sort(None, "a") == ("a", False)
    assert next_sort(("a", False), "a") == ("a", True)
    assert next_sort(("a", True), "a") is None
    assert next_sort(("a", True), "b") == ("b", False)


def make_gui():
    root = tk.Tk()
    root.withdraw()
    return root, DDMGUI(root)


def shown_values(tree, column):
    return [tree.set(row, column) for row in tree.get_children()]


def test_template_sets_the_heading_font_on_every_table():
    root, gui = make_gui()
    try:
        expected = tkfont.Font(root=root, font=DEFAULT_TABLE_VIEW.heading_font).actual()
        assert gui.param_tree._ddm_heading_font.actual() == expected
        assert OverrideTable(root, ["A"]).header_font.actual() == expected
    finally:
        root.destroy()


def test_every_heading_line_leaves_the_room_tk_needs_to_draw_it():
    # With less room Tk silently draws only a heading's first line.
    root, gui = make_gui()
    try:
        for tree in (gui.param_tree, gui.family_tree, gui.group_tree):
            for column in tree["columns"]:
                gui._sort_table(tree, column)
                root.update_idletasks()
                room = int(tree.column(column, "width")) - DEFAULT_TABLE_VIEW.heading_margin
                for line in tree.heading(column, "text").split(chr(10)):
                    assert tree._ddm_heading_font.measure(line) <= room, (column, line)
    finally:
        root.destroy()


def test_clicking_a_header_sorts_and_keeps_each_rows_identity():
    root, gui = make_gui()
    try:
        tree = gui.param_tree
        original = list(tree.get_children())
        names = shown_values(tree, "name")
        assert len(names) > 1

        gui._sort_table(tree, "name")
        assert shown_values(tree, "name") == sorted_rows(names, str)
        assert SORT_ASCENDING_MARK.strip() in tree.heading("name", "text")
        # Items are still named by their position in the data, which edits rely on.
        for row in tree.get_children():
            assert names[int(row)] == tree.set(row, "name")

        gui._sort_table(tree, "name")
        assert shown_values(tree, "name") == sorted_rows(names, str, descending=True)
        assert SORT_DESCENDING_MARK.strip() in tree.heading("name", "text")

        # A re-render, such as after an edit, keeps the sort.
        gui.render_tables()
        assert shown_values(tree, "name") == sorted_rows(names, str, descending=True)

        gui._sort_table(tree, "name")
        assert list(tree.get_children()) == original
        assert SORT_ASCENDING_MARK.strip() not in tree.heading("name", "text")
    finally:
        root.destroy()


def test_columns_fit_when_a_database_loads_and_a_dragged_width_then_stays():
    root, gui = make_gui()
    try:
        tree = gui.param_tree
        font = tkfont.Font(root=root, font=DEFAULT_TABLE_VIEW.heading_font)
        width = int(tree.column("name", "width"))
        entries = gui.params_df["name"].tolist()
        assert width == fitted_width(entries, gui._humanize_column_name("name"), tree_body_font(tree), font)

        tree.column("name", width=width + 77)
        gui.render_tables()
        assert int(tree.column("name", "width")) == width + 77
    finally:
        root.destroy()


def test_dragging_a_column_edge_leaves_the_other_columns_alone():
    root = tk.Tk()
    root.geometry("600x300")
    try:
        tree = ttk.Treeview(root, columns=("a", "b", "c"), show="headings")
        for column in ("a", "b", "c"):
            tree.column(column, width=100)
        tree.pack(fill="both", expand=True)
        resizer = ColumnResizer(tree)
        root.update()

        resizer.begin("a", 100)
        resizer.drag(160)
        assert [int(tree.column(column, "width")) for column in ("a", "b", "c")] == [160, 100, 100]
        resizer.drag(60)
        assert [int(tree.column(column, "width")) for column in ("a", "b", "c")] == [60, 100, 100]
        resizer.drag(-500)
        assert int(tree.column("a", "width")) == DEFAULT_TABLE_VIEW.min_column_width

        # A real drag, through the window's events.
        tree.column("a", width=100)
        root.update()
        assert tree.identify_region(100, 10) == "separator"
        assert resizer.column_at_edge(100) == "a"
        tree.event_generate("<ButtonPress-1>", x=100, y=10)
        tree.event_generate("<B1-Motion>", x=180, y=10)
        tree.event_generate("<ButtonRelease-1>", x=180, y=10)
        root.update()
        assert [int(tree.column(column, "width")) for column in ("a", "b", "c")] == [180, 100, 100]
    finally:
        root.destroy()


def test_the_edge_is_found_when_the_table_is_scrolled_sideways():
    root = tk.Tk()
    root.geometry("300x200")
    try:
        tree = ttk.Treeview(root, columns=("a", "b", "c"), show="headings")
        for column in ("a", "b", "c"):
            tree.column(column, width=200)
        tree.pack(fill="both", expand=True)
        resizer = ColumnResizer(tree)
        root.update()
        tree.xview_moveto(0.5)
        root.update()
        scrolled = tree.xview()[0] * 600
        assert resizer.column_at_edge(400 - scrolled) == "b"
    finally:
        root.destroy()
