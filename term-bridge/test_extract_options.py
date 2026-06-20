"""Tests for interactive_prompt.extract_select_options."""
from __future__ import annotations

from interactive_prompt import extract_select_options


def test_basic_menu_with_cursor():
    cap = "Do you want to proceed?\n❯ 1. Yes\n  2. No\n  3. Always allow\n↑↓ navigate · Enter to select"
    assert extract_select_options(cap) == [(1, "Yes"), (2, "No"), (3, "Always allow")]


def test_takes_last_menu_block_starting_at_one():
    cap = "1. first thing\n2. second thing\n\nProceed?\n❯ 1. Approve\n  2. Deny"
    assert extract_select_options(cap) == [(1, "Approve"), (2, "Deny")]


def test_empty_when_no_menu():
    assert extract_select_options("just some running output\nediting files") == []


def test_ignores_block_not_starting_at_one():
    # a stray "3. ..." with no 1. is not a menu
    assert extract_select_options("see note 3. foobar here") == []
