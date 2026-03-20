"""Keyword highlighting engine for FedoraXTerm.

Provides :class:`KeywordHighlighter` for matching user-defined patterns
in terminal output and producing Pango-markup text suitable for GTK
rendering – mirroring SecureCRT's keyword-highlight feature with
built-in presets for common use-cases.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Dataclass ────────────────────────────────────────────────────────


@dataclass
class KeywordRule:
    """A single keyword-highlight rule.

    Attributes
    ----------
    pattern:
        Text or regex pattern to match.
    foreground:
        Foreground colour as a hex string (e.g. ``#ff0000``).
    background:
        Optional background colour as a hex string.
    bold:
        Render matched text in bold.
    underline:
        Render matched text with an underline.
    whole_word:
        Match only whole words (word-boundary anchored).
    case_sensitive:
        Whether matching is case-sensitive.
    is_regex:
        Treat *pattern* as a regular expression.
    """

    pattern: str
    foreground: str = "#ff0000"
    background: str = ""
    bold: bool = False
    underline: bool = False
    whole_word: bool = False
    case_sensitive: bool = True
    is_regex: bool = False


# ── Built-in presets ─────────────────────────────────────────────────

_PRESETS: dict[str, list[KeywordRule]] = {
    "Errors": [
        KeywordRule(pattern="error", foreground="#ef2929", bold=True, case_sensitive=False),
        KeywordRule(pattern="fail", foreground="#ef2929", bold=True, case_sensitive=False),
        KeywordRule(pattern="fatal", foreground="#ef2929", bold=True, case_sensitive=False),
    ],
    "Warnings": [
        KeywordRule(pattern="warn", foreground="#fce94f", case_sensitive=False),
        KeywordRule(pattern="warning", foreground="#fce94f", case_sensitive=False),
    ],
    "Success": [
        KeywordRule(pattern="ok", foreground="#8ae234", case_sensitive=False),
        KeywordRule(pattern="success", foreground="#8ae234", case_sensitive=False),
        KeywordRule(pattern="passed", foreground="#8ae234", case_sensitive=False),
    ],
    "Network": [
        KeywordRule(
            pattern=r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
            foreground="#34e2e2",
            is_regex=True,
        ),
        KeywordRule(
            pattern=r":\d{1,5}\b",
            foreground="#729fcf",
            is_regex=True,
        ),
    ],
}

# ── Compiled rule wrapper ────────────────────────────────────────────


@dataclass
class _CompiledRule:
    """Internal: a rule together with its compiled regex."""

    rule: KeywordRule
    regex: re.Pattern[str] = field(default=None, repr=False)  # type: ignore[assignment]


# ── Highlighter ──────────────────────────────────────────────────────


class KeywordHighlighter:
    """Match keyword rules against text and produce Pango markup.

    Rules are evaluated in the order they were added.  The first
    matching rule wins for any given character position.
    """

    def __init__(self) -> None:
        self.rules: list[KeywordRule] = []
        self._compiled: list[_CompiledRule] = []

    # ── Rule management ──────────────────────────────────────────

    def add_rule(self, rule: KeywordRule) -> None:
        """Append a rule and recompile."""
        self.rules.append(rule)
        self.compile_rules()

    def remove_rule(self, index: int) -> None:
        """Remove the rule at *index* and recompile.

        Raises
        ------
        IndexError
            If *index* is out of range.
        """
        del self.rules[index]
        self.compile_rules()

    def update_rule(self, index: int, rule: KeywordRule) -> None:
        """Replace the rule at *index* with *rule* and recompile.

        Raises
        ------
        IndexError
            If *index* is out of range.
        """
        self.rules[index] = rule
        self.compile_rules()

    # ── Compilation ──────────────────────────────────────────────

    def compile_rules(self) -> None:
        """Pre-compile all rule patterns into :class:`re.Pattern` objects."""
        compiled: list[_CompiledRule] = []
        for rule in self.rules:
            try:
                pattern = rule.pattern if rule.is_regex else re.escape(rule.pattern)
                if rule.whole_word and not rule.is_regex:
                    pattern = rf"\b{pattern}\b"
                flags = 0 if rule.case_sensitive else re.IGNORECASE
                regex = re.compile(pattern, flags)
                compiled.append(_CompiledRule(rule=rule, regex=regex))
            except re.error:
                logger.warning(
                    "Invalid regex in keyword rule %r – skipping.",
                    rule.pattern,
                )
        self._compiled = compiled

    # ── Matching ─────────────────────────────────────────────────

    def find_matches(
        self,
        text: str,
    ) -> list[tuple[int, int, KeywordRule]]:
        """Find all keyword matches in *text*.

        Returns a list of ``(start, end, rule)`` tuples sorted by
        position.  Overlapping matches are resolved in favour of the
        first (highest-priority) rule.
        """
        occupied: set[int] = set()
        matches: list[tuple[int, int, KeywordRule]] = []

        for cr in self._compiled:
            for m in cr.regex.finditer(text):
                start, end = m.start(), m.end()
                if any(pos in occupied for pos in range(start, end)):
                    continue
                occupied.update(range(start, end))
                matches.append((start, end, cr.rule))

        matches.sort(key=lambda t: t[0])
        return matches

    # ── Pango markup ─────────────────────────────────────────────

    def get_pango_markup(self, text: str) -> str:
        """Return *text* with Pango markup applied for matched keywords.

        Characters that are not matched by any rule are XML-escaped but
        otherwise unmodified.
        """
        from xml.sax.saxutils import escape as xml_escape

        matches = self.find_matches(text)
        if not matches:
            return xml_escape(text)

        parts: list[str] = []
        prev_end = 0

        for start, end, rule in matches:
            # Unmatched gap before this match.
            if start > prev_end:
                parts.append(xml_escape(text[prev_end:start]))

            attrs: list[str] = [f'foreground="{rule.foreground}"']
            if rule.background:
                attrs.append(f'background="{rule.background}"')
            if rule.bold:
                attrs.append('weight="bold"')
            if rule.underline:
                attrs.append('underline="single"')

            attr_str = " ".join(attrs)
            parts.append(f"<span {attr_str}>{xml_escape(text[start:end])}</span>")
            prev_end = end

        # Trailing unmatched text.
        if prev_end < len(text):
            parts.append(xml_escape(text[prev_end:]))

        return "".join(parts)

    # ── Presets ──────────────────────────────────────────────────

    @staticmethod
    def load_preset(name: str) -> list[KeywordRule]:
        """Return a copy of the built-in preset rules for *name*.

        Available presets: ``Errors``, ``Warnings``, ``Success``,
        ``Network``.

        Raises
        ------
        KeyError
            If *name* does not match a known preset.
        """
        if name not in _PRESETS:
            raise KeyError(
                f"Unknown preset {name!r}. "
                f"Available: {list(_PRESETS)}."
            )
        # Return copies so callers cannot mutate the built-in list.
        return [
            KeywordRule(
                pattern=r.pattern,
                foreground=r.foreground,
                background=r.background,
                bold=r.bold,
                underline=r.underline,
                whole_word=r.whole_word,
                case_sensitive=r.case_sensitive,
                is_regex=r.is_regex,
            )
            for r in _PRESETS[name]
        ]
