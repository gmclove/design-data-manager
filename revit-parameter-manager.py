import os
import pickle
import re
import uuid

from config.revit_dtype_catalog import REVIT_DTYPE_TABLE, get_dtype_row
from config.revit_family_category_catalog import get_family_category_row
from config.revit_property_pallet_catalog import get_property_palette_row


class Param(object):
	FORMULA_ALLOWED_IDENTIFIERS = {
		'ABS', 'ACOS', 'AND', 'ASIN', 'ATAN', 'CEILING', 'COS', 'EXP',
		'FALSE', 'IF', 'INT', 'LN', 'LOG', 'MAX', 'MIN', 'MOD', 'NOT',
		'OR', 'PI', 'POWER', 'ROUND', 'SIGN', 'SIN', 'SQRT', 'TAN', 'TRUE',
	}
	OVERRIDABLE_ATTRIBUTES = (
		'group_under',
		'value',
		'formula',
		'instance_param',
	)
	_instances = []

	def __init__(self, name, dtype, guid=None, group_under=None, value=None,
				 formula=None, instance_param=True):
		self._name = name
		self._validate_dtype_name(dtype)
		self._dtype = dtype
		self.guid = guid or str(uuid.uuid4())
		self._group_under = None
		self.group_under = group_under
		self.value = value
		self._formula = None
		self.formula = formula
		self.instance_param = instance_param
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
		# catalog can be rebuilt in batches without failing on later parameters that
		# are valid but not yet instantiated in the same pass.
		self._formula = new_formula

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, new_name):
		if new_name == self._name:
			return

		old_name = self._name
		self._name = new_name
		self.guid = str(uuid.uuid4())

		# Update formulas in all instances of Param that reference the old name
		for param in self.__class__._instances:
			if not param.formula:
				continue

			if old_name in param.formula:
				param.formula = param.formula.replace(old_name, new_name)

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

		# Group labels are user-facing metadata in this catalog workflow. They are
		# often project-specific and should not block parameter creation when they are
		# not yet present in the global Revit property palette catalog.
		if get_property_palette_row(new_group_under) is not None:
			self._group_under = new_group_under
			return

		# Preserve custom project groups instead of raising during model builds.
		self._group_under = new_group_under

	def _validate_dtype_name(self, dtype):
		if get_dtype_row(dtype) is None:
			raise ValueError(
				"Unknown dtype '{}'. Update the catalog or choose a valid Revit dtype.".format(dtype)
			)

	def validate(self):
		self.status = 'Ready'
		self.validation_message = ''
		if not self.formula:
			return self

		cleaned_formula = re.sub(r'"[^"]*"|\'[^\']*\'', ' ', self.formula)
		identifiers = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', cleaned_formula)
		param_names = {param.name for param in self.__class__._instances}
		invalid_identifiers = sorted({
			identifier for identifier in identifiers
			if identifier.upper() not in self.FORMULA_ALLOWED_IDENTIFIERS
			and identifier not in param_names
		})

		if invalid_identifiers:
			self.status = 'Error'
			self.validation_message = 'Formula references parameter(s) that do not exist yet: {}'.format(
				', '.join(invalid_identifiers)
			)
			return self

		return self

	def _validate_formula_references(self, formula):
		if not formula:
			return []

		cleaned_formula = re.sub(r'"[^"]*"|\'[^\']*\'', ' ', formula)
		identifiers = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', cleaned_formula)
		param_names = {param.name for param in self.__class__._instances}
		invalid_identifiers = sorted({
			identifier for identifier in identifiers
			if identifier.upper() not in self.FORMULA_ALLOWED_IDENTIFIERS
			and identifier not in param_names
		})

		if invalid_identifiers:
			raise ValueError(
				"Formula references parameter(s) that do not exist yet: {}".format(
					', '.join(invalid_identifiers)
				)
			)
		return []

	def _validate_formula_compatibility(self, new_dtype):
		for param in self.__class__._instances:
			if not param.formula or self.name not in param.formula:
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
		self.params = list(COMMON_PARAMS)
		self.params.extend(params or [])
		self.overrides = dict(overrides) if overrides is not None else {}
		self.validate()

	def _validate_category_name(self, category):
		if category is None:
			return

		if get_family_category_row(category) is None:
			raise ValueError(
				"Unknown family category '{}'. Update the category catalog or choose a valid family category.".format(category)
			)

	def validate(self):
		self.status = 'Ready'
		self.validation_message = ''
		if not self.name:
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

		known_param_names = {param.name for param in Param._instances}
		family_param_names = {param.name for param in self.params}
		issues = []
		for param in self.params:
			if not param.formula:
				continue

			cleaned_formula = re.sub(r'"[^"]*"|\'[^\']*\'', ' ', param.formula)
			identifiers = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', cleaned_formula)
			family_missing_identifiers = sorted({
				identifier for identifier in identifiers
				if identifier in known_param_names
				and identifier not in family_param_names
			})

			if family_missing_identifiers:
				issues.append(
					"Formula for '{}' references parameter(s) not associated with family '{}': {}".format(
						param.name,
						self.name,
						', '.join(family_missing_identifiers),
					)
				)

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

			cleaned_formula = re.sub(r'"[^"]*"|\'[^\']*\'', ' ', param.formula)
			identifiers = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', cleaned_formula)
			family_missing_identifiers = sorted({
				identifier for identifier in identifiers
				if identifier in known_param_names
				and identifier not in family_param_names
			})

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

	def rename_param(self, current_name, new_name):
		param = self._find_param(current_name)
		if current_name == new_name:
			return param

		if any(existing.name == new_name for existing in self.params
			   if existing is not param):
			raise ValueError('Parameter already exists: {}'.format(new_name))

		param.name = new_name

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

	def __init__(self, name=None, fams=None):
		self._name = None
		self.name = name
		self.fams = []
		self.params = []
		self.status = 'Ready'
		self.validation_message = ''
		self.__class__._instances.append(self)
		for fam in fams or []:
			self.add_family(fam)
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

	def refresh_params(self):
		self.params = []
		for fam in self.fams:
			self.params.extend(fam.resolved_params())

	def to_dict(self):
		return {
			'name': self.name,
			'fams': [fam.to_dict() for fam in self.fams],
		}

	@classmethod
	def from_dict(cls, data):
		schedule = cls(name=data.get('name'))
		schedule.fams = [Fam.from_dict(fam_data) for fam_data in data.get('fams', [])]
		schedule.refresh_params()
		return schedule

	def override_param(self, param_name, **overrides):
		Param.validate_overrides(overrides)
		matching_families = []
		for fam in self.fams:
			try:
				fam._find_param(param_name)
			except ValueError:
				continue
			fam.override_param(param_name, **overrides)
			matching_families.append(fam)

		if not matching_families:
			raise ValueError('Parameter not found: {}'.format(param_name))

		self.refresh_params()
		return [
			param for param in self.params if param.name == param_name
		]

	def rename_param(self, current_name, new_name):
		renamed = []
		for fam in self.fams:
			try:
				fam._find_param(current_name)
			except ValueError:
				continue

			fam.rename_param(current_name, new_name)
			renamed.append(fam)

		if not renamed:
			raise ValueError('Parameter not found: {}'.format(current_name))

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

		self.schedule = Schedule.from_dict(state.get('schedule', {'fams': []}))
		return self.schedule
