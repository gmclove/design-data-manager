import json

import pytest

import formula
from revit_parameter_manager import (
	COMMON_PARAMS,
	Catalog,
	Fam,
	FamType,
	Param,
	guid_change_warning,
)


@pytest.fixture
def catalog():
	return Catalog()


def issues_for(formula_text, known=('Width', 'Height')):
	return formula.check_syntax(formula.tokenize(formula_text, set(known)))


# --- formula: reference scanning -----------------------------------------

def test_scan_matches_longest_known_name_first():
	known, unknown = formula.scan_references('Rough Width * 2 + Width', {'Width', 'Rough Width'})
	assert known == {'Rough Width', 'Width'}
	assert unknown == set()


def test_scan_ignores_functions_and_quoted_text():
	known, unknown = formula.scan_references('IF(Width > 1, "Big Thing", "small")', {'Width'})
	assert known == {'Width'}
	assert unknown == set()


def test_scan_reports_unknown_identifiers():
	_, unknown = formula.scan_references('Length * GhostParam', {'Length'})
	assert unknown == {'GhostParam'}


def test_known_name_wins_over_function_name():
	known, _ = formula.scan_references('Min * 2', {'Min'})
	assert known == {'Min'}


def test_rename_reference_only_touches_whole_references():
	names = {'Width', 'GlassWidth', 'Rough Width'}
	result = formula.rename_reference('GlassWidth + Rough Width + Width', 'Width', 'PanelWidth', names)
	assert result == 'GlassWidth + Rough Width + PanelWidth'


def test_rename_reference_leaves_quoted_text():
	result = formula.rename_reference('IF(Width > 1, "Width", "")', 'Width', 'W', {'Width'})
	assert result == 'IF(W > 1, "Width", "")'


# --- formula: tokenizer and syntax checks -------------------------------

def test_tokenize_kinds():
	tokens = formula.tokenize('IF(Rough Width > 1.5, "a", Ghost)', {'Rough Width'})
	assert [token.kind for token in tokens] == [
		formula.FUNCTION, formula.LPAREN, formula.PARAM, formula.OP, formula.NUMBER,
		formula.COMMA, formula.STRING, formula.COMMA, formula.NAME, formula.RPAREN,
	]


@pytest.mark.parametrize('text', [
	'Width * Height',
	'IF(Width > 1, "a", "b")',
	'PI()',
	'-Width + 2',
	'ROUND(Width / 2)',
	'NOT(Width < 2)',
	'(Width + Height) * 2',
])
def test_valid_formulas_have_no_syntax_issues(text):
	assert issues_for(text) == []


@pytest.mark.parametrize('text, expected', [
	('(Width', "Unclosed '('"),
	('Width)', "Unmatched ')'"),
	('Width +', 'ends with an operator'),
	('* Width', "Operator '*' is missing a value"),
	('Width Height', "Missing operator before 'Height'"),
	('MAX(Width, , 2)', "Missing value before ','"),
	('()', "Missing value before ')'"),
	('Width, 2', 'Comma outside a function call'),
	('"open', 'Unterminated text string'),
	('Width # 2', "Unexpected character '#'"),
])
def test_syntax_problems_are_reported(text, expected):
	issues = issues_for(text)
	assert len(issues) == 1, issues
	assert expected in issues[0]


@pytest.mark.parametrize('text', [
	'Width * 2 + 0\' 0 1/256"',
	'0\' 0 1/16"',
	'0\' 0"',
	'2\' 6" + 3/8" + 1 1/2"',
])
def test_feet_and_inch_lengths_are_numbers(text):
	assert issues_for(text) == []


def test_formulas_may_use_revit_builtin_length(catalog):
	catalog.add_param('Spacing', 'Length')
	param = catalog.add_param('Count', 'Integer', formula='Length / Spacing - 1').validate()
	assert param.status == 'Ready', param.validation_message


def test_param_validate_reports_syntax_errors(catalog):
	catalog.add_param('Width', 'Length')
	param = catalog.add_param('A', 'Length', formula='(Width * 2').validate()
	assert param.status == 'Error'
	assert "Unclosed '('" in param.validation_message


# --- catalog basics -------------------------------------------------------

def test_catalogs_are_isolated():
	first, second = Catalog(), Catalog()
	first.add_param('Width', 'Length')
	user = second.add_param('A', 'Length', formula='Width * 2').validate()
	assert user.status == 'Error'
	assert 'Width' in user.validation_message


def test_duplicate_names_rejected(catalog):
	catalog.add_param('Width', 'Length')
	with pytest.raises(ValueError):
		catalog.add_param('Width', 'Length')

	catalog.add_family('F', ['Width'])
	with pytest.raises(ValueError):
		catalog.add_family('F', ['Width'])

	catalog.add_schedule('S1')
	with pytest.raises(ValueError):
		catalog.add_schedule('S1')


def test_rename_to_existing_name_rejected(catalog):
	catalog.add_param('Width', 'Length')
	catalog.add_param('Height', 'Length')
	with pytest.raises(ValueError):
		catalog.rename_param('Width', 'Height')
	assert catalog.get_param('Width') is not None


def test_families_share_catalog_param_definitions(catalog):
	catalog.add_param('Width', 'Length')
	first = catalog.add_family('F1', ['Width'])
	second = catalog.add_family('F2', ['Width'])

	first.rename_param('Width', 'PanelWidth', keep_guid=True)

	assert 'PanelWidth' in {param.name for param in second.params}


def test_remove_param_detaches_it_from_families(catalog):
	catalog.add_param('Width', 'Length')
	catalog.add_param('Height', 'Length')
	fam = catalog.add_family('F', ['Width', 'Height'])
	fam.override_param('Width', value=3)

	catalog.remove_param('Width')

	assert 'Width' not in {param.name for param in fam.params}
	assert 'Width' not in fam.overrides


def test_remove_family_detaches_it_from_schedules(catalog):
	catalog.add_param('Width', 'Length')
	catalog.add_family('F', ['Width'])
	schedule = catalog.add_schedule('S', ['F'])

	catalog.remove_family('F')

	assert schedule.fams == []


def test_catalog_validate_collects_issues(catalog):
	catalog.add_param('Width', 'Length')
	catalog.add_param('Area', 'Area', formula='Width * Ghost')
	catalog.add_family('F', ['Area'])
	kinds = {(kind, name) for kind, name, _ in catalog.validate()}
	assert ('parameter', 'Area') in kinds
	assert ('family', 'F') in kinds


# --- bug 1: rename corrupted names that contain the old name ---------------

def test_param_rename_does_not_touch_longer_names(catalog):
	width = catalog.add_param('Width', 'Length')
	catalog.add_param('GlassWidth', 'Length')
	area = catalog.add_param('A', 'Length', formula='GlassWidth * Width')

	width.name = 'PanelWidth'

	assert area.formula == 'GlassWidth * PanelWidth'


def test_rename_updates_override_keys(catalog):
	catalog.add_param('Width', 'Length')
	fam = catalog.add_family('F', ['Width'])
	fam.override_param('Width', value=2)

	catalog.rename_param('Width', 'PanelWidth')

	assert fam.overrides == {'PanelWidth': {'value': 2}}


# --- bug 2 / step 6: saving and reloading --------------------------------

def build_sample(catalog):
	catalog.add_param('Width', 'Length')
	catalog.add_param('Height', 'Length', group_under='Dimensions')
	catalog.add_param('Area', 'Area', formula='Width * Height', instance_param=False)
	fam = catalog.add_family('F', ['Width', 'Height', 'Area'], category='Doors', client='Client A')
	fam.override_param('Width', value=3)
	fam.add_param(Param('LocalOnly', 'Number'))
	catalog.add_schedule('S1', ['F'])
	return catalog


def test_catalog_json_round_trip(catalog, tmp_path):
	build_sample(catalog)
	path = catalog.save(tmp_path / 'catalog.json', extra={'note': 'kept'})

	loaded, extra = Catalog.load(path)

	assert extra == {'note': 'kept'}
	assert loaded.to_dict() == catalog.to_dict()
	fam = loaded.get_family('F')
	assert fam.overrides == {'Width': {'value': 3}}
	# Catalog params are shared again after loading, not copied per family.
	assert loaded.get_param('Width') in fam.params
	assert loaded.get_schedule('S1').fams == [fam]


def test_saved_file_is_readable_json(catalog, tmp_path):
	build_sample(catalog)
	path = catalog.save(tmp_path / 'catalog.json')
	data = json.loads(path.read_text() if hasattr(path, 'read_text') else open(path).read())
	assert data['version'] == 3
	assert [param['name'] for param in data['params']] == ['Width', 'Height', 'Area']
	assert data['families'][0]['param_names'] == ['Width', 'Height', 'Area']
	assert [param['name'] for param in data['families'][0]['custom_params']] == ['LocalOnly']


def test_loading_twice_does_not_collide(catalog, tmp_path):
	build_sample(catalog)
	path = catalog.save(tmp_path / 'catalog.json')
	first, _ = Catalog.load(path)
	second, _ = Catalog.load(path)
	assert first.get_schedule('S1') is not second.get_schedule('S1')


def test_unknown_format_version_rejected():
	with pytest.raises(ValueError):
		Catalog.from_dict({'version': 1})


# --- bug 3: names with spaces were split into unknown identifiers ----------

def test_formula_with_spaced_parameter_name_is_valid(catalog):
	catalog.add_param('Rough Width', 'Length')
	param = catalog.add_param('B', 'Length', formula='Rough Width * 2').validate()
	assert param.status == 'Ready', param.validation_message


def test_family_flags_spaced_reference_missing_from_family(catalog):
	catalog.add_param('Rough Width', 'Length')
	catalog.add_param('B', 'Length', formula='Rough Width * 2')
	fam = catalog.add_family('F', ['B'])
	assert fam.status == 'Error'
	assert 'Rough Width' in fam.validation_message


# --- bug 4: common params were shared objects across every family ----------

def test_common_param_rename_stays_in_one_family(catalog):
	catalog.add_param('X', 'Length')
	first = catalog.add_family('F1', ['X'])
	second = catalog.add_family('F2', ['X'])

	first.rename_param('IPS_GROUP_Schedule_Name', 'Renamed')

	assert 'IPS_GROUP_Schedule_Name' in {param.name for param in second.params}
	assert COMMON_PARAMS[4].name == 'IPS_GROUP_Schedule_Name'


def test_common_param_copies_keep_guid(catalog):
	catalog.add_param('X', 'Length')
	fam = catalog.add_family('F', ['X'])
	copy = next(param for param in fam.params if param.name == 'IPS_GROUP_Schedule_Name')
	assert copy is not COMMON_PARAMS[4]
	assert copy.guid == COMMON_PARAMS[4].guid


def test_common_params_cannot_be_removed(catalog):
	catalog.add_param('X', 'Length')
	fam = catalog.add_family('F', ['X'])
	with pytest.raises(ValueError):
		fam.remove_param('IPS_GROUP_Schedule_Name')


# --- FamType ----------------------------------------------------------------

def test_famtype_has_each_common_param_once(catalog):
	catalog.add_param('X', 'Length')
	fam = catalog.add_family('F', ['X'])
	fam_type = FamType(fam, 'Type 1')
	names = [param.name for param in fam_type.params]
	assert len(names) == len(set(names))
	assert fam_type not in catalog.families


def test_famtype_override_layers_on_parent(catalog):
	catalog.add_param('X', 'Length')
	fam = catalog.add_family('F', ['X'])
	fam.override_param('X', group_under='Dimensions')
	fam_type = FamType(fam, 'Type 1')
	fam_type.override_param_value('X', 5)

	resolved = {param.name: param for param in fam_type.resolved_params()}
	assert resolved['X'].value == 5
	assert resolved['X'].group_under == 'Dimensions'


# --- standalone objects (no catalog) ---------------------------------------

def test_standalone_family_validates_against_its_own_params():
	width = Param('Width', 'Length')
	area = Param('Area', 'Area', formula='Width * 2')
	assert Fam(name='F', params=[width, area]).status == 'Ready'


# --- GUID policy: rename assigns a new GUID unless the user keeps it -------

def test_rename_assigns_new_guid_by_default(catalog):
	param = catalog.add_param('Width', 'Length')
	original = param.guid
	param.rename('PanelWidth')
	assert param.guid != original


def test_name_setter_assigns_new_guid(catalog):
	param = catalog.add_param('Width', 'Length')
	original = param.guid
	param.name = 'PanelWidth'
	assert param.guid != original


def test_rename_can_keep_guid(catalog):
	param = catalog.add_param('Width', 'Length')
	user = catalog.add_param('A', 'Length', formula='Width * 2')
	original = param.guid
	param.rename('PanelWidth', keep_guid=True)
	assert param.guid == original
	assert user.formula == 'PanelWidth * 2'


def test_family_and_schedule_rename_pass_keep_guid(catalog):
	param = catalog.add_param('Width', 'Length')
	fam = catalog.add_family('F', ['Width'])
	schedule = catalog.add_schedule('S', ['F'])
	original = param.guid

	schedule.rename_param('Width', 'PanelWidth', keep_guid=True)
	assert param.guid == original

	fam.rename_param('PanelWidth', 'Width')
	assert param.guid != original


def test_schedule_rename_with_shared_param_across_families(catalog):
	catalog.add_param('Width', 'Length')
	catalog.add_family('F1', ['Width'])
	catalog.add_family('F2', ['Width'])
	schedule = catalog.add_schedule('S', ['F1', 'F2'])

	renamed = schedule.rename_param('Width', 'PanelWidth')

	# A schedule lists a shared parameter once; every family sees the new name.
	assert [param.name for param in renamed] == ['PanelWidth']
	for family_name in ('F1', 'F2'):
		assert 'PanelWidth' in {param.name for param in catalog.get_family(family_name).params}


def test_guid_change_warning_mentions_revit_label_remap():
	message = guid_change_warning('Width', 'PanelWidth')
	assert "'Width'" in message and "'PanelWidth'" in message
	assert 'Revit labels' in message
	assert 'remapped to the new parameter GUID' in message


# --- merged from dev: headers, widths and header groups inside a catalog ----

def test_catalog_rename_moves_schedule_overrides_and_header_groups(catalog):
	catalog.add_param('Width', 'Length')
	catalog.add_param('Height', 'Length')
	catalog.add_family('F', ['Width', 'Height'])
	schedule = catalog.add_schedule('S', ['F'])
	schedule.override_param('Width', header_text='W', grid_column_width=2.0)
	schedule.add_header_group('Size', ['Width', 'Height'])

	catalog.rename_param('Width', 'PanelWidth')

	assert schedule.header_text_overrides == {'PanelWidth': 'W'}
	assert schedule.grid_column_width_overrides == {'PanelWidth': 2.0}
	assert schedule.header_groups[0]['parameter_names'][0] == 'PanelWidth'
	header = {param.name: param.header_text for param in schedule.params}
	assert header['PanelWidth'] == 'W'


def test_catalog_round_trip_keeps_schedule_headers(catalog, tmp_path):
	catalog.add_param('Width', 'Length', header_text='Overall Width', grid_column_width=1.5)
	catalog.add_param('Height', 'Length')
	catalog.add_family('F', ['Width', 'Height'])
	schedule = catalog.add_schedule('S', ['F'])
	schedule.override_param('Height', header_text='H')
	schedule.add_header_group('Size', ['Width', 'Height'])

	loaded, _ = Catalog.load(catalog.save(tmp_path / 'catalog.json'))

	assert loaded.to_dict() == catalog.to_dict()
	restored = loaded.get_schedule('S')
	headers = {param.name: param.header_text for param in restored.params}
	assert headers == {**{name: name for name in headers}, 'Width': 'Overall Width', 'Height': 'H'}
	assert restored.header_groups[0]['caption'] == 'Size'


def test_blank_param_names_rejected_in_catalog(catalog):
	for name in (None, '', '   '):
		with pytest.raises(ValueError):
			catalog.add_param(name, 'Text')
	param = catalog.add_param('  Width  ', 'Length')
	assert param.name == 'Width'


# --- schedule fields and override locations ---------------------------------

@pytest.fixture
def scheduled(catalog):
	catalog.add_param('Width', 'Length', value=1)
	catalog.add_param('Height', 'Length', value=2)
	catalog.add_param('Depth', 'Length')
	catalog.add_family('F1', ['Width', 'Height', 'Depth'])
	catalog.add_family('F2', ['Width'])
	catalog.add_schedule('S1', ['F1', 'F2'], field_names=['Width', 'Height'])
	catalog.add_schedule('S2', ['F1'])
	return catalog


def test_schedule_field_names_pick_and_order_columns(scheduled):
	schedule = scheduled.get_schedule('S1')
	assert [param.name for param in schedule.params] == ['Width', 'Height']
	assert schedule.family_param_names(scheduled.get_family('F2')) == ['Width']

	schedule.set_field_names(['Height', 'Width'])
	assert [param.name for param in schedule.params] == ['Height', 'Width']

	all_fields = scheduled.get_schedule('S2')
	assert {param.name for param in all_fields.params} >= {'Width', 'Height', 'Depth'}


def test_schedule_flags_fields_no_family_has(scheduled):
	schedule = scheduled.get_schedule('S1')
	schedule.set_field_names(['Width', 'Ghost'])
	assert schedule.status == 'Error'
	assert 'Ghost' in schedule.validation_message


def test_schedule_override_beats_family_override_beats_default(scheduled):
	assert scheduled.resolved_value(('F1', 'S1'), 'Width') == 1

	scheduled.apply_override(('F1', None), 'Width', value=5)
	assert scheduled.resolved_value(('F1', None), 'Width') == 5
	assert scheduled.resolved_value(('F1', 'S1'), 'Width') == 5
	assert scheduled.resolved_value(('F1', 'S2'), 'Width') == 5

	scheduled.apply_override(('F1', 'S1'), 'Width', value=9)
	assert scheduled.resolved_value(('F1', 'S1'), 'Width') == 9
	assert scheduled.resolved_value(('F1', 'S2'), 'Width') == 5
	assert scheduled.resolved_value(('F2', 'S1'), 'Width') == 1

	scheduled.apply_override(('F1', 'S1'), 'Width', value=None)
	assert scheduled.resolved_value(('F1', 'S1'), 'Width') == 5
	assert 'F1' not in scheduled.get_schedule('S1').family_overrides
	scheduled.apply_override(('F1', None), 'Width', value=None)
	assert 'Width' not in scheduled.get_family('F1').overrides


def test_schedule_override_requires_family_in_schedule_with_param(scheduled):
	with pytest.raises(ValueError):
		scheduled.apply_override(('F2', 'S2'), 'Width', value=3)
	with pytest.raises(ValueError):
		scheduled.apply_override(('F2', 'S1'), 'Height', value=3)


def test_renames_and_removals_follow_schedule_fields_and_overrides(scheduled):
	scheduled.apply_override(('F1', 'S1'), 'Width', value=9)
	scheduled.get_schedule('S1').add_header_group('Size', ['Width', 'Height'])

	scheduled.rename_param('Width', 'Span', keep_guid=True)
	schedule = scheduled.get_schedule('S1')
	assert schedule.field_names == ['Span', 'Height']
	assert schedule.family_overrides == {'F1': {'Span': {'value': 9}}}

	scheduled.get_family('F1').name = 'Frame'
	assert schedule.family_overrides == {'Frame': {'Span': {'value': 9}}}

	scheduled.remove_param('Height')
	assert schedule.field_names == ['Span']
	assert schedule.header_groups == []


def test_schedule_fields_and_family_overrides_round_trip(scheduled, tmp_path):
	scheduled.apply_override(('F1', 'S1'), 'Width', value=9)
	path = scheduled.save(tmp_path / 'catalog.json')

	loaded, _ = Catalog.load(path)

	schedule = loaded.get_schedule('S1')
	assert schedule.field_names == ['Width', 'Height']
	assert loaded.resolved_value(('F1', 'S1'), 'Width') == 9
	assert loaded.get_schedule('S2').field_names is None


def test_version_2_catalogs_still_load(scheduled):
	data = scheduled.to_dict()
	data['version'] = 2
	for schedule in data['schedules']:
		del schedule['field_names'], schedule['family_overrides']

	loaded = Catalog.from_dict(data)

	assert loaded.get_schedule('S1').field_names is None


# --- formula and group under overrides ----------------------------------------

def test_schedule_overrides_are_values_only(scheduled):
	with pytest.raises(ValueError, match='Only the value'):
		scheduled.apply_override(('F1', 'S1'), 'Width', formula='Height * 2')
	with pytest.raises(ValueError, match='Only the value'):
		scheduled.apply_override(('F1', 'S1'), 'Width', group_under='Dimensions')


def test_family_can_override_formula_and_group_under(scheduled):
	scheduled.apply_override(('F1', None), 'Width', formula='Height * 2', group_under='Dimensions')

	assert scheduled.resolved_value(('F1', None), 'Width', 'formula') == 'Height * 2'
	assert scheduled.resolved_value(('F1', 'S1'), 'Width', 'group_under') == 'Dimensions'
	assert scheduled.resolved_value(('F2', None), 'Width', 'formula') is None


def test_family_formula_override_is_validated(scheduled):
	fam = scheduled.get_family('F1')
	fam.override_param('Width', formula='Height * (2')
	fam.validate()
	assert fam.status == 'Error'
	assert "Formula override for 'Width'" in fam.validation_message

	fam.override_param('Width', formula='Ghost * 2')
	fam.validate()
	assert 'Ghost' in fam.validation_message

	# F2 has Width but not Height, so an override referencing Height is outside the family.
	scheduled.get_family('F2').override_param('Width', formula='Height * 2')
	scheduled.get_family('F2').validate()
	assert 'not associated with family' in scheduled.get_family('F2').validation_message


def test_rename_updates_family_formula_overrides(scheduled):
	scheduled.apply_override(('F1', None), 'Width', formula='Height * 2')

	scheduled.rename_param('Height', 'Tall', keep_guid=True)

	assert scheduled.get_family('F1').overrides['Width']['formula'] == 'Tall * 2'


# --- hidden schedule columns -----------------------------------------------

def test_schedule_columns_are_added_after_a_column_and_removed_with_their_settings(scheduled):
	schedule = scheduled.get_schedule('S1')
	schedule.add_columns(['Depth', 'Width'], after='Width')  # Width is already a column
	assert [param.name for param in schedule.params] == ['Width', 'Depth', 'Height']
	with pytest.raises(ValueError, match="Unknown parameter 'Nope'"):
		schedule.add_columns(['Nope'])

	schedule.override_param('Depth', header_text='DEEP')
	schedule.override_family_param('F1', 'Depth', value='3')
	schedule.set_field_hidden('Depth', True)
	schedule.remove_columns(['Depth'])
	assert [param.name for param in schedule.params] == ['Width', 'Height']
	assert 'Depth' not in schedule.header_text_overrides
	assert 'Depth' not in schedule.family_overrides.get('F1', {})
	assert schedule.hidden_field_names == set()
	assert schedule.status == 'Ready'

	# A schedule showing all its families' parameters keeps the rest when one is removed.
	all_fields = scheduled.get_schedule('S2')
	before = [param.name for param in all_fields.params]
	all_fields.remove_columns(['Height'])
	assert [param.name for param in all_fields.params] == [name for name in before if name != 'Height']


def test_schedule_columns_move_left_and_right_without_splitting_header_groups(scheduled):
	schedule = scheduled.get_schedule('S1')
	schedule.add_columns(['Depth'])
	names = lambda: [param.name for param in schedule.params]  # noqa: E731
	assert names() == ['Width', 'Height', 'Depth']

	assert schedule.move_columns(['Depth'], -1) and names() == ['Width', 'Depth', 'Height']
	assert not schedule.move_columns(['Height'], 1)  # already at the right end
	# Columns that aren't next to each other move together, keeping their order.
	assert schedule.move_columns(['Width', 'Height'], -1) is False  # Width is at the left end
	assert schedule.move_columns(['Depth', 'Height'], -1) and names() == ['Depth', 'Height', 'Width']

	schedule.add_header_group('Pair', ['Depth', 'Height'])
	with pytest.raises(ValueError, match="split header group 'Pair'"):
		schedule.move_columns(['Width'], -1)
	assert names() == ['Depth', 'Height', 'Width']
	# Inside the group, or the whole group together, is fine.
	assert schedule.move_columns(['Height'], -1) and names() == ['Height', 'Depth', 'Width']
	assert schedule.header_groups[0]['parameter_names'] == ['Height', 'Depth']
	assert schedule.move_columns(['Height', 'Depth'], 1) and names() == ['Width', 'Height', 'Depth']


def test_hidden_columns_follow_renames_removals_and_round_trip(scheduled):
	schedule = scheduled.schedules[0]
	names = [param.name for param in schedule.params]
	schedule.set_field_hidden(names[0], True)
	assert schedule.hidden_field_names == {names[0]}
	with pytest.raises(ValueError, match='is not a column'):
		schedule.set_field_hidden('Ghost', True)

	restored = Catalog.from_dict(json.loads(json.dumps(scheduled.to_dict())))
	assert restored.schedules[0].hidden_field_names == {names[0]}

	scheduled.rename_param(names[0], 'Renamed', keep_guid=True)
	assert schedule.hidden_field_names == {'Renamed'}
	schedule.set_field_names([name for name in schedule.field_names if name != 'Renamed'])
	assert schedule.hidden_field_names == set()

	schedule.set_field_hidden(names[1], True)
	scheduled.remove_param(names[1])
	assert schedule.hidden_field_names == set()


# --- schedules without families --------------------------------------------

def test_a_schedule_can_stand_alone_with_catalog_parameters(scheduled):
	schedule = scheduled.add_schedule('Loose', field_names=['Depth', 'Width'])

	assert [param.name for param in schedule.params] == ['Depth', 'Width']
	assert schedule.status == 'Ready'
	schedule.override_param('Depth', header_text='DEPTH (IN)', grid_column_width=2)
	assert schedule.params[0].header_text == 'DEPTH (IN)'
	schedule.set_field_hidden('Width', True)
	schedule.add_header_group('Size', ['Depth', 'Width'])

	restored = Catalog.from_dict(json.loads(json.dumps(scheduled.to_dict()))).get_schedule('Loose')
	assert [param.name for param in restored.params] == ['Depth', 'Width']
	assert restored.hidden_field_names == {'Width'}

	schedule.set_field_names(['Depth', 'Ghost'])
	assert schedule.status == 'Error'
	assert 'Ghost' in schedule.validation_message

	# Adding a family later links it as usual.
	schedule.set_field_names(['Depth', 'Width'])
	schedule.add_family(scheduled.get_family('F1'))
	assert schedule.family_param_names(scheduled.get_family('F1')) == ['Depth', 'Width']


# --- schedule settings -----------------------------------------------------

def test_schedule_filter_value_overrides_every_family_and_defaults_to_the_name(scheduled):
	schedule = scheduled.get_schedule('S1')
	assert (schedule.filter_value, schedule.itemize, schedule.view_template) == (None, True, None)
	for fam in schedule.fams:
		assert schedule.resolved_family_param(fam, 'IPS_GROUP_Schedule_Name').value == 'S1'

	schedule.name = 'Renamed'
	assert scheduled.resolved_value(('F2', 'Renamed'), 'IPS_GROUP_Schedule_Name') == 'Renamed'

	schedule.filter_value = 'DOORS'
	for fam in schedule.fams:
		assert schedule.resolved_family_param(fam, 'IPS_GROUP_Schedule_Name').value == 'DOORS'
	# Outside the schedule the family keeps its own value.
	assert scheduled.resolved_value(('F2', None), 'IPS_GROUP_Schedule_Name') in (None, '')


def test_schedule_settings_round_trip(scheduled):
	schedule = scheduled.get_schedule('S1')
	schedule.filter_value = 'DOORS'
	schedule.itemize = False
	schedule.view_template = 'IPS Schedule Template'

	restored = Catalog.from_dict(json.loads(json.dumps(scheduled.to_dict()))).get_schedule('S1')
	assert (restored.filter_value, restored.itemize, restored.view_template) == (
		'DOORS', False, 'IPS Schedule Template')

	data = scheduled.to_dict()
	for key in ('filter_value', 'itemize', 'view_template'):
		del data['schedules'][0][key]
	older = Catalog.from_dict(data).get_schedule('S1')
	assert (older.filter_value, older.itemize, older.view_template) == (None, True, None)


# --- client and country codes ----------------------------------------------

def test_client_and_country_codes_belong_to_the_catalog(catalog):
	catalog.add_param('Width', 'Length')
	f1 = catalog.add_family('F1', ['Width'], client='Acme Corp', country='United States')
	f2 = catalog.add_family('F2', ['Width'], client='Acme Corp', country='Canada')

	assert f1.client_code == ''
	catalog.set_code('client', 'Acme Corp', ' ACME ')
	catalog.set_code('country', 'United States', 'USA')
	assert (f1.client_code, f2.client_code) == ('ACME', 'ACME')
	assert (f1.country_code, f2.country_code) == ('USA', '')

	# Listed names include ones a family uses before any code is set.
	assert catalog.names('country') == ['Canada', 'United States']
	catalog.set_code('client', 'Beta Ltd', 'BETA')
	assert catalog.names('client') == ['Acme Corp', 'Beta Ltd']


def test_codes_must_be_unique_and_round_trip(catalog):
	catalog.set_code('client', 'Acme Corp', 'ACME')
	with pytest.raises(ValueError, match="already used by 'Acme Corp'"):
		catalog.set_code('client', 'Another', 'acme')
	with pytest.raises(ValueError, match='Client name is required'):
		catalog.set_code('client', ' ', 'X')
	catalog.set_code('country', 'Canada', 'ACME')  # codes are unique per kind only

	restored = Catalog.from_dict(json.loads(json.dumps(catalog.to_dict())))
	assert restored.codes == catalog.codes

	data = catalog.to_dict()
	del data['clients'], data['countries']
	assert Catalog.from_dict(data).codes == {
		'client': {}, 'country': {}, 'category': {}, 'category_1': {}, 'category_2': {}}


def test_category_codes_are_shared_and_families_build_their_names(catalog):
	catalog.set_code('client', 'IPS', 'IPS')
	catalog.set_code('country', 'United States', 'US')
	catalog.set_code('category_1', 'Control', 'CTRL')
	catalog.set_code('category_2', 'Device', 'Device')
	with pytest.raises(ValueError, match="Category 1 code 'ctrl' is already used by 'Control'"):
		catalog.set_code('category_1', 'Controls', 'ctrl')
	# Categories share their view codes.
	catalog.set_code('category', 'Detail Item', '2D')
	catalog.set_code('category', 'Generic Annotation', '2D')

	fam = catalog.add_family(
		'Old Name', client='IPS', country='United States', category='Detail Item',
		category_1='Control', category_2='Device', description='Pilot Light',
	)
	assert (fam.category_code, fam.category_1_code, fam.category_2_code) == ('2D', 'CTRL', 'Device')
	assert catalog.build_family_name(fam) == 'IPS-US_CTRL_Device_Pilot Light_2D'
	# A blank term is left out with its prefix and suffix; unused terms are skipped.
	fam.category_2 = None
	assert catalog.build_family_name(fam) == 'IPS-US_CTRL_Pilot Light_2D'
	name_format = [
		{'term': 'client_code', 'use': False, 'prefix': '', 'suffix': ''},
		{'term': 'description', 'use': True, 'prefix': '#', 'suffix': ' ('},
		{'term': 'category_1', 'use': True, 'prefix': '', 'suffix': ')'},
	]
	# The first term in the name has no prefix: it separates a term from the one before.
	assert catalog.build_family_name(fam, name_format) == 'Pilot Light (Control)'
	fam.client = None
	assert catalog.build_family_name(fam) == 'US_CTRL_Pilot Light_2D'
	fam.client = 'IPS'

	catalog.set_family_name_format(name_format)
	assert [part['term'] for part in catalog.family_name_format][:3] == ['client_code', 'description', 'category_1']
	assert len(catalog.family_name_format) == 8  # the other terms follow, unused
	with pytest.raises(ValueError, match='Unknown family name term'):
		catalog.set_family_name_format([{'term': 'nope'}])

	restored = Catalog.from_dict(json.loads(json.dumps(catalog.to_dict())))
	assert restored.family_name_format == catalog.family_name_format
	assert restored.codes == catalog.codes
	restored_fam = restored.get_family('Old Name')
	assert (restored_fam.category_1, restored_fam.category_2) == ('Control', None)
