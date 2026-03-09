"""Tests for second_brain.graph module."""

import pytest
from second_brain import config
from second_brain.graph import (
    _luminance,
    _pick_colors,
    check_links,
    generate_dot,
    get_backlinks,
    scan_brain,
)


class TestScanBrain:
    """Brain scanning for nodes and edges."""

    def test_scan_empty_dir(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges, external_nodes = scan_brain()
            assert nodes == []
            assert edges == []
            assert external_nodes == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_single_file_no_links(self, tmp_path):
        (tmp_path / "notes.md").write_text("# Notes\n\nSome content here.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges, external_nodes = scan_brain()
            assert nodes == ["notes"]
            assert edges == []
            assert external_nodes == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_wikilinks(self, tmp_path):
        (tmp_path / "alpha.md").write_text("Link to [[beta]] here.")
        (tmp_path / "beta.md").write_text("# Beta\n\nContent.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges, external_nodes = scan_brain()
            assert "alpha" in nodes
            assert "beta" in nodes
            assert ("alpha", "beta") in edges
            assert external_nodes == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_excludes_dump(self, tmp_path):
        (tmp_path / "dump.md").write_text("Raw dump content.")
        (tmp_path / "notes.md").write_text("# Notes")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges, external_nodes = scan_brain()
            assert "dump" not in nodes
            assert "notes" in nodes
            assert external_nodes == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_ignores_invalid_links(self, tmp_path):
        """Links to non-existent files create edges to external nodes."""
        (tmp_path / "alpha.md").write_text("Link to [[nonexistent]].")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges, external_nodes = scan_brain()
            assert nodes == ["alpha"]
            assert ("alpha", "nonexistent") in edges  # edge to external node
            assert "nonexistent" in external_nodes
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_deduplicates_edges(self, tmp_path):
        (tmp_path / "alpha.md").write_text("[[beta]] and again [[beta]].")
        (tmp_path / "beta.md").write_text("Content.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges, external_nodes = scan_brain()
            assert edges.count(("alpha", "beta")) == 1
            assert external_nodes == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_self_links_excluded(self, tmp_path):
        (tmp_path / "alpha.md").write_text("Self link [[alpha]].")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges, external_nodes = scan_brain()
            assert edges == []
            assert external_nodes == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_strips_md_extension_from_link(self, tmp_path):
        (tmp_path / "alpha.md").write_text("Link to [[beta.md]].")
        (tmp_path / "beta.md").write_text("Content.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges, external_nodes = scan_brain()
            assert ("alpha", "beta") in edges
            assert external_nodes == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_scan_detects_external_wikilinks(self, tmp_path):
        """Wiki links to topics without matching files are external."""
        (tmp_path / "notes.md").write_text("Learn about [[black cookbook]] and [[DNS]].")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            nodes, edges, external_nodes = scan_brain()
            assert "notes" in nodes
            assert "black cookbook" in external_nodes
            assert "DNS" in external_nodes
            # Edges should connect notes to external topics
            assert ("notes", "black cookbook") in edges
            assert ("notes", "DNS") in edges
        finally:
            config.BRAIN_DIR = old_dir


class TestGenerateDot:
    """DOT string generation."""

    def test_dot_starts_with_digraph(self):
        dot = generate_dot(["a", "b"], [("a", "b")], [])
        assert dot.startswith("digraph SecondBrain")

    def test_dot_contains_nodes(self):
        dot = generate_dot(["alpha", "beta"], [], [])
        assert '"alpha"' in dot
        assert '"beta"' in dot

    def test_dot_contains_edges(self):
        dot = generate_dot(["a", "b"], [("a", "b")], [])
        assert '"a" -> "b"' in dot

    def test_dot_transparent_bg(self):
        dot = generate_dot(["a"], [], [])
        assert "transparent" in dot

    def test_dot_label_truncation(self):
        long_name = "a" * 20
        dot = generate_dot([long_name], [], [])
        # Label should be truncated to 14 chars (12 + "..")
        assert '.."' in dot  # truncated label ends with .."

    def test_dot_uses_neato_layout(self):
        dot = generate_dot(["a"], [], [])
        assert "neato" in dot

    def test_dot_contains_external_nodes(self):
        dot = generate_dot(["a"], [], ["black cookbook", "DNS"])
        assert '"black cookbook"' in dot
        assert '"DNS"' in dot
        assert "dashed" in dot  # external nodes should have dashed style


class TestGetBacklinks:
    """Backlinks detection."""

    def test_no_backlinks(self, tmp_path):
        (tmp_path / "alpha.md").write_text("# Alpha\n\nNo links here.")
        (tmp_path / "beta.md").write_text("# Beta\n\nStandalone content.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            backlinks = get_backlinks("alpha.md")
            assert backlinks == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_single_backlink(self, tmp_path):
        (tmp_path / "alpha.md").write_text("# Alpha\n\nContent.")
        (tmp_path / "beta.md").write_text("See [[alpha]] for more.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            backlinks = get_backlinks("alpha.md")
            assert backlinks == ["beta.md"]
        finally:
            config.BRAIN_DIR = old_dir

    def test_multiple_backlinks(self, tmp_path):
        (tmp_path / "alpha.md").write_text("# Alpha\n\nContent.")
        (tmp_path / "beta.md").write_text("See [[alpha]] for more.")
        (tmp_path / "gamma.md").write_text("Also check [[alpha]].")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            backlinks = get_backlinks("alpha.md")
            assert sorted(backlinks) == ["beta.md", "gamma.md"]
        finally:
            config.BRAIN_DIR = old_dir

    def test_backlink_with_display_text(self, tmp_path):
        (tmp_path / "alpha.md").write_text("# Alpha\n\nContent.")
        (tmp_path / "beta.md").write_text("See [[alpha|this page]] for more.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            backlinks = get_backlinks("alpha.md")
            assert backlinks == ["beta.md"]
        finally:
            config.BRAIN_DIR = old_dir

    def test_backlink_case_insensitive(self, tmp_path):
        (tmp_path / "alpha.md").write_text("# Alpha\n\nContent.")
        (tmp_path / "beta.md").write_text("See [[Alpha]] for more.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            backlinks = get_backlinks("alpha.md")
            assert backlinks == ["beta.md"]
        finally:
            config.BRAIN_DIR = old_dir

    def test_backlink_excludes_dump(self, tmp_path):
        (tmp_path / "alpha.md").write_text("# Alpha\n\nContent.")
        (tmp_path / "dump.md").write_text("Raw [[alpha]] dump.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            backlinks = get_backlinks("alpha.md")
            assert backlinks == []  # dump.md should be excluded
        finally:
            config.BRAIN_DIR = old_dir


class TestCheckLinks:
    """Link checking for broken/orphaned links."""

    def test_empty_brain(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            result = check_links()
            assert result["external_links"] == {}
            assert result["orphaned_files"] == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_no_external_links(self, tmp_path):
        (tmp_path / "alpha.md").write_text("Link to [[beta]].")
        (tmp_path / "beta.md").write_text("# Beta")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            result = check_links()
            assert result["external_links"] == {}
            assert result["orphaned_files"] == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_detects_external_links(self, tmp_path):
        (tmp_path / "notes.md").write_text("Learn about [[DNS]] and [[black cookbook]].")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            result = check_links()
            assert "DNS" in result["external_links"]
            assert "black cookbook" in result["external_links"]
            assert result["external_links"]["DNS"] == ["notes.md"]
        finally:
            config.BRAIN_DIR = old_dir

    def test_detects_orphaned_files(self, tmp_path):
        (tmp_path / "alpha.md").write_text("Link to [[beta]].")
        (tmp_path / "beta.md").write_text("# Beta")
        (tmp_path / "orphan.md").write_text("# Orphan\n\nNo links here.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            result = check_links()
            assert "orphan" in result["orphaned_files"]
            assert "alpha" not in result["orphaned_files"]  # has outgoing link
            assert "beta" not in result["orphaned_files"]  # has incoming link
        finally:
            config.BRAIN_DIR = old_dir

    def test_external_links_grouped_by_file(self, tmp_path):
        (tmp_path / "notes1.md").write_text("See [[DNS]].")
        (tmp_path / "notes2.md").write_text("Also [[DNS]] is important.")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            result = check_links()
            assert result["external_links"]["DNS"] == ["notes1.md", "notes2.md"]
        finally:
            config.BRAIN_DIR = old_dir


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
