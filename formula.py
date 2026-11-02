"""Reference scanning for Revit-style parameter formulas.

Revit parameter names may contain spaces (``Rough Width``), so a formula cannot
be split into identifiers on whitespace. Instead, known parameter names are
matched against the formula longest first, and whatever identifier-like text is
left over is reported as unknown.
"""

import re

FORMULA_FUNCTIONS = frozenset({
	'ABS', 'ACOS', 'AND', 'ASIN', 'ATAN', 'CEILING', 'COS', 'EXP',
	'FALSE', 'IF', 'INT', 'LN', 'LOG', 'MAX', 'MIN', 'MOD', 'NOT',
	'OR', 'PI', 'POWER', 'ROUND', 'SIGN', 'SIN', 'SQRT', 'TAN', 'TRUE',
})

_STRING_LITERAL = re.compile(r'"[^"]*"|\'[^\']*\'')
_IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_WORD_CHAR = r'A-Za-z0-9_'


def _mask_string_literals(formula):
	"""Blank out quoted text, keeping every other character at its position."""
	return _STRING_LITERAL.sub(lambda match: ' ' * len(match.group()), formula)


def reference_spans(formula, known_names):
	"""Return ``(start, end, name)`` for each known name referenced in ``formula``.

	Longer names win, so ``Rough Width`` is one reference, not ``Width``. Matches
	must sit on identifier boundaries, so ``Width`` never matches inside
	``GlassWidth``. Quoted text is ignored.
	"""
	if not formula:
		return []

	masked = _mask_string_literals(formula)
	taken = [False] * len(masked)
	spans = []
	names = sorted({name for name in known_names if name}, key=len, reverse=True)
	for name in names:
		pattern = r'(?<![{w}]){name}(?![{w}])'.format(w=_WORD_CHAR, name=re.escape(name))
		for match in re.finditer(pattern, masked):
			start, end = match.span()
			if any(taken[start:end]):
				continue
			taken[start:end] = [True] * (end - start)
			spans.append((start, end, name))

	return sorted(spans)


def scan_references(formula, known_names):
	"""Split a formula's references into ``(known, unknown)`` sets of names."""
	if not formula:
		return set(), set()

	masked = list(_mask_string_literals(formula))
	known = set()
	for start, end, name in reference_spans(formula, known_names):
		known.add(name)
		masked[start:end] = ' ' * (end - start)

	unknown = {
		identifier for identifier in _IDENTIFIER.findall(''.join(masked))
		if identifier.upper() not in FORMULA_FUNCTIONS
	}
	return known, unknown


def rename_reference(formula, old_name, new_name, known_names):
	"""Rewrite references to ``old_name`` as ``new_name``, leaving everything else as is."""
	if not formula:
		return formula

	names = set(known_names) | {old_name}
	result = formula
	for start, end, name in reversed(reference_spans(formula, names)):
		if name == old_name:
			result = result[:start] + new_name + result[end:]
	return result
