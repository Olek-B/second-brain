"""The Graph Engine - scan brain, extract wikilinks, render Graphviz."""

import re
import subprocess
import tempfile
from pathlib import Path

from . import config
from .external_links import scan_external_links_for_graph
from .plugins import get_manager


def normalize_wikilinks(content: str, valid_names: set[str] | None = None) -> str:
    """Normalize wikilinks in content to consistent format.

    Converts [[text|Label]] to [[text]] when the link text matches
    the target file name (case-insensitive), keeping the simpler form.

    Args:
        content: Markdown content to normalize.
        valid_names: Set of valid file names (without .md). If None,
            normalizes all links; if provided, only normalizes links
            to existing files.

    Returns:
        Content with normalized wikilinks.
    """
    # Pattern matches [[target]] or [[target|label]]
    link_pattern = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

    def replace_link(match: re.Match) -> str:
        target = match.group(1).strip()
        label = match.group(2)

        # If there's no label, keep as-is
        if label is None:
            return f"[[{target}]]"

        # If valid_names is provided, only normalize links to existing files
        if valid_names is not None and target not in valid_names:
            # Keep external links as-is
            return f"[[{target}|{label}]]"

        # Normalize: if label matches target (case-insensitive), use simple form
        # This handles both [[vercel|Vercel]] -> [[vercel]] and [[Vercel|vercel]] -> [[vercel]]
        if label.lower() == target.lower():
            # Use lowercase for consistency
            return f"[[{target.lower()}]]"

        # Keep the labeled form when they differ
        return f"[[{target}|{label}]]"

    return link_pattern.sub(replace_link, content)


def get_existing_wikilinks(brain_dir: Path | None = None) -> tuple[set[str], list[str]]:
    """Get list of existing wikilinks (both internal and external).

    Args:
        brain_dir: Path to brain directory. Defaults to config.BRAIN_DIR.

    Returns:
        Tuple of (internal_files, external_topics) where internal_files
        are .md file stems and external_topics are wiki links that don't
        match any internal file.
    """
    if brain_dir is None:
        brain_dir = config.BRAIN_DIR

    md_files = sorted(brain_dir.glob("*.md"))
    # Exclude dump.md from internal files
    internal_files = {f.stem for f in md_files if f.name != "dump.md"}

    # Scan all files for external wiki links
    link_pattern = re.compile(r"\[\[([^\]]+)\]\]")
    external_topics: set[str] = set()

    for md_file in md_files:
        if md_file.name == "dump.md":
            continue
        content = md_file.read_text()
        for match in link_pattern.finditer(content):
            target = match.group(1).strip()
            if target.endswith(".md"):
                target = target[:-3]
            if target not in internal_files:
                external_topics.add(target)

    return internal_files, sorted(external_topics)


def scan_brain() -> tuple[list[str], list[tuple[str, str]], list[str], list[dict]]:
    """Scan the brain directory for nodes and edges.

    Returns:
        (nodes, edges, external_nodes, external_links) where:
        - nodes: filenames (without .md)
        - edges: (source, target) tuples based on [[wikilinks]]
        - external_nodes: wiki links without matching files
        - external_links: list of dicts with external URL node data
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

    # Scan for external URL links
    external_link_nodes, external_edges = scan_external_links_for_graph(brain_dir)
    edges.extend(external_edges)

    # --- Hook: after_scan_brain (mutating) ---
    nodes, edges = pm.dispatch_after_scan_brain(nodes, edges)

    # --- Hook: after_scan_brain_external (mutating) ---
    external_nodes = pm.dispatch_after_scan_brain_external(external_nodes)

    return nodes, edges, list(external_nodes), external_link_nodes


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
    nodes: list[str],
    edges: list[tuple[str, str]],
    external_nodes: list[str] | None = None,
    external_link_nodes: list[dict] | None = None,
) -> str:
    """Generate a Graphviz DOT string with pywal-themed styling.

    The graph is sized to fit the RIGHT 60% of the screen,
    leaving the left 40% free for the todo overlay.

    External nodes (wiki links without matching files) are shown with
    a different style to indicate they link to Wikipedia.

    External link nodes (URLs) are shown as small squares with favicons.
    """
    pm = get_manager()

    external_nodes = external_nodes or []
    external_link_nodes = external_link_nodes or []

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

    # Add external link nodes (URLs) with favicons
    if external_link_nodes:
        dot_lines.append("  // External link nodes (URLs)")
        for ext_link in external_link_nodes:
            node_id = ext_link["id"]
            label = ext_link["label"]
            favicon_path = ext_link.get("favicon")

            # External link nodes: square shape, smaller, with favicon image
            node_attrs = {
                "label": label,
                "shape": "square",
                "fillcolor": "#ffffff10",
                "color": colors["fg"],
                "fontcolor": colors["fg"],
                "style": "filled,bold",
                "penwidth": "1.5",
                "width": "0.8",
                "height": "0.8",
                "fontsize": "9",
            }

            # Add favicon as image if available
            if favicon_path and favicon_path.exists():
                node_attrs["image"] = str(favicon_path)
                node_attrs["imagepos"] = "tc"  # image at top center
                node_attrs["labelloc"] = "b"  # label at bottom

            # --- Hook: on_dot_external_link_node (mutating) ---
            node_attrs = pm.dispatch_on_dot_external_link_node(ext_link, node_attrs)

            attr_str = " ".join(f'{k}="{v}"' for k, v in node_attrs.items())
            dot_lines.append(f'  "{node_id}" [{attr_str}]')
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

    nodes, edges, external_nodes, external_link_nodes = scan_brain()

    if not nodes:
        # Create a placeholder node
        nodes = ["empty_brain"]
        edges = []
        external_nodes = []
        external_link_nodes = []

    dot_source = generate_dot(nodes, edges, external_nodes, external_link_nodes)

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
