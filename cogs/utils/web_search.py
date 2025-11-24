import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return detailed results."""
    try:
        from duckduckgo_search import DDGS
        
        logger.info(f"🔍 Starting web search for: {query}")
        ddgs = DDGS()
        
        # Perform search with timeout
        results = []
        try:
            results = list(ddgs.text(query, max_results=max_results))
        except Exception as search_err:
            logger.error(f"DuckDuckGo search error: {search_err}")
            return None
        
        if not results or len(results) == 0:
            logger.warning(f"No search results for: {query}")
            return None
        
        # Format detailed results
        summary = f"🔍 **Recent Web Information about '{query}':**\n\n"
        
        for i, result in enumerate(results[:max_results], 1):
            try:
                title = result.get('title', 'No title')
                body = result.get('body', 'No description')
                link = result.get('href', 'No link')
                
                # Clean up body text
                body = body[:200] if body else "No description available"
                body = re.sub(r'\s+', ' ', body).strip()
                
                summary += f"**{i}. {title}**\n"
                summary += f"📝 {body}\n"
                summary += f"🔗 Source: {link}\n\n"
            except Exception as e:
                logger.error(f"Error processing result {i}: {e}")
                continue
        
        logger.info(f"✅ Web search successful - found {len(results)} results")
        return summary if summary != f"🔍 **Recent Web Information about '{query}':**\n\n" else None
        
    except ImportError:
        logger.error("❌ duckduckgo-search not installed")
        return None
    except Exception as e:
        logger.error(f"❌ Web search error: {e}")
        return None


async def fetch_url_content(url: str, timeout: int = 10) -> str:
    """Fetch and parse content from a URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'}) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style", "nav", "footer"]):
                        script.decompose()
                    
                    # Get text
                    text = soup.get_text()
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    text = ' '.join(chunk for chunk in chunks if chunk)
                    
                    return text[:1500]
                else:
                    logger.warning(f"URL fetch failed with status {response.status}")
                    return None
    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching URL: {url}")
        return None
    except Exception as e:
        logger.error(f"URL fetch error: {e}")
        return None


async def search_and_summarize(query: str) -> str:
    """Search the web and return context for AI. Returns None if no results."""
    logger.info(f"📡 Initiating web search for: '{query}'")
    
    try:
        result = await asyncio.wait_for(web_search(query), timeout=10.0)
        
        if result:
            logger.info(f"✅ Web search returned {len(result)} characters of data")
            return result
        else:
            logger.warning(f"⚠️ Web search returned no results for: {query}")
            return None
            
    except asyncio.TimeoutError:
        logger.error("⏱️ Web search timeout")
        return None
    except Exception as e:
        logger.error(f"❌ search_and_summarize error: {e}")
        return None


async def get_latest_info(query: str) -> str:
    """Get the latest information with web search. Returns formatted string or empty."""
    try:
        result = await search_and_summarize(query)
        if result:
            return result
        else:
            return ""
    except Exception as e:
        logger.error(f"Error getting latest info: {e}")
        return ""