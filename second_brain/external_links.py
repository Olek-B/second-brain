"""External Links - extract URLs from markdown, fetch favicons, manage link nodes."""

import hashlib
import logging
import re
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from . import config

log = logging.getLogger("second_brain.external_links")

# Module-level regex patterns (pre-compiled for performance)
_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Rate limiting for favicon downloads
_favicon_rate_limit: float = 0
_MIN_FAVICON_INTERVAL = 0.5  # 500ms between requests

# Domain-level favicon cache (in-memory)
_favicon_domain_cache: dict[str, Path | None] = {}


@dataclass
class ExternalLink:
    """Represents an external link found in a markdown file."""

    url: str
    title: str
    source_file: str
    domain: str
    favicon_path: Path | None = None


# Popular domains with known favicon URLs
POPULAR_FAVICONS = {
    "youtube.com": "https://www.youtube.com/s/desktop/1496b515/img/favicon_48x48.png",
    "www.youtube.com": "https://www.youtube.com/s/desktop/1496b515/img/favicon_48x48.png",
    "youtu.be": "https://www.youtube.com/s/desktop/1496b515/img/favicon_48x48.png",
    "github.com": "https://github.com/favicon.ico",
    "www.github.com": "https://github.com/favicon.ico",
    "twitter.com": "https://abs.twimg.com/favicons/twitter.3.ico",
    "x.com": "https://abs.twimg.com/favicons/twitter.3.ico",
    "reddit.com": "https://www.redditstatic.com/desktop2x/img/favicon/favicon-32x32.png",
    "www.reddit.com": "https://www.redditstatic.com/desktop2x/img/favicon/favicon-32x32.png",
    "stackoverflow.com": "https://cdn.sstatic.net/Sites/stackoverflow/Img/favicon.ico",
    "medium.com": "https://medium.com/favicon.ico",
    "wikipedia.org": "https://www.wikipedia.org/static/favicon/wikipedia.ico",
    "en.wikipedia.org": "https://www.wikipedia.org/static/favicon/wikipedia.ico",
    "amazon.com": "https://www.amazon.com/favicon.ico",
    "linkedin.com": "https://static.licdn.com/sc/h/al2o9zrvru7aqj8e1x2rzsrca",
    "www.linkedin.com": "https://static.licdn.com/sc/h/al2o9zrvru7aqj8e1x2rzsrca",
    "instagram.com": "https://www.instagram.com/static/images/ico/favicon.ico/36b3ee2d91ed.ico",
    "facebook.com": "https://www.facebook.com/favicon.ico",
    "www.facebook.com": "https://www.facebook.com/favicon.ico",
    "twitch.tv": "https://static.twitchcdn.net/assets/favicon-32-e29e246c157142c94346.png",
    "www.twitch.tv": "https://static.twitchcdn.net/assets/favicon-32-e29e246c157142c94346.png",
    "discord.com": "https://discord.com/assets/f9bb9c4af2b9c32a2c5ee0014661546d.png",
    "slack.com": "https://a.slack-edge.com/86453/img/icons/app-256.png",
    "notion.so": "https://www.notion.so/images/favicon.ico",
    "www.notion.so": "https://www.notion.so/images/favicon.ico",
    "arxiv.org": "https://arxiv.org/static/browse/0.3.4/images/arxiv.ico",
    "google.com": "https://www.google.com/favicon.ico",
    "www.google.com": "https://www.google.com/favicon.ico",
    "news.ycombinator.com": "https://news.ycombinator.com/favicon.ico",
}


def _normalize_url(url: str) -> str:
    """Normalize URL for deduplication.

    Normalizes:
    - HTTP to HTTPS
    - Removes www. prefix
    - Sorts query parameters
    - Removes fragments

    Args:
        url: URL to normalize.

    Returns:
        Normalized URL.
    """
    parsed = urlparse(url)

    # Force HTTPS
    scheme = "https" if parsed.scheme == "http" else parsed.scheme

    # Remove www.
    netloc = parsed.netloc.replace("www.", "")

    # Sort query parameters for consistent ordering
    if parsed.query:
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        sorted_query = urlencode(sorted(query_params.items()), doseq=True)
    else:
        sorted_query = ""

    # Reconstruct URL without fragment
    normalized = f"{scheme}://{netloc}{parsed.path}"
    if sorted_query:
        normalized += f"?{sorted_query}"

    return normalized


def extract_domain(url: str) -> str:
    """Extract the domain from a URL."""
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path.split("/")[0]
    # Remove www. prefix for cleaner display
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def url_to_node_id(url: str) -> str:
    """Convert a URL to a safe Graphviz node ID."""
    # Use hash for unique ID, but keep domain readable
    domain = extract_domain(url)
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    # Sanitize domain for node ID
    safe_domain = re.sub(r"[^a-zA-Z0-9]", "_", domain)
    return f"ext_{safe_domain}_{url_hash}"


def extract_external_links(brain_dir: Path | None = None) -> list[ExternalLink]:
    """Extract all external links from markdown files in the brain directory.

    Args:
        brain_dir: Path to brain directory. Defaults to config.BRAIN_DIR.

    Returns:
        List of ExternalLink objects, deduplicated by normalized URL.
    """
    if brain_dir is None:
        brain_dir = config.BRAIN_DIR

    # Use pre-compiled pattern
    links_by_url: dict[str, ExternalLink] = {}
    url_to_normalized: dict[str, str] = {}  # Map original URL to normalized form

    md_files = sorted(brain_dir.glob("*.md"))

    for md_file in md_files:
        if md_file.name == "dump.md":
            continue

        content = md_file.read_text()
        source = md_file.stem

        for match in _LINK_PATTERN.finditer(content):
            title = match.group(1).strip()
            url = match.group(2).strip()

            # Skip wiki links and anchors
            if url.startswith(("wiki:", "#", "mailto:", "tel:")):
                continue

            # Validate URL
            if not (url.startswith("http://") or url.startswith("https://")):
                continue

            domain = extract_domain(url)
            normalized_url = _normalize_url(url)

            # Check if we've seen this normalized URL before
            if normalized_url not in url_to_normalized:
                # New URL
                links_by_url[normalized_url] = ExternalLink(
                    url=url,  # Keep original URL
                    title=title,
                    source_file=source,
                    domain=domain,
                )
                url_to_normalized[normalized_url] = normalized_url
            else:
                # Existing URL - add source file
                existing = links_by_url[normalized_url]
                if existing.source_file != source:
                    existing.source_file = f"{existing.source_file}, {source}"

    return list(links_by_url.values())


def get_favicon_cache_dir() -> Path:
    """Get the favicon cache directory."""
    cache_dir = config._XDG_CACHE / "second_brain" / "favicons"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _url_to_cache_filename(url: str) -> str:
    """Convert a URL to a safe cache filename."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return f"{url_hash}.png"


def fetch_favicon(url: str, domain: str, timeout: float = 5.0) -> Path | None:
    """Fetch and cache a favicon for a domain.

    Args:
        url: The full URL
        domain: The domain name
        timeout: Request timeout in seconds (default: 5.0)

    Returns:
        Path to cached favicon, or None if fetching failed.
    """
    global _favicon_rate_limit

    # Check domain cache first (in-memory)
    if domain in _favicon_domain_cache:
        return _favicon_domain_cache[domain]

    cache_dir = get_favicon_cache_dir()
    cache_file = cache_dir / _url_to_cache_filename(url)

    # Return cached version if available
    if cache_file.exists():
        _favicon_domain_cache[domain] = cache_file
        return cache_file

    # Rate limiting - wait if needed
    elapsed = time.time() - _favicon_rate_limit
    if elapsed < _MIN_FAVICON_INTERVAL:
        time.sleep(_MIN_FAVICON_INTERVAL - elapsed)
    _favicon_rate_limit = time.time()

    # Try to get favicon URL
    favicon_url = POPULAR_FAVICONS.get(domain) or POPULAR_FAVICONS.get(
        domain.replace("www.", "")
    )

    if not favicon_url:
        # Try common favicon locations
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        favicon_url = f"{base_url}/favicon.ico"

    # Download favicon with timeout
    try:
        with urllib.request.urlopen(favicon_url, timeout=timeout) as response:
            data = response.read()

        if not data:
            log.debug("Empty favicon response for %s", domain)
            return None

        cache_file.write_bytes(data)

        # Verify it's a valid size (minimum 100 bytes for reasonable favicon)
        if cache_file.stat().st_size >= 100:
            _favicon_domain_cache[domain] = cache_file
            return cache_file
        else:
            log.debug("Favicon too small (%d bytes) for %s", cache_file.stat().st_size, domain)
            cache_file.unlink(missing_ok=True)
            _favicon_domain_cache[domain] = None
            return None

    except urllib.error.URLError as e:
        log.debug("URL error fetching favicon for %s: %s", domain, e)
        cache_file.unlink(missing_ok=True)
        _favicon_domain_cache[domain] = None
        return None
    except TimeoutError as e:
        log.debug("Timeout fetching favicon for %s: %s", domain, e)
        cache_file.unlink(missing_ok=True)
        _favicon_domain_cache[domain] = None
        return None
    except OSError as e:
        log.debug("OS error fetching favicon for %s: %s", domain, e)
        cache_file.unlink(missing_ok=True)
        _favicon_domain_cache[domain] = None
        return None
    except Exception as e:
        log.debug("Unexpected error fetching favicon for %s: %s", domain, e)
        cache_file.unlink(missing_ok=True)
        _favicon_domain_cache[domain] = None
        return None


def get_favicon_for_link(link: ExternalLink) -> Path | None:
    """Get cached favicon for an external link."""
    if link.favicon_path and link.favicon_path.exists():
        return link.favicon_path

    favicon = fetch_favicon(link.url, link.domain)
    link.favicon_path = favicon
    return favicon


def get_domain_display_name(domain: str) -> str:
    """Get a clean display name for a domain."""
    # Remove common TLDs and www
    name = domain.replace("www.", "")

    # Remove .com, .org, etc for cleaner display
    for tld in [".com", ".org", ".net", ".io", ".co", ".edu", ".gov"]:
        if name.endswith(tld):
            name = name[: -len(tld)]
            break

    # Capitalize
    return name.title()


def scan_external_links_for_graph(
    brain_dir: Path | None = None,
    fetch_favicons: bool = True,
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Scan brain for external links and prepare data for graph rendering.

    Args:
        brain_dir: Path to brain directory.
        fetch_favicons: Whether to fetch favicons (default: True).
                       Set to False for faster scanning when favicons
                       aren't needed immediately.

    Returns:
        Tuple of (external_nodes, edges) where:
        - external_nodes: list of dicts with node data (id, url, domain, label, favicon)
        - edges: list of (source_file, node_id) tuples
    """
    if brain_dir is None:
        brain_dir = config.BRAIN_DIR

    links = extract_external_links(brain_dir)
    nodes = []
    edges = []

    for link in links:
        node_id = url_to_node_id(link.url)

        # Only fetch favicons if requested (lazy loading)
        favicon_path = None
        if fetch_favicons:
            favicon_path = get_favicon_for_link(link)

        nodes.append(
            {
                "id": node_id,
                "url": link.url,
                "domain": link.domain,
                "label": get_domain_display_name(link.domain),
                "favicon": favicon_path,
                "sources": link.source_file,
            }
        )

        # Create edges from source files to this external node
        for source in link.source_file.split(", "):
            edges.append((source.strip(), node_id))

    return nodes, edges


def create_favicon_overlay(
    favicon_path: Path,
    output_size: tuple[int, int] = (64, 64),
) -> Path | None:
    """Create a square overlay image from a favicon for Graphviz.

    Args:
        favicon_path: Path to favicon file.
        output_size: Desired output size (width, height).

    Returns:
        Path to processed overlay image, or None if processing failed.
    """
    try:
        from PIL import Image, ImageFile

        # Open and resize favicon
        with Image.open(favicon_path) as img:
            # Convert to RGBA if needed
            if img.mode != "RGBA":
                img = img.convert("RGBA")  # type: ignore[assignment]

            # Resize to output size
            img = img.resize(output_size, Image.Resampling.LANCZOS)  # type: ignore[assignment]

            # Save to temp file
            output = Path(tempfile.mktemp(suffix=".png"))
            img.save(output, "PNG")
            return output
    except Exception as e:
        log.debug("Error creating favicon overlay: %s", e)
        return None


def check_external_links(
    brain_dir: Path | None = None,
) -> dict[str, list[tuple[str, str]]]:
    """Check external links in the brain directory.

    Args:
        brain_dir: Path to brain directory.

    Returns:
        Dict with:
        - "by_domain": dict of {domain: [(file, url), ...]}
        - "by_file": dict of {file: [url, ...]}
    """
    if brain_dir is None:
        brain_dir = config.BRAIN_DIR

    links = extract_external_links(brain_dir)

    by_domain: dict[str, list[tuple[str, str]]] = {}
    by_file: dict[str, list[str]] = {}

    for link in links:
        # Group by domain
        by_domain.setdefault(link.domain, []).append((link.source_file, link.url))

        # Group by file
        for source in link.source_file.split(", "):
            source = source.strip()
            by_file.setdefault(source, []).append(link.url)

    return {
        "by_domain": by_domain,  # type: ignore[dict-item]
        "by_file": by_file,  # type: ignore[dict-item]
    }


def clear_favicon_cache() -> int:
    """Clear the favicon cache directory.

    Returns:
        Number of files deleted.
    """
    cache_dir = get_favicon_cache_dir()
    count = 0

    if cache_dir.exists():
        for file in cache_dir.glob("*.png"):
            try:
                file.unlink()
                count += 1
            except OSError:
                pass

    # Clear in-memory cache too
    _favicon_domain_cache.clear()

    log.info("Cleared %d favicon cache files", count)
    return count
