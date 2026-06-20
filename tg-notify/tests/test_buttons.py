"""Tests for parse_button_spec — --buttons JSON → rows of (label, callback_data)."""
from __future__ import annotations

import pytest

from tg_notify.cli import parse_button_spec


def test_flat_pairs_become_one_button_per_row():
    rows = parse_button_spec('[["1. Yes", "sel:72:1:1"], ["2. No", "sel:72:1:2"]]')
    assert rows == [[("1. Yes", "sel:72:1:1")], [("2. No", "sel:72:1:2")]]


def test_nested_rows_kept_as_rows():
    rows = parse_button_spec('[[["a", "x"], ["b", "y"]]]')
    assert rows == [[("a", "x"), ("b", "y")]]


def test_non_list_raises():
    with pytest.raises(ValueError):
        parse_button_spec('{"a": 1}')


def test_invalid_json_raises():
    with pytest.raises(ValueError):
        parse_button_spec("not json")
