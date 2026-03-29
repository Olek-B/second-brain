"""CLI entry point for Second Brain."""

import argparse
import logging
import os
import sys
from pathlib import Path

# Configure logging for CLI usage
log = logging.getLogger("second_brain.cli")


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    root_logger = logging.getLogger("second_brain")
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    # Also log plugin messages
    logging.getLogger("second_brain.plugins").setLevel(level)


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
  ask          Ask your brain a question and get an AI answer
  list         List all brain files
  dot          Output the DOT graph to stdout (for debugging)
  check-links  Check for broken/orphaned links and external wiki links
  daily        Create or open today's daily note (YYYY-MM-DD.md)
  tags         List all tags or show files with a specific tag
  duplicates   Find potential duplicate notes
  pull         Pull messages from Telegram inbox into dump.md
  sync         Push brain notes to remote Telegram inbox server
  boot-sync    Pull Telegram + process dump (for boot automation)
  install-timer  Install systemd user timer for boot-sync
  uninstall-timer  Remove the systemd user timer
  rss          List RSS feeds or fetch latest entries
  analytics    Show personal analytics about your knowledge base

examples:
  second-brain                  # Launch TUI
  second-brain setup            # Auto-detect and generate config
  second-brain process          # Process dump.md
  second-brain graph            # Generate graph + wallpaper
  second-brain janitor          # Run cleanup pass
  second-brain janitor --dry-run # Preview changes without writing
  second-brain ask "what did I write about DNS?"
  second-brain backlinks        # Show backlink summary
  second-brain backlinks dns    # Show files linking to dns.md
  second-brain check-links      # Check for broken/orphaned links
  second-brain daily            # Create/open today's note
  second-brain tags             # List all tags
  second-brain tag dns          # Show files with #dns tag
  second-brain duplicates       # Find duplicate notes
  second-brain dot > graph.dot  # Export DOT for debugging
  second-brain pull             # Pull Telegram messages
  second-brain sync             # Push notes to remote
  second-brain invest "{ale} allegro - 3 - 25.50"  # Add investment with buy price
  second-brain invest --refresh            # Refresh all investment prices
  second-brain librus                      # Sync grades/exams from Librus
""",
    )

    parser.add_argument(
        "command",
        nargs="?",
        default="tui",
        choices=[
            "tui",
            "setup",
            "process",
            "graph",
            "janitor",
            "ask",
            "backlinks",
            "list",
            "dot",
            "check-links",
            "daily",
            "tags",
            "tag",
            "duplicates",
            "pull",
            "sync",
            "boot-sync",
            "install-timer",
            "uninstall-timer",
            "invest",
            "librus",
            "rss",
            "analytics",
        ],
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

    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh all investment prices from Stooq (used with 'invest' command)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose (debug) logging",
    )

    parser.add_argument(
        "--add",
        nargs=2,
        metavar=("NAME", "URL"),
        help="Add a new RSS feed (used with 'rss' command)",
    )

    parser.add_argument(
        "--remove",
        metavar="NAME",
        help="Remove an RSS feed by name (used with 'rss' command)",
    )

    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days for analytics (used with 'analytics' command)",
    )

    parser.add_argument(
        "--export",
        choices=["json", "markdown"],
        help="Export format (used with 'analytics' command)",
    )

    parser.add_argument(
        "question",
        nargs="?",
        default=None,
        help="Question to ask your brain (used with 'ask' command)",
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(verbose=args.verbose)

    if args.command == "tui":
        from .tui import run_tui

        run_tui()

    elif args.command == "setup":
        from .setup import run_setup

        run_setup(interactive=True)

    elif args.command == "process":
        from .librarian import clear_dump, execute_actions, process_dump

        log.info("Processing dump.md...")
        try:
            actions = process_dump()
        except RuntimeError as e:
            log.error("Error: %s", e)
            sys.exit(1)

        if "error" in actions:
            log.error("Error: %s", actions["error"])
            sys.exit(1)

        summaries = execute_actions(actions)
        for s in summaries:
            log.info("  %s", s)

        clear_dump()
        log.info("Done. dump.md cleared.")

    elif args.command == "graph":
        from .graph import render_graph

        log.info("Generating knowledge graph...")
        graph_path = render_graph()
        log.info("Graph rendered: %s", graph_path)

        if not args.no_wallpaper:
            from .wallpaper import composite_wallpaper, set_wallpaper

            try:
                composited = composite_wallpaper(graph_path=graph_path)
                log.info("Composited: %s", composited)
                if set_wallpaper(composited):
                    log.info("Wallpaper updated!")
                else:
                    log.warning("Could not set wallpaper automatically.")
            except FileNotFoundError as e:
                log.warning("Warning: %s", e)
                log.warning("Graph saved but wallpaper not updated.")

    elif args.command == "janitor":
        from .janitor import run_janitor

        mode = "DRY RUN" if args.dry_run else "LIVE"
        log.info("Running janitor (%s)...", mode)
        try:
            summaries = run_janitor(dry_run=args.dry_run)
        except RuntimeError as e:
            log.error("Error: %s", e)
            sys.exit(1)

        for s in summaries:
            log.info("  %s", s)
        log.info("Done.")

    elif args.command == "ask":
        from .ask import ask_brain

        question = args.question
        if not question:
            # Read from stdin if no argument given
            print("What would you like to ask your brain?", file=sys.stderr)
            question = input("> ").strip()

        if not question:
            log.error("No question provided.")
            sys.exit(1)

        log.info("Searching your brain...")
        try:
            answer = ask_brain(question)
        except RuntimeError as e:
            log.error("Error: %s", e)
            sys.exit(1)

        print()
        print(answer)

    elif args.command == "backlinks":
        from .backlinks import get_all_backlinks, get_backlinks

        target = args.question
        if target:
            # Show backlinks for a specific file
            if not target.endswith(".md"):
                target = f"{target}.md"
            backlinks = get_backlinks(target)
            if not backlinks:
                log.info("No files link to %s", target)
            else:
                log.info("Files linking to %s (%d):\n", target, len(backlinks))
                for bl in sorted(backlinks):
                    log.info("  [[%s]]", bl.removesuffix(".md"))
        else:
            # Show backlink summary for all files
            backlink_index = get_all_backlinks()
            files_with_backlinks = {k: v for k, v in backlink_index.items() if v}
            if not files_with_backlinks:
                log.info("No backlinks found in your brain.")
            else:
                log.info("Backlink Summary (%d files with incoming links):\n", len(files_with_backlinks))
                for fname in sorted(files_with_backlinks.keys()):
                    blist = files_with_backlinks[fname]
                    log.info("  %s (%d backlinks)", fname, len(blist))
                    for bl in sorted(blist)[:5]:  # Show first 5
                        log.info("    <- [[%s]]", bl.removesuffix(".md"))
                    if len(blist) > 5:
                        log.info("    ... and %d more", len(blist) - 5)

    elif args.command == "list":
        from . import config

        files = config.get_brain_files()
        if not files:
            log.info("No files in brain directory.")
        else:
            log.info("Brain files (%d):", len(files))
            for f in files:
                log.info("  %s", f)

    elif args.command == "dot":
        from .graph import generate_dot, scan_brain

        nodes, edges, external_nodes = scan_brain()
        print(generate_dot(nodes, edges, external_nodes))

    elif args.command == "check-links":
        from .graph import check_links

        result = check_links()

        # Report external links (wiki links to non-existent files)
        if result["external_links"]:
            log.info("External Wiki Links (to Wikipedia):")
            for topic, files in sorted(result["external_links"].items()):
                log.info("  [[%s]] - linked from: %s", topic, ", ".join(sorted(files)))
        else:
            log.info("No external wiki links found.")

        log.info("")

        # Report orphaned files
        if result["orphaned_files"]:
            log.info("Orphaned Files (no incoming or outgoing links):")
            for f in result["orphaned_files"]:
                log.info("  %s.md", f)
        else:
            log.info("No orphaned files found.")

        log.info("")

        # Summary
        total_external = sum(len(files) for files in result["external_links"].values())
        log.info(
            "Summary: %d external topics (%d links), %d orphaned files",
            len(result["external_links"]),
            total_external,
            len(result["orphaned_files"]),
        )

    elif args.command == "daily":
        from .daily_note import create_daily_note

        note_path, was_created = create_daily_note(open_editor=True)
        if was_created:
            log.info("Created daily note: %s", note_path)
        else:
            log.info("Opened existing daily note: %s", note_path)

    elif args.command == "tags":
        from .tags import get_all_tags

        tag_index = get_all_tags()
        if not tag_index:
            log.info("No tags found. Add #tags to your notes like #dns or #homelab")
        else:
            log.info("Tags (%d total):\n", len(tag_index))
            for tag in sorted(tag_index.keys()):
                files = tag_index[tag]
                log.info("  #%s (%d file%s)", tag, len(files), "s" if len(files) > 1 else "")

    elif args.command == "tag":
        if not args.question:
            log.error("Usage: second-brain tag <tagname>")
            log.error("Example: second-brain tag dns")
            sys.exit(1)

        from .tags import get_files_by_tag

        tag = args.question.lstrip("#")
        files = get_files_by_tag(tag)

        if not files:
            log.info("No files found with #%s", tag)
        else:
            log.info("Files with #%s (%d):\n", tag, len(files))
            for f in files:
                log.info("  - %s", f)

    elif args.command == "duplicates":
        from .duplicates import find_duplicates

        duplicates = find_duplicates(threshold=0.4)

        if not duplicates:
            log.info("No potential duplicates found.")
        else:
            log.info("Potential duplicates (%d pairs):\n", len(duplicates))
            for file1, file2, similarity in duplicates:
                pct = int(similarity * 100)
                log.info("  %s + %s (%d%% similar)", file1, file2, pct)
            log.info("\nTip: Review these files and consider merging if they cover the same topic.")

    elif args.command == "pull":
        from .plugins import get_manager

        pm = get_manager()
        # Find the telegram_pull plugin
        pull_plugin = None
        for p in pm.plugins:
            if p.name == "telegram_pull":
                pull_plugin = p
                break

        if pull_plugin is None:
            # Fall back to standalone function with config
            from . import config as cfg

            plugin_cfg = cfg.get_plugin_config("telegram_pull")
            url = plugin_cfg.get("remote_url", "")
            secret = plugin_cfg.get("pull_secret", "")
            if not url or not secret:
                log.error(
                    "Error: telegram_pull not configured.\n"
                    "Add remote_url and pull_secret to "
                    "plugins.config.telegram_pull in config.json",
                )
                sys.exit(1)

            # Use standalone function from examples
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
            from telegram_pull import pull_messages

            count = pull_messages(url, secret, cfg.DUMP_FILE)
            log.info("Pulled %d message(s)", count)
        else:
            pull_plugin.do_pull()  # type: ignore[attr-defined]

    elif args.command == "sync":
        from .plugins import get_manager

        pm = get_manager()
        sync_plugin = None
        for p in pm.plugins:
            if p.name == "telegram_pull":
                sync_plugin = p
                break

        if sync_plugin is None:
            from . import config as cfg

            plugin_cfg = cfg.get_plugin_config("telegram_pull")
            url = plugin_cfg.get("remote_url", "")
            secret = plugin_cfg.get("pull_secret", "")
            if not url or not secret:
                log.error(
                    "Error: telegram_pull not configured.\n"
                    "Add remote_url and pull_secret to "
                    "plugins.config.telegram_pull in config.json",
                )
                sys.exit(1)

            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
            from telegram_pull import sync_notes

            count = sync_notes(url, secret, cfg.BRAIN_DIR)
            log.info("Synced %d note(s)", count)
        else:
            sync_plugin.do_sync()  # type: ignore[attr-defined]

    elif args.command == "boot-sync":
        _run_boot_sync()

    elif args.command == "install-timer":
        _install_timer()

    elif args.command == "uninstall-timer":
        _uninstall_timer()

    elif args.command == "invest":
        from .investments import (
            get_portfolio_summary,
            parse_investment_input,
            refresh_all_investments,
            update_investment,
        )

        if args.refresh:
            # Refresh all investments
            log.info("Refreshing all investment prices from Stooq...")
            try:
                updated = refresh_all_investments()
                summary = get_portfolio_summary()
                log.info("Refreshed %d investments", len(updated))
                log.info(
                    "Portfolio: %d/%d positions valued at %.2f PLN",
                    summary["invested_count"],
                    summary["total_count"],
                    summary["total_value"],
                )
            except Exception as e:
                log.error("Error refreshing investments: %s", e)
                sys.exit(1)
        else:
            # Add/update single investment
            investment_str = args.question
            if not investment_str:
                # Read from stdin if no argument given
                print(
                    "Enter investment in format: {ticker} name - shares [- buy_price]",
                    file=sys.stderr,
                )
                print("Example: {ale} allegro - 3 - 25.50", file=sys.stderr)
                investment_str = input("> ").strip()

            if not investment_str:
                log.error("No investment provided.")
                sys.exit(1)

            try:
                ticker, name, shares, buy_price = parse_investment_input(investment_str)
            except ValueError as e:
                log.error("Error: %s", e)
                sys.exit(1)

            log.info("Adding/updating investment: %s (%s) - %.2f shares @ %.2f", name, ticker, shares, buy_price)
            try:
                investment = update_investment(ticker, name, shares, buy_price)
                if investment.current_price:
                    gain_loss = investment.gain_loss
                    gain_loss_pct = investment.gain_loss_pct
                    if gain_loss is not None and gain_loss_pct is not None:
                        sign = "+" if gain_loss >= 0 else ""
                        log.info(
                            "Updated! %s: %d shares × %.2f %s = %.2f %s | P/L: %s%.2f (%s%.1f%%)",
                            investment.ticker,
                            investment.shares,
                            investment.current_price,
                            investment.currency,
                            investment.market_value,
                            investment.currency,
                            sign,
                            gain_loss,
                            sign,
                            gain_loss_pct,
                        )
                    else:
                        log.info(
                            "Updated! %s: %d shares × %.2f %s = %.2f %s",
                            investment.ticker,
                            investment.shares,
                            investment.current_price,
                            investment.currency,
                            investment.market_value,
                            investment.currency,
                        )
                else:
                    log.info(
                        "Updated! %s: %d shares (price unavailable)",
                        investment.ticker,
                        investment.shares,
                    )
            except Exception as e:
                log.error("Error updating investment: %s", e)
                sys.exit(1)

    elif args.command == "librus":
        from .plugins import get_manager

        pm = get_manager()
        librus_plugin = None
        for p in pm.plugins:
            if p.name == "librus_sync":
                librus_plugin = p
                break

        if librus_plugin is None:
            log.error(
                "Error: librus_sync plugin not loaded.\n"
                "Enable it in config.json: plugins.enabled"
            )
            sys.exit(1)

        librus_plugin.do_sync()  # type: ignore[attr-defined]

    elif args.command == "rss":
        _run_rss(add=args.add, remove=args.remove)

    elif args.command == "analytics":
        _run_analytics(days=args.days, export_format=args.export)


def _run_rss(
    add: tuple[str, str] | None = None,
    remove: str | None = None,
) -> None:
    """Run RSS feed commands.
    
    Args:
        add: Tuple of (name, url) to add new feed.
        remove: Name of feed to remove.
    """
    from .rss_reader import RSSFeed, load_feeds, save_feeds, get_all_entries
    
    if add:
        # Add new feed
        name, url = add
        feeds = load_feeds()
        
        # Check if already exists
        for feed in feeds:
            if feed.name.lower() == name.lower():
                log.error("Feed '%s' already exists", name)
                sys.exit(1)
        
        # Determine feed type
        feed_type = "youtube" if "youtube.com" in url else "standard"
        
        feeds.append(RSSFeed(name=name, url=url, feed_type=feed_type))
        save_feeds(feeds)
        log.info("Added %s feed: %s (%s)", feed_type, name, url)
        
    elif remove:
        # Remove feed
        feeds = load_feeds()
        original_count = len(feeds)
        feeds = [f for f in feeds if f.name.lower() != remove.lower()]
        
        if len(feeds) == original_count:
            log.error("Feed '%s' not found", remove)
            sys.exit(1)
        
        save_feeds(feeds)
        log.info("Removed feed: %s", remove)
        
    else:
        # List feeds or fetch entries
        feeds = load_feeds()
        
        if not feeds:
            log.info("No RSS feeds configured.")
            log.info("Add feeds with: second-brain rss --add \"Name\" \"URL\"")
            return
        
        log.info("Configured RSS Feeds (%d):", len(feeds))
        for feed in feeds:
            log.info("  %s [%s] - %s", feed.name, feed.feed_type, feed.url)
        
        # Always fetch latest entries when listing
        log.info("\nFetching latest entries...")
        entries = get_all_entries()
        
        if entries:
            log.info("\nLatest Entries (%d):", len(entries))
            for entry in entries[:10]:  # Show 10 most recent
                log.info(
                    "  [%s] %s - %s (%s)",
                    entry.source,
                    entry.title,
                    entry.published.strftime("%Y-%m-%d %H:%M"),
                    entry.link[:50] + "..." if len(entry.link) > 50 else entry.link,
                )
        else:
            log.info("\nNo entries fetched.")


def _run_analytics(days: int = 30, export_format: str | None = None) -> None:
    """Run analytics and display/export results.
    
    Args:
        days: Number of days for trend analysis.
        export_format: Export format ('json', 'markdown', or None for dashboard).
    """
    from .analytics import (
        export_analytics_json,
        export_analytics_markdown,
        format_analytics_dashboard,
        get_full_analytics,
    )
    
    log.info("Gathering analytics...")
    
    try:
        data = get_full_analytics(days=days)
    except Exception as e:
        log.error("Error gathering analytics: %s", e)
        sys.exit(1)
    
    if export_format == "json":
        print(export_analytics_json(data))
    elif export_format == "markdown":
        print(export_analytics_markdown(data))
    else:
        # Display dashboard
        dashboard = format_analytics_dashboard(data)
        print(dashboard)


def _run_boot_sync() -> None:
    """Pull from Telegram then process the dump — designed for unattended boot automation."""
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger("boot-sync")

    # --- Step 1: Pull from Telegram ---
    log.info("Pulling messages from Telegram...")
    pulled = 0
    try:
        from .plugins import get_manager

        pm = get_manager()
        pull_plugin = None
        for p in pm.plugins:
            if p.name == "telegram_pull":
                pull_plugin = p
                break

        if pull_plugin is not None:
            pulled = pull_plugin.do_pull() or 0  # type: ignore[attr-defined]
        else:
            from . import config as cfg

            plugin_cfg = cfg.get_plugin_config("telegram_pull")
            url = plugin_cfg.get("remote_url", "")
            secret = plugin_cfg.get("pull_secret", "")
            if url and secret:
                sys.path.insert(
                    0,
                    str(Path(__file__).resolve().parent.parent / "examples"),
                )
                from telegram_pull import pull_messages

                pulled = pull_messages(url, secret, cfg.DUMP_FILE)
            else:
                log.warning("telegram_pull not configured, skipping pull")
    except Exception as e:
        log.error("Pull failed: %s", e)

    log.info("Pulled %d message(s)", pulled)

    # --- Step 2: Process dump ---
    from . import config

    dump_path = config.DUMP_FILE
    if dump_path.exists() and dump_path.read_text().strip():
        log.info("Processing dump.md...")
        try:
            from .librarian import clear_dump, execute_actions, process_dump

            actions = process_dump()
            if "error" in actions:
                log.error("Process error: %s", actions["error"])
            else:
                summaries = execute_actions(actions)
                for s in summaries:
                    log.info("  %s", s)
                clear_dump()
                log.info("Done. dump.md cleared.")
        except Exception as e:
            log.error("Processing failed: %s", e)
    else:
        log.info("dump.md is empty, nothing to process.")


def _install_timer() -> None:
    """Install the systemd user timer for boot-sync."""
    import shutil

    user_unit_dir = Path.home() / ".config" / "systemd" / "user"
    user_unit_dir.mkdir(parents=True, exist_ok=True)

    # Find the python interpreter to use
    python_bin = sys.executable or shutil.which("python3") or "python3"

    service_content = f"""\
[Unit]
Description=Second Brain boot sync (pull Telegram + process dump)

[Service]
Type=oneshot
ExecStart={python_bin} -m second_brain boot-sync
Environment=PATH={os.environ.get("PATH", "/usr/bin")}
"""

    # Forward GROQ_API_KEY if set in the environment
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        service_content += f"Environment=GROQ_API_KEY={groq_key}\n"

    timer_content = """\
[Unit]
Description=Run Second Brain boot-sync 3 minutes after boot

[Timer]
OnBootSec=3min
Unit=second-brain-boot-sync.service

[Install]
WantedBy=timers.target
"""

    service_path = user_unit_dir / "second-brain-boot-sync.service"
    timer_path = user_unit_dir / "second-brain-boot-sync.timer"

    service_path.write_text(service_content)
    timer_path.write_text(timer_content)

    log.info("Wrote %s", service_path)
    log.info("Wrote %s", timer_path)

    # Enable and start the timer
    import subprocess

    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        check=True,
    )
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", "second-brain-boot-sync.timer"],
        check=True,
    )
    log.info("Timer enabled and started.")
    log.info("Check status: systemctl --user status second-brain-boot-sync.timer")
    log.info("View logs:    journalctl --user -u second-brain-boot-sync.service")


def _uninstall_timer() -> None:
    """Remove the systemd user timer for boot-sync."""
    import subprocess

    subprocess.run(
        ["systemctl", "--user", "disable", "--now", "second-brain-boot-sync.timer"],
        check=False,
    )

    user_unit_dir = Path.home() / ".config" / "systemd" / "user"
    service_path = user_unit_dir / "second-brain-boot-sync.service"
    timer_path = user_unit_dir / "second-brain-boot-sync.timer"

    for path in (service_path, timer_path):
        if path.exists():
            path.unlink()
            log.info("Removed %s", path)

    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        check=False,
    )
    log.info("Timer uninstalled.")


if __name__ == "__main__":
    main()
