"""Telegram Pull — local plugin that syncs with the remote inbox.

This plugin provides two operations:
  1. PULL:  Fetch queued messages from the remote inbox, write them to
           dump.md, and acknowledge them.
  2. SYNC:  Push all brain .md files to the remote server so they can
           be browsed via Telegram.

Uses ONLY stdlib (urllib.request, json) — no third-party HTTP library
needed on the local machine.

SETUP:
  1. Deploy the telegram_inbox/ service on PythonAnywhere.
  2. Add to ~/.config/second_brain/config.json:
     {
       "plugins": {
         "enabled": ["telegram_pull"],
         "config": {
           "telegram_pull": {
             "remote_url": "https://yourusername.pythonanywhere.com",
             "pull_secret": "your-shared-secret-here"
           }
         }
       }
     }
  3. Copy this file to ~/.config/second_brain/plugins/telegram_pull.py

The plugin also provides standalone functions (pull_messages, sync_notes)
that can be called from the CLI via `second-brain pull` and `second-brain sync`.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from second_brain.plugins import BrainAPI, SecondBrainPlugin

log = logging.getLogger("second_brain.plugins.telegram_pull")


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only)
# ---------------------------------------------------------------------------

def _request(
    url: str,
    secret: str,
    method: str = "GET",
    data: dict | None = None,
    timeout: int = 15,
) -> dict:
    """Make an authenticated HTTP request to the remote inbox."""
    headers = {
        "X-Pull-Secret": secret,
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode()[:200]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code} from {url}: {body_text}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach {url}: {e.reason}") from e


# ---------------------------------------------------------------------------
# Core operations (usable standalone or from plugin)
# ---------------------------------------------------------------------------

def pull_messages(remote_url: str, pull_secret: str, dump_file: Path) -> int:
    """Pull pending messages from the remote inbox and append to dump.md.

    Returns the number of messages pulled.
    """
    base = remote_url.rstrip("/")

    # Fetch messages
    result = _request(f"{base}/messages", pull_secret)
    messages = result.get("messages", [])

    if not messages:
        return 0

    # Append to dump.md
    lines = []
    for msg in messages:
        text = msg.get("text", "").strip()
        if text:
            lines.append(text)

    if not lines:
        return 0

    # Read existing dump
    if dump_file.exists():
        existing = dump_file.read_text().rstrip()
    else:
        existing = "# Dump"

    new_content = existing + "\n\n" + "\n\n".join(lines) + "\n"
    dump_file.write_text(new_content)

    # Acknowledge
    _request(f"{base}/messages/ack", pull_secret, method="POST")

    return len(messages)


def sync_notes(remote_url: str, pull_secret: str, brain_dir: Path) -> int:
    """Push all brain .md files to the remote server.

    Returns the number of files synced.
    """
    base = remote_url.rstrip("/")

    # Collect all .md files
    notes = {}
    for md_file in sorted(brain_dir.glob("*.md")):
        if md_file.name == "dump.md":
            continue
        try:
            notes[md_file.name] = md_file.read_text()
        except OSError:
            log.warning("Could not read %s, skipping", md_file.name)

    if not notes:
        return 0

    result = _request(
        f"{base}/notes",
        pull_secret,
        method="POST",
        data={"notes": notes},
        timeout=30,
    )
    return result.get("stored", 0)


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------

class TelegramPull(SecondBrainPlugin):
    """Plugin that pulls messages from the remote Telegram inbox."""

    name = "telegram_pull"

    def _get_remote(self) -> tuple[str, str]:
        """Get remote URL and secret from config."""
        url = self.config.get("remote_url", "")
        secret = self.config.get("pull_secret", "")
        if not url:
            raise RuntimeError(
                "telegram_pull: No remote_url in config. "
                "Add it to plugins.config.telegram_pull.remote_url"
            )
        if not secret:
            raise RuntimeError(
                "telegram_pull: No pull_secret in config. "
                "Add it to plugins.config.telegram_pull.pull_secret"
            )
        return url, secret

    def on_load(self, ctx: BrainAPI) -> None:
        self.ctx = ctx
        url = self.config.get("remote_url", "")
        secret = self.config.get("pull_secret", "")
        if not url:
            log.warning(
                "telegram_pull: No remote_url configured. "
                "Pull/sync will not work."
            )
        if not secret:
            log.warning(
                "telegram_pull: No pull_secret configured. "
                "Pull/sync will not work."
            )

    def do_pull(self) -> int:
        """Pull messages from remote inbox to dump.md."""
        url, secret = self._get_remote()
        count = pull_messages(url, secret, self.ctx.dump_file)
        if count:
            log.info("Pulled %d message(s) from Telegram inbox", count)
            print(f"[telegram] Pulled {count} message(s) into dump.md")
        else:
            print("[telegram] No new messages")
        return count

    def do_sync(self) -> int:
        """Push brain notes to remote server."""
        url, secret = self._get_remote()
        count = sync_notes(url, secret, self.ctx.brain_dir)
        log.info("Synced %d note(s) to remote", count)
        print(f"[telegram] Synced {count} note(s)")
        return count

    # Auto-sync after librarian processes dump
    def after_execute_actions(self, summaries: list[str]) -> None:
        """Push updated notes after librarian writes files."""
        if not self.config.get("auto_sync", True):
            return
        try:
            self.do_sync()
        except Exception as e:
            log.error("Auto-sync after execute failed: %s", e)

    # Auto-sync after janitor
    def after_janitor_run(self, summaries: list[str]) -> None:
        """Push updated notes after janitor writes files."""
        if not self.config.get("auto_sync", True):
            return
        try:
            self.do_sync()
        except Exception as e:
            log.error("Auto-sync after janitor failed: %s", e)
