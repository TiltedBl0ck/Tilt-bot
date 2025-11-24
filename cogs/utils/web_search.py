import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 3) -> str:
    """Search the web using DuckDuckGo and return summarized results."""
    try:
        # Perform search
        results = DDGS().text(query, max_results=max_results)
        
        if not results:
            return "No search results found."
        
        # Format results
        summary = f"🔍 **Web Search Results for '{query}':**\n\n"
        for i, result in enumerate(results, 1):
            title = result.get('title', 'No title')
            body = result.get('body', 'No description')[:150]
            link = result.get('href', 'No link')
            summary += f"**{i}. {title}**\n{body}...\n🔗 {link}\n\n"
        
        return summary
        
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return f"Search failed: {str(e)}"


async def fetch_url_content(url: str, timeout: int = 10) -> str:
    """Fetch and parse content from a URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style"]):
                        script.decompose()
                    
                    # Get text
                    text = soup.get_text()
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    text = ' '.join(chunk for chunk in chunks if chunk)
                    
                    return text[:1000]  # Return first 1000 chars
                else:
                    return f"Failed to fetch (HTTP {response.status})"
    except Exception as e:
        logger.error(f"URL fetch error: {e}")
        return f"Failed to fetch: {str(e)}"


async def search_and_summarize(query: str) -> str:
    """Search the web and return context for AI."""
    return await web_search(query)