"""CLI command handlers for Second Brain."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("second_brain.cli")


def _run_rss(
    add: tuple[str, str] | None = None,
    remove: str | None = None,
) -> None:
    """Run RSS feed commands.

    Args:
        add: Tuple of (name, url) to add new feed.
        remove: Name of feed to remove.
    """
    from ..rss_reader import RSSFeed, get_all_entries, load_feeds, save_feeds

    if add:
        name, url = add
        feeds = load_feeds()

        for feed in feeds:
            if feed.name.lower() == name.lower():
                log.error("Feed '%s' already exists", name)
                sys.exit(1)

        feed_type = "youtube" if "youtube.com" in url else "standard"
        feeds.append(RSSFeed(name=name, url=url, feed_type=feed_type))
        save_feeds(feeds)
        log.info("Added %s feed: %s (%s)", feed_type, name, url)

    elif remove:
        feeds = load_feeds()
        original_count = len(feeds)
        feeds = [f for f in feeds if f.name.lower() != remove.lower()]

        if len(feeds) == original_count:
            log.error("Feed '%s' not found", remove)
            sys.exit(1)

        save_feeds(feeds)
        log.info("Removed feed: %s", remove)

    else:
        feeds = load_feeds()

        if not feeds:
            log.info("No RSS feeds configured.")
            log.info('Add feeds with: second-brain rss --add "Name" "URL"')
            return

        log.info("Configured RSS Feeds (%d):", len(feeds))
        for feed in feeds:
            log.info("  %s [%s] - %s", feed.name, feed.feed_type, feed.url)

        log.info("\nFetching latest entries...")
        entries = get_all_entries()

        if entries:
            log.info("\nLatest Entries (%d):", len(entries))
            for entry in entries[:10]:
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
    from ..analytics import (
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
        dashboard = format_analytics_dashboard(data)
        print(dashboard)


def _run_boot_sync() -> None:
    """Pull from Telegram then process the dump — designed for unattended boot automation."""
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
        from ..plugins import get_manager

        pm = get_manager()
        pull_plugin = None
        for p in pm.plugins:
            if p.name == "telegram_pull":
                pull_plugin = p
                break

        if pull_plugin is not None:
            pulled = pull_plugin.do_pull() or 0  # type: ignore[attr-defined]
        else:
            from .. import config as cfg

            plugin_cfg = cfg.get_plugin_config("telegram_pull")
            url = plugin_cfg.get("remote_url", "")
            secret = plugin_cfg.get("pull_secret", "")
            if url and secret:
                sys.path.insert(
                    0,
                    str(Path(__file__).resolve().parent.parent.parent / "examples"),
                )
                from telegram_pull import pull_messages

                pulled = pull_messages(url, secret, cfg.DUMP_FILE)
            else:
                log.warning("telegram_pull not configured, skipping pull")
    except Exception as e:
        log.error("Pull failed: %s", e)

    log.info("Pulled %d message(s)", pulled)

    # --- Step 2: Process dump ---
    from .. import config

    dump_path = config.DUMP_FILE
    if dump_path.exists() and dump_path.read_text().strip():
        log.info("Processing dump.md...")
        try:
            from ..librarian import clear_dump, execute_actions, process_dump

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
    user_unit_dir = Path.home() / ".config" / "systemd" / "user"
    user_unit_dir.mkdir(parents=True, exist_ok=True)

    python_bin = sys.executable or shutil.which("python3") or "python3"

    service_content = f"""\
[Unit]
Description=Second Brain boot sync (pull Telegram + process dump)

[Service]
Type=oneshot
ExecStart={python_bin} -m second_brain boot-sync
Environment=PATH={os.environ.get("PATH", "/usr/bin")}
"""

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
