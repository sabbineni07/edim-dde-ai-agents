"""Tests for text diff helpers."""

from shared.utils.text_diff import unified_diff_text


def test_unified_diff_text_shows_changes():
    diff = unified_diff_text("line one\n", "line two\n", from_label="a", to_label="b")
    assert "-line one" in diff
    assert "+line two" in diff


def test_unified_diff_text_empty_when_identical():
    assert unified_diff_text("same", "same", from_label="a", to_label="b") == ""
