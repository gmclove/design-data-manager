"""The parameter model: parameters, families, family types and schedules.

A ``Catalog`` owns everything that belongs together: the parameter definitions,
the families that use them, and the schedules that group families. Validation,
renames and persistence go through the catalog, so separate catalogs never see
each other's names. Objects built without a catalog are standalone and validate
against their own contents only.
"""

import contextlib
import json
import math
import os
import uuid

from config.revit_dtype_definitions import get_dtype_row
from config.revit_family_category_definitions import get_family_category_row
from formula import FORMULA_FUNCTIONS, check_syntax, rename_reference, scan_references, tokenize

CATALOG_FORMAT_VERSION = 4
# Version 2 files lack schedule field lists and per-schedule family overrides; both default.
# Client and country codes were added within version 3; files without them load with none.
# Version 3 files have no schedule sections. An older app must refuse version 4, not drop them.
# Combined parameters came within version 4, before it was released.
READABLE_CATALOG_FORMAT_VERSIONS = (2, 3, 4)

# Families name a client, a country, a Category 1 and a Category 2, each picked from a list
# the user adds to; the catalog keeps one code (abbreviation) for each, unique per kind.
CODE_KINDS = ('client', 'country', 'category_1', 'category_2')
# The Revit category also has a code: 3D for families placed in floor plans, 2D for those on
# drafting views, blank for both. Many categories share one, so it isn't unique.
CODED_KINDS = CODE_KINDS + ('category',)
CODE_LABELS = {
	'client': 'Client', 'country': 'Country', 'category': 'Category',
	'category_1': 'Category 1', 'category_2': 'Category 2',
}
# JSON keys of each kind's codes.
_CODE_KEYS = {
	'client': 'clients', 'country': 'countries', 'category': 'category_codes',
	'category_1': 'category_1_codes', 'category_2': 'category_2_codes',
}

# What a family name can be built from: the attribute and its label, in the builder's order.
FAMILY_NAME_TERMS = (
	('client_code', 'Client Code'),
	('country_code', 'Country Code'),
	('category_1_code', 'Category 1 Code'),
	('category_2_code', 'Category 2 Code'),
	('description', 'Description'),
	('category_code', 'Category Code'),
	('category_1', 'Category 1'),
	('category_2', 'Category 2'),
)
# The master workbook's naming, e.g. IPS-US_CTRL_Device_Pilot Light_2D. A blank term is left
# out with its prefix and suffix, and a prefix separates a term from the one before it, so the
# first term in a name has none (as the workbook's TEXTJOIN does).
DEFAULT_FAMILY_NAME_FORMAT = (
	{'term': 'client_code', 'use': True, 'prefix': '', 'suffix': ''},
	{'term': 'country_code', 'use': True, 'prefix': '-', 'suffix': ''},
	{'term': 'category_1_code', 'use': True, 'prefix': '_', 'suffix': ''},
	{'term': 'category_2_code', 'use': True, 'prefix': '_', 'suffix': ''},
	{'term': 'description', 'use': True, 'prefix': '_', 'suffix': ''},
	{'term': 'category_code', 'use': True, 'prefix': '_', 'suffix': ''},
	{'term': 'category_1', 'use': False, 'prefix': '_', 'suffix': ''},
	{'term': 'category_2', 'use': False, 'prefix': '_', 'suffix': ''},
)

# Parameter names are built like family names, from terms and a shared format. Terms keep their
# own underscores and spaces (a Clarifier of "_TermUnit").
PARAM_NAME_COMPANY = 'IPS'
PARAM_NAME_PREFIX = PARAM_NAME_COMPANY + '_'
PARAM_NAME_TERMS = (
	('company_code', 'Company Code'),
	('parent_category', 'Parent Category'),
	('child_category', 'Child Category'),
	('descriptor', 'Descriptor'),
	('clarifier', 'Clarifier'),
	('units', 'Units'),
)
# The master workbook's naming, e.g. IPS_SPACE_Air_ExhOccMax_CFM. Nothing separates Descriptor
# from Clarifier.
DEFAULT_PARAM_NAME_FORMAT = (
	{'term': 'company_code', 'use': True, 'prefix': '', 'suffix': ''},
	{'term': 'parent_category', 'use': True, 'prefix': '_', 'suffix': ''},
	{'term': 'child_category', 'use': True, 'prefix': '_', 'suffix': ''},
	{'term': 'descriptor', 'use': True, 'prefix': '_', 'suffix': ''},
	{'term': 'clarifier', 'use': True, 'prefix': '', 'suffix': ''},
	{'term': 'units', 'use': True, 'prefix': '_', 'suffix': ''},
)
# The workbook flags longer names: "LONG NAME DETECTED, CONSIDER SHORTENING".
PARAM_NAME_LONG_LENGTH = 30


def _join_name_terms(name_format, value_of):
	"""A name from a format: each used, non-blank term with its prefix and suffix, except that
	the first term in the name has no prefix."""
	parts = []
	for part in name_format:
		value = value_of(part['term'])
		if part.get('use', True) and value:
			parts.append((part.get('prefix', '') if parts else '') + value + part.get('suffix', ''))
	return ''.join(parts)


def build_param_name(terms, name_format=None):
	"""The parameter name for ``terms`` (``{term: text}``); ``''`` when every used term is blank."""
	return _join_name_terms(name_format or DEFAULT_PARAM_NAME_FORMAT, lambda term: terms.get(term) or '')


def upgrade_name_terms(terms):
	"""Terms in the workbook's shape as this format needs them, building the same name.

	The workbook has no Company Code, and its formula gives a Clarifier without a Descriptor a
	separator, which a Clarifier has no prefix for, so such a Clarifier becomes the Descriptor.
	"""
	upgraded = {term: terms.get(term) or '' for term, _label in PARAM_NAME_TERMS}
	upgraded['company_code'] = upgraded['company_code'] or PARAM_NAME_COMPANY
	if not upgraded['descriptor'] and upgraded['clarifier']:
		upgraded['descriptor'], upgraded['clarifier'] = upgraded['clarifier'], ''
	return upgraded


def split_param_name(name, known_units=()):
	"""A best guess at the terms that build ``name``, or ``None`` if none can.

	Whatever it guesses always builds exactly ``name`` in the default format. Units are the
	longest ending in ``known_units``, else a last part in capitals; a Clarifier is never guessed.
	"""
	if not name.startswith(PARAM_NAME_PREFIX) or name == PARAM_NAME_PREFIX:
		return None
	rest = name[len(PARAM_NAME_PREFIX):]
	segments = rest.split('_')
	if not segments[0] and len(segments) > 1:  # IPS__ARROW_End: the underscore is the Parent's
		segments = ['_' + segments[1]] + segments[2:]
	others = segments[1:]
	units = ''
	for index in range(len(others)):
		ending = '_'.join(others[index:])
		if ending in known_units or (index == len(others) - 1 and ending.isupper()):
			units, others = ending, others[:index]
			break
	terms = {term: '' for term, _label in PARAM_NAME_TERMS}
	terms.update(company_code=PARAM_NAME_COMPANY, parent_category=segments[0], units=units)
	if len(others) == 1:
		terms['descriptor'] = others[0]
	elif others:
		terms.update(child_category=others[0], descriptor='_'.join(others[1:]))
	if build_param_name(terms) != name:  # e.g. a double underscore mid-name
		terms = {term: '' for term, _label in PARAM_NAME_TERMS}
		terms.update(company_code=PARAM_NAME_COMPANY, parent_category=rest)
	return terms


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
		self._name_terms = None
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
		self._name_terms = None  # they described the old name
		if not keep_guid:
			self.guid = str(uuid.uuid4())
		if self.catalog is not None:
			self.catalog._param_renamed(old_name, new_name)
		return self

	@property
	def has_name_terms(self):
		"""Whether terms were recorded for the current name (a rename clears them).

		They can build another name once the shared format has changed, as a family's can.
		"""
		return self._name_terms is not None

	@property
	def name_terms(self):
		"""This parameter's name terms: as recorded, else a guess from its name, else all blank."""
		if self.has_name_terms:
			return dict(self._name_terms)
		known_units = self.catalog.recorded_param_units() if self.catalog is not None else ()
		guess = split_param_name(self._name, known_units)
		return guess or {term: '' for term, _label in PARAM_NAME_TERMS}

	def set_name_terms(self, terms):
		"""Record ``terms`` if they build this parameter's name; never renames. Returns whether they did."""
		cleaned = {term: terms.get(term) or '' for term, _label in PARAM_NAME_TERMS}
		name_format = self.catalog.param_name_format if self.catalog is not None else None
		if build_param_name(cleaned, name_format) != self._name:
			return False
		self._name_terms = cleaned
		return True

	def load_name_terms(self, terms):
		"""Restore saved terms, as they were saved. Ones from before Company Code are upgraded."""
		if not any(terms.values()):
			return
		if 'company_code' not in terms:
			terms = upgrade_name_terms(terms)
		self._name_terms = {term: terms.get(term) or '' for term, _label in PARAM_NAME_TERMS}

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
		return {self.name} | COMMON_PARAM_NAMES | REVIT_BUILTIN_PARAM_NAMES

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
		data = {
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
		if self.has_name_terms:
			data['name_terms'] = dict(self._name_terms)
		return data

	@classmethod
	def from_dict(cls, data, catalog=None):
		param = cls(
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
		param.load_name_terms(data.get('name_terms') or {})
		return param


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
# Revit's own family parameters that formulas may use (Length: line-based families).
REVIT_BUILTIN_PARAM_NAMES = frozenset({'Length'})
# Revit schedules list the elements whose value of this parameter matches the schedule's filter.
SCHEDULE_FILTER_PARAM = 'IPS_GROUP_Schedule_Name'


class Fam(object):
	def __init__(self, name=None, client=None, country=None, description=None,
				 category=None, params=None, overrides=None, catalog=None, category_1=None, category_2=None):
		self._name = name
		self.client = client
		self.country = country
		self.category_1 = category_1
		self.category_2 = category_2
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
	def category_code(self):
		return self.catalog.code('category', self.category) if self.catalog is not None else ''

	@property
	def category_1_code(self):
		return self.catalog.code('category_1', self.category_1) if self.catalog is not None else ''

	@property
	def category_2_code(self):
		return self.catalog.code('category_2', self.category_2) if self.catalog is not None else ''

	@property
	def custom_params(self):
		"""The family's parameters other than the common IPS_GROUP_* ones."""
		return [param for param in self.params if param.name not in COMMON_PARAM_NAMES]

	def known_names(self):
		if self.catalog is not None:
			return self.catalog.known_names()
		return {param.name for param in self.params} | REVIT_BUILTIN_PARAM_NAMES

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
			'category_1': self.category_1,
			'category_2': self.category_2,
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
			category_1=data.get('category_1'),
			category_2=data.get('category_2'),
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


def _clean_combined_part(part):
	"""One part of a combined parameter: ``{'parameter', 'prefix', 'suffix', 'separator'}``.
	Prefix, suffix and separator keep their spaces: they are printed as typed."""
	if isinstance(part, str):
		part = {'parameter': part}
	if not isinstance(part, dict):
		raise ValueError('A combined parameter part is a parameter name with a prefix, suffix and separator.')
	cleaned = {'parameter': _clean_name(part.get('parameter'))}
	for key in ('prefix', 'suffix', 'separator'):
		value = part.get(key)
		cleaned[key] = '' if value is None else str(value)
	return cleaned


class CombinedParam(object):
	"""A schedule column that joins several parameters into one cell, as Revit's combined
	parameters do: ``TAG`` from the tag terms. It is only a column: no family holds it, it isn't
	in the shared parameter file, and Revit works out its value from its parts.

	``parts`` lists ``{'parameter', 'prefix', 'suffix', 'separator'}`` in order. Each part shows as
	prefix, value, suffix; its separator goes between it and the next part.
	"""

	is_combined = True
	# Read like a parameter's, so tables that list columns can show one.
	dtype = 'Text'
	group_under = None
	value = None
	formula = None
	instance_param = True

	def __init__(self, name, parts=(), header_text=None, grid_column_width=1.0, guid=None, catalog=None):
		self._name = _clean_name(name, 'Combined parameter')
		self.catalog = None
		self.guid = _clean_optional(guid) or str(uuid.uuid4())
		self.parts = [_clean_combined_part(part) for part in parts]
		self._header_text = None
		self.header_text = header_text
		self._grid_column_width = Param._coerce_grid_column_width(grid_column_width)
		self.status = 'Ready'
		self.validation_message = ''
		if catalog is not None:
			catalog._register_combined_param(self)

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, new_name):
		"""Rename; schedules and sections that list it follow."""
		cleaned = _clean_name(new_name, 'Combined parameter')
		if cleaned == self._name:
			return
		old_name = self._name
		if self.catalog is not None:
			self.catalog._check_column_name_free(cleaned, ignore=self)
		self._name = cleaned
		if self.catalog is not None:
			self.catalog._param_renamed(old_name, cleaned)

	@property
	def header_text(self):
		return self.name if self._header_text is None else self._header_text

	@header_text.setter
	def header_text(self, new_header_text):
		self._header_text = _clean_optional(new_header_text)

	@property
	def grid_column_width(self):
		return self._grid_column_width

	@grid_column_width.setter
	def grid_column_width(self, new_width):
		self._grid_column_width = Param._coerce_grid_column_width(new_width)

	@property
	def parameter_names(self):
		return [part['parameter'] for part in self.parts]

	def set_parts(self, parts):
		parts = [_clean_combined_part(part) for part in parts]
		if self.catalog is not None:
			self.catalog._check_combined_parts(self.name, parts)
		self.parts = parts

	def pattern(self):
		"""The parts as text: ``[IPS_TAG_TERM_1]-[IPS_TAG_TERM_2]...``."""
		text = ''
		for index, part in enumerate(self.parts):
			text += '{}[{}]{}'.format(part['prefix'], part['parameter'], part['suffix'])
			if index < len(self.parts) - 1:
				text += part['separator']
		return text

	def sample(self, values):
		"""The value from ``values`` (parameter name to text). A part with no value is left out,
		with its prefix, suffix and separator; check Revit agrees before relying on it."""
		shown = [(part, str(values.get(part['parameter']) or '')) for part in self.parts]
		shown = [(part, value) for part, value in shown if value]
		text = ''
		for index, (part, value) in enumerate(shown):
			text += part['prefix'] + value + part['suffix']
			if index < len(shown) - 1:
				text += part['separator']
		return text

	def validate(self):
		self.status = 'Ready'
		self.validation_message = ''
		issues = []
		if not self.parts:
			issues.append('No parameters to combine.')
		if self.catalog is not None:
			unknown = [name for name in self.parameter_names if self.catalog.get_param(name) is None]
			if unknown:
				issues.append('Unknown parameter(s): {}'.format(', '.join(unknown)))
		if issues:
			self.status = 'Error'
			self.validation_message = ' '.join(issues)
		return self

	def with_overrides(self, **overrides):
		"""An unregistered copy with a schedule's header text or column width."""
		not_allowed = set(overrides) - {'header_text', 'grid_column_width'}
		if not_allowed:
			raise ValueError('A combined parameter has only a header and a column width to override.')
		result = CombinedParam(
			self.name, self.parts, header_text=self._header_text,
			grid_column_width=self.grid_column_width, guid=self.guid,
		)
		for attribute, value in overrides.items():
			setattr(result, attribute, value)
		return result

	def to_dict(self):
		return {
			'name': self.name,
			'guid': self.guid,
			'parts': [dict(part) for part in self.parts],
			'header_text': self._header_text,
			'grid_column_width': self.grid_column_width,
		}

	@classmethod
	def from_dict(cls, data, catalog=None):
		return cls(
			data.get('name'), data.get('parts', []), header_text=data.get('header_text'),
			grid_column_width=data.get('grid_column_width', 1.0), guid=data.get('guid'), catalog=catalog,
		)


def _section_block_issue(section, order):
	"""Why columns ``order`` break ``section``'s block (together, in its order), or ``None``."""
	columns = [order.index(name) for name in section.parameter_names if name in order]
	if columns and columns != list(range(columns[0], columns[0] + len(columns))):
		return "Section '{}' sets the order of its columns and keeps them together.".format(section.name)
	return None


def _clean_section_groups(groups):
	"""A section's own header groups: ``[{'caption', 'parameter_names'}]``."""
	cleaned = []
	for group in groups or ():
		caption = _clean_optional(group.get('caption'))
		if not caption:
			raise ValueError('A header group needs a caption.')
		names = [_clean_name(name) for name in group.get('parameter_names', ())]
		if not names:
			raise ValueError("Header group '{}' needs at least one column.".format(caption))
		cleaned.append({'caption': caption, 'parameter_names': names})
	return cleaned


def _clean_section_member(member):
	"""A member is a parameter name, or ``{'section': guid}`` for an included section."""
	if isinstance(member, dict):
		guid = _clean_optional(member.get('section'))
		if not guid:
			raise ValueError('An included section needs its GUID.')
		return {'section': guid}
	return _clean_name(member)


class ScheduleSection(object):
	"""A standard block of columns that many schedules share, such as electrical data.

	Schedules link to a section, and their own columns, header groups and hidden columns hold
	the result, so nothing downstream needs to know sections exist. Changing a section changes
	every schedule that uses it. A section decides which columns travel together, their order,
	their caption and which are hidden; headers and widths still come from the parameters.

	``members`` are the section's contents, in order: parameter names and other sections, so
	Pump can include Electric Motor, which includes Electrical Data. ``parameter_names`` is the
	resolved list of columns. An included section needs its catalog to resolve.
	"""

	def __init__(self, name, members=(), caption=None, hidden_parameter_names=(), guid=None, catalog=None,
				 header_groups=()):
		self.catalog = None
		self.guid = _clean_optional(guid) or str(uuid.uuid4())
		self._name = None
		self.name = name
		# The header group over all its columns.
		self.caption = _clean_optional(caption)
		# Header groups over some of its columns, inside the caption: [{'caption', 'parameter_names'}].
		self.header_groups = _clean_section_groups(header_groups)
		self.members = [_clean_section_member(member) for member in members]
		if not self.members:
			raise ValueError("Section '{}' needs at least one parameter.".format(self.name))
		own = self.own_parameter_names
		duplicates = sorted({param_name for param_name in own if own.count(param_name) > 1})
		if duplicates:
			raise ValueError("Section '{}' lists a parameter twice: {}".format(self.name, ', '.join(duplicates)))
		# Only its own columns: an included section says which of its columns are hidden.
		self.own_hidden = {_clean_name(param_name) for param_name in hidden_parameter_names}
		strays = sorted(self.own_hidden - set(own))
		if strays:
			raise ValueError("Section '{}' hides a parameter it doesn't list: {}".format(self.name, ', '.join(strays)))
		if catalog is not None:
			catalog._register_section(self)

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, new_name):
		cleaned_name = '' if new_name is None else str(new_name).strip()
		if not cleaned_name:
			raise ValueError('Section name is required.')
		if self.catalog is not None:
			self.catalog._check_section_name_free(cleaned_name, ignore=self)
		self._name = cleaned_name

	@property
	def own_parameter_names(self):
		return [member for member in self.members if not isinstance(member, dict)]

	def included_sections(self):
		"""The sections listed directly in this one."""
		included = []
		for member in self.members:
			if isinstance(member, dict):
				section = self.catalog.get_section_by_guid(member['section']) if self.catalog is not None else None
				if section is None:
					raise ValueError("Section '{}' includes a section that isn't in the database.".format(self.name))
				included.append(section)
		return included

	def included_guids(self):
		"""The GUID of every section inside this one, at any depth."""
		found = set()
		waiting = [self]
		while waiting:
			for member in waiting.pop().members:
				if isinstance(member, dict) and member['section'] not in found:
					found.add(member['section'])
					section = self.catalog.get_section_by_guid(member['section']) if self.catalog is not None else None
					if section is not None:
						waiting.append(section)
		return found

	def _resolved_names(self, path=()):
		if self.guid in path:
			raise ValueError("Section '{}' can't include itself, directly or through another section.".format(self.name))
		names = []
		included = iter(self.included_sections())
		for member in self.members:
			if isinstance(member, dict):
				names.extend(next(included)._resolved_names(path + (self.guid,)))
			else:
				names.append(member)
		return names

	@property
	def parameter_names(self):
		"""Every column, in order, with included sections expanded."""
		return self._resolved_names()

	@property
	def hidden_parameter_names(self):
		hidden = set(self.own_hidden)
		for section in self.included_sections():
			hidden |= section.hidden_parameter_names
		return hidden

	def bands(self):
		"""``(caption, columns)`` for each header group, outermost first. The outermost caption wins:
		a section with a caption covers everything inside it, so its included sections' header groups
		don't show; one without leaves theirs showing. Its own header groups always show."""
		names = self.parameter_names
		own = [
			(group['caption'], [name for name in names if name in group['parameter_names']])
			for group in self.header_groups
		]
		if self.caption:
			return [(self.caption, names)] + own
		bands = list(own)
		for section in self.included_sections():
			bands.extend(section.bands())
		return bands

	def band_issue(self):
		"""Why its header groups can't all be built, or ``None``: each needs its columns side by
		side, and two must be one inside the other or apart, never the same columns."""
		names = self.parameter_names
		spans = []
		for group in self.header_groups:
			missing = [name for name in group['parameter_names'] if name not in names]
			if missing:
				return "Header group '{}' lists columns not in the section: {}".format(
					group['caption'], ', '.join(missing))
		for caption, columns in self.bands():
			indices = sorted(names.index(name) for name in columns)
			if indices[-1] - indices[0] + 1 != len(indices):
				return "Header group '{}' needs its columns side by side.".format(caption)
			spans.append((caption, indices[0], indices[-1]))
		for index, (caption, start, end) in enumerate(spans):
			for other, other_start, other_end in spans[index + 1:]:
				if (start, end) == (other_start, other_end):
					return "Header groups '{}' and '{}' cover the same columns.".format(caption, other)
				inside = (start <= other_start and other_end <= end) or (other_start <= start and end <= other_end)
				apart = end < other_start or other_end < start
				if not inside and not apart:
					return "Header groups '{}' and '{}' overlap; one must be inside the other.".format(caption, other)
		return None

	def edited(self, **changes):
		"""A proposed version of this section, outside the catalog, to preview before committing."""
		if 'parameter_names' in changes:
			changes['members'] = changes.pop('parameter_names')
		fields = dict(
			name=self.name, members=self.members, caption=self.caption,
			hidden_parameter_names=self.own_hidden, guid=self.guid, header_groups=self.header_groups,
		)
		fields.update(changes)
		proposed = ScheduleSection(**fields)
		proposed.catalog = self.catalog
		return proposed

	def to_dict(self):
		return {
			'name': self.name,
			'guid': self.guid,
			'caption': self.caption,
			'members': [dict(member) if isinstance(member, dict) else member for member in self.members],
			'hidden_parameter_names': [
				param_name for param_name in self.own_parameter_names if param_name in self.own_hidden
			],
			'header_groups': [
				{'caption': group['caption'], 'parameter_names': list(group['parameter_names'])}
				for group in self.header_groups
			],
		}

	@classmethod
	def from_dict(cls, data, catalog=None):
		return cls(
			name=data.get('name'),
			members=data.get('members', data.get('parameter_names', [])),
			caption=data.get('caption'),
			hidden_parameter_names=data.get('hidden_parameter_names', []),
			guid=data.get('guid'),
			catalog=catalog,
			header_groups=data.get('header_groups', []),
		)


class SectionChange(object):
	"""What applying a section would do to one schedule, worked out without changing anything.

	``order``, ``header_groups``, ``hidden`` and ``excluded`` are the schedule's new state. The
	rest describes it for a preview: the section's columns ``before`` and after (``block``), the
	``captions`` of its header groups, the sections it ``absorbs`` (used here and now inside this
	one), columns ``added``, ``moved`` and ``removed``, columns newly
	``hidden`` and ``shown``, the captions of header groups ``replaced``, ``trimmed`` and ``dropped``,
	and ``local_headers``, ``(parameter, schedule header, parameter header)`` for each section
	column whose header in this schedule differs from the parameter's.
	"""

	def __init__(self, schedule, section, **fields):
		self.schedule = schedule
		self.section = section
		for name, value in fields.items():
			setattr(self, name, value)

	@property
	def changes_anything(self):
		return bool(
			self.added or self.moved or self.removed or self.hidden_now or self.shown_now
			or self.replaced or self.trimmed or self.dropped or self.caption_changed or self.absorbs
		)


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
				 filter_value=None, itemize=True, view_template=None, guid=None, section_uses=None):
		self._name = None
		self.catalog = None
		# Sections this schedule links to: [{'section_guid', 'excluded': [parameters left out here]}].
		self.section_uses = [
			{'section_guid': use['section_guid'], 'excluded': list(use.get('excluded', []))}
			for use in section_uses or []
		]
		# Stays the same through renames, so a Revit project can tell which schedule this is.
		self.guid = _clean_optional(guid) or str(uuid.uuid4())
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
				section_guid=group.get('section_guid'),
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
		self._sync_section_uses()
		self.validate()

	def add_columns(self, param_names, after=None):
		"""Add catalog parameters as columns, after column ``after`` or at the end.
		Columns already in the schedule are left where they are. A column its section
		lists goes back in the section's order, wherever ``after`` says."""
		current = [param.name for param in self.params]
		added = [name for name in dict.fromkeys(param_names) if name not in current]
		for name in added:
			if self.catalog is None or self.catalog.get_column(name) is None:
				raise ValueError("Unknown parameter '{}' for schedule '{}'.".format(name, self.name))
		position = current.index(after) + 1 if after in current else len(current)
		order = current[:position] + added + current[position:]
		restored_hidden = set()
		for section, _use in self._used_sections():
			restored = set(added) & set(section.parameter_names)
			if not restored:
				continue
			restored_hidden |= restored & section.hidden_parameter_names
			block = [name for name in section.parameter_names if name in order]
			kept = [name for name in block if name not in restored]
			first = kept[0] if kept else block[0]
			others = [name for name in order if name not in block]
			position = sum(1 for name in order[:order.index(first)] if name not in block)
			order = others[:position] + block + others[position:]
		self._check_section_blocks(order)
		self.set_field_names(order)
		self.hidden_field_names |= restored_hidden

	# --- sections ---------------------------------------------------------

	def _used_sections(self):
		"""``(section, use)`` for each section this schedule links to."""
		if self.catalog is None:
			return []
		used = []
		for use in self.section_uses:
			section = self.catalog.get_section_by_guid(use['section_guid'])
			if section is not None:
				used.append((section, use))
		return used

	def _section_use(self, section_guid):
		return next((use for use in self.section_uses if use['section_guid'] == section_guid), None)

	def _section_groups(self, section_guid):
		return [group for group in self.header_groups if group.get('section_guid') == section_guid]

	def sections_through(self, section):
		"""The sections used here that are ``section`` or include it."""
		return [
			used for used, _use in self._used_sections()
			if used.guid == section.guid or section.guid in used.included_guids()
		]

	def _check_section_blocks(self, order):
		"""Raise ``ValueError`` if ``order`` splits a section or changes its order."""
		for section, _use in self._used_sections():
			issue = _section_block_issue(section, order)
			if issue:
				raise ValueError("{} Move all of its columns together, or change the order in the section.".format(issue))

	def _sync_section_uses(self):
		"""After the columns change: a section column no longer here is excluded, and a section
		with none left is no longer used. Keeps each section's header group on its columns."""
		order = [param.name for param in self.params]
		for use in list(self.section_uses):
			section = self.catalog.get_section_by_guid(use['section_guid']) if self.catalog is not None else None
			if section is None and self.catalog is None:
				continue
			groups = self._section_groups(use['section_guid'])
			block = [name for name in section.parameter_names if name in order] if section is not None else []
			if not block:
				self.section_uses.remove(use)
				self.header_groups = [group for group in self.header_groups if group not in groups]
				continue
			use['excluded'] = [name for name in section.parameter_names if name not in order]
			bands = [(caption, [name for name in names if name in order]) for caption, names in section.bands()]
			bands = [(caption, names) for caption, names in bands if names]
			if sorted((group['caption'], sorted(group['parameter_names'])) for group in groups) == sorted(
				(caption, sorted(names)) for caption, names in bands
			):
				continue
			self.header_groups = [group for group in self.header_groups if group not in groups]
			if not _section_block_issue(section, order):
				for caption, names in bands:
					self.add_header_group(caption, names, section_guid=section.guid)

	def plan_section(self, section, excluded=None, after=None, previous=None):
		"""Work out what applying ``section`` would do here, changing nothing.

		``excluded`` lists the section's columns this schedule leaves out; by default, what it
		leaves out already. The block goes where its first column already is, otherwise after
		column ``after`` or at the end. A section used here that ``section`` includes is absorbed
		into it. ``previous`` is the section's columns before an edit, when they've changed.
		Raises ``ValueError`` if it can't be applied.
		"""
		if self.catalog is None:
			raise ValueError('A schedule needs a catalog to use a section.')
		use = self._section_use(section.guid)
		included = section.included_guids()
		absorbs = [other for other, _use in self._used_sections() if other.guid in included]
		if excluded is None:
			left_out = set(use['excluded'] if use else ())
			for _other, other_use in self._used_sections():
				if other_use['section_guid'] in included:
					left_out |= set(other_use['excluded'])
		else:
			left_out = set(excluded)
		block = [name for name in section.parameter_names if name not in left_out]
		if not block:
			raise ValueError("Schedule '{}' would have no columns from section '{}'.".format(self.name, section.name))
		for name in block:
			if self.catalog.get_column(name) is None:
				raise ValueError("Unknown parameter '{}' in section '{}'.".format(name, section.name))
		current = [param.name for param in self.params]
		for other, other_use in self._used_sections():
			if other.guid == section.guid or other.guid in included:
				continue
			shared = (set(other.parameter_names) - set(other_use['excluded'])) & set(block)
			if shared:
				raise ValueError("Schedule '{}' already has {} in section '{}'.".format(
					self.name, ', '.join(sorted(shared)), other.name))

		if previous is None:
			linked = self.catalog.get_section_by_guid(section.guid) if use else None
			previous = set(linked.parameter_names) if linked is not None else set()
		removed = [name for name in current if name in previous and name not in block]
		others = [name for name in current if name not in removed and name not in block]
		first = next((name for name in current if name in block), None)
		if first is not None:
			position = sum(1 for name in current[:current.index(first)] if name in others)
		elif after in others:
			position = others.index(after) + 1
		else:
			position = len(others)
		order = others[:position] + block + others[position:]
		self._check_section_blocks_except(section, order)

		replaced, trimmed, dropped, groups = [], [], [], []
		block_names = set(block)
		for group in self.header_groups:
			if group.get('section_guid') == section.guid or group.get('section_guid') in included:
				continue
			names = [name for name in group['parameter_names'] if name not in removed]
			rest = [name for name in names if name not in block_names]
			if not rest:
				replaced.append(group['caption'])
				continue
			columns = sorted(order.index(name) for name in rest)
			if columns[-1] - columns[0] + 1 != len(columns):
				dropped.append(group['caption'])
				continue
			if len(rest) != len(group['parameter_names']):
				trimmed.append(group['caption'])
			groups.append(dict(group, parameter_names=sorted(rest, key=order.index)))
		captions = []
		for caption, names in section.bands():
			names = [name for name in names if name in block_names]
			if names:
				captions.append(caption)
				groups.append({
					'caption': caption, 'parameter_names': names,
					'top_row': 0, 'bottom_row': 0, 'section_guid': section.guid,
				})

		hidden = (self.hidden_field_names - set(removed) - block_names) | (section.hidden_parameter_names & block_names)
		kept = [name for name in current if name in order]
		new_kept = [name for name in order if name in current]
		local_headers = []
		for name in block:
			local = self.header_text_overrides.get(name)
			param = self.catalog.get_column(name)
			if local is not None and local != param.header_text:
				local_headers.append((name, local, param.header_text))
		return SectionChange(
			self, section,
			order=order,
			block=block,
			before=[name for name in current if name in block_names or name in removed],
			header_groups=groups,
			hidden=hidden,
			excluded=[name for name in section.parameter_names if name not in block_names],
			added=[name for name in block if name not in current],
			removed=removed,
			moved=[
				name for name in block
				if name in current and kept.index(name) != new_kept.index(name)
			],
			hidden_now=sorted(hidden - self.hidden_field_names),
			shown_now=sorted((self.hidden_field_names - hidden) - set(removed)),
			replaced=replaced,
			trimmed=trimmed,
			dropped=dropped,
			caption_changed=sorted(group['caption'] for group in self._section_groups(section.guid)) != sorted(captions),
			captions=captions,
			absorbs=absorbs,
			local_headers=local_headers,
		)

	def _check_section_blocks_except(self, section, order):
		for other, _use in self._used_sections():
			if other.guid != section.guid:
				issue = _section_block_issue(other, order)
				if issue:
					raise ValueError(issue)

	def apply_section_change(self, change, clear_headers=()):
		"""Commit a change from ``plan_section``. ``clear_headers`` lists columns to give back
		the parameter's own header."""
		for name in change.removed:
			self.header_text_overrides.pop(name, None)
			self.grid_column_width_overrides.pop(name, None)
			for param_overrides in self.family_overrides.values():
				param_overrides.pop(name, None)
		self.family_overrides = {
			family_name: param_overrides
			for family_name, param_overrides in self.family_overrides.items() if param_overrides
		}
		for name in clear_headers:
			self.header_text_overrides.pop(name, None)
		self.field_names = list(change.order)
		self.header_groups = [dict(group, parameter_names=list(group['parameter_names'])) for group in change.header_groups]
		self.hidden_field_names = set(change.hidden)
		use = self._section_use(change.section.guid)
		if use is None:
			use = {'section_guid': change.section.guid, 'excluded': []}
			self.section_uses.append(use)
		use['excluded'] = list(change.excluded)
		absorbed = {other.guid for other in change.absorbs}
		self.section_uses = [other for other in self.section_uses if other['section_guid'] not in absorbed]
		self.refresh_params()
		self.validate()

	def apply_section(self, section, excluded=None, after=None, clear_headers=()):
		"""Use ``section`` in this schedule, or bring it back in line with the section."""
		self.apply_section_change(self.plan_section(section, excluded=excluded, after=after), clear_headers=clear_headers)

	def detach_section(self, section):
		"""Stop using ``section`` and keep its columns as ordinary ones."""
		use = self._section_use(section.guid)
		if use is None:
			return
		self.section_uses.remove(use)
		for group in self._section_groups(section.guid):
			del group['section_guid']

	def remove_section(self, section):
		"""Stop using ``section`` and take its columns out of the schedule."""
		if self._section_use(section.guid) is None:
			return
		current = {param.name for param in self.params}
		self.remove_columns([name for name in section.parameter_names if name in current])
		# Removing its last column ends the use; this covers a use with no columns left to remove.
		self.detach_section(section)

	def move_columns(self, param_names, step):
		"""Move columns one place left (``step`` -1) or right (+1), keeping them in order.

		Returns ``False`` when they're already at that end. Raises ``ValueError`` if the
		move would split a header group (moving every column of a group together is fine).
		"""
		order = [param.name for param in self.params]
		moving = set(param_names) & set(order)
		indices = [index for index, name in enumerate(order) if name in moving]
		if not indices or (step < 0 and indices[0] == 0) or (step > 0 and indices[-1] == len(order) - 1):
			return False
		for index in (indices if step < 0 else reversed(indices)):
			if order[index + step] not in moving:
				order[index], order[index + step] = order[index + step], order[index]
		self._check_section_blocks(order)
		for group in self.header_groups:
			columns = sorted(order.index(name) for name in group['parameter_names'])
			if columns[-1] - columns[0] + 1 != len(columns):
				raise ValueError("That would split header group '{}'. Select all of its columns to move it, "
								 "or remove the group first.".format(group['caption']))
		for group in self.header_groups:
			group['parameter_names'].sort(key=order.index)
		self.set_field_names(order)
		return True

	def remove_columns(self, param_names):
		"""Take columns out of the schedule, with their settings and Schedule Default Values."""
		if self.field_names is None:
			# Columns from the families: fix the rest so the removed ones stay out.
			self.field_names = [param.name for param in self.params]
		for name in param_names:
			self._param_removed(name)
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

		order = [param.name for param in self.params]
		for section, _use in self._used_sections():
			issue = _section_block_issue(section, order)
			if issue:
				issues.append(issue)

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
					# A combined parameter is only ever a chosen column.
					param = self.catalog.get_column(name)
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

	def add_header_group(self, caption, parameter_names, top_row=0, bottom_row=0, section_guid=None):
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
		# Marks a group a section made, so changing the section can rebuild it.
		if section_guid:
			group['section_guid'] = section_guid
		self.header_groups.append(group)
		return dict(group)

	def remove_header_group(self, parameter_names):
		"""Remove the innermost header group around ``parameter_names`` and return it.

		Raises ``ValueError`` when no group holds all of them, or when that group comes from a
		section, which decides its own header groups.
		"""
		names = set(parameter_names)
		if not names:
			raise ValueError('Select a header in the group to remove first.')
		around = [group for group in self.header_groups if names <= set(group['parameter_names'])]
		if not around:
			raise ValueError('No header group holds all the selected headers.')
		group = min(around, key=lambda group: (len(group['parameter_names']), -group['top_row']))
		if group.get('section_guid'):
			section = self.catalog.get_section_by_guid(group['section_guid']) if self.catalog is not None else None
			name = section.name if section is not None else 'a section'
			raise ValueError("Header group '{}' comes from section '{}'; change it there.".format(
				group['caption'], name))
		self.header_groups.remove(group)
		return dict(group)

	def to_dict(self):
		"""Serialize the schedule.

		In a catalog, families are stored by name (the catalog stores them in
		full). A standalone schedule embeds its families.
		"""
		data = {'name': self.name, 'guid': self.guid}
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
					**({'section_guid': group['section_guid']} if group.get('section_guid') else {}),
				}
				for group in self.header_groups
			],
			'hidden_field_names': [param.name for param in self.params if param.name in self.hidden_field_names],
			'filter_value': self.filter_value,
			'itemize': self.itemize,
			'view_template': self.view_template,
		})
		if self.section_uses:
			data['section_uses'] = [
				{'section_guid': use['section_guid'], 'excluded': list(use['excluded'])}
				for use in self.section_uses
			]
		return data

	@classmethod
	def from_dict(cls, data, catalog=None):
		fams = [Fam.from_dict(fam_data) for fam_data in data.get('fams', [])]
		for family_name in data.get('family_names', []):
			fam = catalog.get_family(family_name) if catalog is not None else None
			if fam is None:
				raise ValueError("Schedule '{}' uses unknown family '{}'.".format(data.get('name'), family_name))
			fams.append(fam)
		for use in data.get('section_uses', []):
			if catalog is None or catalog.get_section_by_guid(use.get('section_guid')) is None:
				raise ValueError("Schedule '{}' uses unknown section '{}'.".format(data.get('name'), use.get('section_guid')))
		return cls(
			section_uses=data.get('section_uses'),
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
			guid=data.get('guid'),
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
		for use in self.section_uses:
			use['excluded'] = [new_name if name == old_name else name for name in use['excluded']]

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
		self._sync_section_uses()

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
		self.sections = []
		# Schedule columns joining several parameters (CombinedParam).
		self.combined_params = []
		# A section being previewed, by GUID: lookups see it instead of the saved one.
		self._proposed_sections = {}
		# Code (abbreviation) of each client, country, category, ... by name: {'client': {name: code}, ...}.
		self.codes = {kind: {} for kind in CODED_KINDS}
		# How family names are built: [{'term', 'use', 'prefix', 'suffix'}, ...] (FAMILY_NAME_TERMS).
		self.family_name_format = [dict(part) for part in DEFAULT_FAMILY_NAME_FORMAT]
		self.param_name_format = [dict(part) for part in DEFAULT_PARAM_NAME_FORMAT]

	# --- lookups ----------------------------------------------------------

	def param_names(self):
		return {param.name for param in self.params}

	def known_names(self):
		"""Every name a formula in this catalog may reference."""
		names = self.param_names() | COMMON_PARAM_NAMES | REVIT_BUILTIN_PARAM_NAMES
		for fam in self.families:
			names.update(param.name for param in fam.params)
		return names

	def get_param(self, name):
		return next((param for param in self.params if param.name == name), None)

	def get_combined_param(self, name):
		return next((combined for combined in self.combined_params if combined.name == name), None)

	def get_column(self, name):
		"""What a schedule column named ``name`` shows: a parameter or a combined parameter."""
		return self.get_param(name) or self.get_combined_param(name)

	def column_present(self, name, names):
		"""Whether columns ``names`` already give column ``name``: it is among them, or it is a
		combined parameter and all its parts are."""
		if name in names:
			return True
		combined = self.get_combined_param(name)
		return combined is not None and bool(combined.parts) and set(combined.parameter_names) <= set(names)

	def get_family(self, name):
		return next((fam for fam in self.families if fam.name == name), None)

	def get_schedule(self, name):
		return next((schedule for schedule in self.schedules if schedule.name == name), None)

	def get_section(self, name):
		return next((section for section in self.sections if section.name == name), None)

	def get_section_by_guid(self, guid):
		proposed = self._proposed_sections.get(guid)
		if proposed is not None:
			return proposed
		return next((section for section in self.sections if section.guid == guid), None)

	@contextlib.contextmanager
	def proposing(self, proposed):
		"""While previewing: sections that include ``proposed`` resolve with it, not the saved one."""
		self._proposed_sections = {proposed.guid: proposed}
		try:
			yield
		finally:
			self._proposed_sections = {}

	def sections_including(self, section):
		"""Every section with ``section`` inside it, at any depth."""
		return [other for other in self.sections if section.guid in other.included_guids()]

	def schedules_using(self, section):
		"""The schedules that use ``section``, directly or through a section that includes it."""
		return [schedule for schedule in self.schedules if schedule.sections_through(section)]

	# --- sections ---------------------------------------------------------

	def add_section(self, name, members=(), **kwargs):
		section = ScheduleSection(name, members, **kwargs)
		section.catalog = self
		self._check_section_definition(section)
		section.catalog = None
		self._register_section(section)
		return section

	def _check_section_definition(self, section):
		"""Raise ``ValueError`` for an unknown parameter or section, a loop or a repeated column."""
		names = section.parameter_names
		unknown = [name for name in names if self.get_column(name) is None]
		if unknown:
			raise ValueError("Unknown parameter(s) for section '{}': {}".format(section.name, ', '.join(unknown)))
		repeated = sorted({name for name in names if names.count(name) > 1})
		if repeated:
			raise ValueError("Section '{}' would list a parameter twice: {}".format(section.name, ', '.join(repeated)))
		issue = section.band_issue()
		if issue:
			raise ValueError("Section '{}': {}".format(section.name, issue))

	def plan_section_update(self, section, proposed):
		"""What changing ``section`` to ``proposed`` (from ``section.edited``) would do: a list of
		``SectionChange``, one per schedule and section it uses that has ``section`` inside.
		``change.section`` says which that is. Changes nothing."""
		self._check_section_name_free(proposed.name, ignore=section)
		previous = {other.guid: set(other.parameter_names) for other in self.sections}
		changes = []
		with self.proposing(proposed):
			self._check_section_definition(proposed)
			for other in self.sections_including(section):
				self._check_section_definition(other)
			for schedule in self.schedules:
				for used in schedule.sections_through(section):
					changes.append(schedule.plan_section(used, previous=previous[used.guid]))
		return changes

	def commit_section_update(self, section, proposed, changes, clear_headers=None):
		"""Change ``section`` to ``proposed`` and apply ``changes``, the accepted ones from
		``plan_section_update``. A schedule with no accepted change keeps its columns, and stops
		using the section that reached it. ``clear_headers`` maps schedule name to columns."""
		accepted = {(change.schedule.name, change.section.guid) for change in changes}
		for schedule in self.schedules:
			for used in schedule.sections_through(section):
				if (schedule.name, used.guid) not in accepted:
					schedule.detach_section(used)
		# The definition first: applying a change validates the schedule against its section.
		section.name = proposed.name
		section.caption = proposed.caption
		section.members = [dict(member) if isinstance(member, dict) else member for member in proposed.members]
		section.own_hidden = set(proposed.own_hidden)
		section.header_groups = [dict(group, parameter_names=list(group['parameter_names'])) for group in proposed.header_groups]
		for change in changes:
			change.schedule.apply_section_change(change, (clear_headers or {}).get(change.schedule.name, ()))

	def update_section(self, section, **changes):
		"""Change ``section`` and every schedule using it."""
		proposed = section.edited(**changes)
		self.commit_section_update(section, proposed, self.plan_section_update(section, proposed))

	def remove_section(self, name):
		"""Delete a section. Schedules using it keep its columns as ordinary ones, and sections
		including it take in its members, so their columns stay the same."""
		section = self.get_section(name)
		if section is None:
			raise ValueError('Section not found: {}'.format(name))
		including = self.sections_including(section)
		for schedule in self.schedules:
			schedule.detach_section(section)
		for other in including:
			members = []
			for member in other.members:
				if member == {'section': section.guid}:
					members.extend(section.members)
					other.own_hidden |= section.own_hidden
					if not other.caption:
						other.header_groups.extend(
							{'caption': caption, 'parameter_names': list(columns)}
							for caption, columns in section.bands()
						)
				else:
					members.append(member)
			other.members = members
		self.sections.remove(section)
		section.catalog = None
		# Its caption went with it, so the header groups of those sections may change.
		for other in including:
			for schedule in self.schedules:
				if schedule._section_use(other.guid) is not None:
					schedule.apply_section(other)
		return section

	def _drop_empty_sections(self):
		"""After a parameter is removed: a section with nothing left goes, and leaves those including it."""
		empty = [section for section in self.sections if not section.members]
		while empty:
			for section in empty:
				self.sections.remove(section)
				section.catalog = None
				for other in self.sections:
					other.members = [member for member in other.members if member != {'section': section.guid}]
			empty = [section for section in self.sections if not section.members]

	# --- building ---------------------------------------------------------

	def add_param(self, name, dtype, **kwargs):
		return Param(name, dtype, catalog=self, **kwargs)

	# --- combined parameters ----------------------------------------------

	def add_combined_param(self, name, parts=(), **kwargs):
		"""Define a combined parameter. Add it to schedules as a column, or to a section."""
		self._check_combined_parts(name, [_clean_combined_part(part) for part in parts])
		return CombinedParam(name, parts, catalog=self, **kwargs)

	def _check_combined_parts(self, name, parts):
		if not parts:
			raise ValueError("Combined parameter '{}' needs at least one parameter.".format(name))
		unknown = [part['parameter'] for part in parts if self.get_param(part['parameter']) is None]
		if unknown:
			raise ValueError("Unknown parameter(s) for combined parameter '{}': {}".format(name, ', '.join(unknown)))

	def remove_combined_param(self, name):
		"""Delete a combined parameter: it leaves every schedule and section that lists it."""
		combined = self.get_combined_param(name)
		if combined is None:
			raise ValueError('Combined parameter not found: {}'.format(name))
		self.combined_params.remove(combined)
		combined.catalog = None
		self._column_removed(name)
		return combined

	def schedules_with_column(self, name):
		return [schedule for schedule in self.schedules if name in {param.name for param in schedule.params}]

	def recorded_param_units(self):
		"""Every Units term recorded on a parameter."""
		return {
			param._name_terms['units'] for param in self.params
			if param._name_terms is not None and param._name_terms['units']
		}

	def set_param_name_format(self, name_format):
		"""Set the shared parameter name format: a list of {'term', 'use', 'prefix', 'suffix'}."""
		self.param_name_format = self._clean_name_format(name_format, PARAM_NAME_TERMS, 'parameter')

	def param_term_values(self, term):
		"""The values of name term ``term`` across the catalog's parameters, sorted for a dropdown."""
		known_units = self.recorded_param_units()
		values = set()
		for param in self.params:
			terms = param._name_terms if param.has_name_terms else split_param_name(param.name, known_units)
			if terms and terms[term]:
				values.add(terms[term])
		return sorted(values, key=str.lower)

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
		# A combined parameter loses that part; with none left, it shows as an error.
		for combined in self.combined_params:
			combined.parts = [part for part in combined.parts if part['parameter'] != name]
		self._column_removed(name)
		return param

	def _column_removed(self, name):
		"""A parameter or combined parameter is gone: sections and schedules drop it."""
		for section in self.sections:
			if name in section.members:
				section.members.remove(name)
				section.own_hidden.discard(name)
			for group in section.header_groups:
				if name in group['parameter_names']:
					group['parameter_names'].remove(name)
			section.header_groups = [group for group in section.header_groups if group['parameter_names']]
		self._drop_empty_sections()
		for schedule in self.schedules:
			schedule._param_removed(name)

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

	# --- codes and family names -------------------------------------------

	def names(self, kind):
		"""Every client (country, Category 1, ...) name with a code or used by a family, sorted."""
		used = {getattr(fam, kind) for fam in self.families if getattr(fam, kind)}
		return sorted(set(self.codes[kind]) | used, key=str.lower)

	def code(self, kind, name):
		"""The code of client (country, category, ...) ``name``; ``''`` when it has none."""
		return self.codes[kind].get(name, '') if name else ''

	def set_code(self, kind, name, code):
		"""Add client (country, Category 1, ...) ``name`` or change its code.

		Codes are unique per kind, except category codes (2D, 3D), which categories share.
		"""
		name = (name or '').strip()
		code = (code or '').strip()
		label = CODE_LABELS[kind]
		if not name:
			raise ValueError('{} name is required.'.format(label))
		if code and kind in CODE_KINDS:
			for other_name, other_code in self.codes[kind].items():
				if other_name != name and other_code.lower() == code.lower():
					raise ValueError("{} code '{}' is already used by '{}'.".format(label, code, other_name))
		self.codes[kind][name] = code
		return code

	def set_family_name_format(self, name_format):
		"""Set the shared family name format: a list of {'term', 'use', 'prefix', 'suffix'}."""
		self.family_name_format = self._clean_name_format(name_format, FAMILY_NAME_TERMS, 'family')

	@staticmethod
	def _clean_name_format(name_format, known_terms, kind):
		terms = {term for term, _label in known_terms}
		cleaned = []
		for part in name_format:
			if part.get('term') not in terms:
				raise ValueError("Unknown {} name term: {}".format(kind, part.get('term')))
			cleaned.append({
				'term': part['term'], 'use': bool(part.get('use', True)),
				'prefix': str(part.get('prefix') or ''), 'suffix': str(part.get('suffix') or ''),
			})
		# Terms the format doesn't mention go at the end, unused.
		listed = {part['term'] for part in cleaned}
		cleaned.extend(
			{'term': term, 'use': False, 'prefix': '', 'suffix': ''}
			for term, _label in known_terms if term not in listed
		)
		return cleaned

	def build_family_name(self, fam, name_format=None):
		"""``fam``'s name from the name format: each used, non-blank term with its prefix and
		suffix, except that the first term in the name has no prefix."""
		return _join_name_terms(
			name_format or self.family_name_format,
			lambda term: str(getattr(fam, term) or '').strip(),
		)

	def copy_name(self, name):
		"""A free name for a copy of schedule ``name``: ``name Copy``, then ``name Copy 2``, ..."""
		candidate = '{} Copy'.format(name)
		number = 2
		while self.get_schedule(candidate) is not None:
			candidate = '{} Copy {}'.format(name, number)
			number += 1
		return candidate

	def duplicate_schedule(self, name, new_name):
		"""Copy schedule ``name`` as ``new_name``, right after it in the list, and return the copy.

		The copy has everything the original has (columns, families, overrides, header groups,
		hidden columns, sections used, settings) and its own GUID, so Revit makes it a new schedule.
		"""
		schedule = self.get_schedule(name)
		if schedule is None:
			raise ValueError('Schedule not found: {}'.format(name))
		new_name = '' if new_name is None else str(new_name).strip()
		if not new_name:
			raise ValueError('Schedule name is required.')
		self._check_schedule_name_free(new_name)
		data = schedule.to_dict()
		data['name'] = new_name
		data['guid'] = None
		copy = Schedule.from_dict(data, catalog=self)
		self.schedules.remove(copy)
		self.schedules.insert(self.schedules.index(schedule) + 1, copy)
		return copy

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
		# A schedule column name means one thing.
		if any(combined is not ignore and combined.name == name for combined in self.combined_params):
			raise ValueError("A combined parameter is already called '{}'.".format(name))

	def _check_column_name_free(self, name, ignore=None):
		self._check_param_name_free(name, ignore=ignore)

	def _register_combined_param(self, combined):
		self._check_column_name_free(combined.name)
		if any(other.guid == combined.guid for other in self.combined_params):
			combined.guid = str(uuid.uuid4())
		combined.catalog = self
		self.combined_params.append(combined)

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
		# A shared GUID (a hand-edited file) would make two schedules fight over one Revit schedule.
		if any(other.guid == schedule.guid for other in self.schedules):
			schedule.guid = str(uuid.uuid4())
		schedule.catalog = self
		self.schedules.append(schedule)

	def _check_section_name_free(self, name, ignore=None):
		if any(section is not ignore and section.name == name for section in self.sections):
			raise ValueError("Section name '{}' already exists.".format(name))

	def _register_section(self, section):
		self._check_section_name_free(section.name)
		# A shared GUID (a hand-edited file) would link schedules to the wrong section.
		if self.get_section_by_guid(section.guid) is not None:
			section.guid = str(uuid.uuid4())
		section.catalog = self
		self.sections.append(section)

	def _param_renamed(self, old_name, new_name):
		for combined in self.combined_params:
			for part in combined.parts:
				if part['parameter'] == old_name:
					part['parameter'] = new_name
		for section in self.sections:
			section.members = [new_name if member == old_name else member for member in section.members]
			for group in section.header_groups:
				group['parameter_names'] = [new_name if name == old_name else name for name in group['parameter_names']]
			if old_name in section.own_hidden:
				section.own_hidden.discard(old_name)
				section.own_hidden.add(new_name)
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
		for combined in self.combined_params:
			combined.validate()
			if combined.status == 'Error':
				issues.append(('combined parameter', combined.name, combined.validation_message))
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
			**{key: dict(self.codes[kind]) for kind, key in _CODE_KEYS.items()},
			'family_name_format': [dict(part) for part in self.family_name_format],
			'param_name_format': [dict(part) for part in self.param_name_format],
			**({'sections': [section.to_dict() for section in self.sections]} if self.sections else {}),
			**({'combined_params': [combined.to_dict() for combined in self.combined_params]}
			   if self.combined_params else {}),
		}

	@classmethod
	def from_dict(cls, data):
		version = data.get('version')
		if version not in READABLE_CATALOG_FORMAT_VERSIONS:
			raise ValueError('Unsupported catalog format version: {}'.format(version))

		catalog = cls()
		for kind, key in _CODE_KEYS.items():
			for name, code in (data.get(key) or {}).items():
				catalog.set_code(kind, name, code)
		if data.get('family_name_format'):
			catalog.set_family_name_format(data['family_name_format'])
		if data.get('param_name_format'):
			catalog.set_param_name_format(data['param_name_format'])
		for param_data in data.get('params', []):
			Param.from_dict(param_data, catalog=catalog)
		for fam_data in data.get('families', []):
			Fam.from_dict(fam_data, catalog=catalog)
		# Before sections and schedules, which list them as columns.
		for combined_data in data.get('combined_params', []):
			CombinedParam.from_dict(combined_data, catalog=catalog)
		for section_data in data.get('sections', []):
			ScheduleSection.from_dict(section_data, catalog=catalog)
		# After all are loaded: a section can include one listed later.
		for section in catalog.sections:
			catalog._check_section_definition(section)
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
