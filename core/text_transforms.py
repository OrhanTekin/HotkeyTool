"""
Text transformation functions used by the Transform Text action.

Each entry in TRANSFORMS is a 3-tuple: (display_label, key, fn).
  display_label — shown in the picker UI
  key           — stored in the action value (not currently used; transforms have no config)
  fn            — callable(str) -> str
"""
from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import quote, unquote


# ── helpers ───────────────────────────────────────────────────────────────────

def _sentence_case(s: str) -> str:
    lower = s.lower()
    return re.sub(r'(^|(?<=[.!?])\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), lower)


def _to_words(s: str) -> list[str]:
    """Split a string into words, handling camelCase/PascalCase and separators."""
    s = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', s)
    s = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', s)
    s = re.sub(r'[-_.\s/\\]+', ' ', s)
    return [w for w in s.strip().split(' ') if w]


def _camel_case(s: str) -> str:
    words = _to_words(s)
    if not words:
        return s
    return words[0].lower() + ''.join(w.capitalize() for w in words[1:])


def _pascal_case(s: str) -> str:
    return ''.join(w.capitalize() for w in _to_words(s))


def _snake_case(s: str) -> str:
    return '_'.join(w.lower() for w in _to_words(s))


def _kebab_case(s: str) -> str:
    return '-'.join(w.lower() for w in _to_words(s))


def _add_line_numbers(s: str) -> str:
    # Preserve the original line-ending style so the result pastes correctly
    ending = "\r\n" if "\r\n" in s else "\n"
    lines   = s.splitlines()
    if not lines:
        return s
    width = len(str(len(lines)))
    return ending.join(f'{i + 1:>{width}}. {line}' for i, line in enumerate(lines))


def _dedup_lines(s: str) -> str:
    seen: set[str] = set()
    result = []
    for line in s.splitlines():
        if line not in seen:
            seen.add(line)
            result.append(line)
    return '\n'.join(result)


def _rot13(s: str) -> str:
    result = []
    for c in s:
        if 'a' <= c <= 'z':
            result.append(chr((ord(c) - ord('a') + 13) % 26 + ord('a')))
        elif 'A' <= c <= 'Z':
            result.append(chr((ord(c) - ord('A') + 13) % 26 + ord('A')))
        else:
            result.append(c)
    return ''.join(result)


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _count_text(s: str) -> str:
    """Count characters (excluding line-break chars), words, and lines."""
    chars = len(s.replace('\r', '').replace('\n', ''))
    words = len(s.split())
    lines = len(s.splitlines()) or 1
    c_s = '' if chars == 1 else 's'
    w_s = '' if words == 1 else 's'
    l_s = '' if lines == 1 else 's'
    return f"{chars} character{c_s},  {words} word{w_s},  {lines} line{l_s}"


def _wrap_words(s: str, width: int = 80) -> str:
    import textwrap
    return '\n'.join(
        textwrap.fill(line, width=width) if line.strip() else line
        for line in s.splitlines()
    )


# ── transform table ───────────────────────────────────────────────────────────

TRANSFORMS: list[tuple[str, str]] = [
    ("UPPERCASE",              lambda s: s.upper()),
    ("lowercase",              lambda s: s.lower()),
    ("Title Case",             lambda s: s.title()),
    ("Sentence case",          _sentence_case),
    ("camelCase",              _camel_case),
    ("PascalCase",             _pascal_case),
    ("snake_case",             _snake_case),
    ("kebab-case",             _kebab_case),
    ("CONSTANT_CASE",          lambda s: _snake_case(s).upper()),
    ("Reverse Text",           lambda s: s[::-1]),
    ("Trim Whitespace",        lambda s: s.strip()),
    ("Collapse Spaces",        lambda s: re.sub(r'[ \t]+', ' ', s).strip()),
    ("Remove Line Breaks",     lambda s: re.sub(r'[\r\n]+', ' ', s).strip()),
    ("Add Line Numbers",       _add_line_numbers),
    ("Sort Lines A→Z",         lambda s: '\n'.join(sorted(s.splitlines()))),
    ("Sort Lines Z→A",         lambda s: '\n'.join(sorted(s.splitlines(), reverse=True))),
    ("Remove Duplicate Lines", _dedup_lines),
    ("ROT13",                  _rot13),
    ("URL Encode",             lambda s: quote(s, safe='')),
    ("URL Decode",             lambda s: unquote(s)),
    ("HTML Escape",            html.escape),
    ("HTML Unescape",          html.unescape),
    ("Strip Accents",          _strip_accents),
    ("Word Wrap (80)",         _wrap_words),
    ("Count: chars & words",   _count_text),
]

# Transforms that show an info popup instead of replacing the selected text.
INFO_ONLY_TRANSFORMS: frozenset[str] = frozenset({"Count: chars & words"})
