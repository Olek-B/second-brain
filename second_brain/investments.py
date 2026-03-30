"""Investment tracking module for Second Brain.

Fetches stock data from Stooq.com and uses Groq AI to parse the HTML,
then tracks investments in investments.md with current values.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

from . import config

log = logging.getLogger("second_brain.investments")

INVESTMENTS_FILE = config.BRAIN_DIR / "investments.md"

# Groq model for AI parsing
GROQ_MODEL = config.GROQ_MODEL


@dataclass
class Investment:
    """Represents a single investment holding."""

    ticker: str
    name: str
    shares: float
    buy_price: float  # Price at purchase
    current_price: float | None = None
    currency: str = "PLN"
    last_updated: datetime | None = None

    @property
    def market_value(self) -> float | None:
        """Calculate total market value."""
        if self.current_price is None:
            return None
        return self.shares * self.current_price

    @property
    def cost_basis(self) -> float:
        """Calculate total cost basis (what was paid)."""
        return self.shares * self.buy_price

    @property
    def gain_loss(self) -> float | None:
        """Calculate gain/loss in currency units."""
        if self.current_price is None:
            return None
        return self.market_value - self.cost_basis  # type: ignore[operator]

    @property
    def gain_loss_pct(self) -> float | None:
        """Calculate gain/loss as percentage."""
        if self.current_price is None or self.buy_price == 0:
            return None
        return ((self.current_price - self.buy_price) / self.buy_price) * 100

    def to_markdown(self) -> str:
        """Convert to markdown table row."""
        if self.current_price is None:
            price_str = "N/A"
            value_str = "N/A"
            change_str = "N/A"
        else:
            price_str = f"{self.current_price:.2f} {self.currency}"
            value_str = f"{self.market_value:.2f} {self.currency}"
            gain_loss = self.gain_loss
            gain_loss_pct = self.gain_loss_pct
            if gain_loss is not None and gain_loss_pct is not None:
                sign = "+" if gain_loss >= 0 else ""
                change_str = f"{sign}{gain_loss:.2f} ({sign}{gain_loss_pct:.1f}%)"
            else:
                change_str = "N/A"

        updated = (
            self.last_updated.strftime("%Y-%m-%d %H:%M")
            if self.last_updated
            else "Never"
        )
        return f"| {self.ticker} | {self.name} | {self.shares} | {self.buy_price:.2f} {self.currency} | {price_str} | {change_str} | {value_str} | {updated} |"


def fetch_stooq_csv(ticker: str) -> dict | None:
    """Fetch stock data from Stooq.com CSV API.

    Args:
        ticker: Stock ticker symbol (e.g., 'ale' for Allegro)

    Returns:
        Dict with keys: name, price, currency, or None if failed
    """
    # Stooq CSV API: s=symbol, f=sd2t2o2c (symbol, date, time, close), h=0 (no header), r=1 (CSV)
    url = f"https://stooq.com/q/l/?s={ticker.lower()}&f=sd2t2o2c&h=0&r=1"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        lines = response.text.strip().split("\n")

        if len(lines) < 2:
            return None

        # Parse CSV: Symbol,Date,Time,Close
        data_line = lines[1]
        parts = data_line.split(",")

        if len(parts) < 4:
            return None

        symbol = parts[0]
        close_price = parts[3]

        # Get company name from the quote page (lightweight fetch)
        name = _fetch_company_name(ticker)

        return {
            "name": name or symbol,
            "price": float(close_price) if close_price else None,
            "currency": "PLN",  # Stooq is Polish, defaults to PLN
        }

    except requests.RequestException as e:
        log.error("Failed to fetch Stooq CSV data for %s: %s", ticker, e)
        return None
    except (ValueError, IndexError) as e:
        log.error("Failed to parse Stooq CSV for %s: %s", ticker, e)
        return None


def _fetch_company_name(ticker: str) -> str | None:
    """Fetch company name from Stooq quote page.

    Makes a lightweight request to get the company name from the page title.
    """
    url = f"https://stooq.com/q/?s={ticker.lower()}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # Extract title: <TITLE>...
        import re

        title_match = re.search(r"<TITLE>([^<]+)</TITLE>", response.text, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
            # Title format: "ALLEGRO.PL - Akcje, notowania na GPW - Stooq.pl"
            # Extract just the company name part before the dash
            name = title.split(" - ")[0].strip()
            # Remove ".PL" suffix if present
            name = re.sub(r"\.PL\s*$", "", name, flags=re.IGNORECASE)
            return name

    except Exception as e:
        log.debug("Could not fetch company name for %s: %s", ticker, e)

    return None


def parse_investment_input(user_input: str) -> tuple[str, str, float, float]:
    """Parse user investment input like '{ale} allegro - 3 - 25.50'.

    Args:
        user_input: String in format "{ticker} name - shares - buy_price"
                   or "{ticker} name - shares" (buy_price optional)

    Returns:
        Tuple of (ticker, name, shares, buy_price)
    """
    # Pattern: {ticker} name - shares [- buy_price]
    pattern = r"\{([^}]+)\}\s+([^-]+?)\s+-\s+(\d+(?:\.\d+)?)(?:\s+-\s+(\d+(?:\.\d+)?))?"
    match = re.match(pattern, user_input.strip())

    if not match:
        raise ValueError(
            f"Invalid format. Expected: '{{ticker}} name - shares [- buy_price]', got: {user_input}"
        )

    ticker = match.group(1).strip().lower()
    name = match.group(2).strip()
    shares = float(match.group(3)) if match.group(3) else 0.0
    buy_price = float(match.group(4)) if match.group(4) else 0.0

    return ticker, name, shares, buy_price


def load_investments() -> list[Investment]:
    """Load investments from investments.md.

    Returns:
        List of Investment objects
    """
    if not INVESTMENTS_FILE.exists():
        return []

    content = INVESTMENTS_FILE.read_text()
    investments = []

    # Parse markdown table rows
    # Format: | ticker | name | shares | buy_price | current_price | change | value | updated |
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("|") or "ticker" in line.lower():
            continue
        
        # Skip header separator line (|---|---|...)
        if re.match(r'^\|[-\s|]+\|$', line):
            continue

        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8:
            continue

        try:
            ticker = parts[1].strip()
            name = parts[2].strip()
            shares_str = parts[3].strip()
            shares = float(shares_str.replace(",", ".")) if shares_str != "N/A" else 0

            # Parse buy price
            buy_price_str = parts[4].split()[0] if len(parts) > 4 else "0"
            buy_price = float(buy_price_str.replace(",", ".")) if buy_price_str != "N/A" else 0

            # Parse current price
            current_price = None
            if len(parts) > 5 and parts[5] != "N/A":
                price_str = parts[5].split()[0]
                if price_str:
                    try:
                        current_price = float(price_str.replace(",", "."))
                    except ValueError:
                        pass

            # Parse currency
            currency = "PLN"
            if len(parts) > 4:
                price_parts = parts[4].split()
                if len(price_parts) > 1:
                    currency = price_parts[-1]

            investments.append(
                Investment(
                    ticker=ticker,
                    name=name,
                    shares=shares,
                    buy_price=buy_price,
                    current_price=current_price,
                    currency=currency,
                )
            )
        except (ValueError, IndexError) as e:
            log.warning("Failed to parse investment line: %s - %s", line, e)
            continue

    return investments


def save_investments(investments: list[Investment]) -> None:
    """Save investments to investments.md.

    Args:
        investments: List of Investment objects to save
    """
    header = """# Investment Portfolio

Track stock holdings with live data from Stooq.com.

| Ticker | Name | Shares | Buy Price | Current Price | Gain/Loss | Value | Last Updated |
|--------|------|--------|-----------|---------------|-----------|-------|--------------|
"""

    rows = [inv.to_markdown() for inv in investments]
    content = header + "\n".join(rows) + "\n"

    INVESTMENTS_FILE.write_text(content)
    log.info("Saved %d investments to %s", len(investments), INVESTMENTS_FILE)


def update_investment(ticker: str, name: str, shares: float, buy_price: float) -> Investment:
    """Add or update a single investment with fresh data from Stooq.

    Args:
        ticker: Stock ticker symbol
        name: Company name
        shares: Number of shares owned
        buy_price: Price per share at purchase (for gain/loss tracking)

    Returns:
        Updated Investment object
    """
    log.info("Fetching data for %s (%s)...", name, ticker)

    # Fetch data from Stooq CSV API
    data = fetch_stooq_csv(ticker)

    # Load existing investments
    investments = load_investments()

    # Find and update or add investment
    investment = None
    for inv in investments:
        if inv.ticker == ticker:
            investment = inv
            investment.shares = shares
            investment.name = name
            # Only update buy_price if explicitly provided
            if buy_price > 0:
                investment.buy_price = buy_price
            break

    if not investment:
        if buy_price <= 0:
            # If no buy price provided for new investment, use current price
            if data and data["price"]:
                buy_price = float(data["price"])
            else:
                buy_price = 0
        investment = Investment(ticker=ticker, name=name, shares=shares, buy_price=buy_price)

    # Update with fresh data
    if data and data["price"] is not None:
        investment.current_price = float(data["price"])
        investment.currency = data.get("currency", "PLN")
        if data.get("name"):
            investment.name = data["name"]
    investment.last_updated = datetime.now()

    # Save back
    # Replace existing or add new
    investments = [inv for inv in investments if inv.ticker != ticker]
    investments.append(investment)
    save_investments(investments)

    return investment


def refresh_all_investments() -> list[Investment]:
    """Refresh all investments with current data from Stooq.

    Returns:
        List of updated Investment objects
    """
    investments = load_investments()
    updated = []

    for inv in investments:
        log.info("Refreshing %s...", inv.ticker)
        try:
            data = fetch_stooq_csv(inv.ticker)
            if data and data["price"] is not None:
                inv.current_price = float(data["price"])
                inv.currency = data.get("currency", "PLN")
                if data.get("name"):
                    inv.name = data["name"]
                inv.last_updated = datetime.now()
                updated.append(inv)
        except Exception as e:
            log.warning("Failed to refresh %s: %s", inv.ticker, e)

    if updated:
        save_investments(investments)

    return updated


def get_portfolio_summary() -> dict:
    """Get summary of portfolio value.

    Returns:
        Dict with total_value, invested_count, last_updated
    """
    investments = load_investments()

    total_value = 0.0
    count_with_price = 0
    last_updated = None

    for inv in investments:
        if inv.current_price is not None:
            value = inv.market_value
            if value is not None:
                total_value += value
                count_with_price += 1
                if inv.last_updated and (
                    last_updated is None or inv.last_updated > last_updated
                ):
                    last_updated = inv.last_updated

    return {
        "total_value": total_value,
        "invested_count": count_with_price,
        "total_count": len(investments),
        "last_updated": last_updated,
    }
