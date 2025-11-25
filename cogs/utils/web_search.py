import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re
import os

logger = logging.getLogger(__name__)

# Perplexity API key for fallback
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DDGS (new package) and return detailed results."""
    try:
        from ddgs import DDGS
        
        logger.info(f"🔍 Starting web search for: {query}")
        
        # Detect query type for better filtering
        query_lower = query.lower()
        
        # Crypto detection - use direct price search
        crypto_symbols = {
            'btc': 'bitcoin price',
            'eth': 'ethereum price',
            'crypto': 'cryptocurrency prices',
            'bitcoin': 'bitcoin price usd',
            'ethereum': 'ethereum price usd'
        }
        
        search_query = query
        for symbol, replacement in crypto_symbols.items():
            if symbol in query_lower:
                search_query = replacement
                break
        
        # For very short queries, just search directly
        if len(query) <= 3:
            search_query = query
        else:
            # For longer queries, use filters
            search_query = f'"{search_query}" -site:zhihu.com -site:mayo -site:medical -site:forum'
        
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
            link = result.get('href', 'No link')
            
            # Skip irrelevant sites
            if any(blocked in link for blocked in ['reddit.com', 'forum', 'discuss']):
                continue
            
            # For crypto queries, prioritize price/market data
            if 'price' in query_lower or 'btc' in query_lower or 'crypto' in query_lower:
                if any(keyword in title + body for keyword in ['price', 'usd', '$', 'market', 'trading', 'chart']):
                    filtered_results.append(result)
                else:
                    continue
            else:
                # For other queries, be lenient
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
                
                # Highlight crypto prices
                if '$' in body or 'USD' in body or body.startswith('$'):
                    summary += f"💰 **{i}. {title}**\n"
                else:
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


async def perplexity_search(query: str) -> str:
    """Fallback to Perplexity API when DDGS fails."""
    if not PERPLEXITY_API_KEY:
        logger.warning("⚠️ PERPLEXITY_API_KEY not configured - skipping Perplexity fallback")
        return None
    
    try:
        logger.info(f"🔄 Falling back to Perplexity API for: {query}")
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "sonar",
                "messages": [
                    {
                        "role": "user",
                        "content": query
                    }
                ]
            }
            
            async with session.post(
                "https://api.perplexity.ai/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    if content:
                        logger.info(f"✅ Perplexity API returned results")
                        return f"🔍 **Perplexity Search Results:**\n\n{content}"
                    else:
                        logger.warning("Perplexity API returned empty content")
                        return None
                else:
                    logger.error(f"Perplexity API error: {response.status}")
                    return None
    
    except asyncio.TimeoutError:
        logger.error("Perplexity API timeout")
        return None
    except Exception as e:
        logger.error(f"Perplexity API error: {e}")
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
        # Try DDGS first
        result = await asyncio.wait_for(web_search(query), timeout=15.0)
        
        if result:
            logger.info(f"✅ Web search returned results")
            return result
        else:
            logger.warning(f"⚠️ Web search returned no results - trying Perplexity API...")
            # Fallback to Perplexity
            perplexity_result = await perplexity_search(query)
            if perplexity_result:
                return perplexity_result
            else:
                logger.warning(f"⚠️ Perplexity also returned no results for: {query}")
                return None
            
    except asyncio.TimeoutError:
        logger.error("⏱️ Web search timeout - trying Perplexity API...")
        perplexity_result = await perplexity_search(query)
        if perplexity_result:
            return perplexity_result
        else:
            logger.error("Perplexity API also timed out")
            return None
    except Exception as e:
        logger.error(f"❌ search_and_summarize error: {e} - trying Perplexity API...")
        perplexity_result = await perplexity_search(query)
        if perplexity_result:
            return perplexity_result
        else:
            logger.error(f"Perplexity API also failed: {e}")
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