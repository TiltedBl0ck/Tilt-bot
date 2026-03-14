# cogs/utils/web_search.py
import logging
import aiohttp
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime
from typing import Optional, List, Dict

try:
    from duckduckgo_search import AsyncDDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False

logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"

# ── SSRF protection ────────────────────────────────────────────────────────────

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / AWS metadata
    ipaddress.ip_network("100.64.0.0/10"),    # CGNAT
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return True  # unparseable → treat as unsafe


def _is_safe_url(url: str) -> bool:
    """
    Returns False if the URL resolves to a private/internal IP,
    uses a non-http(s) scheme, or has no valid hostname.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        # Resolve hostname synchronously (acceptable at call-time — see note)
        resolved_ips = socket.getaddrinfo(hostname, None)
        for info in resolved_ips:
            ip = info[4][0]
            if _is_private_ip(ip):
                logger.warning(f"SSRF blocked: {url} resolves to private IP {ip}")
                return False
        return True
    except Exception as exc:
        logger.warning(f"URL safety check failed for {url}: {exc}")
        return False


# Blocked site hostnames (parsed, not substring)
_BLOCKED_HOSTNAMES = {
    "reddit.com", "www.reddit.com", "old.reddit.com",
    "twitter.com", "www.twitter.com",
    "x.com", "www.x.com",
    "facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com",
}


def _is_blocked_site(url: str) -> bool:
    try:
        hostname = urlparse(url).hostname or ""
        return hostname.lower() in _BLOCKED_HOSTNAMES
    except Exception:
        return True  # block on parse error


# ── Content validation ─────────────────────────────────────────────────────────

def validate_content(content: str, query: str) -> bool:
    if not content or len(content) < 50:
        return False
    content_lower = content.lower()
    error_phrases = [
        "access denied", "security check", "enable javascript",
        "captcha", "robot", "403 forbidden", "404 not found",
        "turn on cookies", "browser is not supported",
        "please wait...", "ddos-guard",
    ]
    return not any(phrase in content_lower for phrase in error_phrases)


def format_search_results(results: List[Dict], query: str) -> str:
    if not results:
        return None
    summary = f"📡 **Fresh Search Results for '{query}':**\n\n"
    for i, result in enumerate(results, 1):
        title = result.get("title", "No title")
        body = result.get("body", "No description")
        link = result.get("href", "No link")
        is_official = result.get("is_official", False)
        emoji = "📑" if "**[Full Content]**" in body else ("💰" if result.get("is_financial") else "📊")
        official_tag = " ✅ Official" if is_official else ""
        summary += f"{emoji} **{i}. {title}**{official_tag}\n"
        display_body = body[:300] + "..." if len(body) > 300 else body
        summary += f"{display_body}\n🔗 {link}\n\n"
    return summary


# ── URL fetcher with SSRF guard ────────────────────────────────────────────────

async def fetch_url_content(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """Fetch and extract text from a URL. Blocks private IPs and unsafe redirects."""
    # Pre-flight SSRF check (DNS resolution)
    if not _is_safe_url(url):
        logger.warning(f"Skipping unsafe URL (SSRF guard): {url}")
        return None

    try:
        # allow_redirects=False: we validate each hop manually
        async with session.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=5),
            allow_redirects=False,
        ) as response:
            # Follow up to 5 redirects, validating each destination
            redirect_count = 0
            current_response = response
            while current_response.status in (301, 302, 303, 307, 308) and redirect_count < 5:
                location = current_response.headers.get("Location", "")
                if not location or not _is_safe_url(location):
                    logger.warning(f"SSRF redirect blocked: {url} -> {location}")
                    return None
                async with session.get(
                    location,
                    headers={"User-Agent": USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=5),
                    allow_redirects=False,
                ) as redir_resp:
                    current_response = redir_resp
                redirect_count += 1

            if current_response.status != 200:
                return None

            content = await current_response.read()
            if len(content) > 1_000_000:
                return None

            text = content.decode("utf-8", errors="ignore")
            soup = BeautifulSoup(text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript", "form"]):
                tag.decompose()
            clean_text = re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()
            return clean_text[:2500] if len(clean_text) > 100 else None

    except (asyncio.TimeoutError, aiohttp.ClientError):
        return None
    except Exception as exc:
        logger.warning(f"Scrape error for {url}: {exc}")
        return None


# ── Web search ─────────────────────────────────────────────────────────────────

async def web_search(query: str, max_results: int = 5) -> Optional[List[Dict]]:
    if not HAS_DDGS:
        logger.warning("⚠️ duckduckgo_search package not installed. Skipping free search.")
        return None

    try:
        logger.info(f"🔍 Starting fresh web search for: {query}")
        query_lower = query.lower()
        is_financial = any(k in query_lower for k in ["price", "btc", "ethereum", "crypto", "stock", "rate", "cost", "current", "trading", "value"])

        if is_financial:
            today = datetime.now().strftime("%B %d, %Y")
            search_query = f'"{query}" today {today} -cache -old'
        else:
            search_query = query

        if "price" in query_lower:
            if "btc" in query_lower or "bitcoin" in query_lower:
                search_query = "bitcoin price today USD"
            elif "eth" in query_lower or "ethereum" in query_lower:
                search_query = "ethereum price today USD"

        results = []
        async with AsyncDDGS() as ddgs:
            try:
                results = await ddgs.text(search_query, max_results=max_results + 5)
            except Exception as search_err:
                logger.warning(f"AsyncDDGS primary search failed: {search_err}")
                try:
                    results = await ddgs.text(query, max_results=max_results + 3)
                except Exception as exc:
                    logger.error(f"AsyncDDGS fallback search failed: {exc}")
                    return None

        if not results:
            return None

        official_sites = [
            "coinmarketcap.com", "coingecko.com", "finance.yahoo.com",
            "google.com/finance", "bloomberg.com", "cnbc.com",
        ]

        filtered_results = []
        for result in results:
            title = result.get("title", "")
            body = result.get("body", "")
            link = result.get("href", "")

            if not validate_content(body, query):
                continue
            # VULN-17: proper hostname parse, not substring
            if _is_blocked_site(link):
                continue

            is_official = any(site in link.lower() for site in official_sites)
            body = re.sub(r"\s+", " ", body).strip()
            if len(body) > 300:
                body = body[:297] + "..."

            entry = {
                "title": title,
                "body": body,
                "href": link,
                "is_official": is_official,
                "is_financial": is_financial,
                "scraped": False,
            }
            if is_official:
                filtered_results.insert(0, entry)
            else:
                filtered_results.append(entry)

            if len(filtered_results) >= max_results:
                break

        if filtered_results:
            logger.info("🕵️ Deep Search: Attempting to read top 2 results...")
            async with aiohttp.ClientSession() as session:
                targets = filtered_results[:2]
                scraped_contents = await asyncio.gather(
                    *[fetch_url_content(session, r["href"]) for r in targets],
                    return_exceptions=True,
                )
                for i, content in enumerate(scraped_contents):
                    if isinstance(content, str) and validate_content(content, query):
                        filtered_results[i]["body"] = f"**[Full Content]** {content}"
                        filtered_results[i]["scraped"] = True
                        logger.info(f"✅ Scraped {len(content)} chars from {filtered_results[i]['href']}")

        return filtered_results or None

    except Exception as exc:
        logger.error(f"❌ Web search unexpected error: {exc}", exc_info=True)
        return None


# ── Perplexity fallback ────────────────────────────────────────────────────────

async def perplexity_search(query: str) -> Optional[str]:
    if not PERPLEXITY_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.perplexity.ai/chat/completions",
                json={
                    "model": "sonar",
                    "messages": [
                        {"role": "system", "content": "You are a helpful search assistant. Provide current, up-to-date information."},
                        {"role": "user", "content": f"{query} - provide current/today's data only"},
                    ],
                },
                headers={"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return f"🌐 **Real-Time Data (Perplexity AI):**\n\n{content}" if content else None
                logger.error(f"Perplexity API error: {response.status}")
                return None
    except asyncio.TimeoutError:
        logger.error("Perplexity API timeout")
        return None
    except Exception as exc:
        logger.error(f"Perplexity API error: {exc}")
        return None


async def search_and_summarize(query: str) -> str:
    logger.info(f"📡 Initiating search workflow for: '{query}'")
    try:
        results = await asyncio.wait_for(web_search(query), timeout=20.0)
        if results:
            formatted = format_search_results(results, query)
            if formatted:
                return formatted
        perplexity_result = await perplexity_search(query)
        return perplexity_result or None
    except asyncio.TimeoutError:
        logger.error("⏱️ DDGS/Scraping timeout")
        return await perplexity_search(query)
    except Exception as exc:
        logger.error(f"❌ Search workflow error: {exc}")
        return await perplexity_search(query)


async def get_latest_info(query: str) -> str:
    try:
        result = await search_and_summarize(query)
        return result if result else ""
    except Exception as exc:
        logger.error(f"Error getting latest info: {exc}")
        return ""
