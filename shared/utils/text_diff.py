"""Unified text diff helpers."""

from __future__ import annotations

import difflib


def unified_diff_text(before: str, after: str, *, from_label: str, to_label: str) -> str:
    """Return a unified diff string; empty when texts are identical."""
    before_lines = (before or "").splitlines(keepends=True)
    after_lines = (after or "").splitlines(keepends=True)
    if before_lines == after_lines:
        return ""
    diff_lines = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=from_label,
        tofile=to_label,
        lineterm="",
    )
    return "\n".join(diff_lines)
