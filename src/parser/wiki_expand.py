"""Offline wikitext expander for the LoL Wiki ``SpellData`` effect text.

The Wiki's own parser (``action=parse``) is unreliable (the host currently
returns 403 to non-browser clients), so the summoner-spell ``effect`` text is
expanded **locally** instead. This module is pure and network-free: it takes the
raw wikitext stored in the cached ``SpellData`` Lua modules and returns plain
text.

Template semantics (reverse-engineered from the Wiki's rendered output -- see
``docs`` / the task brief for the three golden strings):

* ``{{as|A|type}}``            -> ``A`` (no leading space)
* ``{{sti|A|B}}`` / ``{{si|A|B}}`` / ``{{tip|A|B}}``
  ``{{bi|A|B}}`` / ``{{ui|A|B}}`` / ``{{sis|A|B}}`` / ``{{ccib|f|B}}``
                               -> the *last* positional arg, **with a leading
                                  space** (the Wiki renders these inline icons)
* ``{{sbc|A}}`` / ``{{g|A}}`` / ``{{tt|A|B}}`` / ``{{ft|A|B}}``
                               -> the *first* positional arg (``tt``/``ft`` keep
                                  the primary text; the second arg is a
                                  tooltip/footnote and is dropped)
* ``{{fd|A}}``                 -> ``A`` (raw)
* ``{{ap|EXPR|round=N}}``      -> the arithmetic value of ``EXPR``
* ``{{pp|...}}``               -> ``min – max （基于等级）`` (see ``_resolve_pp``)
* ``{{plus}}`` -> ``+``, ``{{times}}`` -> ``×``, ``{{degree}}`` -> ``°``

Unknown templates are **never invented**: their positional argument text is kept
(dropping the template name and braces), a ``[WARN]`` is emitted and the name is
tallied so the caller can audit coverage.
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any

# -- safe arithmetic (whitelist via the AST, never ``eval``) -----------------

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def _eval_arith(expr: str, x: float | None = None) -> float:
    """Evaluate a small arithmetic expression, optionally with ``x`` bound.

    Only numeric literals, ``x``, the four operators plus ``^``/``**`` and
    parentheses are permitted; anything else raises ``ValueError``.
    """
    node = ast.parse(expr.replace("^", "**").strip(), mode="eval").body

    def walk(current: ast.AST) -> float:
        if isinstance(current, ast.Constant):
            if isinstance(current.value, (int, float)) and not isinstance(
                current.value, bool
            ):
                return float(current.value)
            raise ValueError("non-numeric constant")
        if isinstance(current, ast.BinOp) and type(current.op) in _BIN_OPS:
            return _BIN_OPS[type(current.op)](
                walk(current.left), walk(current.right)
            )
        if isinstance(current, ast.UnaryOp) and type(current.op) in _UNARY_OPS:
            return _UNARY_OPS[type(current.op)](walk(current.operand))
        if isinstance(current, ast.Name) and current.id == "x":
            if x is None:
                raise ValueError("x used outside a scaling context")
            return float(x)
        raise ValueError("disallowed expression")

    return walk(node)


# -- number formatting -------------------------------------------------------

def _fmt_num(value: float, decimals: int | None = None) -> str:
    """Format a number the way the Wiki does: integers bare, floats trimmed."""
    if value != value:  # NaN guard
        return ""
    if float(value).is_integer():
        return str(int(value))
    if decimals is not None:
        text = f"{value:.{decimals}f}"
    else:
        text = f"{value:.3f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


# -- argument splitting (respects nested ``[[ ]]``) --------------------------

_NAMED_ARG = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_ ]*=")


def _split_args(inner: str) -> list[str]:
    """Split a template body on top-level ``|`` (ignoring ``[[..|..]]``)."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    index = 0
    length = len(inner)
    while index < length:
        two = inner[index:index + 2]
        if two == "[[":
            depth += 1
            current.append(two)
            index += 2
            continue
        if two == "]]":
            depth = max(depth - 1, 0)
            current.append(two)
            index += 2
            continue
        char = inner[index]
        if char == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


# -- ``{{pp}}`` evaluation ---------------------------------------------------

_RANGE_RE = re.compile(r"\s*(.+?)\s+to\s+(.+?)(?:\s+by\s+(.+?))?\s*$")
_THEN_RE = re.compile(r"^(.+?)\s+for\s+(\d+)$")


def _arith_steps(lo: float, hi: float, step: float) -> list[float]:
    if step <= 0:
        step = 1.0
    span = (hi - lo) / step
    if span <= 0:
        return [lo]
    if span > 500:
        # Distance-scaled ranges can span thousands; sample evenly.
        return [lo + (hi - lo) * i / 500 for i in range(501)]
    steps: list[float] = []
    value = lo
    while value <= hi + 1e-9:
        steps.append(value)
        value += step
    return steps or [lo]


def _parse_range(range_part: str | None) -> tuple[float, float, float]:
    if not range_part:
        return 1.0, 18.0, 1.0
    head = range_part.split(";")[0]
    match = _RANGE_RE.match(head)
    if not match:
        return 1.0, 18.0, 1.0
    try:
        lo = _eval_arith(match.group(1))
        hi = _eval_arith(match.group(2))
        step = _eval_arith(match.group(3)) if match.group(3) else 1.0
    except ValueError:
        return 1.0, 18.0, 1.0
    return lo, hi, step


def _sequence(
    value_part: str, level_count: int, warn: list[str]
) -> list[float]:
    """Expand a ``;``-separated value list, resolving ``then +E*x for N`` runs."""
    values: list[float] = []
    for segment in (s.strip() for s in value_part.split(";")):
        if not segment:
            continue
        if segment.lower().startswith("then"):
            body = segment[4:].strip()
            match = _THEN_RE.match(body)
            if match:
                expr, count = match.group(1), int(match.group(2))
            else:
                expr, count = body, None
            base = values[-1] if values else 0.0
            if count is None:
                count = max(level_count - len(values), 1)
            for k in range(1, count + 1):
                try:
                    values.append(base + _eval_arith(expr, x=k))
                except ValueError:
                    warn.append(f"pp-then:{expr}")
                    break
            continue
        if " to " in segment and "x" not in segment:
            lo_text, hi_text = (p.strip() for p in segment.split(" to ", 1))
            try:
                values.extend(
                    [_eval_arith(lo_text), _eval_arith(hi_text)]
                )
            except ValueError:
                warn.append(f"pp-seg:{segment}")
            continue
        try:
            values.append(_eval_arith(segment))
        except ValueError:
            warn.append(f"pp-seg:{segment}")
    return values


def _resolve_pp(
    positional: list[str], named: dict[str, str], warn: list[str]
) -> str:
    value_part = positional[0] if positional else ""
    range_part = positional[1] if len(positional) > 1 else None
    if not value_part:
        return ""

    decimals: int | None = None
    if "round" in named:
        try:
            decimals = int(_eval_arith(named["round"]))
        except ValueError:
            decimals = None

    is_distance = "distance" in named.get("type", "").lower()
    lo, hi, step = _parse_range(range_part)
    # Champion level caps at 18; only distance-scaled ranges may exceed it.
    if not is_distance and hi > 18:
        hi = 18.0
    levels = _arith_steps(lo, hi, step)

    try:
        if ";" in value_part:
            values = _sequence(value_part, len(levels), warn)
        elif " to " in value_part and "x" not in value_part:
            lo_text, hi_text = (
                p.strip() for p in value_part.split(" to ", 1)
            )
            values = [_eval_arith(lo_text), _eval_arith(hi_text)]
        elif "x" in value_part:
            values = [_eval_arith(value_part, x=v) for v in levels]
        else:
            values = [_eval_arith(value_part)]
    except ValueError:
        warn.append(f"pp:{value_part}")
        return value_part

    if not values:
        return value_part

    minimum, maximum = min(values), max(values)
    if abs(maximum - minimum) < 1e-9:
        return _fmt_num(minimum, decimals)
    return (
        f"{_fmt_num(minimum, decimals)} – "
        f"{_fmt_num(maximum, decimals)} （基于等级）"
    )


# -- template resolution -----------------------------------------------------

# Icon-like templates: display their last positional arg, prefixed by a space.
_SPACE_PREFIXED = {"sti", "si", "tip", "bi", "ui", "sis", "ccib"}
# Text templates: display their first positional arg (tooltip/footnote dropped).
_FIRST_ARG = {"as", "sbc", "g", "tt", "ft"}

_UNKNOWN_TEMPLATES: dict[str, int] = {}


def unknown_templates() -> dict[str, int]:
    """Snapshot of unrecognised template names -> occurrence counts."""
    return dict(_UNKNOWN_TEMPLATES)


def _resolve(inner: str, warn: list[str]) -> str:
    parts = _split_args(inner)
    name = parts[0].strip()
    lowered = name.lower()
    raw_args = parts[1:]
    positional = [a for a in raw_args if not _NAMED_ARG.match(a)]
    named: dict[str, str] = {}
    for arg in raw_args:
        if _NAMED_ARG.match(arg):
            key, _, value = arg.partition("=")
            named[key.strip().lower()] = value.strip()

    if lowered in _SPACE_PREFIXED:
        if not positional:
            return ""
        display = positional[-1].strip()
        return f" {display}" if display else ""
    if lowered in _FIRST_ARG:
        return positional[0].strip() if positional else ""
    if lowered == "fd":
        return positional[0].strip() if positional else ""
    if lowered == "ap":
        if not positional:
            return ""
        try:
            return _fmt_num(
                _eval_arith(positional[0]),
                int(_eval_arith(named["round"])) if "round" in named else None,
            )
        except ValueError:
            warn.append(f"ap:{positional[0]}")
            return positional[0].strip()
    if lowered == "pp":
        return _resolve_pp(positional, named, warn)
    if lowered == "plus":
        return "+"
    if lowered == "times":
        return "×"
    if lowered == "degree":
        return "°"

    # Unknown template: keep argument text (never invent), warn and tally.
    _UNKNOWN_TEMPLATES[name] = _UNKNOWN_TEMPLATES.get(name, 0) + 1
    warn.append(f"template:{name}")
    print(f"[WARN] wiki: unknown template '{name}'")
    return " ".join(a.strip() for a in positional if a.strip())


_INNER_TEMPLATE = re.compile(r"\{\{([^{}]*)\}\}")
_LINK_PIPED = re.compile(r"\[\[([^\]|]+)\|([^\]]*)\]\]")
_LINK_PLAIN = re.compile(r"\[\[([^\]]+)\]\]")
_HTML_TAG = re.compile(r"<[^>]+>")
_INLINE_SPACE = re.compile(r"[ \t\u00a0]+")


def expand_wikitext(value: str) -> str:
    """Expand cached Wiki wikitext into plain text (pure, deterministic).

    Templates are expanded innermost-first, then links / emphasis / stray HTML
    are stripped and inline whitespace is collapsed.
    """
    if not value:
        return ""

    warn: list[str] = []
    text = value
    guard = 0
    while "{{" in text and guard < 200:
        expanded = _INNER_TEMPLATE.sub(lambda m: _resolve(m.group(1), warn), text)
        if expanded == text:
            break
        text = expanded
        guard += 1

    text = _LINK_PIPED.sub(lambda m: m.group(2), text)
    text = _LINK_PLAIN.sub(lambda m: m.group(1), text)
    text = text.replace("'''", "").replace("''", "")
    text = _HTML_TAG.sub("", text)
    text = _INLINE_SPACE.sub(" ", text)
    return text.strip()
