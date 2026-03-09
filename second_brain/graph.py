"""The Graph Engine - scan brain, extract wikilinks, render Graphviz."""

import re
import subprocess
import tempfile
from pathlib import Path

from . import config
from .plugins import get_manager


def scan_brain() -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """Scan the brain directory for nodes and edges.

    Returns:
        (nodes, edges, external_nodes) where nodes are filenames (without .md),
        edges are (source, target) tuples based on [[wikilinks]] (including
        edges to external Wikipedia topics), and external_nodes are wiki links
        that don't match internal files (potential Wikipedia topics).
    """
    pm = get_manager()

    # --- Hook: before_scan_brain ---
    pm.dispatch_before_scan_brain()

    brain_dir = config.BRAIN_DIR
    nodes: list[str] = []
    edges: list[tuple[str, str]] = []
    external_nodes: set[str] = set()
    link_pattern = re.compile(r"\[\[([^\]]+)\]\]")

    md_files = sorted(brain_dir.glob("*.md"))
    valid_names = {f.stem for f in md_files}

    for md_file in md_files:
        if md_file.name == "dump.md":
            continue
        source = md_file.stem
        nodes.append(source)

        content = md_file.read_text()
        for match in link_pattern.finditer(content):
            target = match.group(1).strip()
            # Normalize: remove .md extension if present
            if target.endswith(".md"):
                target = target[:-3]
            if target in valid_names and target != source:
                edges.append((source, target))
            elif target not in valid_names:
                # External wiki link - create edge to external node
                external_nodes.add(target)
                edges.append((source, target))

    # Deduplicate edges
    edges = list(set(edges))

    # --- Hook: after_scan_brain (mutating) ---
    nodes, edges = pm.dispatch_after_scan_brain(nodes, edges)

    # --- Hook: after_scan_brain_external (mutating) ---
    external_nodes = pm.dispatch_after_scan_brain_external(external_nodes)

    return nodes, edges, list(external_nodes)


def get_backlinks(target_file: str) -> list[str]:
    """Find all files that link to the given target file.

    Args:
        target_file: Filename (with or without .md extension)

    Returns:
        List of filenames that contain wiki links to the target.
    """
    brain_dir = config.BRAIN_DIR
    target = target_file.removesuffix(".md")
    backlinks: list[str] = []
    # Pattern matches [[target]] or [[target|label]]
    link_pattern = re.compile(rf"\[\[({re.escape(target)})(?:\|[^\]]+)?\]\]", re.IGNORECASE)

    for md_file in brain_dir.glob("*.md"):
        if md_file.name == "dump.md":
            continue
        content = md_file.read_text()
        if link_pattern.search(content):
            backlinks.append(md_file.name)

    return backlinks


def check_links() -> dict:
    """Check for broken and orphaned links in the brain.

    Returns:
        Dict with:
        - "external_links": dict of {topic: [files that link to it]}
        - "orphaned_files": list of files with no incoming or outgoing links
        - "broken_internal": list of wiki links to files that don't exist
    """
    brain_dir = config.BRAIN_DIR
    link_pattern = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

    md_files = sorted(f for f in brain_dir.glob("*.md") if f.name != "dump.md")
    valid_names = {f.stem for f in md_files}

    external_links: dict[str, list[str]] = {}  # topic -> [files linking to it]
    outgoing_links: dict[str, set[str]] = {}  # file -> set of targets
    incoming_links: dict[str, set[str]] = {}  # file -> set of sources

    for md_file in md_files:
        source = md_file.stem
        outgoing_links[source] = set()
        incoming_links.setdefault(source, set())

        content = md_file.read_text()
        for match in link_pattern.finditer(content):
            target = match.group(1).strip()
            if target.endswith(".md"):
                target = target[:-3]

            if target in valid_names and target != source:
                # Internal link
                outgoing_links[source].add(target)
                incoming_links.setdefault(target, set()).add(source)
            elif target not in valid_names:
                # External/broken link
                external_links.setdefault(target, []).append(md_file.name)

    # Find orphaned files (no incoming and no outgoing internal links)
    orphaned_files = [
        name
        for name in outgoing_links
        if not outgoing_links[name] and not incoming_links.get(name, set())
    ]

    return {
        "external_links": external_links,
        "orphaned_files": sorted(orphaned_files),
        "broken_internal": [],  # Could be added if we want to track links to deleted files
    }


def _pick_colors() -> dict:
    """Pick colors from pywal for graph styling."""
    wal = config.get_wal_colors()
    colors = wal.get("colors", {})

    # Find non-empty colors for variety
    available = []
    for i in range(1, 16):
        c = colors.get(f"color{i}", "")
        if c:
            available.append(c)

    if not available:
        available = ["#cc241d", "#98971a", "#d79921", "#458588", "#b16286", "#689d6a", "#fb4934"]

    bg = colors.get("color0", "#1d2021")
    fg = colors.get("color15", "#ebdbb2")

    return {
        "bg": bg,
        "fg": fg,
        "node_colors": available,
        "edge_color": fg + "88",  # semi-transparent foreground
    }


def _luminance(hex_color: str) -> float:
    """Calculate relative luminance of a hex color."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) < 6:
        return 0.5
    r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def generate_dot(
    nodes: list[str], edges: list[tuple[str, str]], external_nodes: list[str] | None = None
) -> str:
    """Generate a Graphviz DOT string with pywal-themed styling.

    The graph is sized to fit the RIGHT 60% of the screen,
    leaving the left 40% free for the todo overlay.

    External nodes (wiki links without matching files) are shown with
    a different style to indicate they link to Wikipedia.
    """
    pm = get_manager()

    external_nodes = external_nodes or []

    # --- Hook: before_generate_dot ---
    pm.dispatch_before_generate_dot(nodes, edges)

    colors = _pick_colors()
    width, height = config.get_monitor_resolution()
    _, gv_font = config.get_font()

    dpi = 96
    # Graph occupies right 78% of the screen (todo panel takes ~20% on the left)
    graph_w = (width * 0.76) / dpi
    graph_h = height / dpi

    dot_lines = [
        "digraph SecondBrain {",
        '  bgcolor="transparent"',
        f"  dpi={dpi}",
        f'  size="{graph_w:.2f},{graph_h:.2f}!"',
        '  ratio="fill"',
        "  overlap=false",
        "  splines=true",
        "  layout=neato",
        "",
        "  // Global node style",
        "  node [",
        "    shape=circle",
        '    style="filled,bold"',
        f'    fontname="{gv_font}"',
        f'    fontcolor="{colors["fg"]}"',
        "    fontsize=11",
        "    width=1.2",
        "    height=1.2",
        "    penwidth=2.5",
        "  ]",
        "",
        "  // Global edge style",
        "  edge [",
        f'    color="{colors["edge_color"]}"',
        "    penwidth=1.5",
        "    arrowsize=0.6",
        "  ]",
        "",
    ]

    # Add internal nodes with rotating colors and glow effect
    node_colors = colors["node_colors"]
    for i, node in enumerate(nodes):
        nc = node_colors[i % len(node_colors)]
        # Create a lighter "glow" ring color
        glow = nc
        label = node.replace("_", " ")
        if len(label) > 14:
            label = label[:12] + ".."

        # Base node attributes
        node_attrs = {
            "label": label,
            "fillcolor": f"{nc}40",
            "color": glow,
            "fontcolor": colors["fg"],
        }

        # --- Hook: on_dot_node (mutating) ---
        node_attrs = pm.dispatch_on_dot_node(node, node_attrs)

        attr_str = " ".join(f'{k}="{v}"' for k, v in node_attrs.items())
        dot_lines.append(f'  "{node}" [{attr_str}]')

    dot_lines.append("")

    # Add external nodes (Wikipedia links) with distinct styling
    if external_nodes:
        dot_lines.append("  // External nodes (Wikipedia links)")
        for ext_node in external_nodes:
            label = ext_node.replace("_", " ")
            if len(label) > 14:
                label = label[:12] + ".."
            # External nodes: dashed border, lighter fill, Wikipedia icon hint
            node_attrs = {
                "label": label,
                "fillcolor": "#ffffff20",
                "color": colors["fg"],
                "fontcolor": colors["fg"],
                "style": "filled,dashed",
                "penwidth": "1.5",
            }

            # --- Hook: on_dot_external_node (mutating) ---
            node_attrs = pm.dispatch_on_dot_external_node(ext_node, node_attrs)

            attr_str = " ".join(f'{k}="{v}"' for k, v in node_attrs.items())
            dot_lines.append(f'  "{ext_node}" [{attr_str}]')
        dot_lines.append("")

    # Add edges
    for src, tgt in edges:
        # Base edge attributes (empty — uses global defaults)
        edge_attrs: dict[str, str] = {}

        # --- Hook: on_dot_edge (mutating) ---
        edge_attrs = pm.dispatch_on_dot_edge(src, tgt, edge_attrs)

        if edge_attrs:
            attr_str = " ".join(f'{k}="{v}"' for k, v in edge_attrs.items())
            dot_lines.append(f'  "{src}" -> "{tgt}" [{attr_str}]')
        else:
            dot_lines.append(f'  "{src}" -> "{tgt}"')

    dot_lines.append("}")
    dot_source = "\n".join(dot_lines)

    # --- Hook: after_generate_dot (mutating) ---
    dot_source = pm.dispatch_after_generate_dot(dot_source)

    return dot_source


def render_graph(output_path: Path | None = None) -> Path:
    """Scan brain, generate DOT, render to PNG.

    Returns the path to the rendered PNG.
    """
    pm = get_manager()

    if output_path is None:
        output_path = config.GRAPH_OUTPUT

    nodes, edges, external_nodes = scan_brain()

    if not nodes:
        # Create a placeholder node
        nodes = ["empty_brain"]
        edges = []
        external_nodes = []

    dot_source = generate_dot(nodes, edges, external_nodes)

    # --- Hook: before_render_graph (mutating) ---
    dot_source = pm.dispatch_before_render_graph(dot_source)

    # Write DOT to temp file and render
    dot_file = Path(tempfile.mktemp(suffix=".dot"))
    dot_file.write_text(dot_source)

    try:
        subprocess.run(
            [
                "dot",
                "-Tpng",
                "-Gdpi=96",
                str(dot_file),
                "-o",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.CalledProcessError:
        # Fallback to neato layout if dot fails
        subprocess.run(
            [
                "neato",
                "-Tpng",
                "-Gdpi=96",
                str(dot_file),
                "-o",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        dot_file.unlink(missing_ok=True)

    # --- Hook: after_render_graph ---
    pm.dispatch_after_render_graph(output_path)

    return output_path
