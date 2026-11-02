import importlib

import pytest

import formula
import revit_parameter_manager


@pytest.fixture
def m():
	"""A fresh model module, so class-level registries start empty for each test."""
	return importlib.reload(revit_parameter_manager)


# --- formula helper -------------------------------------------------------

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


def test_rename_reference_only_touches_whole_references():
	names = {'Width', 'GlassWidth', 'Rough Width'}
	result = formula.rename_reference('GlassWidth + Rough Width + Width', 'Width', 'PanelWidth', names)
	assert result == 'GlassWidth + Rough Width + PanelWidth'


def test_rename_reference_leaves_quoted_text():
	result = formula.rename_reference('IF(Width > 1, "Width", "")', 'Width', 'W', {'Width'})
	assert result == 'IF(W > 1, "Width", "")'


# --- bug 1: rename corrupted names that contain the old name ---------------

def test_param_rename_does_not_touch_longer_names(m):
	width = m.Param('Width', 'Length')
	m.Param('GlassWidth', 'Length')
	area = m.Param('A', 'Length', formula='GlassWidth * Width')

	width.name = 'PanelWidth'

	assert area.formula == 'GlassWidth * PanelWidth'


# --- bug 2: reloading a checkpoint collided with the live schedule ----------

def test_checkpoint_round_trip_while_original_is_alive(m, tmp_path):
	param = m.Param('Height', 'Length')
	schedule = m.Schedule(name='S1', fams=[m.Fam(name='F', params=[param])])
	state = m.ParameterManagerState(tmp_path, schedule=schedule)
	state.save()

	loaded = state.load()

	assert loaded is not schedule
	assert loaded.name == 'S1'
	assert [fam.name for fam in loaded.fams] == ['F']
	assert 'Height' in {p.name for p in loaded.fams[0].params}
	assert schedule not in m.Schedule._instances


def test_duplicate_live_schedule_names_still_rejected(m):
	m.Schedule(name='S1')
	with pytest.raises(ValueError):
		m.Schedule(name='S1')


# --- bug 3: names with spaces were split into unknown identifiers ----------

def test_formula_with_spaced_parameter_name_is_valid(m):
	m.Param('Rough Width', 'Length')
	param = m.Param('B', 'Length', formula='Rough Width * 2').validate()
	assert param.status == 'Ready', param.validation_message


def test_family_flags_spaced_reference_missing_from_family(m):
	m.Param('Rough Width', 'Length')
	user = m.Param('B', 'Length', formula='Rough Width * 2')
	fam = m.Fam(name='F', params=[user])
	assert fam.status == 'Error'
	assert 'Rough Width' in fam.validation_message


# --- bug 4: common params were shared objects across every family ----------

def test_common_param_rename_stays_in_one_family(m):
	first = m.Fam(name='F1', params=[m.Param('X', 'Length')])
	second = m.Fam(name='F2', params=[m.Param('Y', 'Length')])

	first.rename_param('IPS_GROUP_Schedule_Name', 'Renamed')

	assert 'IPS_GROUP_Schedule_Name' in {p.name for p in second.params}
	assert m.COMMON_PARAMS[4].name == 'IPS_GROUP_Schedule_Name'


def test_common_param_copies_keep_guid(m):
	fam = m.Fam(name='F', params=[m.Param('X', 'Length')])
	copy = next(p for p in fam.params if p.name == 'IPS_GROUP_Schedule_Name')
	original = m.COMMON_PARAMS[4]
	assert copy is not original
	assert copy.guid == original.guid


# --- GUID policy: rename assigns a new GUID unless the user keeps it -------

def test_rename_assigns_new_guid_by_default(m):
	param = m.Param('Width', 'Length')
	original = param.guid
	param.rename('PanelWidth')
	assert param.guid != original


def test_name_setter_assigns_new_guid(m):
	param = m.Param('Width', 'Length')
	original = param.guid
	param.name = 'PanelWidth'
	assert param.guid != original


def test_rename_can_keep_guid(m):
	param = m.Param('Width', 'Length')
	user = m.Param('A', 'Length', formula='Width * 2')
	original = param.guid
	param.rename('PanelWidth', keep_guid=True)
	assert param.guid == original
	assert user.formula == 'PanelWidth * 2'


def test_family_and_schedule_rename_pass_keep_guid(m):
	param = m.Param('Width', 'Length')
	fam = m.Fam(name='F', params=[param])
	schedule = m.Schedule(name='S', fams=[fam])
	original = param.guid

	schedule.rename_param('Width', 'PanelWidth', keep_guid=True)
	assert param.guid == original

	fam.rename_param('PanelWidth', 'Width')
	assert param.guid != original


def test_guid_change_warning_mentions_revit_label_remap(m):
	message = m.guid_change_warning('Width', 'PanelWidth')
	assert "'Width'" in message and "'PanelWidth'" in message
	assert 'Revit labels' in message
	assert 'remapped to the new parameter GUID' in message
