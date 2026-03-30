"""CSS styles for Second Brain TUI components."""

MAIN_CSS = """
Screen {
    layout: horizontal;
}

#sidebar {
    width: 30;
    dock: left;
    border-right: solid $accent;
    padding: 0 1;
}

#sidebar-title {
    text-style: bold;
    color: $accent;
    padding: 1 0;
    text-align: center;
}

#main {
    width: 1fr;
    padding: 1 2;
}

#preview-title {
    text-style: bold;
    color: $secondary;
    padding: 0 0 1 0;
}

#status-bar {
    dock: bottom;
    height: 3;
    padding: 0 1;
    border-top: solid $surface;
    color: $text-muted;
}

#ask-input {
    dock: bottom;
    margin: 0 1;
    display: none;
}

#ask-input.visible {
    display: block;
}

ListItem {
    padding: 0 1;
}

ListItem > Label {
    width: 100%;
}

ListView > ListItem.--highlight {
    background: $accent 20%;
}
"""

PREVIEW_PANE_CSS = """
PreviewPane {
    height: 1fr;
    border: round $surface;
    padding: 1;
    overflow-y: auto;
}

PreviewPane > MarkdownLink {
    color: $accent;
    text-style: underline;
}

PreviewPane > MarkdownLink:hover {
    color: $secondary;
    background: $surface;
}
"""
