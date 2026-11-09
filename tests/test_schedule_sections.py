"""Schedule sections: standard blocks of columns that schedules link to."""
import pytest

from ddm_tables import catalog_from_tables, read_database_csv, write_database_csv
from revit_parameter_manager import Catalog

ELECTRICAL = ['Volts', 'Phase', 'Hertz', 'FLA', 'MCA']


@pytest.fixture
def catalog():
	catalog = Catalog()
	for name in ELECTRICAL + ['Tag', 'Flow', 'Notes', 'Height', 'Width', 'Linker']:
		catalog.add_param(name, 'Text', header_text=name.upper())
	return catalog


@pytest.fixture
def electrical(catalog):
	return catalog.add_section('Electrical', ELECTRICAL, caption='ELEC DATA')


def columns(schedule):
	return [param.name for param in schedule.params]


def groups(schedule):
	return {group['caption']: group['parameter_names'] for group in schedule.header_groups}


# --- defining ------------------------------------------------------------

def test_a_section_needs_a_name_columns_and_known_parameters(catalog):
	with pytest.raises(ValueError, match='name is required'):
		catalog.add_section(' ', ELECTRICAL)
	with pytest.raises(ValueError, match='at least one'):
		catalog.add_section('Empty', [])
	with pytest.raises(ValueError, match='Unknown parameter'):
		catalog.add_section('Bad', ['Nope'])
	with pytest.raises(ValueError, match='twice'):
		catalog.add_section('Twice', ['Volts', 'Volts'])
	with pytest.raises(ValueError, match="doesn't list"):
		catalog.add_section('Stray', ['Volts'], hidden_parameter_names=['Phase'])


def test_section_names_are_unique(catalog, electrical):
	with pytest.raises(ValueError, match='already exists'):
		catalog.add_section('Electrical', ['Tag'])
	other = catalog.add_section('Other', ['Tag'])
	with pytest.raises(ValueError, match='already exists'):
		other.name = 'Electrical'


# --- applying ------------------------------------------------------------

def test_applying_adds_the_columns_at_the_end_with_a_header_group(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag', 'Flow'])
	schedule.apply_section(electrical)
	assert columns(schedule) == ['Tag', 'Flow'] + ELECTRICAL
	assert groups(schedule) == {'ELEC DATA': ELECTRICAL}
	assert schedule.status == 'Ready'


def test_applying_gathers_existing_columns_at_the_first_ones_place_in_section_order(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag', 'Hertz', 'Flow', 'Phase', 'Volts', 'Notes'])
	change = schedule.plan_section(electrical)
	assert change.added == ['FLA', 'MCA']
	assert set(change.moved) == {'Volts', 'Phase', 'Hertz'}
	assert columns(schedule) == ['Tag', 'Hertz', 'Flow', 'Phase', 'Volts', 'Notes'], 'planning changes nothing'
	schedule.apply_section_change(change)
	assert columns(schedule) == ['Tag'] + ELECTRICAL + ['Flow', 'Notes']


def test_excluded_columns_stay_out(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag'])
	schedule.apply_section(electrical, excluded=['MCA'])
	assert columns(schedule) == ['Tag', 'Volts', 'Phase', 'Hertz', 'FLA']
	assert schedule.section_uses[0]['excluded'] == ['MCA']


def test_a_section_can_go_after_a_chosen_column(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag', 'Notes'])
	schedule.apply_section(electrical, after='Tag')
	assert columns(schedule) == ['Tag'] + ELECTRICAL + ['Notes']


def test_applying_twice_changes_nothing(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag'])
	schedule.apply_section(electrical)
	assert not schedule.plan_section(electrical).changes_anything
	schedule.apply_section(electrical)
	assert len(schedule.header_groups) == 1


def test_section_sets_which_columns_are_hidden(catalog):
	admin = catalog.add_section('Admin', ['Linker', 'Notes'], hidden_parameter_names=['Linker'])
	schedule = catalog.add_schedule('Fan', field_names=['Tag', 'Notes'], hidden_field_names=['Notes'])
	change = schedule.plan_section(admin)
	assert change.hidden_now == ['Linker']
	assert change.shown_now == ['Notes']
	schedule.apply_section_change(change)
	assert schedule.hidden_field_names == {'Linker'}


def test_section_without_a_caption_makes_no_header_group(catalog):
	admin = catalog.add_section('Admin', ['Linker'])
	schedule = catalog.add_schedule('Fan', field_names=['Tag'])
	schedule.apply_section(admin)
	assert schedule.header_groups == []


def test_a_parameter_can_only_be_in_one_section_per_schedule(catalog, electrical):
	other = catalog.add_section('Other', ['Volts', 'Tag'])
	schedule = catalog.add_schedule('Fan', field_names=['Flow'])
	schedule.apply_section(electrical)
	with pytest.raises(ValueError, match="already has Volts in section 'Electrical'"):
		schedule.plan_section(other)
	schedule.apply_section(other, excluded=['Volts'])
	assert 'Tag' in columns(schedule)


def test_a_section_can_leave_no_columns(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag'])
	with pytest.raises(ValueError, match='no columns'):
		schedule.plan_section(electrical, excluded=ELECTRICAL)


# --- existing header groups ----------------------------------------------

def test_group_inside_the_block_is_replaced(catalog, electrical):
	schedule = catalog.add_schedule(
		'Fan', field_names=['Tag', 'Volts', 'Phase'],
		header_groups=[{'caption': 'OLD ELEC', 'parameter_names': ['Volts', 'Phase']}])
	change = schedule.plan_section(electrical)
	assert change.replaced == ['OLD ELEC']
	schedule.apply_section_change(change)
	assert groups(schedule) == {'ELEC DATA': ELECTRICAL}


def test_group_partly_inside_the_block_loses_those_columns(catalog, electrical):
	schedule = catalog.add_schedule(
		'Fan', field_names=['Tag', 'Notes', 'Volts'],
		header_groups=[{'caption': 'NOTES', 'parameter_names': ['Notes', 'Volts']}])
	change = schedule.plan_section(electrical)
	assert change.trimmed == ['NOTES']
	schedule.apply_section_change(change)
	assert groups(schedule)['NOTES'] == ['Notes']


def test_group_the_block_would_split_is_dropped(catalog, electrical):
	schedule = catalog.add_schedule(
		'Fan', field_names=['Tag', 'Volts', 'Notes'],
		header_groups=[{'caption': 'MIXED', 'parameter_names': ['Tag', 'Volts', 'Notes']}])
	change = schedule.plan_section(electrical)
	assert change.dropped == ['MIXED']
	schedule.apply_section_change(change)
	assert 'MIXED' not in groups(schedule)


def test_unrelated_group_is_left_alone(catalog, electrical):
	schedule = catalog.add_schedule(
		'Fan', field_names=['Tag', 'Flow'],
		header_groups=[{'caption': 'AIR', 'parameter_names': ['Tag', 'Flow']}])
	schedule.apply_section(electrical)
	assert groups(schedule)['AIR'] == ['Tag', 'Flow']


# --- local headers -------------------------------------------------------

def test_local_headers_are_reported_kept_and_can_be_cleared(catalog, electrical):
	schedule = catalog.add_schedule(
		'Tower', field_names=['Volts', 'Hertz', 'Phase'],
		header_text_overrides={'Hertz': 'PHASE', 'Phase': 'HERTZ', 'Volts': 'VOLTS'})
	change = schedule.plan_section(electrical)
	assert change.local_headers == [('Phase', 'HERTZ', 'PHASE'), ('Hertz', 'PHASE', 'HERTZ')]
	schedule.apply_section_change(change, clear_headers=['Hertz'])
	assert 'Hertz' not in schedule.header_text_overrides
	assert schedule.header_text_overrides['Phase'] == 'HERTZ'


# --- editing a schedule that uses a section -------------------------------

def test_a_section_moves_only_as_a_whole(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag', 'Flow'])
	schedule.apply_section(electrical)
	with pytest.raises(ValueError, match='Section'):
		schedule.move_columns(['Phase'], -1)
	with pytest.raises(ValueError, match='Section'):
		schedule.move_columns(['Flow'], 1)
	assert schedule.move_columns(ELECTRICAL, -1)
	assert columns(schedule) == ['Tag'] + ELECTRICAL + ['Flow']


def test_removing_a_column_excludes_it_and_keeps_the_group_on_the_rest(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag'])
	schedule.apply_section(electrical)
	schedule.remove_columns(['Phase'])
	assert schedule.section_uses[0]['excluded'] == ['Phase']
	assert groups(schedule) == {'ELEC DATA': ['Volts', 'Hertz', 'FLA', 'MCA']}
	assert schedule.status == 'Ready'


def test_adding_an_excluded_column_puts_it_back_in_section_order(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag', 'Flow'])
	schedule.apply_section(electrical, excluded=['Phase'], after='Tag')
	schedule.add_columns(['Phase'], after='Flow')
	assert columns(schedule) == ['Tag'] + ELECTRICAL + ['Flow']
	assert schedule.section_uses[0]['excluded'] == []
	assert groups(schedule) == {'ELEC DATA': ELECTRICAL}


def test_a_new_column_cant_land_inside_a_section(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag'])
	schedule.apply_section(electrical)
	with pytest.raises(ValueError, match='Section'):
		schedule.add_columns(['Notes'], after='Phase')
	schedule.add_columns(['Notes'], after='MCA')
	assert columns(schedule)[-1] == 'Notes'


def test_removing_every_column_ends_the_use(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag'])
	schedule.apply_section(electrical, excluded=['FLA', 'MCA', 'Hertz'])
	schedule.remove_columns(['Volts', 'Phase'])
	assert schedule.section_uses == []
	assert schedule.header_groups == []


def test_columns_put_out_of_order_elsewhere_show_on_the_schedule(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag'])
	schedule.apply_section(electrical)
	schedule.set_field_names(['Phase', 'Tag', 'Volts', 'Hertz', 'FLA', 'MCA'])
	assert schedule.status == 'Error'
	assert 'Electrical' in schedule.validation_message
	schedule.apply_section(electrical)
	assert schedule.status == 'Ready'
	assert columns(schedule) == ELECTRICAL + ['Tag']


def test_detach_keeps_the_columns_and_remove_takes_them(catalog, electrical):
	kept = catalog.add_schedule('Kept', field_names=['Tag'])
	gone = catalog.add_schedule('Gone', field_names=['Tag'], header_text_overrides={'Volts': 'V'})
	kept.apply_section(electrical)
	gone.apply_section(electrical)
	kept.detach_section(electrical)
	gone.remove_section(electrical)
	assert columns(kept) == ['Tag'] + ELECTRICAL
	assert kept.section_uses == []
	assert 'section_guid' not in kept.header_groups[0]
	assert columns(gone) == ['Tag']
	assert gone.section_uses == [] and gone.header_groups == []
	assert 'Volts' not in gone.header_text_overrides


# --- changing a section --------------------------------------------------

def test_changing_a_section_changes_every_schedule_using_it(catalog, electrical):
	fan = catalog.add_schedule('Fan', field_names=['Tag'])
	pump = catalog.add_schedule('Pump', field_names=['Flow'])
	other = catalog.add_schedule('Other', field_names=['Notes'])
	fan.apply_section(electrical)
	pump.apply_section(electrical, excluded=['MCA'])
	catalog.update_section(
		electrical, caption='ELECTRICAL', parameter_names=['Phase', 'Volts', 'FLA', 'MCA', 'Notes'],
		hidden_parameter_names=['Notes'])
	assert columns(fan) == ['Tag', 'Phase', 'Volts', 'FLA', 'MCA', 'Notes']
	assert groups(fan) == {'ELECTRICAL': ['Phase', 'Volts', 'FLA', 'MCA', 'Notes']}
	assert fan.hidden_field_names == {'Notes'}
	assert columns(pump) == ['Flow', 'Phase', 'Volts', 'FLA', 'Notes'], 'keeps leaving out MCA'
	assert columns(other) == ['Notes']
	assert fan.status == 'Ready' and pump.status == 'Ready'


def test_previewing_a_change_changes_nothing(catalog, electrical):
	fan = catalog.add_schedule('Fan', field_names=['Tag'])
	fan.apply_section(electrical)
	proposed = electrical.edited(parameter_names=['Volts', 'Phase'])
	changes = catalog.plan_section_update(electrical, proposed)
	assert [change.removed for change in changes] == [['Hertz', 'FLA', 'MCA']]
	assert electrical.parameter_names == ELECTRICAL
	assert columns(fan) == ['Tag'] + ELECTRICAL


def test_a_schedule_not_accepted_keeps_its_columns_and_stops_using_the_section(catalog, electrical):
	fan = catalog.add_schedule('Fan', field_names=['Tag'])
	pump = catalog.add_schedule('Pump', field_names=['Tag'])
	fan.apply_section(electrical)
	pump.apply_section(electrical)
	proposed = electrical.edited(parameter_names=['Volts'])
	changes = catalog.plan_section_update(electrical, proposed)
	catalog.commit_section_update(electrical, proposed, [change for change in changes if change.schedule is fan])
	assert columns(fan) == ['Tag', 'Volts']
	assert columns(pump) == ['Tag'] + ELECTRICAL
	assert catalog.schedules_using(electrical) == [fan]


def test_change_that_would_overlap_another_section_is_refused(catalog, electrical):
	other = catalog.add_section('Other', ['Tag'])
	fan = catalog.add_schedule('Fan', field_names=['Flow'])
	fan.apply_section(electrical)
	fan.apply_section(other)
	with pytest.raises(ValueError, match='already has Tag'):
		catalog.update_section(electrical, parameter_names=ELECTRICAL + ['Tag'])
	assert electrical.parameter_names == ELECTRICAL


def test_deleting_a_section_leaves_the_columns(catalog, electrical):
	fan = catalog.add_schedule('Fan', field_names=['Tag'])
	fan.apply_section(electrical)
	catalog.remove_section('Electrical')
	assert catalog.sections == []
	assert columns(fan) == ['Tag'] + ELECTRICAL
	assert fan.section_uses == []


# --- parameters ----------------------------------------------------------

def test_renaming_a_parameter_follows_through_sections(catalog):
	section = catalog.add_section('S', ['Volts', 'Phase', 'Hertz'], caption='C', hidden_parameter_names=['Phase'])
	fan = catalog.add_schedule('Fan', field_names=['Tag'])
	pump = catalog.add_schedule('Pump', field_names=['Tag'])
	fan.apply_section(section)
	pump.apply_section(section, excluded=['Volts'])
	catalog.rename_param('Phase', 'PH')
	catalog.rename_param('Volts', 'V')
	assert section.parameter_names == ['V', 'PH', 'Hertz']
	assert section.hidden_parameter_names == {'PH'}
	assert columns(fan) == ['Tag', 'V', 'PH', 'Hertz']
	assert groups(fan) == {'C': ['V', 'PH', 'Hertz']}
	assert pump.section_uses[0]['excluded'] == ['V']
	assert fan.status == 'Ready'


def test_removing_a_parameter_leaves_the_section_and_its_schedules(catalog):
	section = catalog.add_section('S', ['Volts', 'Phase'], caption='C')
	fan = catalog.add_schedule('Fan', field_names=['Tag'])
	fan.apply_section(section)
	catalog.remove_param('Phase')
	assert section.parameter_names == ['Volts']
	assert fan.section_uses[0]['excluded'] == []
	assert groups(fan) == {'C': ['Volts']}


def test_removing_a_sections_last_parameter_removes_the_section(catalog):
	section = catalog.add_section('S', ['Volts'], caption='C')
	fan = catalog.add_schedule('Fan', field_names=['Tag'])
	fan.apply_section(section)
	catalog.remove_param('Volts')
	assert catalog.sections == []
	assert fan.section_uses == [] and fan.header_groups == []


# --- saving --------------------------------------------------------------

def test_sections_survive_a_save_and_load(catalog, electrical, tmp_path):
	fan = catalog.add_schedule('Fan', field_names=['Tag'])
	fan.apply_section(electrical, excluded=['MCA'])
	loaded, _extra = Catalog.load(catalog.save(str(tmp_path / 'catalog.json')))
	section = loaded.get_section('Electrical')
	assert section.guid == electrical.guid
	assert section.caption == 'ELEC DATA'
	assert section.parameter_names == ELECTRICAL
	schedule = loaded.get_schedule('Fan')
	assert schedule.section_uses == [{'section_guid': electrical.guid, 'excluded': ['MCA']}]
	assert schedule.header_groups[0]['section_guid'] == electrical.guid
	assert loaded.to_dict() == catalog.to_dict()
	# Still linked: a change reaches it.
	loaded.update_section(section, parameter_names=['Volts'])
	assert columns(schedule) == ['Tag', 'Volts']


def test_a_catalog_without_sections_saves_as_before(catalog):
	catalog.add_schedule('Fan', field_names=['Tag'])
	data = catalog.to_dict()
	assert 'sections' not in data
	assert 'section_uses' not in data['schedules'][0]


def test_version_3_catalogs_still_load(catalog):
	catalog.add_schedule('Fan', field_names=['Tag'])
	data = catalog.to_dict()
	data['version'] = 3
	assert Catalog.from_dict(data).sections == []


def test_a_use_of_an_unknown_section_is_refused(catalog):
	catalog.add_schedule('Fan', field_names=['Tag'])
	data = catalog.to_dict()
	data['schedules'][0]['section_uses'] = [{'section_guid': 'missing', 'excluded': []}]
	with pytest.raises(ValueError, match='unknown section'):
		Catalog.from_dict(data)


def test_sections_survive_the_csv(catalog, electrical, tmp_path):
	admin = catalog.add_section('Admin', ['Linker', 'Notes'], hidden_parameter_names=['Linker'])
	fan = catalog.add_schedule('Fan', field_names=['Tag'])
	fan.apply_section(electrical, excluded=['MCA'])
	fan.apply_section(admin)
	path = str(tmp_path / 'database.csv')
	write_database_csv(catalog, path)
	tables, header_groups = read_database_csv(path)
	loaded, issues = catalog_from_tables(header_groups=header_groups, **tables)
	assert issues == []
	assert [section.to_dict() for section in loaded.sections] == [section.to_dict() for section in catalog.sections]
	schedule = loaded.get_schedule('Fan')
	assert schedule.section_uses == fan.section_uses
	assert schedule.header_groups == fan.header_groups
	assert schedule.hidden_field_names == {'Linker'}
	assert schedule.status == 'Ready'


def test_a_csv_use_of_a_missing_section_is_reported(catalog, electrical, tmp_path):
	fan = catalog.add_schedule('Fan', field_names=['Tag'])
	fan.apply_section(electrical)
	path = str(tmp_path / 'database.csv')
	write_database_csv(catalog, path)
	tables, header_groups = read_database_csv(path)
	tables['sections'] = None
	loaded, issues = catalog_from_tables(header_groups=header_groups, **tables)
	assert loaded.get_schedule('Fan').section_uses == []
	assert any('section' in issue for issue in issues)


# --- sections that include sections ---------------------------------------

@pytest.fixture
def motor(catalog, electrical):
	return catalog.add_section('Electric Motor', ['Height', {'section': electrical.guid}, 'Width'], caption='MOTOR DATA')


@pytest.fixture
def pump(catalog, motor):
	return catalog.add_section('Pump', ['Flow', {'section': motor.guid}])


def test_included_sections_expand_in_place(motor, pump):
	assert motor.parameter_names == ['Height'] + ELECTRICAL + ['Width']
	assert pump.parameter_names == ['Flow', 'Height'] + ELECTRICAL + ['Width']


def test_the_outermost_caption_wins(electrical, motor, pump):
	assert electrical.bands() == [('ELEC DATA', ELECTRICAL)]
	assert motor.bands() == [('MOTOR DATA', motor.parameter_names)]
	assert pump.bands() == [('MOTOR DATA', motor.parameter_names)], 'no caption, so the motor band still shows'


def test_a_section_without_a_caption_keeps_every_included_band(catalog, electrical):
	admin = catalog.add_section('Admin', ['Linker'], caption='ADMIN')
	both = catalog.add_section('Both', [{'section': electrical.guid}, 'Tag', {'section': admin.guid}])
	schedule = catalog.add_schedule('Fan', field_names=['Flow'])
	schedule.apply_section(both)
	assert groups(schedule) == {'ELEC DATA': ELECTRICAL, 'ADMIN': ['Linker']}
	schedule.remove_columns(['Phase'])
	assert groups(schedule)['ELEC DATA'] == ['Volts', 'Hertz', 'FLA', 'MCA']
	assert groups(schedule)['ADMIN'] == ['Linker']
	assert schedule.plan_section(both).changes_anything is False


def test_hidden_columns_come_from_each_level(catalog):
	inner = catalog.add_section('Inner', ['Linker', 'Notes'], hidden_parameter_names=['Linker'])
	outer = catalog.add_section('Outer', ['Tag', {'section': inner.guid}], hidden_parameter_names=['Tag'])
	assert outer.hidden_parameter_names == {'Tag', 'Linker'}


def test_a_schedule_using_the_top_section_gets_every_level(catalog, pump, motor):
	schedule = catalog.add_schedule('Pumps', field_names=['Tag'])
	schedule.apply_section(pump, excluded=['MCA'])
	assert columns(schedule) == ['Tag', 'Flow', 'Height', 'Volts', 'Phase', 'Hertz', 'FLA', 'Width']
	assert groups(schedule) == {'MOTOR DATA': ['Height', 'Volts', 'Phase', 'Hertz', 'FLA', 'Width']}
	assert schedule.status == 'Ready'


def test_loops_are_refused(catalog, electrical, motor, pump):
	with pytest.raises(ValueError, match='include itself'):
		catalog.update_section(electrical, parameter_names=['Volts', {'section': pump.guid}])
	assert electrical.parameter_names == ELECTRICAL
	with pytest.raises(ValueError, match='include itself'):
		catalog.plan_section_update(motor, motor.edited(members=[{'section': motor.guid}]))


def test_a_column_cant_be_listed_twice_through_an_include(catalog, electrical, motor):
	with pytest.raises(ValueError, match='twice: Volts'):
		catalog.add_section('Bad', ['Volts', {'section': electrical.guid}])
	with pytest.raises(ValueError, match='twice: Height'):
		catalog.update_section(electrical, parameter_names=ELECTRICAL + ['Height'])
	assert electrical.parameter_names == ELECTRICAL


def test_an_unknown_include_is_refused(catalog):
	with pytest.raises(ValueError, match="isn't in the database"):
		catalog.add_section('Bad', [{'section': 'missing'}])


def test_a_change_flows_up_through_every_level(catalog, electrical, motor, pump):
	direct = catalog.add_schedule('Direct', field_names=['Tag'])
	through_motor = catalog.add_schedule('Motors', field_names=['Tag'])
	through_pump = catalog.add_schedule('Pumps', field_names=['Tag'])
	other = catalog.add_schedule('Other', field_names=['Tag'])
	direct.apply_section(electrical)
	through_motor.apply_section(motor)
	through_pump.apply_section(pump, excluded=['MCA'])
	assert catalog.schedules_using(electrical) == [direct, through_motor, through_pump]

	proposed = electrical.edited(parameter_names=['Hertz', 'Volts', 'MCA', 'Linker'], caption='ELEC')
	changes = catalog.plan_section_update(electrical, proposed)
	assert [(change.schedule.name, change.section.name) for change in changes] == [
		('Direct', 'Electrical'), ('Motors', 'Electric Motor'), ('Pumps', 'Pump'),
	]
	assert columns(through_pump)[:3] == ['Tag', 'Flow', 'Height'], 'previewing changes nothing'
	assert electrical.parameter_names == ELECTRICAL

	catalog.commit_section_update(electrical, proposed, changes)
	assert columns(direct) == ['Tag', 'Hertz', 'Volts', 'MCA', 'Linker']
	assert groups(direct) == {'ELEC': ['Hertz', 'Volts', 'MCA', 'Linker']}
	assert columns(through_motor) == ['Tag', 'Height', 'Hertz', 'Volts', 'MCA', 'Linker', 'Width']
	assert groups(through_motor)['MOTOR DATA'][0] == 'Height'
	assert columns(through_pump) == ['Tag', 'Flow', 'Height', 'Hertz', 'Volts', 'Linker', 'Width'], 'still leaves out MCA'
	assert columns(other) == ['Tag']
	assert all(schedule.status == 'Ready' for schedule in (direct, through_motor, through_pump))


def test_a_schedule_not_accepted_stops_using_its_top_section_only(catalog, electrical, motor):
	direct = catalog.add_schedule('Direct', field_names=['Tag'])
	through = catalog.add_schedule('Motors', field_names=['Tag'])
	direct.apply_section(electrical)
	through.apply_section(motor)
	proposed = electrical.edited(parameter_names=['Volts'])
	changes = catalog.plan_section_update(electrical, proposed)
	catalog.commit_section_update(electrical, proposed, [change for change in changes if change.schedule is direct])
	assert through.section_uses == []
	assert columns(through) == ['Tag', 'Height'] + ELECTRICAL + ['Width']
	assert catalog.get_section('Electric Motor').parameter_names == ['Height', 'Volts', 'Width']
	assert columns(direct) == ['Tag', 'Volts']


def test_applying_a_section_takes_over_one_inside_it(catalog, electrical, motor):
	schedule = catalog.add_schedule('Fan', field_names=['Tag'])
	schedule.apply_section(electrical, excluded=['MCA'])
	change = schedule.plan_section(motor)
	assert change.absorbs == [electrical]
	assert 'MCA' not in change.block, 'keeps what it left out'
	schedule.apply_section_change(change)
	assert [use['section_guid'] for use in schedule.section_uses] == [motor.guid]
	assert groups(schedule) == {'MOTOR DATA': ['Height', 'Volts', 'Phase', 'Hertz', 'FLA', 'Width']}
	assert schedule.status == 'Ready'


def test_a_section_cant_be_added_under_one_already_using_it(catalog, electrical, motor):
	schedule = catalog.add_schedule('Fan', field_names=['Tag'])
	schedule.apply_section(motor)
	with pytest.raises(ValueError, match="already has .* in section 'Electric Motor'"):
		schedule.plan_section(electrical)


def test_a_sections_block_stays_together_at_every_level(catalog, pump):
	schedule = catalog.add_schedule('Pumps', field_names=['Tag'])
	schedule.apply_section(pump)
	with pytest.raises(ValueError, match='Section'):
		schedule.move_columns(['Volts'], 1)
	assert schedule.move_columns(pump.parameter_names, -1)
	assert columns(schedule) == pump.parameter_names + ['Tag']


def test_deleting_an_included_section_flattens_it_into_those_including_it(catalog, electrical, motor, pump):
	schedule = catalog.add_schedule('Pumps', field_names=['Tag'])
	schedule.apply_section(pump)
	before = columns(schedule)
	catalog.remove_section('Electrical')
	assert motor.members == ['Height'] + ELECTRICAL + ['Width']
	assert pump.parameter_names == before[1:]
	assert columns(schedule) == before
	assert schedule.status == 'Ready'
	assert catalog.schedules_using(pump) == [schedule]


def test_deleting_keeps_its_hidden_columns_hidden_above_it(catalog):
	inner = catalog.add_section('Inner', ['Linker'], hidden_parameter_names=['Linker'])
	outer = catalog.add_section('Outer', ['Tag', {'section': inner.guid}])
	catalog.remove_section('Inner')
	assert outer.hidden_parameter_names == {'Linker'}


def test_renaming_and_removing_a_parameter_reach_the_top_section(catalog, electrical, motor, pump):
	schedule = catalog.add_schedule('Pumps', field_names=['Tag'])
	schedule.apply_section(pump)
	catalog.rename_param('Volts', 'V')
	assert pump.parameter_names[2] == 'V'
	assert columns(schedule)[3] == 'V'
	catalog.remove_param('Phase')
	assert 'Phase' not in pump.parameter_names
	assert 'Phase' not in columns(schedule)
	assert groups(schedule)['MOTOR DATA'] == motor.parameter_names
	assert schedule.status == 'Ready'


def test_a_section_emptied_by_removing_parameters_leaves_those_including_it(catalog):
	inner = catalog.add_section('Inner', ['Linker'], caption='INNER')
	outer = catalog.add_section('Outer', ['Tag', {'section': inner.guid}])
	schedule = catalog.add_schedule('Fan', field_names=['Flow'])
	schedule.apply_section(outer)
	catalog.remove_param('Linker')
	assert catalog.get_section('Inner') is None
	assert outer.members == ['Tag']
	assert columns(schedule) == ['Flow', 'Tag']
	assert schedule.header_groups == []


def test_includes_survive_a_save_and_load_in_any_order(catalog, electrical, motor, pump, tmp_path):
	schedule = catalog.add_schedule('Pumps', field_names=['Tag'])
	schedule.apply_section(pump, excluded=['MCA'])
	data = catalog.to_dict()
	data['sections'].reverse()
	loaded = Catalog.from_dict(data)
	assert loaded.get_section('Pump').parameter_names == pump.parameter_names
	assert loaded.get_schedule('Pumps').status == 'Ready'
	loaded.update_section(loaded.get_section('Electrical'), parameter_names=['Volts'])
	assert columns(loaded.get_schedule('Pumps')) == ['Tag', 'Flow', 'Height', 'Volts', 'Width']


def test_includes_survive_the_csv_in_any_order(catalog, electrical, motor, pump, tmp_path):
	schedule = catalog.add_schedule('Pumps', field_names=['Tag'])
	schedule.apply_section(pump, excluded=['MCA'])
	catalog.sections.reverse()
	path = str(tmp_path / 'database.csv')
	write_database_csv(catalog, path)
	tables, header_groups = read_database_csv(path)
	loaded, issues = catalog_from_tables(header_groups=header_groups, **tables)
	assert issues == []
	assert loaded.get_section('Pump').parameter_names == pump.parameter_names
	assert loaded.get_schedule('Pumps').header_groups == schedule.header_groups


def test_a_csv_section_including_a_skipped_one_is_reported_too(catalog, electrical, motor, tmp_path):
	path = str(tmp_path / 'database.csv')
	write_database_csv(catalog, path)
	tables, header_groups = read_database_csv(path)
	tables['sections'] = tables['sections'][tables['sections']['name'] != 'Electrical']
	loaded, issues = catalog_from_tables(header_groups=header_groups, **tables)
	assert loaded.sections == []
	assert any('Electric Motor' in issue for issue in issues)


def test_files_written_before_includes_still_load(catalog):
	data = catalog.to_dict()
	data['sections'] = [{'name': 'Old', 'guid': 'g1', 'caption': 'C', 'parameter_names': ['Volts'], 'hidden_parameter_names': []}]
	assert Catalog.from_dict(data).get_section('Old').parameter_names == ['Volts']

# --- ungrouping in a schedule ------------------------------------------------

def test_ungroup_removes_the_innermost_group_around_the_selection(catalog):
	schedule = catalog.add_schedule('Fan', field_names=['Tag', 'Flow', 'Height', 'Width'])
	schedule.add_header_group('ALL', ['Tag', 'Flow', 'Height', 'Width'])
	schedule.add_header_group('SIZE', ['Height', 'Width'])
	assert schedule.remove_header_group(['Width'])['caption'] == 'SIZE'
	assert groups(schedule) == {'ALL': ['Tag', 'Flow', 'Height', 'Width']}
	with pytest.raises(ValueError, match='Select a header'):
		schedule.remove_header_group([])
	schedule.remove_header_group(['Tag'])
	with pytest.raises(ValueError, match='No header group'):
		schedule.remove_header_group(['Tag'])


def test_ungroup_refuses_a_group_from_a_section(catalog, electrical):
	schedule = catalog.add_schedule('Fan', field_names=['Tag'])
	schedule.apply_section(electrical)
	with pytest.raises(ValueError, match="section 'Electrical'"):
		schedule.remove_header_group(['Volts'])
	assert groups(schedule) == {'ELEC DATA': ELECTRICAL}
