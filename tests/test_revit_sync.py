import json

import pytest

from config.app_paths import get_revit_sync_path
from revit_parameter_manager import SCHEDULE_FILTER_PARAM, Catalog, normalized_sorting
from revit_schedule_macro_generator import schedule_specs
from revit_sync import (
    COLUMN_ADDED,
    COLUMN_ORDER,
    COLUMN_REMOVED,
    HEADING,
    HIDDEN,
    INFORMATION,
    ITEMIZE,
    NAME,
    SORTING,
    SYNC_FORMAT_VERSION,
    WIDTH,
    SyncFileError,
    apply_differences,
    read_sync_file,
    schedule_differences,
)


def make_catalog():
    catalog = Catalog()
    catalog.add_param("DDM_Airflow", "Text", header_text="Airflow", grid_column_width=18)
    catalog.add_param("DDM_Capacity", "Text", grid_column_width=15)
    catalog.add_param("DDM_Notes", "Text")
    catalog.add_param("DDM_Extra", "Text")
    schedule = catalog.add_schedule("Mechanical", field_names=["DDM_Airflow", "DDM_Capacity", "DDM_Notes"])
    schedule.set_field_hidden("DDM_Notes", True)
    return catalog


def sent_from(catalog, role="Finished", name=None):
    """What the macro would send for the schedule, built exactly as the database says."""
    spec = schedule_specs(catalog)[0][0]
    columns = [
        {
            "parameter": column["parameter"],
            "heading": column["header"],
            "width_feet": column["width_feet"],
            "hidden": column["hidden"],
        }
        for column in spec["columns"]
    ]
    # The macro adds the filter column to every schedule, hidden.
    columns.append({"parameter": SCHEDULE_FILTER_PARAM, "heading": "Filter", "width_feet": 1, "hidden": True})
    return {
        "guid": spec["guid"],
        "role": role,
        "name": name or spec["name"],
        "itemize": spec["itemize"],
        # The add-in always sends the schedule's sorting, unsorted or not.
        "sorting": normalized_sorting(spec.get("sorting")),
        "columns": columns,
        "unavailable": [],
    }


def file_with(*schedules, unlinked=()):
    return {
        "version": SYNC_FORMAT_VERSION,
        "project": "Test Project",
        "sent_at": "2026-11-05 10:00",
        "schedules": list(schedules),
        "unlinked": list(unlinked),
    }


def column(sent, parameter):
    return next(item for item in sent["columns"] if item["parameter"] == parameter)


def kinds(differences):
    return [difference.kind for difference in differences]


def test_a_schedule_built_from_the_database_has_no_differences():
    catalog = make_catalog()
    assert schedule_differences(catalog, file_with(sent_from(catalog))) == []


def test_each_kind_of_change_is_found():
    catalog = make_catalog()
    sent = sent_from(catalog, name="Mechanical Renamed")
    sent["itemize"] = False
    column(sent, "DDM_Airflow")["heading"] = "Design Airflow"
    column(sent, "DDM_Airflow")["width_feet"] = 2
    column(sent, "DDM_Capacity")["hidden"] = True
    assert sorted(kinds(schedule_differences(catalog, file_with(sent)))) == sorted(
        [NAME, ITEMIZE, HEADING, WIDTH, HIDDEN]
    )


def test_width_compares_in_inches_with_a_tolerance():
    catalog = make_catalog()
    sent = sent_from(catalog)
    column(sent, "DDM_Airflow")["width_feet"] += 0.0001
    assert schedule_differences(catalog, file_with(sent)) == []
    column(sent, "DDM_Airflow")["width_feet"] = 2
    difference = schedule_differences(catalog, file_with(sent))[0]
    assert (difference.database_value, difference.revit_value) == ("18", "24")


def test_columns_added_removed_and_reordered_are_found():
    catalog = make_catalog()
    sent = sent_from(catalog)
    sent["columns"] = [
        column(sent, "DDM_Notes"),
        column(sent, "DDM_Airflow"),
        {"parameter": "DDM_Extra", "heading": "Extra", "width_feet": 1, "hidden": False},
    ]
    assert sorted(kinds(schedule_differences(catalog, file_with(sent)))) == sorted(
        [COLUMN_REMOVED, COLUMN_ORDER, COLUMN_ADDED]
    )


def test_a_column_revit_cant_schedule_is_information_not_a_removal():
    catalog = make_catalog()
    sent = sent_from(catalog)
    sent["columns"] = [item for item in sent["columns"] if item["parameter"] != "DDM_Capacity"]
    sent["unavailable"] = ["DDM_Capacity"]
    differences = schedule_differences(catalog, file_with(sent))
    assert kinds(differences) == [INFORMATION]
    assert not differences[0].can_apply


def test_the_filter_column_counts_only_when_the_database_lists_it():
    catalog = make_catalog()
    sent = sent_from(catalog)
    catalog.schedules[0].filter_value = "Mechanical"
    assert schedule_differences(catalog, file_with(sent)) == []


def three_schedules(catalog):
    return (
        sent_from(catalog, role="Model", name="3D - Mechanical"),
        sent_from(catalog, role="Working", name="Mechanical - Working"),
        sent_from(catalog),
    )


def test_a_width_changed_on_any_revit_schedule_can_be_accepted():
    # As in a real project: the width was changed on the 3D schedule only.
    catalog = make_catalog()
    model, working, finished = three_schedules(catalog)
    column(model, "DDM_Airflow")["width_feet"] = 1
    differences = schedule_differences(catalog, file_with(model, working, finished))
    assert kinds(differences) == [WIDTH]
    assert differences[0].can_apply
    assert (differences[0].database_value, differences[0].revit_value) == ("18", "12")
    assert "3D - Mechanical" in differences[0].note

    apply_differences(catalog, differences)
    assert catalog.schedules[0].grid_column_width_overrides["DDM_Airflow"] == 12


def test_a_header_changed_on_any_revit_schedule_can_be_accepted():
    catalog = make_catalog()
    model, working, finished = three_schedules(catalog)
    column(working, "DDM_Airflow")["heading"] = "Changed in Working"
    differences = schedule_differences(catalog, file_with(model, working, finished))
    assert kinds(differences) == [HEADING]
    assert "Mechanical - Working" in differences[0].note

    apply_differences(catalog, differences)
    assert catalog.schedules[0].header_text_overrides["DDM_Airflow"] == "Changed in Working"


def test_the_same_change_on_every_revit_schedule_is_one_row():
    catalog = make_catalog()
    schedules = three_schedules(catalog)
    for sent in schedules:
        column(sent, "DDM_Airflow")["width_feet"] = 1
    differences = schedule_differences(catalog, file_with(*schedules))
    assert kinds(differences) == [WIDTH]
    assert differences[0].note == ""


def test_different_values_on_revit_schedules_are_separate_rows_and_finished_wins():
    catalog = make_catalog()
    model, working, finished = three_schedules(catalog)
    column(model, "DDM_Airflow")["width_feet"] = 1
    column(finished, "DDM_Airflow")["width_feet"] = 2
    differences = schedule_differences(catalog, file_with(model, working, finished))
    assert kinds(differences) == [WIDTH, WIDTH]
    assert all("different values" in difference.note for difference in differences)

    apply_differences(catalog, differences)
    assert catalog.schedules[0].grid_column_width_overrides["DDM_Airflow"] == 24


def test_columns_differing_on_other_revit_schedules_are_only_information():
    catalog = make_catalog()
    model, working, finished = three_schedules(catalog)
    working["columns"] = [item for item in working["columns"] if item["parameter"] != "DDM_Capacity"]
    differences = schedule_differences(catalog, file_with(model, working, finished))
    assert kinds(differences) == [INFORMATION]
    assert differences[0].revit_value == "Mechanical - Working"
    assert schedule_differences(catalog, file_with(model, finished)) == []


def test_only_the_finished_schedule_is_compared():
    catalog = make_catalog()
    working = sent_from(catalog, role="Working", name="Mechanical - Working")
    assert kinds(schedule_differences(catalog, file_with(working))) == [INFORMATION]


def test_schedules_without_a_match_are_only_listed():
    catalog = make_catalog()
    gone = dict(sent_from(catalog), guid="not-in-the-database", name="Deleted")
    differences = schedule_differences(catalog, file_with(sent_from(catalog), gone, unlinked=["Door Schedule"]))
    assert kinds(differences) == [INFORMATION, INFORMATION]
    assert [difference.schedule_name for difference in differences] == ["Deleted", "Door Schedule"]
    assert not any(difference.can_apply for difference in differences)


def test_accepting_every_change_leaves_no_differences():
    catalog = make_catalog()
    sent = sent_from(catalog, name="Mechanical Renamed")
    sent["itemize"] = False
    column(sent, "DDM_Airflow")["heading"] = "Design Airflow"
    column(sent, "DDM_Airflow")["width_feet"] = 2
    column(sent, "DDM_Capacity")["hidden"] = True
    filter_column = column(sent, SCHEDULE_FILTER_PARAM)
    sent["columns"] = [
        column(sent, "DDM_Capacity"),
        {"parameter": "DDM_Extra", "heading": "Extra", "width_feet": 1.5, "hidden": True},
        column(sent, "DDM_Airflow"),
        filter_column,
    ]
    data = file_with(sent)

    applied, problems = apply_differences(catalog, schedule_differences(catalog, data))

    assert problems == []
    assert applied
    assert schedule_differences(catalog, data) == []
    schedule = catalog.schedules[0]
    assert schedule.name == "Mechanical Renamed"
    assert [param.name for param in schedule.params] == ["DDM_Capacity", "DDM_Extra", "DDM_Airflow"]
    assert schedule.hidden_field_names == {"DDM_Capacity", "DDM_Extra"}
    assert schedule.grid_column_width_overrides["DDM_Airflow"] == 24
    assert schedule.grid_column_width_overrides["DDM_Extra"] == 18


def test_rejected_changes_change_nothing():
    catalog = make_catalog()
    before = catalog.to_dict()
    sent = sent_from(catalog, name="Mechanical Renamed")
    differences = schedule_differences(catalog, file_with(sent))
    assert differences
    assert apply_differences(catalog, []) == ([], [])
    assert catalog.to_dict() == before


def test_finding_differences_changes_nothing():
    catalog = make_catalog()
    before = catalog.to_dict()
    schedule_differences(catalog, file_with(sent_from(catalog, name="Other")))
    assert catalog.to_dict() == before


def test_accepting_a_rename_keeps_the_schedules_elements():
    catalog = make_catalog()
    schedule = catalog.schedules[0]
    assert schedule.resolved_filter_value == "Mechanical"
    apply_differences(catalog, schedule_differences(catalog, file_with(sent_from(catalog, name="New Name"))))
    assert schedule.name == "New Name"
    assert schedule.resolved_filter_value == "Mechanical"


def test_a_rename_to_a_taken_name_is_a_problem_and_the_rest_still_apply():
    catalog = make_catalog()
    catalog.add_schedule("Taken", field_names=["DDM_Airflow"])
    sent = sent_from(catalog, name="Taken")
    sent["itemize"] = False
    applied, problems = apply_differences(catalog, schedule_differences(catalog, file_with(sent)))
    assert len(problems) == 1 and "Name" in problems[0]
    assert len(applied) == 1
    schedule = catalog.get_schedule("Mechanical")
    assert schedule.itemize is False
    # The failed rename left the schedule filtering on its name, as before.
    assert schedule.filter_value is None


def test_a_column_the_database_doesnt_have_cant_be_accepted():
    catalog = make_catalog()
    sent = sent_from(catalog)
    sent["columns"].insert(0, {"parameter": "Not In Database", "heading": "X", "width_feet": 1, "hidden": False})
    differences = schedule_differences(catalog, file_with(sent))
    assert kinds(differences) == [INFORMATION]
    assert differences[0].parameter == "Not In Database"
    assert not differences[0].can_apply
    assert apply_differences(catalog, differences) == ([], [])


def test_read_sync_file(tmp_path):
    path = tmp_path / "database.revit-sync.json"
    path.write_text(json.dumps(file_with()), encoding="utf-8")
    assert read_sync_file(path)["project"] == "Test Project"

    # The macro's File.WriteAllText writes no byte order mark, but a hand-saved file might.
    path.write_text(json.dumps(file_with()), encoding="utf-8-sig")
    assert read_sync_file(path)["project"] == "Test Project"

    for bad in ("not json", "[]", json.dumps({"version": SYNC_FORMAT_VERSION}), json.dumps({"version": 99, "schedules": []})):
        path.write_text(bad, encoding="utf-8")
        with pytest.raises(SyncFileError):
            read_sync_file(path)
    with pytest.raises(SyncFileError):
        read_sync_file(tmp_path / "missing.json")


def test_the_sync_file_sits_next_to_the_database(tmp_path):
    assert get_revit_sync_path(tmp_path / "equipment.ddm.json") == tmp_path / "equipment.revit-sync.json"


def test_accepting_an_added_column_leaves_the_other_columns_in_their_order():
    catalog = make_catalog()
    sent = sent_from(catalog)
    new = {"parameter": "DDM_Extra", "heading": "Extra", "width_feet": 1, "hidden": False}
    # Revit has the columns in a different order too, which isn't being accepted.
    sent["columns"] = [column(sent, "DDM_Notes"), new, column(sent, "DDM_Capacity"), column(sent, "DDM_Airflow")]
    differences = schedule_differences(catalog, file_with(sent))
    added = [difference for difference in differences if difference.kind == COLUMN_ADDED]

    apply_differences(catalog, added)

    assert [param.name for param in catalog.schedules[0].params] == [
        "DDM_Airflow", "DDM_Capacity", "DDM_Notes", "DDM_Extra",
    ]


def test_an_added_first_column_goes_first():
    catalog = make_catalog()
    sent = sent_from(catalog)
    sent["columns"].insert(0, {"parameter": "DDM_Extra", "heading": "Extra", "width_feet": 1, "hidden": False})
    apply_differences(catalog, schedule_differences(catalog, file_with(sent)))
    assert catalog.schedules[0].params[0].name == "DDM_Extra"


# --- three-way: what was last synced -------------------------------------------------

def synced_file(catalog, sent):
    """A sync file whose project remembers the database as it is now as the last sync."""
    spec = schedule_specs(catalog)[0][0]
    data = file_with(sent)
    data["synced"] = {spec["guid"]: json.loads(json.dumps(spec))}
    return data


def test_with_a_last_sync_each_difference_says_which_side_changed_it():
    from revit_sync import BOTH_CHANGED, REVIT_CHANGED

    catalog = make_catalog()
    sent = sent_from(catalog)
    data = synced_file(catalog, sent)
    schedule = catalog.schedules[0]
    # Since the last sync: Revit changed a header and a width; the database changed the same
    # width differently, and hid a column Revit didn't touch.
    column(sent, "DDM_Airflow")["heading"] = "AIRFLOW (REVIT)"
    column(sent, "DDM_Capacity")["width_feet"] = 2.0
    schedule.override_param("DDM_Capacity", grid_column_width=20)
    schedule.set_field_hidden("DDM_Airflow", True)

    differences = schedule_differences(catalog, data)

    by_kind = {(d.kind, d.parameter): d for d in differences}
    assert by_kind[(HEADING, "DDM_Airflow")].origin == REVIT_CHANGED
    width = by_kind[(WIDTH, "DDM_Capacity")]
    assert width.origin == BOTH_CHANGED and width.note.startswith("Changed in Revit and in the database")
    # Only the database hid it: not for review, but counted.
    assert (HIDDEN, "DDM_Airflow") not in by_kind
    info = [d for d in differences if d.kind == INFORMATION]
    assert [d.note for d in info] == [
        "Changed in the database since the last sync (1): Revit gets it when you save and apply in Revit."]


def test_sorting_changed_in_revit_can_be_accepted():
    catalog = make_catalog()
    schedule = catalog.schedules[0]
    sent = sent_from(catalog)
    revit_sorting = {
        "sort_group_fields": [
            {"parameter": "DDM_Notes", "descending": True, "show_header": True, "show_footer": True,
             "show_footer_title": False, "show_footer_count": True, "show_blank_line": False},
        ],
        "show_grand_total": True, "show_grand_total_title": True, "show_grand_total_count": True,
        "grand_total_title": "All",
    }
    sent["sorting"] = revit_sorting
    differences = schedule_differences(catalog, file_with(sent))
    assert [(d.kind, d.database_value, d.revit_value) for d in differences] == [
        (SORTING, "Not Sorted", "Sort by DDM_Notes (Descending); Grand Totals")]

    applied, problems = apply_differences(catalog, differences)
    assert problems == [] and applied
    assert schedule.sorting_dict() == revit_sorting
    assert schedule_differences(catalog, file_with(sent)) == []

    # Same levels, a different footer: still a difference, said so.
    sent["sorting"] = json.loads(json.dumps(revit_sorting))
    sent["sorting"]["sort_group_fields"][0]["show_footer"] = False
    [difference] = schedule_differences(catalog, file_with(sent))
    assert difference.kind == SORTING and difference.database_value.endswith("(Other Settings Differ)")


def test_sorting_by_a_column_the_database_schedule_lacks_is_a_problem():
    catalog = make_catalog()
    sent = sent_from(catalog)
    sent["sorting"] = {"sort_group_fields": [{"parameter": "Family and Type"}]}
    applied, problems = apply_differences(catalog, schedule_differences(catalog, file_with(sent)))
    assert applied == [] and len(problems) == 1 and "Family and Type" in problems[0]
    assert catalog.schedules[0].sort_group_fields == []


def test_an_older_add_in_or_last_sync_without_sorting_means_not_sorted():
    catalog = make_catalog()
    sent = sent_from(catalog)
    del sent["sorting"]  # an add-in from before sorting
    assert schedule_differences(catalog, file_with(sent)) == []
    # The database sorts now; an older last sync (no "sorting") counts as not sorted.
    sent = sent_from(catalog)
    data = synced_file(catalog, sent)
    catalog.schedules[0].set_sorting([{"parameter": "DDM_Airflow"}])
    differences = schedule_differences(catalog, data)
    assert [d.kind for d in differences] == [INFORMATION]  # only the database changed it


def test_without_a_last_sync_it_is_a_plain_comparison():
    catalog = make_catalog()
    sent = sent_from(catalog)
    column(sent, "DDM_Airflow")["heading"] = "AIRFLOW (REVIT)"
    differences = schedule_differences(catalog, file_with(sent))
    assert [(d.kind, d.origin) for d in differences] == [(HEADING, "")]
