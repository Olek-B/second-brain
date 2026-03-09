"""Flask application for the Telegram Inbox service.

Endpoints:
  POST /webhook              — Telegram webhook (receives updates from Telegram)
  GET  /messages             — Pull pending messages (requires PULL_SECRET)
  POST /messages/ack         — Acknowledge (clear) pulled messages
  POST /notes                — Push note backups from local machine
  GET  /notes                — List backed-up note filenames
  GET  /notes/<fname>        — Read a single backed-up note
  GET  /notes/<fname>/headers — List ## headers in a note

All authenticated endpoints use the X-Pull-Secret header.
"""

from flask import Flask, abort, jsonify, request

try:
    from . import config, storage
    from .bot import register_webhook, handle_update
except ImportError:
    import config, storage  # type: ignore[no-redef]
    from bot import register_webhook, handle_update  # type: ignore[no-redef]

app = Flask(__name__)


def _check_secret() -> None:
    """Abort 403 if the pull secret doesn't match."""
    secret = request.headers.get("X-Pull-Secret", "")
    if secret != config.get_pull_secret():
        abort(403, "Invalid or missing X-Pull-Secret")


# ---------------------------------------------------------------------------
# Telegram webhook
# ---------------------------------------------------------------------------

@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive a Telegram update via webhook."""
    data = request.get_json(force=True, silent=True)
    if not data:
        abort(400, "No JSON body")
    handle_update(data)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Message pull API (used by local second-brain)
# ---------------------------------------------------------------------------

@app.route("/messages", methods=["GET"])
def get_messages():
    """Return all pending messages."""
    _check_secret()
    messages = storage.get_messages()
    return jsonify({"messages": messages})


@app.route("/messages/ack", methods=["POST"])
def ack_messages():
    """Clear the message queue after successful pull."""
    _check_secret()
    count = storage.ack_messages()
    return jsonify({"cleared": count})


# ---------------------------------------------------------------------------
# Note backup API (push from local, browse via Telegram)
# ---------------------------------------------------------------------------

@app.route("/notes", methods=["GET"])
def list_notes():
    """List all backed-up note filenames."""
    _check_secret()
    notes = storage.list_notes()
    return jsonify({"notes": notes})


@app.route("/notes", methods=["POST"])
def push_notes():
    """Receive a batch of notes from the local machine.

    Expects JSON: {"notes": {"filename.md": "content", ...}}
    """
    _check_secret()
    data = request.get_json(force=True, silent=True)
    if not data or "notes" not in data:
        abort(400, "Expected JSON with 'notes' dict")
    count = storage.store_notes(data["notes"])
    return jsonify({"stored": count})


@app.route("/notes/<fname>", methods=["GET"])
def get_note(fname: str):
    """Read a single backed-up note."""
    _check_secret()
    content = storage.read_note(fname)
    if content is None:
        abort(404, f"Note {fname} not found")
    return jsonify({"filename": fname, "content": content})


@app.route("/notes/<fname>/headers", methods=["GET"])
def get_note_headers(fname: str):
    """List ## headers in a backed-up note."""
    _check_secret()
    headers = storage.get_note_headers(fname)
    return jsonify({"filename": fname, "headers": headers})


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

def create_app():
    """Factory for WSGI servers (PythonAnywhere, gunicorn, etc.)."""
    token = config.get_bot_token()
    # Register webhook is called once at startup to tell Telegram
    # where to send updates. On PythonAnywhere you'd call this once
    # manually or via a scheduled task.
    return app
