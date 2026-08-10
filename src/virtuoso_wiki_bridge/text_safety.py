"""Make untrusted text safe to display in terminals and generated context."""

from __future__ import annotations

import unicodedata

_BIDI_CONTROLS = frozenset(
    {
        0x061C,
        0x200E,
        0x200F,
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
        0x2066,
        0x2067,
        0x2068,
        0x2069,
    }
)


def _visible_escape(codepoint: int) -> str:
    width = 4 if codepoint <= 0xFFFF else 8
    return f"\\u{codepoint:0{width}x}"


def sanitize_untrusted_text(value: object) -> str:
    """Escape terminal controls while preserving ordinary text/newlines/tabs."""

    pieces: list[str] = []
    for char in str(value):
        codepoint = ord(char)
        if char in {"\n", "\t"}:
            pieces.append(char)
            continue
        category = unicodedata.category(char)
        if category in {"Cc", "Cs"} or codepoint in _BIDI_CONTROLS:
            pieces.append(_visible_escape(codepoint))
        else:
            pieces.append(char)
    return "".join(pieces)


def sanitize_untrusted_field(value: object) -> str:
    """Escape every control character in a single-line field."""

    return sanitize_untrusted_text(value).replace("\n", "\\u000a").replace("\t", "\\u0009")
