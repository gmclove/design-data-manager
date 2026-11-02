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
