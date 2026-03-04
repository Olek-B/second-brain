"""Telegram Brain Bot - add notes to your Second Brain from your phone.

A plugin that runs a Telegram bot in the background, letting you:
  /dump <text>   - Write thoughts to dump.md and process them with AI
  /quick <text>  - Write directly to dump.md without processing
  /todos         - List pending todo items
  /files         - List all brain files
  /read <file>   - Read a brain file
  /graph         - Regenerate knowledge graph + wallpaper
  /janitor       - Run the AI janitor pass
  /status        - Show brain stats

SETUP:
  1. Create a bot via @BotFather on Telegram, get the token.
  2. Get your Telegram user ID (message @userinfobot).
  3. Add to ~/.config/second_brain/config.json:
     {
       "plugins": {
         "enabled": ["telegram_brain_bot"],
         "config": {
           "telegram_brain_bot": {
             "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
             "allowed_users": [YOUR_USER_ID]
           }
         }
       }
     }
  4. Install the dependency:
     pip install python-telegram-bot

The bot runs in a background thread via run_background() and polls
Telegram for messages.  It is restricted to the user IDs listed in
allowed_users for security.
"""

from __future__ import annotations

import logging
from pathlib import Path

from second_brain.plugins import BrainAPI, SecondBrainPlugin

log = logging.getLogger("second_brain.plugins.telegram_brain_bot")


class TelegramBrainBot(SecondBrainPlugin):
    """Telegram bot plugin for Second Brain."""

    name = "telegram_brain_bot"

    def on_load(self, ctx: BrainAPI) -> None:
        """Validate config on load."""
        self.ctx = ctx
        token = self.config.get("bot_token", "")
        users = self.config.get("allowed_users", [])

        if not token:
            log.warning(
                "telegram_brain_bot: No bot_token in config. "
                "Add it to plugins.config.telegram_brain_bot.bot_token"
            )
        if not users:
            log.warning(
                "telegram_brain_bot: No allowed_users in config. "
                "Bot will reject all messages for security."
            )

    def run_background(self, ctx: BrainAPI) -> None:
        """Start the Telegram bot polling loop."""
        try:
            from telegram import Update
            from telegram.ext import (
                ApplicationBuilder,
                CommandHandler,
                ContextTypes,
                MessageHandler,
                filters,
            )
        except ImportError:
            log.error(
                "telegram_brain_bot: python-telegram-bot not installed. "
                "Run: pip install python-telegram-bot"
            )
            print("[telegram] ERROR: python-telegram-bot not installed. Run: pip install python-telegram-bot")
            return

        token = self.config.get("bot_token", "")
        if not token:
            log.error("telegram_brain_bot: No bot_token configured, cannot start.")
            print("[telegram] ERROR: No bot_token in config.")
            return

        allowed_users: set[int] = set(self.config.get("allowed_users", []))

        def _check_user(user_id: int) -> bool:
            """Security: only allow configured users."""
            if not allowed_users:
                return False
            return user_id in allowed_users

        async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.effective_user or not _check_user(update.effective_user.id):
                return
            await update.message.reply_text(
                "Second Brain Bot\n\n"
                "Commands:\n"
                "/dump <text> - Process thoughts with AI\n"
                "/quick <text> - Add to dump without processing\n"
                "/todos - List pending tasks\n"
                "/files - List brain files\n"
                "/read <file> - Read a file\n"
                "/graph - Regenerate graph\n"
                "/janitor - Run cleanup\n"
                "/status - Brain stats"
            )

        async def cmd_dump(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.effective_user or not _check_user(update.effective_user.id):
                return
            text = " ".join(context.args) if context.args else ""
            if not text:
                await update.message.reply_text("Usage: /dump <your thoughts>")
                return

            await update.message.reply_text("Processing...")
            try:
                print(f"[telegram] /dump received: {text[:80]}...")
                actions = ctx.process_dump(text)
                if "error" in actions:
                    print(f"[telegram] /dump error: {actions['error']}")
                    await update.message.reply_text(f"Error: {actions['error']}")
                    return
                summaries = ctx.execute_actions(actions)
                result = "\n".join(f"  {s}" for s in summaries)
                print(f"[telegram] /dump done: {result}")
                await update.message.reply_text(f"Done!\n{result}")
            except Exception as e:
                print(f"[telegram] /dump exception: {e}")
                await update.message.reply_text(f"Error: {e}")

        async def cmd_quick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.effective_user or not _check_user(update.effective_user.id):
                return
            text = " ".join(context.args) if context.args else ""
            if not text:
                await update.message.reply_text("Usage: /quick <your thoughts>")
                return

            dump_path = ctx.dump_file
            if dump_path.exists():
                existing = dump_path.read_text().rstrip()
            else:
                existing = "# Dump"
            dump_path.write_text(f"{existing}\n\n{text}\n")
            await update.message.reply_text(
                "Added to dump.md. Use /dump to process or process from TUI."
            )

        async def cmd_todos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.effective_user or not _check_user(update.effective_user.id):
                return
            try:
                content = ctx.read_file("todo.md")
                # Extract pending items
                pending = []
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("- [ ]"):
                        pending.append(line)

                if not pending:
                    await update.message.reply_text("No pending todos!")
                else:
                    # Telegram has a 4096 char limit
                    text = "\n".join(pending[:50])
                    if len(pending) > 50:
                        text += f"\n\n... and {len(pending) - 50} more"
                    await update.message.reply_text(f"Pending todos:\n{text}")
            except FileNotFoundError:
                await update.message.reply_text("No todo.md yet.")

        async def cmd_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.effective_user or not _check_user(update.effective_user.id):
                return
            files = ctx.get_brain_files()
            if not files:
                await update.message.reply_text("Brain is empty.")
            else:
                text = "\n".join(f"  {f}" for f in files)
                await update.message.reply_text(f"Brain files ({len(files)}):\n{text}")

        async def cmd_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.effective_user or not _check_user(update.effective_user.id):
                return
            fname = " ".join(context.args) if context.args else ""
            if not fname:
                await update.message.reply_text("Usage: /read <filename.md>")
                return
            if not fname.endswith(".md"):
                fname += ".md"
            try:
                content = ctx.read_file(fname)
                # Telegram limit: 4096 chars
                if len(content) > 4000:
                    content = content[:4000] + "\n\n... (truncated)"
                await update.message.reply_text(content)
            except FileNotFoundError:
                await update.message.reply_text(f"{fname} not found.")

        async def cmd_graph(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.effective_user or not _check_user(update.effective_user.id):
                return
            await update.message.reply_text("Generating graph...")
            try:
                result = ctx.refresh_wallpaper()
                await update.message.reply_text(result)
            except Exception as e:
                await update.message.reply_text(f"Error: {e}")

        async def cmd_janitor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.effective_user or not _check_user(update.effective_user.id):
                return
            await update.message.reply_text("Running janitor...")
            try:
                summaries = ctx.run_janitor()
                result = "\n".join(f"  {s}" for s in summaries)
                await update.message.reply_text(f"Done!\n{result}")
            except Exception as e:
                await update.message.reply_text(f"Error: {e}")

        async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.effective_user or not _check_user(update.effective_user.id):
                return
            files = ctx.get_brain_files()
            nodes, edges = ctx.scan_brain()

            # Count pending todos
            pending = 0
            try:
                content = ctx.read_file("todo.md")
                pending = content.count("- [ ]")
            except FileNotFoundError:
                pass

            text = (
                f"Second Brain Status\n"
                f"  Files: {len(files)}\n"
                f"  Graph nodes: {len(nodes)}\n"
                f"  Graph edges: {len(edges)}\n"
                f"  Pending todos: {pending}"
            )
            await update.message.reply_text(text)

        # Build and run the bot
        app = ApplicationBuilder().token(token).build()

        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("help", cmd_start))
        app.add_handler(CommandHandler("dump", cmd_dump))
        app.add_handler(CommandHandler("quick", cmd_quick))
        app.add_handler(CommandHandler("todos", cmd_todos))
        app.add_handler(CommandHandler("files", cmd_files))
        app.add_handler(CommandHandler("read", cmd_read))
        app.add_handler(CommandHandler("graph", cmd_graph))
        app.add_handler(CommandHandler("janitor", cmd_janitor))
        app.add_handler(CommandHandler("status", cmd_status))

        log.info("Telegram bot starting (polling)...")
        print("[telegram] Bot starting — polling for messages...")
        # We're in a daemon thread, so asyncio.run() / run_polling() fails
        # because it tries to install signal handlers (main thread only).
        # Instead, create our own event loop and run the app manually.
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(app.initialize())
            loop.run_until_complete(
                app.updater.start_polling(drop_pending_updates=True)
            )
            loop.run_until_complete(app.start())
            print("[telegram] Bot is live and polling!")
            # Block until the thread is killed (daemon thread dies with main)
            loop.run_forever()
        except Exception as e:
            log.error("Telegram bot event loop error: %s", e)
            print(f"[telegram] ERROR: Event loop crashed: {e}")
        finally:
            try:
                loop.run_until_complete(app.updater.stop())
                loop.run_until_complete(app.stop())
                loop.run_until_complete(app.shutdown())
            except Exception:
                pass
            loop.close()
