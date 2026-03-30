"""Action handlers for Second Brain TUI."""

import os
import subprocess
import webbrowser

from textual import work
from textual.widgets import Input, Static

from .. import config
from ..plugins import get_manager
from .widgets import FileList, PreviewPane


class ActionMixin:
    """Mixin providing action handlers for BrainApp."""

    def action_edit_file(self) -> None:
        """Open selected file in $EDITOR."""
        app = self  # type: ignore
        if app._selected_file is None:
            app._set_status(" No file selected")
            return

        editor = os.environ.get("EDITOR", "nvim")
        fpath = config.BRAIN_DIR / app._selected_file

        pm = get_manager()
        pm.dispatch_on_tui_edit_file(app._selected_file)

        with app.app.suspend():
            subprocess.run([editor, str(fpath)])

        app._show_preview(app._selected_file)
        app._set_status(f"Returned from {editor}")

    def action_open_dump(self) -> None:
        """Open dump.md in $EDITOR."""
        app = self  # type: ignore
        editor = os.environ.get("EDITOR", "nvim")
        dump_path = config.DUMP_FILE
        if not dump_path.exists():
            dump_path.write_text("# Dump\n\nWrite your raw thoughts here...\n")

        with app.app.suspend():
            subprocess.run([editor, str(dump_path)])

        app._set_status("Dump file edited. Press [p] to process.")

    @work(thread=True)
    def action_process_dump(self) -> None:
        """Process dump.md through the Librarian."""
        app = self  # type: ignore
        app._set_status(" Processing dump.md with AI...")

        pm = get_manager()
        pm.dispatch_before_tui_process_dump()

        try:
            from ..librarian import clear_dump, execute_actions, process_dump

            actions = process_dump()

            if "error" in actions:
                app.app.call_from_thread(app._set_status, f" {actions['error']}")
                return

            summaries = execute_actions(actions)
            clear_dump()

            summary = " | ".join(summaries) if summaries else "No actions taken"
            app.app.call_from_thread(app._set_status, f" {summary}")
            app.app.call_from_thread(app._refresh_file_list)

            pm.dispatch_after_tui_process_dump(summaries)

        except Exception as e:
            app.app.call_from_thread(app._set_status, f" Error: {e}")

    @work(thread=True)
    def action_view_graph(self) -> None:
        """Generate graph and refresh wallpaper."""
        app = self  # type: ignore
        app._set_status(" Generating knowledge graph...")

        pm = get_manager()
        pm.dispatch_before_tui_graph()

        try:
            from ..wallpaper import refresh_wallpaper

            result = refresh_wallpaper()
            app.app.call_from_thread(app._set_status, f" {result}")

            pm.dispatch_after_tui_graph(result)
        except Exception as e:
            app.app.call_from_thread(app._set_status, f" Graph error: {e}")

    def action_refresh_list(self) -> None:
        """Refresh the file list."""
        app = self  # type: ignore
        app._refresh_file_list()
        app._set_status(" File list refreshed")

    @work(thread=True)
    def action_pull_telegram(self) -> None:
        """Pull messages from Telegram inbox into dump.md."""
        app = self  # type: ignore
        app._set_status(" Pulling Telegram messages...")

        pm = get_manager()
        pull_plugin = None
        for p in pm.plugins:
            if p.name == "telegram_pull":
                pull_plugin = p
                break

        if pull_plugin is None:
            app.app.call_from_thread(
                app._set_status,
                " telegram_pull plugin not loaded. Check config.",
            )
            return

        try:
            count = pull_plugin.do_pull()  # type: ignore[attr-defined]
            if count:
                app.app.call_from_thread(
                    app._set_status,
                    f" Pulled {count} message(s). Press [p] to process dump.",
                )
                app.app.call_from_thread(app._refresh_file_list)
            else:
                app.app.call_from_thread(app._set_status, " No new Telegram messages")
        except Exception as e:
            app.app.call_from_thread(app._set_status, f" Telegram pull error: {e}")

    @work(thread=True)
    def action_run_janitor(self) -> None:
        """Run the AI janitor to fix formatting and add missing links."""
        app = self  # type: ignore
        app._set_status(" Running janitor (formatting + links)...")

        pm = get_manager()
        pm.dispatch_before_tui_janitor()

        try:
            from ..janitor import run_janitor

            summaries = run_janitor(dry_run=False)
            summary = " | ".join(summaries)
            app.app.call_from_thread(app._set_status, f" {summary}")
            app.app.call_from_thread(app._refresh_file_list)

            if app._selected_file:
                app.app.call_from_thread(app._show_preview, app._selected_file)

            pm.dispatch_after_tui_janitor(summaries)

        except Exception as e:
            app.app.call_from_thread(app._set_status, f" Janitor error: {e}")

    def action_ask_brain(self) -> None:
        """Show the ask input field."""
        app = self  # type: ignore
        ask_input = app.query_one("#ask-input", Input)
        ask_input.add_class("visible")
        ask_input.focus()
        app._set_status("Type your question and press Enter. Escape to cancel.")

    def action_view_todos(self) -> None:
        """Show the todo list in the preview pane."""
        from ..wallpaper import _parse_todos
        app = self  # type: ignore
        title = app.query_one("#preview-title", Static)
        preview = app.query_one("#preview", PreviewPane)

        title.update(" Todo List")

        items = _parse_todos()
        if not items:
            preview.set_content(
                "*No todo items found.*\n\nTasks are automatically extracted from your dumps when you process them."
            )
            app._set_status(" Todo list is empty")
            return

        content = "## Pending Tasks\n\n"
        pending = [text for done, text in items if not done]
        completed = [text for done, text in items if done]

        if pending:
            content += "### To Do\n\n"
            for text in pending:
                content += f"- [ ] {text}\n"
            content += "\n"

        if completed:
            content += "### Completed\n\n"
            for text in completed:
                content += f"- [x] {text}\n"

        content += "\n---\n\n*Tip: Press `d` to edit todo.md directly, or use any markdown editor to toggle tasks.*"

        preview.set_content(content)
        app._set_status(f" Showing {len(pending)} pending, {len(completed)} completed tasks")

    def action_daily_note(self) -> None:
        """Create or open today's daily note."""
        from ..daily_note import create_daily_note, get_today_filename
        app = self  # type: ignore
        filename = get_today_filename()
        note_path, was_created = create_daily_note(open_editor=False)

        if was_created:
            app._set_status(f"Created: {filename}")
        else:
            app._set_status(f"Opened: {filename}")

        app._refresh_file_list()

        try:
            idx = app._files.index(filename)
            file_list = app.query_one("#file-list", FileList)
            file_list.index = idx
            app._selected_file = filename
            app._show_preview(filename)
        except ValueError:
            pass

    def action_view_tags(self) -> None:
        """Show all tags in the preview pane."""
        from ..tags import get_all_tags
        app = self  # type: ignore
        title = app.query_one("#preview-title", Static)
        preview = app.query_one("#preview", PreviewPane)

        title.update(" Tags")

        tag_index = get_all_tags()
        if not tag_index:
            preview.set_content(
                "*No tags found.*\n\nAdd #tags to your notes like:\n- #dns\n- #homelab\n- #todo\n\nTags are automatically extracted from all files."
            )
            app._set_status(" No tags found")
            return

        content = "## All Tags\n\n"
        for tag in sorted(tag_index.keys()):
            files = tag_index[tag]
            content += f"### #{tag} ({len(files)} file{'s' if len(files) > 1 else ''})\n\n"
            for f in files:
                content += f"- [[{f.removesuffix('.md')}]]\n"
            content += "\n"

        preview.set_content(content)
        app._set_status(f" Showing {len(tag_index)} tags")

    def action_view_duplicates(self) -> None:
        """Show potential duplicates in the preview pane."""
        from ..duplicates import find_duplicates, get_similar_words
        app = self  # type: ignore
        title = app.query_one("#preview-title", Static)
        preview = app.query_one("#preview", PreviewPane)

        title.update(" Potential Duplicates")

        duplicates = find_duplicates(threshold=0.3)
        if not duplicates:
            preview.set_content(
                "*No potential duplicates found.*\n\nYour notes look unique! Files are compared using word overlap analysis."
            )
            app._set_status(" No duplicates found")
            return

        content = "## Potential Duplicates\n\n"
        content += "Files with significant word overlap (may cover similar topics):\n\n"

        for file1, file2, similarity in duplicates:
            pct = int(similarity * 100)
            content += f"### {file1} + {file2} ({pct}% similar)\n\n"

            common = get_similar_words(file1, file2)
            if common:
                content += f"**Common topics:** {', '.join(common[:10])}\n\n"

            content += "*Tip: Review these files and consider merging if they cover the same topic.*\n\n"
            content += "---\n\n"

        preview.set_content(content)
        app._set_status(f" Found {len(duplicates)} potential duplicate pairs")

    def action_view_investments(self) -> None:
        """Show investment portfolio in the preview pane."""
        from ..investments import get_portfolio_summary, load_investments
        app = self  # type: ignore
        title = app.query_one("#preview-title", Static)
        preview = app.query_one("#preview", PreviewPane)

        title.update(" Investment Portfolio")

        investments = load_investments()
        summary = get_portfolio_summary()

        if not investments:
            preview.set_content(
                "*No investments tracked yet.*\n\n"
                "Add investments using the CLI:\n"
                "```\n"
                "second-brain invest \"{ale} allegro - 3 - 25.50\"\n"
                "```\n\n"
                "Format: `{ticker} name - shares [- buy_price]`\n\n"
                "The buy price is used to calculate your gain/loss."
            )
            app._set_status(" No investments tracked")
            return

        content = "## Investment Portfolio\n\n"

        total_gain_loss = sum(
            (inv.gain_loss or 0) for inv in investments if inv.current_price
        )
        content += "**Portfolio Summary:**\n"
        content += f"- **Total Value:** {summary['total_value']:.2f} PLN\n"
        gain_loss_sign = "+" if total_gain_loss >= 0 else ""
        content += f"- **Total Gain/Loss:** {gain_loss_sign}{total_gain_loss:.2f} PLN\n"
        content += f"- **Positions:** {summary['invested_count']}/{summary['total_count']} with current prices\n"
        if summary["last_updated"]:
            content += f"- **Last Updated:** {summary['last_updated'].strftime('%Y-%m-%d %H:%M')}\n"
        content += "\n---\n\n"

        content += "| Ticker | Name | Shares | Buy Price | Current | Gain/Loss | Value |\n"
        content += "|--------|------|--------|-----------|---------|-----------|-------|\n"

        for inv in investments:
            if inv.current_price:
                buy_str = f"{inv.buy_price:.2f} {inv.currency}"
                price_str = f"{inv.current_price:.2f} {inv.currency}"
                value_str = f"{inv.market_value:.2f} {inv.currency}"
                gain_loss = inv.gain_loss
                gain_loss_pct = inv.gain_loss_pct
                if gain_loss is not None and gain_loss_pct is not None:
                    sign = "+" if gain_loss >= 0 else ""
                    gain_str = f"{sign}{gain_loss:.2f} ({sign}{gain_loss_pct:.1f}%)"
                else:
                    gain_str = "N/A"
            else:
                buy_str = f"{inv.buy_price:.2f} {inv.currency}" if inv.buy_price > 0 else "N/A"
                price_str = "N/A"
                value_str = "N/A"
                gain_str = "N/A"

            content += f"| {inv.ticker} | {inv.name} | {inv.shares} | {buy_str} | {price_str} | {gain_str} | {value_str} |\n"

        content += "\n*Data fetched from Stooq.com. Press `I` to refresh prices*"

        preview.set_content(content)
        app._set_status(f" Showing {len(investments)} investments")

    def action_view_rss(self) -> None:
        """Show RSS feed browser in the preview pane."""
        from ..rss_reader import load_feeds, get_all_entries
        app = self  # type: ignore
        title = app.query_one("#preview-title", Static)
        preview = app.query_one("#preview", PreviewPane)

        title.update("📰 RSS Feed Reader")
        app._set_status(" Loading feeds...")

        feeds = load_feeds()

        if not feeds:
            preview.set_content(
                "*No RSS feeds configured.*\n\n"
                "Add feeds using the CLI:\n"
                "```\n"
                "second-brain rss --add \"Channel Name\" \"https://youtube.com/feeds/videos.xml?channel_id=XXX\"\n"
                "```\n\n"
                "Or edit `rss.md` in your brain directory directly."
            )
            app._set_status(" No feeds configured")
            return

        content = "## Configured Feeds\n\n"

        for feed in feeds:
            content += f"### {feed.name} ({feed.feed_type})\n"
            content += f"URL: `{feed.url}`\n\n"

        content += "---\n\n"
        content += "## Latest Entries\n\n"

        entries = get_all_entries()

        if entries:
            for entry in entries[:20]:
                time_str = entry.published.strftime("%Y-%m-%d %H:%M")
                content += f"### [{entry.title}]({entry.link})\n\n"
                content += f"*{time_str} • {entry.source}*\n\n"
                if entry.summary:
                    content += f"{entry.summary}\n\n"
                content += "---\n\n"
        else:
            content += "*No entries fetched yet. Press `R` to refresh.*\n"

        content += "\n*Tip: Click any link to open in browser. Press `R` to refresh feeds.*"

        preview.set_content(content)
        app._set_status(f" Showing {len(feeds)} feeds, {len(entries)} entries")

    @work(thread=True)
    def _do_refresh_rss(self) -> None:
        """Refresh RSS feeds in background thread."""
        from ..rss_reader import get_all_entries, load_feeds
        app = self  # type: ignore
        app.app.call_from_thread(app._set_status, " Refreshing RSS feeds...")

        try:
            entries = get_all_entries()
            feeds = load_feeds()

            title = app.query_one("#preview-title", Static)
            preview = app.query_one("#preview", PreviewPane)

            if not feeds:
                app.app.call_from_thread(
                    app._set_status,
                    " No feeds configured"
                )
                return

            content = "## Configured Feeds\n\n"
            for feed in feeds:
                content += f"### {feed.name} ({feed.feed_type})\n"
                content += f"URL: `{feed.url}`\n\n"

            content += "---\n\n## Latest Entries\n\n"

            if entries:
                for entry in entries[:20]:
                    time_str = entry.published.strftime("%Y-%m-%d %H:%M")
                    content += f"### [{entry.title}]({entry.link})\n\n"
                    content += f"*{time_str} • {entry.source}*\n\n"
                    if entry.summary:
                        content += f"{entry.summary}\n\n"
                    content += "---\n\n"
            else:
                content += "*No entries fetched.*\n"

            app.app.call_from_thread(preview.set_content, content)
            app.app.call_from_thread(
                app._set_status,
                f" Refreshed {len(feeds)} feeds, {len(entries)} entries"
            )

        except Exception as e:
            app.app.call_from_thread(app._set_status, f" RSS refresh error: {e}")

    def action_view_analytics(self) -> None:
        """Show personal analytics dashboard in the preview pane."""
        from ..analytics import get_full_analytics, format_analytics_dashboard
        app = self  # type: ignore
        title = app.query_one("#preview-title", Static)
        preview = app.query_one("#preview", PreviewPane)

        title.update("📊 Analytics Dashboard")
        app._set_status(" Generating analytics...")

        try:
            data = get_full_analytics(days=30)
            dashboard = format_analytics_dashboard(data)
            preview.set_content(dashboard)
            app._set_status(" Analytics dashboard displayed")
        except Exception as e:
            app._set_status(f" Analytics error: {e}")

    @work(thread=True)
    def _do_refresh_investments(self) -> None:
        """Run investment refresh in a background thread."""
        from ..investments import (
            get_portfolio_summary,
            load_investments,
            refresh_all_investments,
        )
        app = self  # type: ignore
        app.app.call_from_thread(app._set_status, " Refreshing investment prices from Stooq...")

        try:
            updated = refresh_all_investments()
            summary = get_portfolio_summary()

            title = app.query_one("#preview-title", Static)
            preview = app.query_one("#preview", PreviewPane)

            app.app.call_from_thread(title.update, " Investment Portfolio")

            investments_list = load_investments()
            content = "## Investment Portfolio (Updated)\n\n"
            content += "**Portfolio Summary:**\n"
            content += f"- **Total Value:** {summary['total_value']:.2f} PLN\n"
            total_gain_loss = sum(
                (inv.gain_loss or 0) for inv in investments_list if inv.current_price
            )
            gain_loss_sign = "+" if total_gain_loss >= 0 else ""
            content += f"- **Total Gain/Loss:** {gain_loss_sign}{total_gain_loss:.2f} PLN\n"
            content += f"- **Positions:** {summary['invested_count']}/{summary['total_count']} with current prices\n"
            content += "\n---\n\n"
            content += "| Ticker | Name | Shares | Buy Price | Current | Gain/Loss | Value |\n"
            content += "|--------|------|--------|-----------|---------|-----------|-------|\n"

            for inv in investments_list:
                if inv.current_price:
                    buy_str = f"{inv.buy_price:.2f} {inv.currency}"
                    price_str = f"{inv.current_price:.2f} {inv.currency}"
                    value_str = f"{inv.market_value:.2f} {inv.currency}"
                    gain_loss = inv.gain_loss
                    gain_loss_pct = inv.gain_loss_pct
                    if gain_loss is not None and gain_loss_pct is not None:
                        sign = "+" if gain_loss >= 0 else ""
                        gain_str = f"{sign}{gain_loss:.2f} ({sign}{gain_loss_pct:.1f}%)"
                    else:
                        gain_str = "N/A"
                else:
                    buy_str = f"{inv.buy_price:.2f} {inv.currency}" if inv.buy_price > 0 else "N/A"
                    price_str = "N/A"
                    value_str = "N/A"
                    gain_str = "N/A"

                content += f"| {inv.ticker} | {inv.name} | {inv.shares} | {buy_str} | {price_str} | {gain_str} | {value_str} |\n"

            content += f"\n*Just refreshed {len(updated)} investments from Stooq.com*"

            app.app.call_from_thread(preview.set_content, content)
            app.app.call_from_thread(app._set_status, f" Refreshed {len(updated)} investments")

        except Exception as e:
            app.app.call_from_thread(app._set_status, f" Refresh error: {e}")

    def action_refresh_investments(self) -> None:
        """Refresh all investment prices from Stooq."""
        self._do_refresh_investments()
