"""The Sections tab, its windows and the Schedule Builder's Add Section."""
import tkinter as tk

import pytest

import ddm_gui as gui_module
from ddm_gui import DDMGUI
from revit_schedule_macro_generator import generate_schedule_macro_source

ELECTRICAL = ['Volts', 'Phase', 'Hertz']


@pytest.fixture
def app(tmp_path, monkeypatch):
	monkeypatch.setattr(gui_module, 'DEFAULT_CHECKPOINT_PATH', tmp_path / 'missing' / 'database.ddm.json')
	root = tk.Tk()
	root.withdraw()
	gui = DDMGUI(root)
	catalog = gui.catalog
	for name in ELECTRICAL + ['Tag', 'Flow', 'Linker']:
		catalog.add_param(name, 'Text', header_text=name.upper())
	catalog.add_schedule('Fan', field_names=['Tag', 'Hertz', 'Volts'])
	catalog.add_schedule('Pump', field_names=['Tag', 'Volts'])
	catalog.add_schedule('Tank', field_names=['Tag'])
	yield gui
	root.destroy()


def columns(gui, name):
	return [param.name for param in gui.catalog.get_schedule(name).params]


def define(gui, picked, name='Electrical', caption='ELEC DATA', names=ELECTRICAL, section=None):
	window = gui.open_section_window(section)
	window.name_var.set(name)
	window.caption_var.set(caption)
	window.names[:] = names
	window.render_columns()
	for schedule_name, var in window.schedule_vars.items():
		var.set(schedule_name in picked)
	return window


def accept(preview, *schedules):
	for row, var in preview.accepted_vars:
		var.set(row.schedule.name in schedules)
	preview.apply()


def test_the_sections_tab_lists_sections(app):
	section = app.catalog.add_section('Electrical', ELECTRICAL, caption='ELEC DATA')
	app.catalog.get_schedule('Fan').apply_section(section)
	app.validate_all()
	tree = app.section_tree
	assert app.notebook.tab(app.sections_tab, 'text') == 'Schedule Sections'
	values = tree.item(tree.get_children()[0], 'values')
	assert list(values) == ['Electrical', 'ELEC DATA', '', '3', '1']


def test_preview_changes_nothing_until_applied_and_only_accepted_schedules_change(app):
	window = define(app, {'Fan', 'Pump'})
	preview = window.preview()
	assert app.catalog.get_section('Electrical') is None
	assert columns(app, 'Fan') == ['Tag', 'Hertz', 'Volts']
	assert [row.schedule.name for row, _var in preview.accepted_vars] == ['Fan', 'Pump']

	accept(preview, 'Fan')
	section = app.catalog.get_section('Electrical')
	assert columns(app, 'Fan') == ['Tag', 'Volts', 'Hertz'], 'only the columns it already had'
	assert columns(app, 'Pump') == ['Tag', 'Volts']
	assert app.catalog.schedules_using(section) == [app.catalog.get_schedule('Fan')]
	assert app.catalog.get_schedule('Fan').section_uses[0]['excluded'] == ['Phase']
	assert not window.winfo_exists()


def test_adding_every_column_when_asked(app):
	window = define(app, {'Pump'})
	window.only_existing_var.set(False)
	accept(window.preview(), 'Pump')
	assert columns(app, 'Pump') == ['Tag'] + ELECTRICAL


def test_a_schedule_with_none_of_the_columns_gets_them_all(app):
	window = define(app, {'Tank'})
	accept(window.preview(), 'Tank')
	assert columns(app, 'Tank') == ['Tag'] + ELECTRICAL


def test_a_section_with_no_schedules_saves_without_a_preview(app):
	window = define(app, set())
	assert window.preview() is None
	assert app.catalog.get_section('Electrical') is not None
	assert not window.winfo_exists()


def test_bad_definitions_are_refused_with_a_message(app, monkeypatch):
	warnings = []
	monkeypatch.setattr(gui_module.messagebox, 'showwarning', lambda _title, text, **_kw: warnings.append(text))
	window = define(app, set(), names=[])
	assert window.preview() is None
	assert 'at least one' in warnings[-1]
	assert window.winfo_exists()


def test_clearing_a_swapped_local_header_from_the_preview(app):
	schedule = app.catalog.get_schedule('Fan')
	schedule.override_header_text('Hertz', 'PHASE')
	schedule.override_header_text('Volts', 'VOLTAGE')
	window = define(app, {'Fan'})
	preview = window.preview()
	assert [name for _row, name, _var in preview.header_vars] == ['Volts', 'Hertz']
	next(var for _row, name, var in preview.header_vars if name == 'Hertz').set(True)
	accept(preview, 'Fan')
	assert 'Hertz' not in schedule.header_text_overrides
	assert schedule.header_text_overrides['Volts'] == 'VOLTAGE'


def test_editing_a_section_previews_its_schedules_and_unaccepted_ones_stop_using_it(app):
	section = app.catalog.add_section('Electrical', ELECTRICAL, caption='ELEC DATA')
	fan, pump = app.catalog.get_schedule('Fan'), app.catalog.get_schedule('Pump')
	fan.apply_section(section)
	pump.apply_section(section)
	window = define(app, {'Fan', 'Pump'}, section=section, names=['Volts', 'Phase'])
	preview = window.preview()
	assert all(row.kind == 'update' for row, _var in preview.accepted_vars)
	accept(preview, 'Fan')
	assert section.parameter_names == ['Volts', 'Phase']
	assert columns(app, 'Fan') == ['Tag', 'Volts', 'Phase']
	assert columns(app, 'Pump') == ['Tag'] + ELECTRICAL
	assert app.catalog.schedules_using(section) == [fan]


def test_unticking_a_schedule_stops_it_using_the_section_and_keeps_its_columns(app):
	section = app.catalog.add_section('Electrical', ELECTRICAL)
	fan = app.catalog.get_schedule('Fan')
	fan.apply_section(section)
	window = define(app, set(), section=section, caption='')
	preview = window.preview()
	assert [row.kind for row, _var in preview.accepted_vars] == ['stop']
	preview.apply()
	assert fan.section_uses == []
	assert columns(app, 'Fan') == ['Tag'] + ELECTRICAL


def test_a_schedule_with_nothing_to_change_stays_linked_without_a_row(app):
	section = app.catalog.add_section('Electrical', ELECTRICAL)
	fan = app.catalog.get_schedule('Fan')
	fan.apply_section(section)
	window = define(app, {'Fan', 'Pump'}, section=section, caption='')
	preview = window.preview()
	assert [row.schedule.name for row, _var in preview.accepted_vars] == ['Pump']
	preview.apply()
	assert app.catalog.schedules_using(section) == [fan, app.catalog.get_schedule('Pump')]


def test_a_schedule_it_cant_be_added_to_is_listed_not_offered(app):
	other = app.catalog.add_section('Other', ['Volts'])
	app.catalog.get_schedule('Pump').apply_section(other)
	window = define(app, {'Pump', 'Fan'})
	preview = window.preview()
	assert [row.schedule.name for row, _var in preview.accepted_vars] == ['Fan']
	assert 'Pump' in preview.problems[0]


def test_reordering_hiding_and_deleting_in_the_section_window(app, monkeypatch):
	monkeypatch.setattr(gui_module.messagebox, 'askyesno', lambda *_args, **_kw: True)
	section = app.catalog.add_section('Electrical', ELECTRICAL)
	fan = app.catalog.get_schedule('Fan')
	fan.apply_section(section)
	window = app.open_section_window(section)
	window.select(['Hertz'])
	window.move(-1)
	assert window.names == ['Volts', 'Hertz', 'Phase']
	window.toggle_hidden()
	assert window.hidden == {'Hertz'}
	window.delete()
	assert app.catalog.sections == []
	assert fan.section_uses == []


def test_add_parameters_offers_only_those_not_in_the_section(app):
	window = define(app, set(), names=['Volts'])
	picker = window.add_parameters()
	assert 'Volts' not in picker.listbox.get(0, 'end')
	assert 'Phase' in picker.listbox.get(0, 'end')
	picker.destroy()


def test_schedule_builder_adds_a_section(app):
	section = app.catalog.add_section('Electrical', ELECTRICAL, caption='ELEC DATA')
	tank = app.catalog.get_schedule('Tank')
	calls = []
	bar = app._build_schedule_edit_buttons(app.root, tank, lambda: None, lambda: calls.append(True))
	picker = bar.add_section()
	assert list(picker.listbox.get(0, 'end')) == ['Electrical']
	picker.listbox.selection_set(0)
	picker.add()
	preview = app.root.preview_window
	assert columns(app, 'Tank') == ['Tag']
	preview.apply()
	assert columns(app, 'Tank') == ['Tag'] + ELECTRICAL
	assert calls == [True]
	assert app.catalog.schedules_using(section) == [tank]


def test_schedule_builder_says_which_sections_are_used_and_explains_a_refused_column(app, monkeypatch):
	warnings = []
	monkeypatch.setattr(gui_module.messagebox, 'showwarning', lambda _title, text, **_kw: warnings.append(text))
	section = app.catalog.add_section('Electrical', ELECTRICAL)
	tank = app.catalog.get_schedule('Tank')
	tank.apply_section(section)

	class Table:
		@staticmethod
		def get_selected_parameter_names():
			return ['Volts']

	bar = app._build_schedule_edit_buttons(app.root, tank, Table, lambda: None)
	labels = [child.cget('text') for child in bar.winfo_children() if child.winfo_class() == 'TLabel']
	assert labels == ['Sections: Electrical']
	picker = bar.add_parameters()
	picker.search_var.set('Flow')
	picker.listbox.selection_set(0)
	picker.add()
	assert 'Section' in warnings[-1]
	assert 'Flow' not in columns(app, 'Tank')


def test_sections_reach_the_macro_and_a_database_without_them_is_unchanged(app):
	catalog = app.catalog
	before = generate_schedule_macro_source(catalog)
	section = catalog.add_section('Electrical', ELECTRICAL, caption='ELEC DATA', hidden_parameter_names=['Hertz'])
	assert generate_schedule_macro_source(catalog) == before, 'defining a section changes nothing yet'
	tank = catalog.get_schedule('Tank')
	tank.apply_section(section)
	source = generate_schedule_macro_source(catalog)
	assert source != before
	assert 'ELEC DATA' in source

	# The macro only sees ordinary columns, so a hand-made equal schedule generates the same code.
	catalog.remove_section('Electrical')
	assert generate_schedule_macro_source(catalog) == source


# --- sections that include sections ---------------------------------------

@pytest.fixture
def hierarchy(app):
	electrical = app.catalog.add_section('Electrical Data', ELECTRICAL, caption='ELEC DATA')
	motor = app.catalog.add_section('Electric Motor', ['Flow', {'section': electrical.guid}], caption='MOTOR DATA')
	return electrical, motor


def test_the_tab_and_window_show_an_included_section_as_one_row(app, hierarchy):
	electrical, motor = hierarchy
	app.validate_all()
	tree = app.section_tree
	row = next(item for item in tree.get_children() if tree.item(item, 'values')[0] == 'Electric Motor')
	assert list(tree.item(row, 'values')) == ['Electric Motor', 'MOTOR DATA', 'Electrical Data', '4', '0']
	window = app.open_section_window(motor)
	table = window.table()
	assert table.parameter_names == ['Flow'] + ELECTRICAL
	included_from = table.rows[0]
	assert included_from['label'] == 'Included From'
	assert [cell['text'] for cell in included_from['cells']] == [''] + ['Electrical Data'] * 3
	# The outermost caption wins, as in a schedule using it.
	assert [group['caption'] for group in table.groups] == ['MOTOR DATA']
	window.select(['Phase'])
	window.move(-1)
	assert window.names == [{'section': electrical.guid}, 'Flow'], 'an included section moves as one'


def test_a_new_section_can_include_another_from_the_window(app, hierarchy):
	_electrical, motor = hierarchy
	window = define(app, {'Tank'}, name='Pump', caption='', names=['Linker'])
	picker = window.add_section()
	assert 'Electric Motor' in picker.listbox.get(0, 'end')
	picker.listbox.selection_set(list(picker.listbox.get(0, 'end')).index('Electric Motor'))
	picker.add()
	assert window.names == ['Linker', {'section': motor.guid}]
	window.only_existing_var.set(False)
	accept(window.preview(), 'Tank')
	section = app.catalog.get_section('Pump')
	assert section.parameter_names == ['Linker', 'Flow'] + ELECTRICAL
	assert columns(app, 'Tank') == ['Tag', 'Linker', 'Flow'] + ELECTRICAL
	assert {group['caption'] for group in app.catalog.get_schedule('Tank').header_groups} == {'MOTOR DATA'}


def test_the_picker_wont_offer_a_section_that_would_make_a_loop(app, hierarchy):
	electrical, _motor = hierarchy
	picker = app.open_section_window(electrical).add_section()
	assert 'Electric Motor' not in picker.listbox.get(0, 'end')
	assert 'Electrical Data' not in picker.listbox.get(0, 'end')


def test_editing_an_included_section_previews_the_schedules_above_it(app, hierarchy):
	electrical, motor = hierarchy
	tank = app.catalog.get_schedule('Tank')
	tank.apply_section(motor)
	window = app.open_section_window(electrical)
	assert window.schedule_vars['Tank'].get()
	window.names[:] = ['Volts', 'Hertz']
	preview = window.preview()
	assert [(row.schedule.name, row.kind, row.through) for row, _var in preview.accepted_vars] == [('Tank', 'update', True)]
	assert columns(app, 'Tank') == ['Tag', 'Flow'] + ELECTRICAL, 'nothing yet'
	preview.apply()
	assert columns(app, 'Tank') == ['Tag', 'Flow', 'Volts', 'Hertz']
	assert motor.parameter_names == ['Flow', 'Volts', 'Hertz']


def test_not_accepting_an_edit_stops_the_schedule_using_the_top_section(app, hierarchy):
	electrical, motor = hierarchy
	tank = app.catalog.get_schedule('Tank')
	tank.apply_section(motor)
	window = app.open_section_window(electrical)
	window.names[:] = ['Volts']
	accept(window.preview())
	assert tank.section_uses == []
	assert columns(app, 'Tank') == ['Tag', 'Flow'] + ELECTRICAL
	assert electrical.parameter_names == ['Volts']


def test_adding_a_section_can_take_over_one_inside_it_from_the_builder(app, hierarchy):
	electrical, motor = hierarchy
	tank = app.catalog.get_schedule('Tank')
	tank.apply_section(electrical)
	bar = app._build_schedule_edit_buttons(app.root, tank, lambda: None, lambda: None)
	picker = bar.add_section()
	assert list(picker.listbox.get(0, 'end')) == ['Electric Motor']
	picker.listbox.selection_set(0)
	picker.add()
	app.root.preview_window.apply()
	assert [use['section_guid'] for use in tank.section_uses] == [motor.guid]
	assert [group['caption'] for group in tank.header_groups] == ['MOTOR DATA']


# --- header groups in the section window -----------------------------------


def test_the_section_window_looks_like_the_schedule_builder(app):
	section = app.catalog.add_section('Electrical', ELECTRICAL, caption='ELEC DATA', hidden_parameter_names=['Hertz'])
	window = app.open_section_window(section)
	table = window.table()
	assert table.header_label == 'Section'
	assert table.header_texts == {'Volts': 'VOLTS', 'Phase': 'PHASE', 'Hertz': 'HERTZ'}
	assert table.hidden_names == {'Hertz'}
	labels = [row['label'] for row in table.rows]
	assert labels[:4] == ['Included From', 'Name', 'Default Header', 'Default Column Width (in)']
	assert not any(cell['editable'] for row in table.rows for cell in row['cells'])
	table.on_hidden_toggle('Volts')
	assert window.hidden == {'Hertz', 'Volts'}


def test_grouping_headers_in_a_section_reaches_its_schedules(app):
	section = app.catalog.add_section('Electrical', ELECTRICAL, caption='ELEC DATA')
	fan = app.catalog.get_schedule('Fan')
	fan.apply_section(section, excluded=[])
	window = app.open_section_window(section)
	window.select(['Phase', 'Hertz'])
	window.group_selected('POWER')
	assert window.header_groups == [{'caption': 'POWER', 'parameter_names': ['Phase', 'Hertz']}]
	assert [group['caption'] for group in window.table().groups] == ['ELEC DATA', 'POWER']
	accept(window.preview(), 'Fan')
	assert section.header_groups == [{'caption': 'POWER', 'parameter_names': ['Phase', 'Hertz']}]
	groups = {group['caption']: group['parameter_names'] for group in fan.header_groups}
	assert groups == {'ELEC DATA': ELECTRICAL, 'POWER': ['Phase', 'Hertz']}
	assert 'new DdmHeaderGroup("POWER", new[] { "Phase", "Hertz" }),' in generate_schedule_macro_source(app.catalog)


def test_ungrouping_takes_the_innermost_group_and_grouping_everything_sets_the_caption(app):
	section = app.catalog.add_section(
		'Electrical', ELECTRICAL, caption='ELEC DATA',
		header_groups=[{'caption': 'POWER', 'parameter_names': ['Phase', 'Hertz']}],
	)
	window = app.open_section_window(section)
	window.select(['Hertz'])
	window.ungroup_selected()
	assert window.header_groups == []
	window.select(['Hertz'])
	window.ungroup_selected()
	assert window.caption_var.get() == ''
	window.select(ELECTRICAL)
	window.group_selected('ELECTRICAL')
	assert window.caption_var.get() == 'ELECTRICAL' and window.header_groups == []


def test_a_header_group_must_nest_or_stay_apart(app, monkeypatch):
	warnings = []
	monkeypatch.setattr(gui_module.messagebox, 'showwarning', lambda _title, text, **_kw: warnings.append(text))
	section = app.catalog.add_section(
		'Electrical', ELECTRICAL, header_groups=[{'caption': 'A', 'parameter_names': ['Volts', 'Phase']}],
	)
	window = app.open_section_window(section)
	window.select(['Phase', 'Hertz'])
	window.group_selected('B')
	assert 'overlap' in warnings[-1]
	assert [group['caption'] for group in window.header_groups] == ['A']
	window.select(['Volts', 'Phase'])
	window.group_selected('C')
	assert 'same columns' in warnings[-1]


def test_header_groups_survive_saving_renames_and_removals(app, tmp_path):
	catalog = app.catalog
	section = catalog.add_section(
		'Electrical', ELECTRICAL, caption='ELEC DATA',
		header_groups=[{'caption': 'POWER', 'parameter_names': ['Phase', 'Hertz']}],
	)
	loaded, _extra = type(catalog).load(catalog.save(tmp_path / 'db.ddm.json'))
	assert loaded.get_section('Electrical').header_groups == section.header_groups
	from ddm_tables import catalog_from_tables, read_database_csv, write_database_csv
	write_database_csv(catalog, tmp_path / 'db.csv')
	tables, header_groups = read_database_csv(tmp_path / 'db.csv')
	from_csv, issues = catalog_from_tables(header_groups=header_groups, **tables)
	assert issues == [] and from_csv.get_section('Electrical').header_groups == section.header_groups
	catalog.rename_param('Phase', 'Phases')
	assert section.header_groups[0]['parameter_names'] == ['Phases', 'Hertz']
	catalog.remove_param('Hertz')
	assert section.header_groups[0]['parameter_names'] == ['Phases']
	catalog.remove_param('Phases')
	assert section.header_groups == []


def test_deleting_an_included_section_keeps_its_header_groups(app, hierarchy):
	electrical, _motor = hierarchy
	pump = app.catalog.add_section('Pump', ['Linker', {'section': electrical.guid}])
	app.catalog.remove_section('Electrical Data')
	assert pump.bands() == [('ELEC DATA', ELECTRICAL)]
