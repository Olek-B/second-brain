"""Configuration for the Telegram Inbox service.

All values are read from environment variables so they can be set
on PythonAnywhere (or any host) without touching code.
"""

import os


def get_bot_token() -> str:
    """Telegram bot token from @BotFather."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable not set")
    return token


def get_pull_secret() -> str:
    """Shared secret used by the local second-brain to authenticate pulls."""
    secret = os.environ.get("PULL_SECRET", "")
    if not secret:
        raise RuntimeError("PULL_SECRET environment variable not set")
    return secret


def get_allowed_users() -> set[int]:
    """Set of Telegram user IDs allowed to interact with the bot.

    Set ALLOWED_USERS as a comma-separated list of integers, e.g.:
        ALLOWED_USERS=123456,789012
    """
    raw = os.environ.get("ALLOWED_USERS", "")
    if not raw:
        return set()
    try:
        return {int(uid.strip()) for uid in raw.split(",") if uid.strip()}
    except ValueError:
        raise RuntimeError(
            f"ALLOWED_USERS must be comma-separated integers, got: {raw}"
        )


def get_data_dir() -> str:
    """Directory for persistent data (messages + note backups).

    Defaults to ./data relative to this file.
    """
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    return os.environ.get("INBOX_DATA_DIR", default)
