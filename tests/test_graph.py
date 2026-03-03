"""Tests for second_brain.graph module."""

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from second_brain import config
from second_brain.graph import scan_brain, generate_dot, _pick_colors, _luminance


class TestScanBrain:
    """Brain scanning for nodes and edges."""

    def test_scan_empty_dir(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges = scan_brain()
            assert nodes == []
            assert edges == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_single_file_no_links(self, tmp_path):
        (tmp_path / "notes.md").write_text("# Notes\n\nSome content here.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges = scan_brain()
            assert nodes == ["notes"]
            assert edges == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_wikilinks(self, tmp_path):
        (tmp_path / "alpha.md").write_text("Link to [[beta]] here.")
        (tmp_path / "beta.md").write_text("# Beta\n\nContent.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges = scan_brain()
            assert "alpha" in nodes
            assert "beta" in nodes
            assert ("alpha", "beta") in edges
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_excludes_dump(self, tmp_path):
        (tmp_path / "dump.md").write_text("Raw dump content.")
        (tmp_path / "notes.md").write_text("# Notes")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges = scan_brain()
            assert "dump" not in nodes
            assert "notes" in nodes
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_ignores_invalid_links(self, tmp_path):
        """Links to non-existent files are excluded."""
        (tmp_path / "alpha.md").write_text("Link to [[nonexistent]].")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges = scan_brain()
            assert nodes == ["alpha"]
            assert edges == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_deduplicates_edges(self, tmp_path):
        (tmp_path / "alpha.md").write_text("[[beta]] and again [[beta]].")
        (tmp_path / "beta.md").write_text("Content.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges = scan_brain()
            assert edges.count(("alpha", "beta")) == 1
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_self_links_excluded(self, tmp_path):
        (tmp_path / "alpha.md").write_text("Self link [[alpha]].")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges = scan_brain()
            assert edges == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_strips_md_extension_from_link(self, tmp_path):
        (tmp_path / "alpha.md").write_text("Link to [[beta.md]].")
        (tmp_path / "beta.md").write_text("Content.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges = scan_brain()
            assert ("alpha", "beta") in edges
        finally:
            config.BRAIN_DIR = old_dir


class TestGenerateDot:
    """DOT string generation."""

    def test_dot_starts_with_digraph(self):
        dot = generate_dot(["a", "b"], [("a", "b")])
        assert dot.startswith("digraph SecondBrain")

    def test_dot_contains_nodes(self):
        dot = generate_dot(["alpha", "beta"], [])
        assert '"alpha"' in dot
        assert '"beta"' in dot

    def test_dot_contains_edges(self):
        dot = generate_dot(["a", "b"], [("a", "b")])
        assert '"a" -> "b"' in dot

    def test_dot_transparent_bg(self):
        dot = generate_dot(["a"], [])
        assert "transparent" in dot

    def test_dot_label_truncation(self):
        long_name = "a" * 20
        dot = generate_dot([long_name], [])
        # Label should be truncated to 14 chars (12 + "..")
        assert '.."' in dot  # truncated label ends with .."

    def test_dot_uses_neato_layout(self):
        dot = generate_dot(["a"], [])
        assert "neato" in dot


class TestPickColors:
    """Color picking from pywal."""

    def test_returns_required_keys(self):
        colors = _pick_colors()
        assert "bg" in colors
        assert "fg" in colors
        assert "node_colors" in colors
        assert "edge_color" in colors

    def test_colors_are_hex(self):
        colors = _pick_colors()
        assert colors["bg"].startswith("#")
        assert colors["fg"].startswith("#")

    def test_node_colors_not_empty(self):
        colors = _pick_colors()
        assert len(colors["node_colors"]) > 0


class TestLuminance:
    """Color luminance calculation."""

    def test_black_luminance(self):
        assert _luminance("#000000") == pytest.approx(0.0)

    def test_white_luminance(self):
        assert _luminance("#ffffff") == pytest.approx(1.0)

    def test_mid_luminance(self):
        lum = _luminance("#808080")
        assert 0.3 < lum < 0.7

    def test_short_hex_returns_half(self):
        assert _luminance("#fff") == 0.5
