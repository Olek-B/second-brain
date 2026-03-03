"""The Graph Engine - scan brain, extract wikilinks, render Graphviz."""

import re
import subprocess
import tempfile
from pathlib import Path

from . import config


def scan_brain() -> tuple[list[str], list[tuple[str, str]]]:
    """Scan the brain directory for nodes and edges.

    Returns:
        (nodes, edges) where nodes are filenames (without .md) and
        edges are (source, target) tuples based on [[wikilinks]].
    """
    brain_dir = config.BRAIN_DIR
    nodes: list[str] = []
    edges: list[tuple[str, str]] = []
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

    # Deduplicate edges
    edges = list(set(edges))
    return nodes, edges


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
        available = ["#cc241d", "#98971a", "#d79921", "#458588",
                      "#b16286", "#689d6a", "#fb4934"]

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
    r, g, b = (int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def generate_dot(nodes: list[str], edges: list[tuple[str, str]]) -> str:
    """Generate a Graphviz DOT string with pywal-themed styling.

    The graph is sized to fit the RIGHT 60% of the screen,
    leaving the left 40% free for the todo overlay.
    """
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
        f'  dpi={dpi}',
        f'  size="{graph_w:.2f},{graph_h:.2f}!"',
        '  ratio="fill"',
        '  overlap=false',
        '  splines=true',
        '  layout=neato',
        "",
        "  // Global node style",
        "  node [",
        '    shape=circle',
        '    style="filled,bold"',
        f'    fontname="{gv_font}"',
        f'    fontcolor="{colors["fg"]}"',
        '    fontsize=11',
        '    width=1.2',
        '    height=1.2',
        '    penwidth=2.5',
        "  ]",
        "",
        "  // Global edge style",
        "  edge [",
        f'    color="{colors["edge_color"]}"',
        '    penwidth=1.5',
        '    arrowsize=0.6',
        "  ]",
        "",
    ]

    # Add nodes with rotating colors and glow effect
    node_colors = colors["node_colors"]
    for i, node in enumerate(nodes):
        nc = node_colors[i % len(node_colors)]
        # Create a lighter "glow" ring color
        glow = nc
        label = node.replace("_", " ")
        if len(label) > 14:
            label = label[:12] + ".."
        dot_lines.append(
            f'  "{node}" ['
            f'label="{label}" '
            f'fillcolor="{nc}40" '
            f'color="{glow}" '
            f'fontcolor="{colors["fg"]}" '
            f']'
        )

    dot_lines.append("")

    # Add edges
    for src, tgt in edges:
        dot_lines.append(f'  "{src}" -> "{tgt}"')

    dot_lines.append("}")
    return "\n".join(dot_lines)


def render_graph(output_path: Path | None = None) -> Path:
    """Scan brain, generate DOT, render to PNG.

    Returns the path to the rendered PNG.
    """
    if output_path is None:
        output_path = config.GRAPH_OUTPUT

    nodes, edges = scan_brain()

    if not nodes:
        # Create a placeholder node
        nodes = ["empty_brain"]
        edges = []

    dot_source = generate_dot(nodes, edges)

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
                "-o", str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as e:
        # Fallback to neato layout if dot fails
        subprocess.run(
            [
                "neato",
                "-Tpng",
                "-Gdpi=96",
                str(dot_file),
                "-o", str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        dot_file.unlink(missing_ok=True)

    return output_path
