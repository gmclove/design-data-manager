"""The parameter model: parameters, families, family types and schedules.

A ``Catalog`` owns everything that belongs together: the parameter definitions,
the families that use them, and the schedules that group families. Validation,
renames and persistence go through the catalog, so separate catalogs never see
each other's names. Objects built without a catalog are standalone and validate
against their own contents only.
"""

import json
import math
import os
import uuid

from config.revit_dtype_definitions import get_dtype_row
from config.revit_family_category_definitions import get_family_category_row
from formula import FORMULA_FUNCTIONS, check_syntax, rename_reference, scan_references, tokenize

CATALOG_FORMAT_VERSION = 3
# Version 2 files lack schedule field lists and per-schedule family overrides; both default.
# Client and country codes were added within version 3; files without them load with none.
READABLE_CATALOG_FORMAT_VERSIONS = (2, 3)

# Families name a client and a country; the catalog keeps one code (abbreviation) for each.
CODE_KINDS = ('client', 'country')

GUID_CHANGE_WARNING = (
	"Renaming parameter '{old_name}' to '{new_name}' will assign it a new GUID. "
	"Any Revit labels that use this parameter will need to be remapped to the new "
	"parameter GUID. You can keep the current GUID instead."
)


def guid_change_warning(old_name, new_name):
	"""The warning to show before a rename assigns a new GUID."""
	return GUID_CHANGE_WARNING.format(old_name=old_name, new_name=new_name)


def _clean_name(name, label='Parameter'):
	if name is None or not str(name).strip():
		raise ValueError('{} name is required.'.format(label))
	return str(name).strip()


def _clean_optional(text):
	"""Stripped text, or ``None`` when blank."""
	if text is None or not str(text).strip():
		return None
	return str(text).strip()


def _merge_overrides(existing, overrides):
	"""Apply ``overrides`` on top of ``existing``; a ``None`` value clears that override."""
	merged = dict(existing)
	for attribute, value in overrides.items():
		if value is None:
			merged.pop(attribute, None)
		else:
			merged[attribute] = value
	return merged


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

	def __init__(self, name, dtype, guid=None, group_under=None, value=None,
				 formula=None, instance_param=True, header_text=None,
				 grid_column_width=1.0, catalog=None):
		self._name = _clean_name(name)
		self._header_text = None
		self._grid_column_width = self._coerce_grid_column_width(grid_column_width)
		self._validate_dtype_name(dtype)
		self._dtype = dtype
		self.guid = guid or str(uuid.uuid4())
		self.group_under = group_under
		self.value = value
		self.formula = formula
		self.instance_param = instance_param
		self.header_text = header_text
		self.status = 'Ready'
		self.validation_message = ''
		self.catalog = None
		if catalog is not None:
			catalog._register_param(self)

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, new_name):
		self.rename(new_name)

	def rename(self, new_name, keep_guid=False):
		"""Rename this parameter and update every formula that references it.

		By default a rename assigns a new GUID. Pass ``keep_guid=True`` to keep the
		current one; see ``guid_change_warning`` for what to tell the user first.
		"""
		new_name = _clean_name(new_name)
		if new_name == self._name:
			return self
		if self.catalog is not None:
			self.catalog._check_param_name_free(new_name, ignore=self)

		old_name = self._name
		self._name = new_name
		if not keep_guid:
			self.guid = str(uuid.uuid4())
		if self.catalog is not None:
			self.catalog._param_renamed(old_name, new_name)
		return self

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

	def _validate_dtype_name(self, dtype):
		if get_dtype_row(dtype) is None:
			raise ValueError(
				"Unknown dtype '{}'. Update the definitions or choose a valid Revit dtype.".format(dtype)
			)

	def known_names(self):
		"""Parameter names this parameter's formula may reference."""
		if self.catalog is not None:
			return self.catalog.known_names()
		return {self.name} | COMMON_PARAM_NAMES

	def validate(self):
		self.status = 'Ready'
		self.validation_message = ''
		if not self.formula:
			return self

		known_names = self.known_names()
		issues = check_syntax(tokenize(self.formula, known_names))
		_, unknown = scan_references(self.formula, known_names)
		if unknown:
			issues.append('Formula references parameter(s) that do not exist yet: {}'.format(
				', '.join(sorted(unknown))
			))
		if issues:
			self.status = 'Error'
			self.validation_message = '; '.join(issues)
		return self

	def _validate_formula_compatibility(self, new_dtype):
		if self.catalog is None:
			return

		known_names = self.catalog.known_names()
		for param in self.catalog.params:
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
		"""An unregistered copy of this parameter with ``overrides`` applied."""
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
	def from_dict(cls, data, catalog=None):
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
			catalog=catalog,
		)


# Templates for the parameters every family carries. Each family gets its own
# copies (same GUIDs), so these objects are never edited directly.
COMMON_PARAMS = (
	Param('IPS_GROUP_ConnectTo_Elect', 'Yes/No', instance_param=True),
	Param('IPS_GROUP_ConnectTo_Plumb', 'Yes/No', instance_param=True),
	Param('IPS_GROUP_Mech_Airside', 'Yes/No', instance_param=True),
	Param('IPS_GROUP_Mech_Waterside', 'Yes/No', instance_param=True),
	Param('IPS_GROUP_Schedule_Name', 'Text', instance_param=True),
)
COMMON_PARAM_NAMES = frozenset(param.name for param in COMMON_PARAMS)
# Revit schedules list the elements whose value of this parameter matches the schedule's filter.
SCHEDULE_FILTER_PARAM = 'IPS_GROUP_Schedule_Name'


class Fam(object):
	def __init__(self, name=None, client=None, country=None, description=None,
				 category=None, params=None, overrides=None, catalog=None):
		self._name = name
		self.client = client
		self.country = country
		self.description = description
		self._validate_category_name(category)
		self.category = category
		self.status = 'Ready'
		self.validation_message = ''
		# Copies, not the shared templates: a rename or edit in one family must not
		# leak into every other family. GUIDs are kept.
		self.params = [common.with_overrides() for common in COMMON_PARAMS]
		self.params.extend(params or [])
		self.overrides = dict(overrides) if overrides is not None else {}
		self.catalog = None
		if catalog is not None:
			catalog._register_family(self)
		self.validate()

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, new_name):
		if new_name == self._name:
			return
		if self.catalog is not None:
			self.catalog._check_family_name_free(new_name, ignore=self)
		old_name = self._name
		self._name = new_name
		if self.catalog is not None:
			self.catalog._family_renamed(old_name, new_name)

	def _validate_category_name(self, category):
		if category is None:
			return

		if get_family_category_row(category) is None:
			raise ValueError(
				"Unknown family category '{}'. Update the category definitions or choose a valid family category.".format(category)
			)

	def set_category(self, category):
		self._validate_category_name(category)
		self.category = category

	@property
	def client_code(self):
		return self.catalog.code('client', self.client) if self.catalog is not None else ''

	@property
	def country_code(self):
		return self.catalog.code('country', self.country) if self.catalog is not None else ''

	@property
	def custom_params(self):
		"""The family's parameters other than the common IPS_GROUP_* ones."""
		return [param for param in self.params if param.name not in COMMON_PARAM_NAMES]

	def known_names(self):
		if self.catalog is not None:
			return self.catalog.known_names()
		return {param.name for param in self.params}

	def validate(self):
		self.status = 'Ready'
		self.validation_message = ''
		if self.name is None or not str(self.name).strip():
			self.status = 'Error'
			self.validation_message = 'Family name is required.'
			return self

		if not self.custom_params:
			# A warning, not an error: imported families start without parameters.
			self.status = 'Warning'
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

		issues.extend(self._validate_formula_overrides())
		issues.extend(self._validate_formula_references(self.resolved_params()))
		if issues:
			self.status = 'Error'
			self.validation_message = '; '.join(issues)
		return self

	def _validate_formula_overrides(self):
		"""Check the formulas this family overrides, like ``Param.validate`` checks its own."""
		known_names = self.known_names()
		issues = []
		for param_name, overrides in self.overrides.items():
			formula = overrides.get('formula')
			if not formula:
				continue
			problems = check_syntax(tokenize(formula, known_names))
			_, unknown = scan_references(formula, known_names)
			if unknown:
				problems.append('references parameter(s) that do not exist yet: {}'.format(
					', '.join(sorted(unknown))))
			if problems:
				issues.append("Formula override for '{}': {}".format(param_name, '; '.join(problems)))
		return issues

	def _validate_formula_references(self, params_to_validate):
		known_param_names = self.known_names()
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

	def add_param(self, param):
		if any(existing.name == param.name for existing in self.params):
			raise ValueError("Family '{}' already has parameter '{}'.".format(self.name, param.name))
		self.params.append(param)
		return param

	def remove_param(self, param_name):
		param = self._find_param(param_name)
		if param.name in COMMON_PARAM_NAMES:
			raise ValueError("'{}' is a common parameter and can't be removed.".format(param_name))
		self.params.remove(param)
		self.overrides.pop(param_name, None)
		return param

	def override_param(self, param_name, **overrides):
		"""Override attributes of a parameter in this family. ``None`` clears an override."""
		Param.validate_overrides(overrides)

		self._find_param(param_name)
		param_overrides = _merge_overrides(self.overrides.get(param_name, {}), overrides)
		if param_overrides:
			self.overrides[param_name] = param_overrides
		else:
			self.overrides.pop(param_name, None)
		resolved_param = self._find_param(param_name).with_overrides(
			**param_overrides)
		self._validate_formula_references(self.resolved_params())
		return resolved_param

	def resolved_params(self):
		return [
			param.with_overrides(**self.overrides.get(param.name, {}))
			for param in self.params
		]

	def _param_renamed(self, old_name, new_name, known_names):
		"""Keep family-local formulas and override keys in step with a rename."""
		for param in self.params:
			if param.catalog is None and param.formula:
				param.formula = rename_reference(param.formula, old_name, new_name, known_names)
		for overrides in self.overrides.values():
			if overrides.get('formula'):
				overrides['formula'] = rename_reference(overrides['formula'], old_name, new_name, known_names)
		if old_name in self.overrides:
			overrides = self.overrides.pop(old_name)
			self.overrides.setdefault(new_name, {}).update(overrides)

	def to_dict(self):
		"""Serialize the family. Catalog parameters are stored by name; others in full."""
		return {
			'name': self.name,
			'client': self.client,
			'country': self.country,
			'description': self.description,
			'category': self.category,
			'param_names': [param.name for param in self.custom_params if param.catalog is not None],
			'custom_params': [param.to_dict() for param in self.custom_params if param.catalog is None],
			'overrides': {name: dict(overrides) for name, overrides in self.overrides.items()},
		}

	@classmethod
	def from_dict(cls, data, catalog=None):
		params = [Param.from_dict(param_data) for param_data in data.get('custom_params', [])]
		for param_name in data.get('param_names', []):
			param = catalog.get_param(param_name) if catalog is not None else None
			if param is None:
				raise ValueError("Family '{}' uses unknown parameter '{}'.".format(data.get('name'), param_name))
			params.append(param)
		return cls(
			name=data.get('name'),
			client=data.get('client'),
			country=data.get('country'),
			description=data.get('description'),
			category=data.get('category'),
			params=params,
			overrides=data.get('overrides', {}),
			catalog=catalog,
		)

	def _find_param(self, param_name):
		for param in self.params:
			if param.name == param_name:
				return param

		raise ValueError('Parameter not found: {}'.format(param_name))

	def rename_param(self, current_name, new_name, keep_guid=False):
		"""Rename a parameter of this family.

		A catalog parameter is a shared definition, so renaming it here renames it
		for every family in the catalog.
		"""
		param = self._find_param(current_name)
		if current_name == new_name:
			return param

		if any(existing.name == new_name for existing in self.params
			   if existing is not param):
			raise ValueError('Parameter already exists: {}'.format(new_name))

		if param.catalog is not None:
			param.rename(new_name, keep_guid=keep_guid)
			return param

		param.rename(new_name, keep_guid=keep_guid)
		self._param_renamed(current_name, new_name, self.known_names() | {new_name})
		return param


class FamType(Fam):
	def __init__(self, fam, type_name):
		# Set before the base constructor, whose validate() resolves params through the parent.
		self.parent_fam = fam
		super(FamType, self).__init__(fam.name, fam.client, fam.country,
									 fam.description, fam.category, fam.custom_params)
		self.type_name = type_name
		# Validate against the parent's catalog without registering the type as a
		# separate family (it shares the parent's name).
		self.catalog = fam.catalog
		self.validate()

	def override_param_value(self, param_name, value):
		return self.override_param(param_name, value=value)

	def resolved_params(self):
		return [
			param.with_overrides(**self.overrides.get(param.name, {}))
			for param in self.parent_fam.resolved_params()
		]


class Schedule(object):
	"""Families scheduled together.

	``field_names`` picks the schedule's columns, in order; ``None`` shows every
	parameter of every family. ``family_overrides`` holds values overridden for one
	family in this schedule only (``{family: {parameter: {attribute: value}}}``);
	they take precedence over the family's own overrides. Only the value can be
	overridden in a schedule: formula and group under belong to the family in Revit.
	"""

	FAMILY_OVERRIDABLE_ATTRIBUTES = ('value',)

	def __init__(self, name=None, fams=None, header_text_overrides=None,
				 header_groups=None, grid_column_width_overrides=None, catalog=None,
				 field_names=None, family_overrides=None, hidden_field_names=None,
				 filter_value=None, itemize=True, view_template=None):
		self._name = None
		self.catalog = None
		self.name = name
		self.fams = []
		self.params = []
		self.field_names = None if field_names is None else [_clean_name(name) for name in field_names]
		self.header_text_overrides = dict(header_text_overrides or {})
		self.grid_column_width_overrides = {
			param_name: Param._coerce_grid_column_width(width)
			for param_name, width in (grid_column_width_overrides or {}).items()
		}
		self.family_overrides = {}
		for family_name, param_overrides in (family_overrides or {}).items():
			for param_name, overrides in param_overrides.items():
				self._validate_family_overrides(overrides)
				self.family_overrides.setdefault(family_name, {})[param_name] = dict(overrides)
		self.header_groups = []
		# Columns hidden in the finished Revit schedule (the working schedule shows them).
		self.hidden_field_names = set(hidden_field_names or ())
		# Value of IPS_GROUP_Schedule_Name for every family here; None means the schedule's name.
		self.filter_value = _clean_optional(filter_value)
		# Revit's "Itemize every instance".
		self.itemize = bool(itemize)
		# Name of a Revit schedule view template to apply, if any.
		self.view_template = _clean_optional(view_template)
		self.status = 'Ready'
		self.validation_message = ''
		if catalog is not None:
			catalog._register_schedule(self)
		for fam in fams or []:
			self.add_family(fam)
		self.refresh_params()
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

		if self.catalog is not None:
			self.catalog._check_schedule_name_free(cleaned_name, ignore=self)
		self._name = cleaned_name

	def add_family(self, fam):
		self.fams.append(fam)
		self.refresh_params()
		self.validate()

	def remove_family(self, family_name):
		self.fams = [fam for fam in self.fams if fam.name != family_name]
		self.family_overrides.pop(family_name, None)
		self.refresh_params()
		self.validate()

	def get_family(self, family_name):
		return next((fam for fam in self.fams if fam.name == family_name), None)

	def set_field_names(self, field_names):
		self.field_names = None if field_names is None else [_clean_name(name) for name in field_names]
		if self.field_names is not None:
			# A header group can't span a field that is no longer in the schedule.
			kept = set(self.field_names)
			self.header_groups = [
				group for group in self.header_groups if set(group['parameter_names']) <= kept
			]
			self.hidden_field_names &= kept
		self.refresh_params()
		self.validate()

	def set_field_hidden(self, param_name, hidden):
		"""Hide (or show) a column in the finished Revit schedule."""
		if param_name not in {param.name for param in self.params}:
			raise ValueError("'{}' is not a column in schedule '{}'.".format(param_name, self.name))
		if hidden:
			self.hidden_field_names.add(param_name)
		else:
			self.hidden_field_names.discard(param_name)

	def family_param_names(self, fam):
		"""The schedule's columns that ``fam`` has, in schedule order."""
		names = [param.name for param in fam.params]
		if self.field_names is None:
			return names
		return [name for name in self.field_names if name in names]

	def override_family_param(self, family_name, param_name, **overrides):
		"""Override a parameter for one family in this schedule only. ``None`` clears."""
		self._validate_family_overrides(overrides)
		fam = self.get_family(family_name)
		if fam is None:
			raise ValueError("Family '{}' is not in schedule '{}'.".format(family_name, self.name))
		fam._find_param(param_name)
		family_overrides = self.family_overrides.setdefault(family_name, {})
		param_overrides = _merge_overrides(family_overrides.get(param_name, {}), overrides)
		if param_overrides:
			family_overrides[param_name] = param_overrides
		else:
			family_overrides.pop(param_name, None)
		if not family_overrides:
			self.family_overrides.pop(family_name, None)
		return self.resolved_family_param(fam, param_name)

	@classmethod
	def _validate_family_overrides(cls, overrides):
		Param.validate_overrides(overrides)
		not_allowed = set(overrides) - set(cls.FAMILY_OVERRIDABLE_ATTRIBUTES)
		if not_allowed:
			raise ValueError(
				'Only the value can be overridden in a schedule; {} belong to the family.'.format(
					', '.join(sorted(not_allowed)))
			)

	@property
	def resolved_filter_value(self):
		"""The IPS_GROUP_Schedule_Name value this schedule's families get and Revit filters on."""
		return self.filter_value or self.name

	def resolved_family_params(self, fam):
		"""``fam``'s parameters with family and then schedule overrides applied.

		The schedule filter value overrides IPS_GROUP_Schedule_Name for every family.
		"""
		schedule_overrides = self.family_overrides.get(fam.name, {})
		resolved = []
		for param in fam.resolved_params():
			overrides = dict(schedule_overrides.get(param.name, {}))
			if param.name == SCHEDULE_FILTER_PARAM:
				overrides['value'] = self.resolved_filter_value
			resolved.append(param.with_overrides(**overrides))
		return resolved

	def resolved_family_param(self, fam, param_name):
		return next(param for param in self.resolved_family_params(fam) if param.name == param_name)

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

		if self.field_names is not None:
			available = set(self._available_params())
			missing = [name for name in self.field_names if name not in available]
			if missing:
				issues.append('Field(s) not on any family in the schedule or in the catalog: {}'.format(
					', '.join(missing)))
			duplicates = sorted({name for name in self.field_names if self.field_names.count(name) > 1})
			if duplicates:
				issues.append('Duplicate field(s): {}'.format(', '.join(duplicates)))

		for family_name, param_overrides in self.family_overrides.items():
			fam = self.get_family(family_name)
			if fam is None:
				issues.append("Overrides for family '{}', which is not in the schedule".format(family_name))
				continue
			family_names = {param.name for param in fam.params}
			for param_name in param_overrides:
				if param_name not in family_names:
					issues.append("Override for '{}' on family '{}', which doesn't have it".format(
						param_name, family_name))

		if issues:
			self.status = 'Error'
			self.validation_message = '; '.join(issues)
		return self

	def _available_params(self):
		"""Parameters this schedule can show, by name: its families' parameters, then the
		catalog's. A schedule with chosen columns can stand alone, without families."""
		params_by_name = {}
		for fam in self.fams:
			for param in fam.resolved_params():
				params_by_name.setdefault(param.name, param)
		if self.field_names is not None and self.catalog is not None:
			for name in self.field_names:
				if name not in params_by_name:
					param = self.catalog.get_param(name)
					if param is not None:
						params_by_name[name] = param
		return params_by_name

	def refresh_params(self):
		params_by_name = self._available_params()
		order = list(params_by_name) if self.field_names is None else [
			name for name in self.field_names if name in params_by_name
		]

		self.params = []
		for param_name in dict.fromkeys(order):
			param = params_by_name[param_name]
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
		"""Serialize the schedule.

		In a catalog, families are stored by name (the catalog stores them in
		full). A standalone schedule embeds its families.
		"""
		data = {'name': self.name}
		if self.catalog is not None:
			data['family_names'] = [fam.name for fam in self.fams]
		else:
			data['fams'] = [fam.to_dict() for fam in self.fams]
		data.update({
			'field_names': None if self.field_names is None else list(self.field_names),
			'family_overrides': {
				family_name: {param_name: dict(overrides) for param_name, overrides in param_overrides.items()}
				for family_name, param_overrides in self.family_overrides.items()
			},
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
			'hidden_field_names': [param.name for param in self.params if param.name in self.hidden_field_names],
			'filter_value': self.filter_value,
			'itemize': self.itemize,
			'view_template': self.view_template,
		})
		return data

	@classmethod
	def from_dict(cls, data, catalog=None):
		fams = [Fam.from_dict(fam_data) for fam_data in data.get('fams', [])]
		for family_name in data.get('family_names', []):
			fam = catalog.get_family(family_name) if catalog is not None else None
			if fam is None:
				raise ValueError("Schedule '{}' uses unknown family '{}'.".format(data.get('name'), family_name))
			fams.append(fam)
		return cls(
			name=data.get('name'),
			fams=fams,
			header_text_overrides=data.get('header_text_overrides', {}),
			header_groups=data.get('header_groups', []),
			grid_column_width_overrides=data.get('grid_column_width_overrides', {}),
			catalog=catalog,
			field_names=data.get('field_names'),
			family_overrides=data.get('family_overrides', {}),
			hidden_field_names=data.get('hidden_field_names', []),
			filter_value=data.get('filter_value'),
			itemize=data.get('itemize', True),
			view_template=data.get('view_template'),
		)

	def override_param(self, param_name, **overrides):
		Param.validate_overrides(overrides)
		matching_families = []
		for fam in self.fams:
			try:
				fam._find_param(param_name)
			except ValueError:
				continue
			matching_families.append(fam)

		if not matching_families and param_name not in {param.name for param in self.params}:
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

	def _param_renamed(self, old_name, new_name):
		"""Move schedule-level overrides and header groups to a renamed parameter."""
		if old_name in self.header_text_overrides:
			self.header_text_overrides[new_name] = self.header_text_overrides.pop(old_name)
		if old_name in self.grid_column_width_overrides:
			self.grid_column_width_overrides[new_name] = self.grid_column_width_overrides.pop(old_name)
		for group in self.header_groups:
			group['parameter_names'] = [
				new_name if name == old_name else name
				for name in group['parameter_names']
			]
		if self.field_names is not None:
			self.field_names = [new_name if name == old_name else name for name in self.field_names]
		for param_overrides in self.family_overrides.values():
			if old_name in param_overrides:
				param_overrides[new_name] = param_overrides.pop(old_name)
		if old_name in self.hidden_field_names:
			self.hidden_field_names.discard(old_name)
			self.hidden_field_names.add(new_name)

	def _param_removed(self, param_name):
		if self.field_names is not None:
			self.set_field_names([name for name in self.field_names if name != param_name])
		for family_name in list(self.family_overrides):
			self.family_overrides[family_name].pop(param_name, None)
			if not self.family_overrides[family_name]:
				del self.family_overrides[family_name]
		self.header_text_overrides.pop(param_name, None)
		self.grid_column_width_overrides.pop(param_name, None)
		self.hidden_field_names.discard(param_name)
		self.refresh_params()

	def _family_renamed(self, old_name, new_name):
		if old_name in self.family_overrides:
			self.family_overrides[new_name] = self.family_overrides.pop(old_name)

	def rename_param(self, current_name, new_name, keep_guid=False):
		renamed = []
		for fam in self.fams:
			try:
				fam._find_param(current_name)
			except ValueError:
				# Already renamed through a shared catalog parameter?
				if any(param.name == new_name for param in fam.params):
					renamed.append(fam)
				continue

			fam.rename_param(current_name, new_name, keep_guid=keep_guid)
			renamed.append(fam)

		if not renamed:
			raise ValueError('Parameter not found: {}'.format(current_name))

		# In a catalog, the rename already reached every schedule.
		if self.catalog is None:
			self._param_renamed(current_name, new_name)

		self.refresh_params()
		return [
			param for param in self.params if param.name == new_name
		]


class Catalog(object):
	"""Owns parameter definitions, families and schedules, and validates them together."""

	def __init__(self):
		self.params = []
		self.families = []
		self.schedules = []
		# Code (abbreviation) of each client and country, by name: {'client': {name: code}, ...}.
		self.codes = {kind: {} for kind in CODE_KINDS}

	# --- lookups ----------------------------------------------------------

	def param_names(self):
		return {param.name for param in self.params}

	def known_names(self):
		"""Every name a formula in this catalog may reference."""
		names = self.param_names() | COMMON_PARAM_NAMES
		for fam in self.families:
			names.update(param.name for param in fam.params)
		return names

	def get_param(self, name):
		return next((param for param in self.params if param.name == name), None)

	def get_family(self, name):
		return next((fam for fam in self.families if fam.name == name), None)

	def get_schedule(self, name):
		return next((schedule for schedule in self.schedules if schedule.name == name), None)

	# --- building ---------------------------------------------------------

	def add_param(self, name, dtype, **kwargs):
		return Param(name, dtype, catalog=self, **kwargs)

	def add_family(self, name, param_names=(), **kwargs):
		params = []
		for param_name in param_names:
			param = self.get_param(param_name)
			if param is None:
				raise ValueError("Unknown parameter '{}' for family '{}'.".format(param_name, name))
			params.append(param)
		return Fam(name=name, params=params, catalog=self, **kwargs)

	def add_schedule(self, name, family_names=(), **kwargs):
		fams = []
		for family_name in family_names:
			fam = self.get_family(family_name)
			if fam is None:
				raise ValueError("Unknown family '{}' for schedule '{}'.".format(family_name, name))
			fams.append(fam)
		return Schedule(name=name, fams=fams, catalog=self, **kwargs)

	def remove_param(self, name):
		"""Remove a parameter definition and detach it from every family."""
		param = self.get_param(name)
		if param is None:
			raise ValueError('Parameter not found: {}'.format(name))
		self.params.remove(param)
		param.catalog = None
		for fam in self.families:
			if param in fam.params:
				fam.params.remove(param)
				fam.overrides.pop(name, None)
		for schedule in self.schedules:
			schedule._param_removed(name)
		return param

	def remove_family(self, name):
		fam = self.get_family(name)
		if fam is None:
			raise ValueError('Family not found: {}'.format(name))
		self.families.remove(fam)
		fam.catalog = None
		for schedule in self.schedules:
			if fam in schedule.fams:
				schedule.remove_family(name)
		return fam

	# --- client and country codes ------------------------------------------

	def names(self, kind):
		"""Every client (or country) name with a code or used by a family, sorted."""
		used = {getattr(fam, kind) for fam in self.families if getattr(fam, kind)}
		return sorted(set(self.codes[kind]) | used, key=str.lower)

	def code(self, kind, name):
		"""The code of client (or country) ``name``; ``''`` when it has none."""
		return self.codes[kind].get(name, '') if name else ''

	def set_code(self, kind, name, code):
		"""Add client (or country) ``name`` or change its code. Codes are unique per kind."""
		name = (name or '').strip()
		code = (code or '').strip()
		label = kind.capitalize()
		if not name:
			raise ValueError('{} name is required.'.format(label))
		if code:
			for other_name, other_code in self.codes[kind].items():
				if other_name != name and other_code.lower() == code.lower():
					raise ValueError("{} code '{}' is already used by '{}'.".format(label, code, other_name))
		self.codes[kind][name] = code
		return code

	def remove_schedule(self, name):
		schedule = self.get_schedule(name)
		if schedule is None:
			raise ValueError('Schedule not found: {}'.format(name))
		self.schedules.remove(schedule)
		schedule.catalog = None
		return schedule

	def rename_param(self, current_name, new_name, keep_guid=False):
		param = self.get_param(current_name)
		if param is None:
			raise ValueError('Parameter not found: {}'.format(current_name))
		return param.rename(new_name, keep_guid=keep_guid)

	# --- overrides --------------------------------------------------------

	def apply_override(self, location, param_name, **overrides):
		"""Set (or, with ``None`` values, clear) overrides at one location.

		A location is ``(family_name, None)`` for the family everywhere, or
		``(family_name, schedule_name)`` for that family in one schedule only.
		"""
		family_name, schedule_name = location
		if schedule_name is None:
			fam = self.get_family(family_name)
			if fam is None:
				raise ValueError('Family not found: {}'.format(family_name))
			result = fam.override_param(param_name, **overrides)
		else:
			schedule = self.get_schedule(schedule_name)
			if schedule is None:
				raise ValueError('Schedule not found: {}'.format(schedule_name))
			result = schedule.override_family_param(family_name, param_name, **overrides)
		for schedule in self.schedules:
			schedule.refresh_params()
		return result

	def resolved_value(self, location, param_name, attribute='value'):
		"""The effective value of ``attribute`` at a location, after overrides."""
		family_name, schedule_name = location
		fam = self.get_family(family_name)
		if fam is None:
			raise ValueError('Family not found: {}'.format(family_name))
		if schedule_name is None:
			params = fam.resolved_params()
		else:
			params = self.get_schedule(schedule_name).resolved_family_params(fam)
		param = next((param for param in params if param.name == param_name), None)
		if param is None:
			raise ValueError("Family '{}' has no parameter '{}'.".format(family_name, param_name))
		return getattr(param, attribute)

	# --- registration (called by the model constructors) -----------------

	def _check_param_name_free(self, name, ignore=None):
		name = _clean_name(name)
		if any(param is not ignore and param.name == name for param in self.params):
			raise ValueError("Parameter '{}' already exists.".format(name))

	def _check_family_name_free(self, name, ignore=None):
		if any(fam is not ignore and fam.name == name for fam in self.families):
			raise ValueError("Family '{}' already exists.".format(name))

	def _check_schedule_name_free(self, name, ignore=None):
		if any(schedule is not ignore and schedule.name == name for schedule in self.schedules):
			raise ValueError("Schedule name '{}' already exists.".format(name))

	def _register_param(self, param):
		self._check_param_name_free(param.name)
		param.catalog = self
		self.params.append(param)

	def _register_family(self, fam):
		self._check_family_name_free(fam.name)
		fam.catalog = self
		self.families.append(fam)

	def _register_schedule(self, schedule):
		if schedule.name is not None:
			self._check_schedule_name_free(schedule.name)
		schedule.catalog = self
		self.schedules.append(schedule)

	def _param_renamed(self, old_name, new_name):
		known_names = self.known_names() | {old_name}
		for param in self.params:
			if param.formula:
				param.formula = rename_reference(param.formula, old_name, new_name, known_names)
		for fam in self.families:
			fam._param_renamed(old_name, new_name, known_names)
		for schedule in self.schedules:
			schedule._param_renamed(old_name, new_name)
			schedule.refresh_params()

	def _family_renamed(self, old_name, new_name):
		for schedule in self.schedules:
			schedule._family_renamed(old_name, new_name)

	# --- validation -------------------------------------------------------

	def validate(self):
		"""Validate everything; return ``(kind, name, message)`` for each error."""
		issues = []
		for param in self.params:
			param.validate()
			if param.status == 'Error':
				issues.append(('parameter', param.name, param.validation_message))
		for fam in self.families:
			fam.validate()
			if fam.status == 'Error':
				issues.append(('family', fam.name, fam.validation_message))
		for schedule in self.schedules:
			schedule.validate()
			if schedule.status == 'Error':
				issues.append(('schedule', schedule.name, schedule.validation_message))
		return issues

	# --- persistence ------------------------------------------------------

	def to_dict(self):
		return {
			'version': CATALOG_FORMAT_VERSION,
			'params': [param.to_dict() for param in self.params],
			'families': [fam.to_dict() for fam in self.families],
			'schedules': [schedule.to_dict() for schedule in self.schedules],
			'clients': dict(self.codes['client']),
			'countries': dict(self.codes['country']),
		}

	@classmethod
	def from_dict(cls, data):
		version = data.get('version')
		if version not in READABLE_CATALOG_FORMAT_VERSIONS:
			raise ValueError('Unsupported catalog format version: {}'.format(version))

		catalog = cls()
		for kind, key in (('client', 'clients'), ('country', 'countries')):
			for name, code in (data.get(key) or {}).items():
				catalog.set_code(kind, name, code)
		for param_data in data.get('params', []):
			Param.from_dict(param_data, catalog=catalog)
		for fam_data in data.get('families', []):
			Fam.from_dict(fam_data, catalog=catalog)
		for schedule_data in data.get('schedules', []):
			Schedule.from_dict(schedule_data, catalog=catalog)
		return catalog

	def save(self, path, extra=None):
		"""Write the catalog as JSON. ``extra`` is stored alongside, untouched."""
		data = self.to_dict()
		if extra:
			data['extra'] = extra
		path = os.path.abspath(path)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		temp_path = path + '.tmp'
		with open(temp_path, 'w', encoding='utf-8') as handle:
			json.dump(data, handle, indent=2, ensure_ascii=False)
			handle.write('\n')
		os.replace(temp_path, path)
		return path

	@classmethod
	def load(cls, path):
		"""Read a catalog saved with ``save``. Returns ``(catalog, extra)``."""
		with open(path, encoding='utf-8') as handle:
			data = json.load(handle)
		return cls.from_dict(data), data.get('extra', {})
