import os
import pickle
import uuid
import math

from config.revit_dtype_definitions import REVIT_DTYPE_TABLE, get_dtype_row
from config.revit_family_category_definitions import get_family_category_row
from config.revit_property_pallet_definitions import get_property_palette_row
from formula import FORMULA_FUNCTIONS, rename_reference, scan_references


GUID_CHANGE_WARNING = (
	"Renaming parameter '{old_name}' to '{new_name}' will assign it a new GUID. "
	"Any Revit labels that use this parameter will need to be remapped to the new "
	"parameter GUID. You can keep the current GUID instead."
)


def guid_change_warning(old_name, new_name):
	"""The warning to show before a rename assigns a new GUID."""
	return GUID_CHANGE_WARNING.format(old_name=old_name, new_name=new_name)


class Param(object):
	FORMULA_ALLOWED_IDENTIFIERS = FORMULA_FUNCTIONS
	OVERRIDABLE_ATTRIBUTES = (
		'group_under',
		'value',
		'formula',
		'instance_param',
		'header_text',
		'grid_column_width',
	)
	_instances = []

	def __init__(self, name, dtype, guid=None, group_under=None, value=None,
				 formula=None, instance_param=True, header_text=None,
				 grid_column_width=1.0):
		self._name = None
		self._header_text = None
		self._grid_column_width: float = self._coerce_grid_column_width(grid_column_width)
		self._validate_dtype_name(dtype)
		self._dtype = dtype
		self.guid = guid or str(uuid.uuid4())
		self.name = name
		self._group_under = None
		self.group_under = group_under
		self.value = value
		self._formula = None
		self.formula = formula
		self.instance_param = instance_param
		self.header_text = header_text
		self.status = 'Ready'
		self.validation_message = ''
		self.__class__._instances.append(self)

	@property
	def formula(self):
		return self._formula

	@formula.setter
	def formula(self, new_formula):
		if new_formula is None:
			self._formula = None
			return

		# Formula references are validated as model state during `validate()` so the
		# database can be rebuilt in batches without failing on later parameters that
		# are valid but not yet instantiated in the same pass.
		self._formula = new_formula

	@property
	def name(self):
		return self._name

	@property
	def header_text(self):
		return self.name if self._header_text is None else self._header_text

	@header_text.setter
	def header_text(self, new_header_text):
		if new_header_text is None or not str(new_header_text).strip():
			self._header_text = None
			return
		self._header_text = str(new_header_text).strip()

	@property
	def grid_column_width(self):
		return self._grid_column_width

	@grid_column_width.setter
	def grid_column_width(self, new_width):
		self._grid_column_width = self._coerce_grid_column_width(new_width)

	@staticmethod
	def _coerce_grid_column_width(width):
		try:
			coerced_width = float(width)
		except (TypeError, ValueError):
			raise ValueError('Grid column width must be a number in inches.')
		if not math.isfinite(coerced_width) or coerced_width <= 0:
			raise ValueError('Grid column width must be a finite, positive number of inches.')
		return coerced_width

	@name.setter
	def name(self, new_name):
		self.rename(new_name)

	def rename(self, new_name, keep_guid=False):
		"""Rename this parameter and update formulas that reference it.

		By default a rename assigns a new GUID. Pass ``keep_guid=True`` to keep the
		current one; see ``guid_change_warning`` for what to tell the user first.
		"""
		if new_name is None or not str(new_name).strip():
			raise ValueError('Parameter name is required.')

		new_name = str(new_name).strip()
		if new_name == self._name:
			return self

		old_name = self._name
		self._name = new_name
		if old_name is None:
			return self

		if not keep_guid:
			self.guid = str(uuid.uuid4())

		# Update formulas in all instances of Param that reference the old name.
		# Matching is by whole reference, so renaming `Width` leaves `GlassWidth`
		# and `Rough Width` alone.
		known_names = {param.name for param in self.__class__._instances}
		for param in self.__class__._instances:
			if param.formula:
				param.formula = rename_reference(param.formula, old_name, new_name, known_names)
		return self

	@property
	def dtype(self):
		return self._dtype

	@dtype.setter
	def dtype(self, new_dtype):
		if new_dtype == self._dtype:
			return

		self._validate_dtype_name(new_dtype)
		self._validate_formula_compatibility(new_dtype)
		self._dtype = new_dtype
		self.guid = str(uuid.uuid4())
	



	@property
	def group_under(self):
		return self._group_under

	@group_under.setter
	def group_under(self, new_group_under):
		if new_group_under is None:
			self._group_under = None
			return

		# Group labels are user-facing metadata in this database workflow. They are
		# often project-specific and should not block parameter creation when they are
		# not yet present in the global Revit property palette definitions.
		if get_property_palette_row(new_group_under) is not None:
			self._group_under = new_group_under
			return

		# Preserve custom project groups instead of raising during model builds.
		self._group_under = new_group_under

	def _validate_dtype_name(self, dtype):
		if get_dtype_row(dtype) is None:
			raise ValueError(
				"Unknown dtype '{}'. Update the definitions or choose a valid Revit dtype.".format(dtype)
			)

	def validate(self):
		self.status = 'Ready'
		self.validation_message = ''
		if not self.formula:
			return self

		param_names = {param.name for param in self.__class__._instances}
		_, unknown = scan_references(self.formula, param_names)
		if unknown:
			self.status = 'Error'
			self.validation_message = 'Formula references parameter(s) that do not exist yet: {}'.format(
				', '.join(sorted(unknown))
			)
		return self

	def _validate_formula_compatibility(self, new_dtype):
		known_names = {param.name for param in self.__class__._instances}
		for param in self.__class__._instances:
			if not param.formula:
				continue

			referenced, _ = scan_references(param.formula, known_names)
			if self.name not in referenced:
				continue

			if self._formula_is_incompatible_with_dtype(param.formula, new_dtype):
				raise ValueError(
					"Formula for '{}' is incompatible with dtype '{}': {}".format(
						param.name,
						new_dtype,
						param.formula,
					)
				)

	@staticmethod
	def _formula_is_incompatible_with_dtype(formula, dtype):
		if not formula:
			return False

		dtype_row = get_dtype_row(dtype)
		if dtype_row is None:
			return False

		dtype_label = dtype_row['Data Types']
		if dtype_label == 'Text':
			return False

		text_indicators = ('&', '"', "'")
		return any(indicator in formula for indicator in text_indicators)

	@classmethod
	def validate_overrides(cls, overrides):
		invalid_attributes = set(overrides) - set(cls.OVERRIDABLE_ATTRIBUTES)
		if invalid_attributes:
			raise ValueError('Cannot override: {}'.format(
				', '.join(sorted(invalid_attributes))))
		if 'grid_column_width' in overrides and overrides['grid_column_width'] is not None:
			cls._coerce_grid_column_width(overrides['grid_column_width'])

	def with_overrides(self, **overrides):
		self.validate_overrides(overrides)
		result = Param(
			self.name,
			self.dtype,
			guid=self.guid,
			group_under=self.group_under,
			value=self.value,
			formula=self.formula,
			instance_param=self.instance_param,
			header_text=self._header_text,
			grid_column_width=self.grid_column_width,
		)
		for attribute, value in overrides.items():
			setattr(result, attribute, value)
		return result

	def to_dict(self):
		return {
			'name': self.name,
			'dtype': self.dtype,
			'guid': self.guid,
			'group_under': self.group_under,
			'value': self.value,
			'formula': self.formula,
			'instance_param': self.instance_param,
			'header_text': self._header_text,
			'grid_column_width': self.grid_column_width,
		}

	@classmethod
	def from_dict(cls, data):
		return cls(
			data['name'],
			data['dtype'],
			guid=data.get('guid'),
			group_under=data.get('group_under'),
			value=data.get('value'),
			formula=data.get('formula'),
			instance_param=data.get('instance_param', True),
			header_text=data.get('header_text'),
			grid_column_width=data.get('grid_column_width', 1.0),
		)


COMMON_PARAMS = (
	Param('IPS_GROUP_ConnectTo_Elect', 'Yes/No', instance_param=True),
	Param('IPS_GROUP_ConnectTo_Plumb', 'Yes/No', instance_param=True),
	Param('IPS_GROUP_Mech_Airside', 'Yes/No', instance_param=True),
	Param('IPS_GROUP_Mech_Waterside', 'Yes/No', instance_param=True),
	Param('IPS_GROUP_Schedule_Name', 'Text', instance_param=True),
)


class Fam(object):
	def __init__(self, name=None, client=None, country=None, description=None,
				 category=None, params=None, overrides=None):
		self.name = name
		self.client = client
		self.country = country
		self.description = description
		self.category = category
		self.status = 'Ready'
		self.validation_message = ''
		self._validate_category_name(category)
		# Copies, not the shared module-level objects: a rename or edit in one
		# family must not leak into every other family. GUIDs are kept.
		self.params = [common.with_overrides() for common in COMMON_PARAMS]
		self.params.extend(params or [])
		self.overrides = dict(overrides) if overrides is not None else {}
		self.validate()

	def _validate_category_name(self, category):
		if category is None:
			return

		if get_family_category_row(category) is None:
			raise ValueError(
				"Unknown family category '{}'. Update the category definitions or choose a valid family category.".format(category)
			)

	def validate(self):
		self.status = 'Ready'
		self.validation_message = ''
		if self.name is None or not str(self.name).strip():
			self.status = 'Error'
			self.validation_message = 'Family name is required.'
			return self

		custom_param_names = {
			param.name for param in self.params
			if param.name not in {common.name for common in COMMON_PARAMS}
		}
		if not custom_param_names:
			self.status = 'Error'
			self.validation_message = 'Family has no associated parameters.'
			return self

		issues = []
		seen_param_names = set()
		duplicate_param_names = set()
		for param in self.params:
			if param.name in seen_param_names:
				duplicate_param_names.add(param.name)
			seen_param_names.add(param.name)
		if duplicate_param_names:
			issues.append(
				"Duplicate parameter(s) in family '{}': {}".format(
					self.name,
					', '.join(sorted(duplicate_param_names)),
				)
			)

		issues.extend(self._validate_formula_references(self.params))
		if issues:
			self.status = 'Error'
			self.validation_message = '; '.join(issues)
		else:
			self.status = 'Ready'
			self.validation_message = ''
		return self

	def _validate_formula_references(self, params_to_validate):
		known_param_names = {param.name for param in Param._instances}
		family_param_names = {param.name for param in self.params}
		issues = []
		for param in params_to_validate:
			if not param.formula:
				continue

			referenced, _ = scan_references(param.formula, known_param_names)
			family_missing_identifiers = sorted(referenced - family_param_names)

			if family_missing_identifiers:
				issues.append(
					"Formula for '{}' references parameter(s) not associated with family '{}': {}".format(
						param.name,
						self.name,
						', '.join(family_missing_identifiers),
					)
				)
		return issues

	def override_param(self, param_name, **overrides):
		Param.validate_overrides(overrides)

		self._find_param(param_name)
		param_overrides = self.overrides.setdefault(param_name, {})
		param_overrides.update(overrides)
		resolved_param = self._find_param(param_name).with_overrides(
			**param_overrides)
		self._validate_formula_references(self.resolved_params())
		return resolved_param

	def resolved_params(self):
		return [
			param.with_overrides(**self.overrides.get(param.name, {}))
			for param in self.params
		]

	def to_dict(self):
		custom_params = [
			param.to_dict()
			for param in self.params
			if param.name not in {common.name for common in COMMON_PARAMS}
		]
		return {
			'name': self.name,
			'client': self.client,
			'country': self.country,
			'description': self.description,
			'category': self.category,
			'custom_params': custom_params,
			'overrides': {name: dict(overrides) for name, overrides in self.overrides.items()},
		}

	@classmethod
	def from_dict(cls, data):
		custom_params = [
			Param.from_dict(param_data)
			for param_data in data.get('custom_params', [])
		]
		return cls(
			name=data.get('name'),
			client=data.get('client'),
			country=data.get('country'),
			description=data.get('description'),
			category=data.get('category'),
			params=custom_params,
			overrides=data.get('overrides', {}),
		)

	def _find_param(self, param_name):
		for param in self.params:
			if param.name == param_name:
				return param

		raise ValueError('Parameter not found: {}'.format(param_name))

	def rename_param(self, current_name, new_name, keep_guid=False):
		param = self._find_param(current_name)
		if current_name == new_name:
			return param

		if any(existing.name == new_name for existing in self.params
			   if existing is not param):
			raise ValueError('Parameter already exists: {}'.format(new_name))

		param.rename(new_name, keep_guid=keep_guid)

		if current_name in self.overrides:
			overrides = self.overrides.pop(current_name)
			if new_name in self.overrides:
				self.overrides[new_name].update(overrides)
			else:
				self.overrides[new_name] = overrides

		return param


class FamType(Fam):
	def __init__(self, fam, type_name):
		super(FamType, self).__init__(fam.name, fam.client, fam.country,
									 fam.description, fam.category, fam.params)
		self.parent_fam = fam
		self.type_name = type_name

	def override_param_value(self, param_name, value):
		return self.override_param(param_name, value=value)

	def resolved_params(self):
		return [
			param.with_overrides(**self.overrides.get(param.name, {}))
			for param in self.parent_fam.resolved_params()
		]


class Schedule(object):
	_instances = []

	def __init__(self, name=None, fams=None, header_text_overrides=None,
				 header_groups=None, grid_column_width_overrides=None):
		self._name = None
		self.name = name
		self.fams = []
		self.params = []
		self.header_text_overrides = dict(header_text_overrides or {})
		self.grid_column_width_overrides = {
			name: Param._coerce_grid_column_width(width)
			for name, width in (grid_column_width_overrides or {}).items()
		}
		self.header_groups = []
		self.status = 'Ready'
		self.validation_message = ''
		self.__class__._instances.append(self)
		for fam in fams or []:
			self.add_family(fam)
		for group in header_groups or []:
			self.add_header_group(
				group.get('caption'),
				group.get('parameter_names', []),
				top_row=group.get('top_row', 0),
				bottom_row=group.get('bottom_row', group.get('top_row', 0)),
			)
		self.validate()

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, new_name):
		if new_name is None:
			self._name = None
			return

		cleaned_name = str(new_name).strip()
		if not cleaned_name:
			raise ValueError('Schedule name is required.')

		if any(existing is not self and getattr(existing, 'name', None) == cleaned_name for existing in self.__class__._instances):
			raise ValueError("Schedule name '{}' already exists.".format(cleaned_name))

		self._name = cleaned_name

	def add_family(self, fam):
		self.fams.append(fam)
		self.refresh_params()
		self.validate()

	def validate(self):
		self.status = 'Ready'
		self.validation_message = ''
		if not self.name:
			self.status = 'Error'
			self.validation_message = 'Schedule name is required.'
			return self

		issues = []
		for fam in self.fams:
			fam.validate()
			if fam.status == 'Error':
				issues.append(f"Family '{fam.name}': {fam.validation_message}")

		if issues:
			self.status = 'Error'
			self.validation_message = '; '.join(issues)
		return self

	def discard(self):
		"""Unregister this schedule so its name can be reused (e.g. on reload)."""
		self.__class__._instances = [
			existing for existing in self.__class__._instances if existing is not self
		]

	def refresh_params(self):
		self.params = []
		seen_param_names = set()
		for fam in self.fams:
			for param in fam.resolved_params():
				if param.name in seen_param_names:
					continue
				seen_param_names.add(param.name)
				param_overrides = {}
				if param.name in self.header_text_overrides:
					param_overrides['header_text'] = self.header_text_overrides[param.name]
				if param.name in self.grid_column_width_overrides:
					param_overrides['grid_column_width'] = self.grid_column_width_overrides[param.name]
				if param_overrides:
					param = param.with_overrides(**param_overrides)
				self.params.append(param)

	def add_header_group(self, caption, parameter_names, top_row=0, bottom_row=0):
		clean_caption = '' if caption is None else str(caption).strip()
		if not clean_caption:
			raise ValueError('Header group caption is required.')

		group_parameter_names = [str(name).strip() for name in parameter_names]
		if not group_parameter_names or any(not name for name in group_parameter_names):
			raise ValueError('Header groups must include parameter names.')
		if len(group_parameter_names) != len(set(group_parameter_names)):
			raise ValueError('Header groups cannot include duplicate parameters.')

		parameter_order = []
		for param in self.params:
			if param.name not in parameter_order:
				parameter_order.append(param.name)
		missing_parameters = set(group_parameter_names) - set(parameter_order)
		if missing_parameters:
			raise ValueError('Parameter not found in schedule: {}'.format(
				', '.join(sorted(missing_parameters))))

		group_parameter_names.sort(key=parameter_order.index)
		column_indices = [parameter_order.index(name) for name in group_parameter_names]
		if column_indices[-1] - column_indices[0] + 1 != len(column_indices):
			raise ValueError('Header group parameters must be contiguous in the schedule.')

		if not isinstance(top_row, int) or not isinstance(bottom_row, int):
			raise ValueError('Header group row bounds must be integers.')
		if top_row < 0 or bottom_row < top_row:
			raise ValueError('Header group row bounds are invalid.')

		group = {
			'caption': clean_caption,
			'parameter_names': group_parameter_names,
			'top_row': top_row,
			'bottom_row': bottom_row,
		}
		self.header_groups.append(group)
		return dict(group)

	def to_dict(self):
		return {
			'name': self.name,
			'fams': [fam.to_dict() for fam in self.fams],
			'header_text_overrides': dict(self.header_text_overrides),
			'grid_column_width_overrides': dict(self.grid_column_width_overrides),
			'header_groups': [
				{
					'caption': group['caption'],
					'parameter_names': list(group['parameter_names']),
					'top_row': group['top_row'],
					'bottom_row': group['bottom_row'],
				}
				for group in self.header_groups
			],
		}

	@classmethod
	def from_dict(cls, data):
		schedule = cls(
			name=data.get('name'),
			header_text_overrides=data.get('header_text_overrides', {}),
			fams=[Fam.from_dict(fam_data) for fam_data in data.get('fams', [])],
			header_groups=data.get('header_groups', []),
			grid_column_width_overrides=data.get('grid_column_width_overrides', {}),
		)
		return schedule

	def override_param(self, param_name, **overrides):
		Param.validate_overrides(overrides)
		matching_families = []
		for fam in self.fams:
			try:
				fam._find_param(param_name)
			except ValueError:
				continue
			matching_families.append(fam)

		if not matching_families:
			raise ValueError('Parameter not found: {}'.format(param_name))

		if 'header_text' in overrides:
			header_text = overrides.pop('header_text')
			if header_text is None or not str(header_text).strip():
				self.header_text_overrides.pop(param_name, None)
			else:
				self.header_text_overrides[param_name] = str(header_text).strip()

		if 'grid_column_width' in overrides:
			grid_column_width = overrides.pop('grid_column_width')
			if grid_column_width is None:
				self.grid_column_width_overrides.pop(param_name, None)
			else:
				self.grid_column_width_overrides[param_name] = Param._coerce_grid_column_width(
					grid_column_width
				)

		for fam in matching_families:
			if overrides:
				fam.override_param(param_name, **overrides)

		self.refresh_params()
		return [
			param for param in self.params if param.name == param_name
		]

	def override_header_text(self, param_name, header_text):
		return self.override_param(param_name, header_text=header_text)

	def rename_param(self, current_name, new_name, keep_guid=False):
		renamed = []
		for fam in self.fams:
			try:
				fam._find_param(current_name)
			except ValueError:
				continue

			fam.rename_param(current_name, new_name, keep_guid=keep_guid)
			renamed.append(fam)

		if not renamed:
			raise ValueError('Parameter not found: {}'.format(current_name))
		if current_name in self.header_text_overrides:
			header_text = self.header_text_overrides.pop(current_name)
			self.header_text_overrides[new_name] = header_text
		if current_name in self.grid_column_width_overrides:
			grid_width = self.grid_column_width_overrides.pop(current_name)
			self.grid_column_width_overrides[new_name] = grid_width
		for group in self.header_groups:
			group['parameter_names'] = [
				new_name if name == current_name else name
				for name in group['parameter_names']
			]

		self.refresh_params()
		return [
			param for param in self.params if param.name == new_name
		]


class ParameterManagerState(object):
	def __init__(self, directory, schedule=None, checkpoint_name='parameter_manager_state.pkl'):
		self.directory = os.path.abspath(directory)
		self.checkpoint_name = checkpoint_name
		self.checkpoint_path = os.path.join(self.directory, self.checkpoint_name)
		self.schedule = schedule or Schedule()
		os.makedirs(self.directory, exist_ok=True)

	def save(self):
		state = {
			'version': 1,
			'schedule': self.schedule.to_dict(),
		}
		with open(self.checkpoint_path, 'wb') as checkpoint_file:
			pickle.dump(state, checkpoint_file, protocol=pickle.HIGHEST_PROTOCOL)
		return self.checkpoint_path

	def load(self):
		if not os.path.exists(self.checkpoint_path):
			return None

		with open(self.checkpoint_path, 'rb') as checkpoint_file:
			state = pickle.load(checkpoint_file)

		# The checkpoint replaces the live schedule, so release its name first.
		previous = self.schedule
		previous.discard()
		try:
			self.schedule = Schedule.from_dict(state.get('schedule', {'fams': []}))
		except Exception:
			Schedule._instances.append(previous)
			raise
		return self.schedule
