import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using duckduckgo_search and return detailed results."""
    try:
        # FIXED: Correct import for the standard library
        from duckduckgo_search import DDGS
        
        logger.info(f"🔍 Starting web search for: {query}")
        
        # For very short queries, just search directly
        if len(query) <= 3:
            search_query = query
        else:
            # For longer queries, use filters to avoid low-quality sites
            search_query = f'"{query}"'
        
        results = []
        try:
            # Use the synchronous DDGS in an executor if needed, 
            # but DDGS methods are sync by default in the library.
            # We run it in a thread to avoid blocking Discord.
            def run_search():
                with DDGS() as ddgs:
                    # .text() is the correct method for recent versions of duckduckgo-search
                    return list(ddgs.text(search_query, max_results=max_results + 2))
            
            results = await asyncio.to_thread(run_search)
            
        except Exception as search_err:
            logger.error(f"DDGS search error: {search_err}")
            # Fallback to basic search without quotes/filters
            try:
                def run_fallback():
                    with DDGS() as ddgs:
                        return list(ddgs.text(query, max_results=max_results))
                results = await asyncio.to_thread(run_fallback)
            except Exception as e:
                logger.error(f"Fallback search failed: {e}")
                return None
        
        if not results:
            logger.warning(f"No search results for: {query}")
            return None
        
        # Format detailed results
        summary = f"📚 **Search Results for '{query}':**\n\n"
        
        # Take the top results (filtering logic simplified for reliability)
        count = 0
        for result in results:
            try:
                title = result.get('title', 'No title')
                body = result.get('body', 'No description')
                link = result.get('href', 'No link')
                
                # Basic cleanup
                if not body: continue
                
                summary += f"**{count + 1}. {title}**\n"
                summary += f"{body}\n"
                summary += f"Source: {link}\n\n"
                count += 1
                
                if count >= max_results:
                    break
            except Exception as e:
                continue
        
        logger.info(f"✅ Web search successful - found {count} results")
        return summary
        
    except ImportError:
        logger.error("❌ duckduckgo-search package not installed. Run: pip install duckduckgo-search")
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
    # Clean query for search (remove mentions of the bot)
    clean_query = re.sub(r'<@!?\d+>', '', query).strip()
    
    logger.info(f"📡 Initiating web search for: '{clean_query}'")
    
    try:
        result = await asyncio.wait_for(web_search(clean_query), timeout=15.0)
        
        if result:
            logger.info(f"✅ Web search returned results")
            return result
        else:
            logger.warning(f"⚠️ Web search returned no results for: {clean_query}")
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