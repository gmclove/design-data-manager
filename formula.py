"""Tokenizing and checking Revit-style parameter formulas.

Revit parameter names may contain spaces (``Rough Width``), so a formula cannot
be split into identifiers on whitespace. The tokenizer matches known parameter
names first, longest first, and only on identifier boundaries; whatever
identifier-like text is left over becomes a NAME token (an unknown reference).
"""

import re
from collections import namedtuple

FORMULA_FUNCTIONS = frozenset({
	'ABS', 'ACOS', 'AND', 'ASIN', 'ATAN', 'CEILING', 'COS', 'EXP',
	'FALSE', 'IF', 'INT', 'LN', 'LOG', 'MAX', 'MIN', 'MOD', 'NOT',
	'OR', 'PI', 'POWER', 'ROUND', 'SIGN', 'SIN', 'SQRT', 'TAN', 'TRUE',
})
OPERATORS = frozenset('+-*/^<>=&')

NUMBER = 'NUMBER'
STRING = 'STRING'
PARAM = 'PARAM'          # a known parameter name
FUNCTION = 'FUNCTION'    # a formula function or constant (IF, PI, TRUE, ...)
NAME = 'NAME'            # an identifier that is neither of the above
OP = 'OP'
LPAREN = 'LPAREN'
RPAREN = 'RPAREN'
COMMA = 'COMMA'
ERROR = 'ERROR'          # unterminated string or unexpected character

Token = namedtuple('Token', 'kind text start end')

_NUMBER = re.compile(r'\d+(?:\.\d*)?|\.\d+')
# Revit length values in feet and inches: 0' 0 1/16", 2' 6", 3/8", 1 1/2".
_INCHES = r'(?:\d+(?:\.\d+)?(?:\s+\d+/\d+)?|\d+/\d+)"'
_LENGTH = re.compile(r"\d+(?:\.\d+)?'(?:\s*" + _INCHES + r')?|' + _INCHES)
_IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_SINGLE_CHAR_KINDS = {'(': LPAREN, ')': RPAREN, ',': COMMA}
_OPERAND_KINDS = {NUMBER, STRING, PARAM, NAME}


def _is_word_char(char):
	return char.isalnum() or char == '_'


def _match_known_name(formula, position, names):
	if position > 0 and _is_word_char(formula[position - 1]):
		return None
	for name in names:
		end = position + len(name)
		if formula.startswith(name, position) and (end == len(formula) or not _is_word_char(formula[end])):
			return name
	return None


def tokenize(formula, known_names=()):
	"""Split a formula into tokens. Known parameter names become PARAM tokens."""
	if not formula:
		return []

	names = sorted({name for name in known_names if name}, key=len, reverse=True)
	tokens = []
	position = 0
	length = len(formula)
	while position < length:
		char = formula[position]
		if char.isspace():
			position += 1
			continue

		if char.isdigit():
			length_value = _LENGTH.match(formula, position)
			if length_value:
				tokens.append(Token(NUMBER, length_value.group(), position, length_value.end()))
				position = length_value.end()
				continue

		if char in '"\'':
			close = formula.find(char, position + 1)
			if close == -1:
				tokens.append(Token(ERROR, formula[position:], position, length))
				break
			tokens.append(Token(STRING, formula[position:close + 1], position, close + 1))
			position = close + 1
			continue

		name = _match_known_name(formula, position, names)
		if name is not None:
			tokens.append(Token(PARAM, name, position, position + len(name)))
			position += len(name)
			continue

		for pattern, kind in ((_NUMBER, NUMBER), (_IDENTIFIER, NAME)):
			match = pattern.match(formula, position)
			if match:
				text = match.group()
				if kind == NAME and text.upper() in FORMULA_FUNCTIONS:
					kind = FUNCTION
				tokens.append(Token(kind, text, position, match.end()))
				position = match.end()
				break
		else:
			kind = OP if char in OPERATORS else _SINGLE_CHAR_KINDS.get(char, ERROR)
			tokens.append(Token(kind, char, position, position + 1))
			position += 1

	return tokens


def check_syntax(tokens):
	"""Return human-readable syntax problems for a tokenized formula (empty if none)."""
	issues = []
	frames = []              # 'call' or 'group' for each open parenthesis
	expect_operand = True
	previous = None
	index = 0
	while index < len(tokens):
		token = tokens[index]
		kind = token.kind

		if kind == ERROR:
			# Report the bad token once, then carry on as if it were an operand
			# (a string) or an operator (a stray character) to avoid cascades.
			if token.text[0] in '"\'':
				issues.append('Unterminated text string starting at position {}'.format(token.start + 1))
				expect_operand = False
			else:
				issues.append("Unexpected character '{}'".format(token.text))
				expect_operand = True
		elif kind == FUNCTION and index + 1 < len(tokens) and tokens[index + 1].kind == LPAREN:
			if not expect_operand:
				issues.append("Missing operator before '{}'".format(token.text))
			frames.append('call')
			index += 1
			previous = tokens[index]
			expect_operand = True
			index += 1
			continue
		elif kind in _OPERAND_KINDS or kind == FUNCTION:
			if not expect_operand:
				issues.append("Missing operator before '{}'".format(token.text))
			expect_operand = False
		elif kind == LPAREN:
			if not expect_operand:
				issues.append("Missing operator before '('")
			frames.append('group')
			expect_operand = True
		elif kind == RPAREN:
			if not frames:
				issues.append("Unmatched ')'")
			else:
				frame = frames.pop()
				empty_call = frame == 'call' and previous is not None and previous.kind == LPAREN
				if expect_operand and not empty_call:
					issues.append("Missing value before ')'")
			expect_operand = False
		elif kind == COMMA:
			if not frames or frames[-1] != 'call':
				issues.append("Comma outside a function call")
			elif expect_operand:
				issues.append("Missing value before ','")
			expect_operand = True
		elif kind == OP:
			if expect_operand and token.text not in '+-':
				issues.append("Operator '{}' is missing a value before it".format(token.text))
			expect_operand = True

		previous = token
		index += 1

	if tokens and expect_operand:
		issues.append('Formula ends with an operator or is missing a value')
	if frames:
		issues.append("Unclosed '(' ({} missing)".format(len(frames)))

	seen = set()
	return [issue for issue in issues if not (issue in seen or seen.add(issue))]


def reference_spans(formula, known_names):
	"""Return ``(start, end, name)`` for each known name referenced in ``formula``."""
	return [
		(token.start, token.end, token.text)
		for token in tokenize(formula, known_names)
		if token.kind == PARAM
	]


def scan_references(formula, known_names):
	"""Split a formula's references into ``(known, unknown)`` sets of names."""
	tokens = tokenize(formula, known_names)
	known = {token.text for token in tokens if token.kind == PARAM}
	unknown = {token.text for token in tokens if token.kind == NAME}
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
