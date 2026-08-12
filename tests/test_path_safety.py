"""Tests for CodeQL-recognized path containment helpers."""

import os
from pathlib import Path

from src.path_safety import safe_path_under


def test_safe_path_under_allows_basename(tmp_path: Path):
    target = safe_path_under(tmp_path, "ynWS968AAAAJ.json")
    assert target is not None
    assert target == (tmp_path / "ynWS968AAAAJ.json").resolve()


def test_safe_path_under_rejects_parent_segment(tmp_path: Path):
    assert safe_path_under(tmp_path, "..") is None
    assert safe_path_under(tmp_path, "..", "etc") is None


def test_safe_path_under_rejects_nested_separators(tmp_path: Path):
    assert safe_path_under(tmp_path, "a/b.json") is None
    # Backslash must be rejected on Linux too (not only when os.altsep is set).
    assert safe_path_under(tmp_path, "a\\b.json") is None
    assert safe_path_under(tmp_path, r"a\b.json") is None


def test_safe_path_under_rejects_absolute_segment(tmp_path: Path):
    abs_seg = os.path.abspath(os.sep)
    assert safe_path_under(tmp_path, abs_seg) is None
