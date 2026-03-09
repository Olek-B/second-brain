"""Telegram bot logic — webhook handler + inline keyboard browsing.

This module handles incoming Telegram updates (messages and callback
queries) and provides two-level inline keyboard navigation:

  1. /browse  -> shows a list of note files as buttons
  2. Tap a file -> shows its ## headers as buttons
  3. Tap a header -> sends that section's content

Regular text messages (not commands) are queued as inbox messages
for the local second-brain to pull.
"""

from __future__ import annotations

import json
import logging
import urllib.request

try:
    from . import config, storage
except ImportError:
    import config, storage  # type: ignore[no-redef]

log = logging.getLogger("telegram_inbox.bot")

_API_BASE = "https://api.telegram.org/bot{token}"


def _api_url(method: str) -> str:
    return f"{_API_BASE.format(token=config.get_bot_token())}/{method}"


def _post(method: str, payload: dict) -> dict:
    """Send a POST request to the Telegram Bot API."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        _api_url(method),
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.error("Telegram API %s failed: %s", method, e)
        return {"ok": False, "description": str(e)}


def _is_allowed(user_id: int) -> bool:
    """Check if user is in the allowed list (empty = deny all)."""
    allowed = config.get_allowed_users()
    if not allowed:
        return False
    return user_id in allowed


# ---------------------------------------------------------------------------
# Outbound helpers
# ---------------------------------------------------------------------------

def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
    """Send a text message to a chat."""
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _post("sendMessage", payload)


def answer_callback(callback_query_id: str, text: str = "") -> dict:
    """Answer a callback query (dismiss the loading spinner)."""
    payload: dict = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return _post("answerCallbackQuery", payload)


def edit_message(chat_id: int, message_id: int, text: str,
                 reply_markup: dict | None = None) -> dict:
    """Edit an existing message."""
    payload: dict = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _post("editMessageText", payload)


# ---------------------------------------------------------------------------
# Webhook registration
# ---------------------------------------------------------------------------

def register_webhook(base_url: str) -> dict:
    """Tell Telegram to send updates to our webhook URL.

    Call this once after deployment:
        python -c "from telegram_inbox.bot import register_webhook; \\
                   register_webhook('https://yourusername.pythonanywhere.com')"
    """
    webhook_url = f"{base_url.rstrip('/')}/webhook"
    return _post("setWebhook", {"url": webhook_url})


def delete_webhook() -> dict:
    """Remove the webhook (switch back to polling if needed)."""
    return _post("deleteWebhook", {})


# ---------------------------------------------------------------------------
# Inline keyboard builders
# ---------------------------------------------------------------------------

def _build_file_keyboard(notes: list[str]) -> dict:
    """Build an inline keyboard with one button per note file."""
    buttons = []
    for fname in notes:
        label = fname.replace(".md", "").replace("_", " ").title()
        buttons.append([{
            "text": label,
            "callback_data": f"file:{fname}",
        }])
    return {"inline_keyboard": buttons}


def _build_header_keyboard(fname: str, headers: list[dict]) -> dict:
    """Build an inline keyboard with one button per ## header."""
    buttons = []
    for h in headers:
        # Callback data has 64-byte limit — use line number as ID
        cb_data = f"section:{fname}:{h['line']}"
        if len(cb_data) > 64:
            # Truncate filename if needed
            short_fname = fname[:30]
            cb_data = f"section:{short_fname}:{h['line']}"
        indent = "  " * (h["level"] - 1)
        buttons.append([{
            "text": f"{indent}{h['header']}",
            "callback_data": cb_data,
        }])
    # Add a "back" button
    buttons.append([{
        "text": "<< Back to files",
        "callback_data": "browse",
    }])
    return {"inline_keyboard": buttons}


# ---------------------------------------------------------------------------
# Update handler (called from app.py webhook endpoint)
# ---------------------------------------------------------------------------

def handle_update(data: dict) -> None:
    """Process a single Telegram update (webhook payload)."""
    if "callback_query" in data:
        _handle_callback(data["callback_query"])
        return

    message = data.get("message")
    if not message:
        return

    user = message.get("from", {})
    user_id = user.get("id", 0)
    chat_id = message.get("chat", {}).get("id", 0)
    text = message.get("text", "").strip()

    if not _is_allowed(user_id):
        return

    if not text:
        return

    # Commands
    if text.startswith("/"):
        _handle_command(chat_id, user_id, user.get("username", ""), text)
    else:
        # Regular text -> queue as inbox message
        storage.add_message(text, user_id, user.get("username", ""))
        send_message(chat_id, "Noted. Your local brain will pick this up on next pull.")


def _handle_command(chat_id: int, user_id: int, username: str, text: str) -> None:
    """Route /commands."""
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]  # strip @botname suffix
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/start" or cmd == "/help":
        send_message(chat_id, (
            "*Second Brain Inbox*\n\n"
            "Send any text and it will be queued for your local brain.\n\n"
            "Commands:\n"
            "/browse - Browse your notes\n"
            "/help - Show this message"
        ))

    elif cmd == "/browse":
        notes = storage.list_notes()
        if not notes:
            send_message(chat_id, "No notes synced yet. Push from your local machine first.")
            return
        keyboard = _build_file_keyboard(notes)
        send_message(chat_id, "Pick a file:", keyboard)

    else:
        send_message(chat_id, f"Unknown command: {cmd}\nSend /help for usage.")


def _handle_callback(callback: dict) -> None:
    """Handle inline keyboard button presses."""
    cb_id = callback.get("id", "")
    data = callback.get("data", "")
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id", 0)
    message_id = message.get("message_id", 0)
    user = callback.get("from", {})
    user_id = user.get("id", 0)

    if not _is_allowed(user_id):
        answer_callback(cb_id, "Not authorized")
        return

    if data == "browse":
        # Show file list
        notes = storage.list_notes()
        if not notes:
            answer_callback(cb_id, "No notes synced")
            return
        keyboard = _build_file_keyboard(notes)
        edit_message(chat_id, message_id, "Pick a file:", keyboard)
        answer_callback(cb_id)

    elif data.startswith("file:"):
        # Show headers for a file
        fname = data.removeprefix("file:")
        headers = storage.get_note_headers(fname)
        if not headers:
            # No headers — just send the whole file (truncated)
            content = storage.read_note(fname)
            if content:
                if len(content) > 4000:
                    content = content[:4000] + "\n\n_(truncated)_"
                edit_message(chat_id, message_id, content)
            else:
                edit_message(chat_id, message_id, f"Could not read {fname}")
            answer_callback(cb_id)
            return

        label = fname.replace(".md", "").replace("_", " ").title()
        keyboard = _build_header_keyboard(fname, headers)
        edit_message(chat_id, message_id, f"*{label}* — pick a section:", keyboard)
        answer_callback(cb_id)

    elif data.startswith("section:"):
        # Show section content
        parts = data.removeprefix("section:").rsplit(":", 1)
        if len(parts) != 2:
            answer_callback(cb_id, "Invalid section")
            return
        fname, line_str = parts
        try:
            line = int(line_str)
        except ValueError:
            answer_callback(cb_id, "Invalid line number")
            return

        section = storage.get_note_section(fname, line)
        if not section:
            answer_callback(cb_id, "Section not found")
            return

        # Telegram message limit is 4096 chars
        if len(section) > 4000:
            section = section[:4000] + "\n\n_(truncated)_"

        # Build a back button to return to headers
        back_keyboard = {"inline_keyboard": [[{
            "text": "<< Back to sections",
            "callback_data": f"file:{fname}",
        }], [{
            "text": "<< Back to files",
            "callback_data": "browse",
        }]]}

        edit_message(chat_id, message_id, section, back_keyboard)
        answer_callback(cb_id)

    else:
        answer_callback(cb_id, "Unknown action")
