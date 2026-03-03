"""CLI entry point for Second Brain."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Second Brain - AI-driven markdown knowledge base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
commands:
  tui          Launch the interactive terminal UI (default)
  setup        Detect system config and generate config.json
  process      Process dump.md through the AI librarian
  graph        Generate the knowledge graph and update wallpaper
  janitor      Run AI cleanup (formatting + missing wikilinks)
  list         List all brain files
  dot          Output the DOT graph to stdout (for debugging)

examples:
  second-brain                  # Launch TUI
  second-brain setup            # Auto-detect and generate config
  second-brain process          # Process dump.md
  second-brain graph            # Generate graph + wallpaper
  second-brain janitor          # Run cleanup pass
  second-brain janitor --dry-run # Preview changes without writing
  second-brain dot > graph.dot  # Export DOT for debugging
""",
    )

    parser.add_argument(
        "command",
        nargs="?",
        default="tui",
        choices=["tui", "setup", "process", "graph", "janitor", "list", "dot"],
        help="Command to run (default: tui)",
    )

    parser.add_argument(
        "--no-wallpaper",
        action="store_true",
        help="Generate graph without updating wallpaper",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview janitor changes without writing files",
    )

    args = parser.parse_args()

    if args.command == "tui":
        from .tui import run_tui
        run_tui()

    elif args.command == "setup":
        from .setup import run_setup
        run_setup(interactive=True)

    elif args.command == "process":
        from .librarian import process_dump, execute_actions, clear_dump

        print("Processing dump.md...")
        try:
            actions = process_dump()
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        if "error" in actions:
            print(f"Error: {actions['error']}", file=sys.stderr)
            sys.exit(1)

        summaries = execute_actions(actions)
        for s in summaries:
            print(f"  {s}")

        clear_dump()
        print("Done. dump.md cleared.")

    elif args.command == "graph":
        from .graph import render_graph

        print("Generating knowledge graph...")
        graph_path = render_graph()
        print(f"Graph rendered: {graph_path}")

        if not args.no_wallpaper:
            from .wallpaper import composite_wallpaper, set_wallpaper

            try:
                composited = composite_wallpaper(graph_path=graph_path)
                print(f"Composited: {composited}")
                if set_wallpaper(composited):
                    print("Wallpaper updated!")
                else:
                    print("Could not set wallpaper automatically.")
            except FileNotFoundError as e:
                print(f"Warning: {e}")
                print("Graph saved but wallpaper not updated.")

    elif args.command == "janitor":
        from .janitor import run_janitor

        mode = "DRY RUN" if args.dry_run else "LIVE"
        print(f"Running janitor ({mode})...")
        try:
            summaries = run_janitor(dry_run=args.dry_run)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        for s in summaries:
            print(f"  {s}")
        print("Done.")

    elif args.command == "list":
        from . import config

        files = config.get_brain_files()
        if not files:
            print("No files in brain directory.")
        else:
            print(f"Brain files ({len(files)}):")
            for f in files:
                print(f"  {f}")

    elif args.command == "dot":
        from .graph import scan_brain, generate_dot

        nodes, edges = scan_brain()
        print(generate_dot(nodes, edges))


if __name__ == "__main__":
    main()
