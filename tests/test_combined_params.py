"""Combined parameters: one schedule column joining several parameters, like Revit's."""
import json
import tkinter as tk

import pytest

import ddm_gui as gui_module
from ddm_gui import DDMGUI
from ddm_tables import catalog_from_tables, read_database_csv, write_database_csv
from revit_parameter_manager import Catalog
from revit_schedule_macro_generator import generate_schedule_macro_source, schedule_specs

TERMS = ['Term1', 'Term2', 'Term3', 'Term4', 'Term5']
TAG_PARTS = [
	{'parameter': 'Term1'}, {'parameter': 'Term2', 'prefix': '-'}, {'parameter': 'Term3'},
	{'parameter': 'Term4', 'prefix': '-'}, {'parameter': 'Term5'},
]


def make_catalog():
	catalog = Catalog()
	for name in TERMS + ['Flow']:
		catalog.add_param(name, 'Text')
	catalog.add_combined_param('TAG', TAG_PARTS)
	return catalog


def names(schedule):
	return [param.name for param in schedule.params]


# --- model ----------------------------------------------------------------------


def test_parts_keep_their_order_prefixes_and_spaces():
	catalog = make_catalog()
	tag = catalog.get_combined_param('TAG')
	assert tag.pattern() == '[Term1]-[Term2][Term3]-[Term4][Term5]'
	assert tag.sample({'Term1': 'AHU', 'Term2': '1', 'Term3': 'A', 'Term4': 'N', 'Term5': '2'}) == 'AHU-1A-N2'
	catalog.add_combined_param('Spaced', [{'parameter': 'Term1', 'separator': ' / '}, 'Term2'])
	assert catalog.get_combined_param('Spaced').pattern() == '[Term1] / [Term2]'


def test_a_combined_parameter_is_a_schedule_column():
	catalog = make_catalog()
	schedule = catalog.add_schedule('Equipment', field_names=TERMS)
	schedule.add_columns(['TAG'], after='Term1')
	assert names(schedule) == ['Term1', 'TAG', 'Term2', 'Term3', 'Term4', 'Term5']
	schedule.override_param('TAG', header_text='EQUIP TAG', grid_column_width=1.5)
	schedule.set_field_hidden('Term1', True)
	schedule.add_header_group('ID', ['Term1', 'TAG'])
	assert schedule.status == 'Ready', schedule.validation_message
	tag = next(param for param in schedule.params if param.name == 'TAG')
	assert (tag.header_text, tag.grid_column_width) == ('EQUIP TAG', 1.5)
	assert catalog.get_combined_param('TAG').header_text == 'TAG', 'the override stays in the schedule'


def test_it_isnt_a_parameter():
	catalog = make_catalog()
	assert catalog.get_param('TAG') is None
	assert 'TAG' not in catalog.param_names()
	assert 'TAG' not in json.dumps(catalog.to_dict()['params'])


def test_a_name_means_one_column():
	catalog = make_catalog()
	with pytest.raises(ValueError, match='combined parameter is already called'):
		catalog.add_param('TAG', 'Text')
	with pytest.raises(ValueError, match='already exists'):
		catalog.add_combined_param('Flow', ['Term1'])
	with pytest.raises(ValueError, match='Unknown parameter'):
		catalog.add_combined_param('Bad', ['Nope'])
	with pytest.raises(ValueError, match='at least one'):
		catalog.add_combined_param('Empty', [])


def test_renames_reach_parts_schedules_and_sections():
	catalog = make_catalog()
	schedule = catalog.add_schedule('Equipment', field_names=TERMS + ['TAG'])
	schedule.set_field_hidden('TAG', True)
	section = catalog.add_section('Tag', ['TAG', 'Term1'])
	catalog.rename_param('Term2', 'TermB')
	assert catalog.get_combined_param('TAG').parameter_names[1] == 'TermB'
	catalog.get_combined_param('TAG').name = 'EQUIP_TAG'
	assert 'EQUIP_TAG' in names(schedule) and 'EQUIP_TAG' in schedule.hidden_field_names
	assert section.members == ['EQUIP_TAG', 'Term1']


def test_deleting_it_takes_it_out_of_schedules_and_sections():
	catalog = make_catalog()
	schedule = catalog.add_schedule('Equipment', field_names=['Term1', 'TAG'])
	section = catalog.add_section('Tag', ['TAG', 'Term1'])
	catalog.remove_combined_param('TAG')
	assert names(schedule) == ['Term1']
	assert section.members == ['Term1']
	assert schedule.status == 'Ready'


def test_deleting_a_part_parameter_leaves_the_rest():
	catalog = make_catalog()
	catalog.remove_param('Term5')
	assert catalog.get_combined_param('TAG').parameter_names == TERMS[:4]
	for name in TERMS[:4]:
		catalog.remove_param(name)
	assert catalog.validate() == [('combined parameter', 'TAG', 'No parameters to combine.')]


def test_saving_and_loading_keeps_it(tmp_path):
	catalog = make_catalog()
	catalog.get_combined_param('TAG').header_text = 'EQUIP TAG'
	schedule = catalog.add_schedule('Equipment', field_names=TERMS + ['TAG'])
	catalog.add_section('Tag', ['TAG', 'Term1'], caption='ID')
	schedule.override_param('TAG', grid_column_width=2)
	loaded, _extra = Catalog.load(catalog.save(tmp_path / 'db.ddm.json'))
	assert loaded.to_dict() == catalog.to_dict()

	csv_path = tmp_path / 'db.csv'
	write_database_csv(catalog, csv_path)
	tables, header_groups = read_database_csv(csv_path)
	from_csv, issues = catalog_from_tables(header_groups=header_groups, **tables)
	assert issues == []
	assert from_csv.get_combined_param('TAG').to_dict() == catalog.get_combined_param('TAG').to_dict()
	assert names(from_csv.get_schedule('Equipment')) == names(schedule)


# --- sections -------------------------------------------------------------------


def test_a_section_can_list_it():
	catalog = make_catalog()
	section = catalog.add_section('Equipment Tag', ['TAG'] + TERMS, hidden_parameter_names=TERMS)
	schedule = catalog.add_schedule('Equipment', field_names=TERMS + ['Flow'])
	schedule.apply_section(section)
	assert names(schedule) == ['TAG'] + TERMS + ['Flow']
	assert schedule.hidden_field_names == set(TERMS)
	assert schedule.status == 'Ready'


def test_a_schedule_with_all_its_parts_has_it_by_default():
	catalog = make_catalog()
	assert catalog.column_present('TAG', set(TERMS))
	assert not catalog.column_present('TAG', set(TERMS[:4]))
	assert catalog.column_present('Flow', {'Flow'}) and not catalog.column_present('Flow', set())


# --- macro ----------------------------------------------------------------------


def test_the_macro_builds_a_combined_column():
	catalog = make_catalog()
	catalog.add_schedule('Equipment', field_names=['TAG', 'Flow'])
	specs, _notes = schedule_specs(catalog)
	assert specs[0]['columns'][0]['parts'][1] == {'parameter': 'Term2', 'prefix': '-', 'suffix': '', 'separator': ''}
	assert specs[0]['columns'][1]['parts'] == []
	source = generate_schedule_macro_source(catalog)
	assert (
		'new DdmColumn("TAG", "TAG", 0.0833333333333, false, new[] { new DdmPart("Term1", "", "", ""), '
		'new DdmPart("Term2", "-", "", ""),'
	) in source
	assert 'new DdmColumn("Flow", "Flow", 0.0833333333333, false),' in source
	assert 'definition.InsertCombinedParameterField(data, column.Parameter, definition.GetFieldCount())' in source


# --- GUI ------------------------------------------------------------------------


@pytest.fixture
def app(tmp_path, monkeypatch):
	monkeypatch.setattr(gui_module, 'DEFAULT_CHECKPOINT_PATH', tmp_path / 'missing' / 'database.ddm.json')
	root = tk.Tk()
	root.withdraw()
	gui = DDMGUI(root)
	for name in TERMS + ['Flow']:
		gui.catalog.add_param(name, 'Text')
	gui.catalog.add_schedule('Equipment', field_names=TERMS)
	yield gui
	root.destroy()


def test_the_window_adds_one(app):
	window = app.open_combined_window()
	window.name_var.set('TAG')
	window.parts[:] = [dict(part, prefix=part.get('prefix', ''), suffix='', separator='') for part in TAG_PARTS]
	window.render()
	assert window.pattern_var.get() == 'Pattern: [Term1]-[Term2][Term3]-[Term4][Term5]'
	window.tree.selection_set(['4'])
	window.update()
	window.edit_vars['prefix'].set('.')
	assert window.parts[4]['prefix'] == '.'
	window.save()
	tag = app.catalog.get_combined_param('TAG')
	assert tag.pattern() == '[Term1]-[Term2][Term3]-[Term4].[Term5]'
	tree = app.combined_tree
	assert app.notebook.tab(app.combined_tab, 'text') == 'Combined Parameters'
	assert list(tree.item(tree.get_children()[0], 'values'))[:3] == ['TAG', 'TAG', tag.pattern()]


def test_the_window_refuses_a_bad_edit_without_changing_anything(app, monkeypatch):
	app.catalog.add_combined_param('TAG', TAG_PARTS)
	warnings = []
	monkeypatch.setattr(gui_module.messagebox, 'showwarning', lambda *args, **kwargs: warnings.append(args))
	window = app.open_combined_window(app.catalog.get_combined_param('TAG'))
	window.name_var.set('Flow')
	window.parts[:] = window.parts[:2]
	assert window.save() is None
	assert warnings and app.catalog.get_combined_param('TAG').parameter_names == TERMS


def test_the_schedule_builder_offers_and_shows_it(app):
	catalog = app.catalog
	catalog.add_combined_param('TAG', TAG_PARTS)
	fam = catalog.add_family('AHU', TERMS)
	for name, value in zip(TERMS, ['AHU', '1', 'A', 'N', '2']):
		fam.override_param(name, value=value)
	schedule = catalog.get_schedule('Equipment')
	schedule.add_family(fam)
	schedule.add_columns(['TAG'])
	rows = app._schedule_table_rows(schedule)
	column = names(schedule).index('TAG')
	by_label = {row['label']: row for row in rows if row['section'] == 'Parameter' or not row.get('family')}
	assert by_label['Default Header']['cells'][column]['text'] == 'TAG'
	family_value = next(row for row in rows if row.get('family') == 'AHU' and row['attribute'] == 'value')
	assert family_value['cells'][column]['text'] == 'AHU-1A-N2'
	assert 'action' not in family_value['cells'][column], 'never "Add Parameter to Family"'
