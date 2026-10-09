"""A tiny, dependency-free parser for the Lua *table literal* subset used by
League of Legends Wiki data modules.

The Wiki modules we consume (``Module:SpellData/data`` and its zh-CN sandbox)
are essentially one big ``return { ... }`` table. Rather than pull in a full
Lua interpreter we parse just enough:

* ``["key"] = value`` and bare ``key = value`` entries;
* nested tables (``maps = { ["sr"] = true, ... }``);
* double- and single-quoted strings with the usual escape sequences;
* numbers (int / float / scientific), booleans, ``nil``;
* ``--`` line comments and ``--[[ ... ]]`` block comments;
* arbitrary mixing of tabs / spaces / newlines.

Anything unexpected raises :class:`LuaParseError` so a malformed module fails
loudly in tests instead of silently returning half the data.
"""

from __future__ import annotations

import re
from typing import Any


class LuaParseError(ValueError):
    """Raised when a Lua literal cannot be parsed."""


_KEYWORD_VALUES: dict[str, Any] = {"true": True, "false": False, "nil": None}

_IDENT_START = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
)
_IDENT_BODY = _IDENT_START | frozenset("0123456789")

_NUMBER_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")

_ESCAPES = {
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
    '"': '"',
    "'": "'",
    "\n": "\n",
}


class _LuaReader:
    """Cursor over Lua source with the parsing primitives we need."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    # -- low level --------------------------------------------------------

    def _peek(self) -> str:
        return self.text[self.pos] if self.pos < self.length else ""

    def _skip_space_and_comments(self) -> None:
        while self.pos < self.length:
            ch = self.text[self.pos]
            if ch in " \t\r\n\f\v":
                self.pos += 1
                continue
            if ch == "-" and self.text.startswith("--", self.pos):
                self._skip_comment()
                continue
            break

    def _skip_comment(self) -> None:
        # Block comment ``--[[ ... ]]`` (also the ``--[==[ ... ]==]`` form).
        if self.text.startswith("--[", self.pos):
            opener = self.text.find("[", self.pos + 2)
            if opener != -1:
                level = 0
                cursor = opener + 1
                while cursor < self.length and self.text[cursor] == "=":
                    level += 1
                    cursor += 1
                if cursor < self.length and self.text[cursor] == "[":
                    closer = "]" + "=" * level + "]"
                    end = self.text.find(closer, cursor + 1)
                    self.pos = self.length if end < 0 else end + len(closer)
                    return
        # Line comment: run to end of line.
        newline = self.text.find("\n", self.pos)
        self.pos = self.length if newline < 0 else newline + 1

    def _expect(self, char: str) -> None:
        if self._peek() != char:
            raise LuaParseError(
                f"expected {char!r} at {self.pos}, got {self._peek()!r}"
            )
        self.pos += 1

    # -- grammar ----------------------------------------------------------

    def parse(self) -> Any:
        self._skip_space_and_comments()
        # Tolerate the optional leading ``return`` keyword.
        if self.text.startswith("return", self.pos):
            after = self.pos + len("return")
            if after >= self.length or not _is_ident_body(self.text[after]):
                self.pos = after
        value = self._parse_value()
        return value

    def _parse_value(self) -> Any:
        self._skip_space_and_comments()
        ch = self._peek()
        if ch == "":
            raise LuaParseError("unexpected end of input")
        if ch == "{":
            return self._parse_table()
        if ch in "\"'":
            return self._parse_string()
        if ch == "[":
            if self.text.startswith("[[", self.pos):
                return self._parse_long_string()
            raise LuaParseError(f"unexpected '[' at {self.pos}")
        if ch == "-" or ch.isdigit() or ch == ".":
            return self._parse_number()
        if ch in _IDENT_START:
            word = self._parse_identifier()
            if word in _KEYWORD_VALUES:
                return _KEYWORD_VALUES[word]
            return word  # bareword fallback ("unknown" / enum-like tokens)
        raise LuaParseError(f"unexpected char {ch!r} at {self.pos}")

    def _parse_table(self) -> Any:
        self._expect("{")
        assoc: dict[Any, Any] = {}
        array: list[Any] = []
        while True:
            self._skip_space_and_comments()
            ch = self._peek()
            if ch == "}":
                self.pos += 1
                break
            if ch == "":
                raise LuaParseError("unterminated table")

            if ch == "[" and not self.text.startswith("[[", self.pos):
                self.pos += 1
                key = self._parse_value()
                self._skip_space_and_comments()
                self._expect("]")
                self._skip_space_and_comments()
                self._expect("=")
                assoc[key] = self._parse_value()
            elif ch in _IDENT_START:
                save = self.pos
                word = self._parse_identifier()
                self._skip_space_and_comments()
                if self._peek() == "=":
                    self.pos += 1
                    assoc[word] = self._parse_value()
                else:
                    # A positional value that merely starts with a letter.
                    self.pos = save
                    array.append(self._parse_value())
            else:
                array.append(self._parse_value())

            self._skip_space_and_comments()
            nxt = self._peek()
            if nxt in ",;":
                self.pos += 1
                continue
            if nxt == "}":
                self.pos += 1
                break
            if nxt == "":
                raise LuaParseError("unterminated table")
            raise LuaParseError(f"expected ',' or '}}' at {self.pos}")

        if array and not assoc:
            return array
        if array:
            for index, value in enumerate(array, start=1):
                assoc.setdefault(index, value)
        return assoc

    def _parse_string(self) -> str:
        quote = self.text[self.pos]
        self.pos += 1
        out: list[str] = []
        while True:
            if self.pos >= self.length:
                raise LuaParseError("unterminated string")
            ch = self.text[self.pos]
            if ch == quote:
                self.pos += 1
                break
            if ch == "\\":
                self.pos += 1
                if self.pos >= self.length:
                    raise LuaParseError("unterminated escape")
                esc = self.text[self.pos]
                if esc.isdigit():
                    digits = ""
                    while (
                        len(digits) < 3
                        and self.pos < self.length
                        and self.text[self.pos].isdigit()
                    ):
                        digits += self.text[self.pos]
                        self.pos += 1
                    out.append(chr(int(digits) & 0xFF))
                    continue
                out.append(_ESCAPES.get(esc, esc))
                self.pos += 1
                continue
            out.append(ch)
            self.pos += 1
        return "".join(out)

    def _parse_long_string(self) -> str:
        end = self.text.find("]]", self.pos + 2)
        if end < 0:
            raise LuaParseError("unterminated long string")
        value = self.text[self.pos + 2 : end]
        self.pos = end + 2
        return value

    def _parse_number(self) -> Any:
        match = _NUMBER_RE.match(self.text, self.pos)
        if not match:
            raise LuaParseError(f"invalid number at {self.pos}")
        token = match.group(0)
        self.pos = match.end()
        if any(ch in token for ch in ".eE"):
            return float(token)
        return int(token)

    def _parse_identifier(self) -> str:
        start = self.pos
        while self.pos < self.length and _is_ident_body(self.text[self.pos]):
            self.pos += 1
        if self.pos == start:
            raise LuaParseError(f"expected identifier at {self.pos}")
        return self.text[start : self.pos]


def _is_ident_body(ch: str) -> bool:
    return ch in _IDENT_BODY


def parse_lua(text: str) -> Any:
    """Parse a Lua table literal (optionally prefixed with ``return``).

    Returns ``dict`` for associative tables, ``list`` for pure positional
    tables and Python scalars for string / number / boolean / ``None`` values.
    """
    if text is None:
        raise LuaParseError("no input")
    return _LuaReader(text).parse()
