import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DDGS (new package) and return detailed results."""
    try:
        from ddgs import DDGS  # NEW: Use ddgs instead of duckduckgo_search
        
        logger.info(f"🔍 Starting web search for: {query}")
        
        # For very short queries, just search directly
        if len(query) <= 3:
            search_query = query
        else:
            # For longer queries, use filters
            search_query = f'"{query}" -site:zhihu.com -site:mayo -site:medical'
        
        results = []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(search_query, max_results=max_results + 2))
        except Exception as search_err:
            logger.error(f"DDGS search error: {search_err}")
            # Fallback to basic search
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=max_results))
            except:
                return None
        
        if not results or len(results) == 0:
            logger.warning(f"No search results for: {query}")
            return None
        
        # Filter relevant results
        filtered_results = []
        query_words = set(query.lower().split())
        
        for result in results:
            title = result.get('title', '').lower()
            body = result.get('body', '').lower()
            
            # For short queries, be lenient
            if len(query_words) <= 2:
                filtered_results.append(result)
            else:
                # Check relevance - at least 1 word from query should match
                matching_words = sum(1 for word in query_words if word in title or word in body)
                if matching_words >= 1:
                    filtered_results.append(result)
            
            if len(filtered_results) >= max_results:
                break
        
        if not filtered_results:
            logger.warning(f"No relevant results after filtering for: {query}")
            return None
        
        # Format detailed results
        summary = f"📚 **Search Results for '{query}':**\n\n"
        
        for i, result in enumerate(filtered_results[:max_results], 1):
            try:
                title = result.get('title', 'No title')
                body = result.get('body', 'No description')
                link = result.get('href', 'No link')
                
                # Clean up body text
                body = body[:200] if body else "No description available"
                body = re.sub(r'\s+', ' ', body).strip()
                
                summary += f"**{i}. {title}**\n"
                summary += f"{body}\n"
                summary += f"Source: {link}\n\n"
            except Exception as e:
                logger.error(f"Error processing result {i}: {e}")
                continue
        
        logger.info(f"✅ Web search successful - found {len(filtered_results)} relevant results")
        return summary if summary != f"📚 **Search Results for '{query}':**\n\n" else None
        
    except ImportError:
        logger.error("❌ ddgs package not installed. Run: pip install ddgs")
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
        result = await asyncio.wait_for(web_search(query), timeout=15.0)
        
        if result:
            logger.info(f"✅ Web search returned results")
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