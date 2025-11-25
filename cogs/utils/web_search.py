import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# Perplexity API key for fallback
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DDGS with fresh/no-cache results."""
    try:
        from ddgs import DDGS
        
        logger.info(f"🔍 Starting fresh web search for: {query}")
        
        query_lower = query.lower()
        
        # Always add "today" or "now" for real-time queries
        realtime_keywords = ['price', 'btc', 'ethereum', 'crypto', 'rate', 'cost', 'current']
        if any(keyword in query_lower for keyword in realtime_keywords):
            # Force fresh results with date/time
            today = datetime.now().strftime("%B %d, %Y")
            search_query = f'"{query}" today {today} -cache -old'
        else:
            search_query = query
        
        # Crypto detection - use direct price search with today
        crypto_symbols = {
            'btc': 'bitcoin price today USD',
            'eth': 'ethereum price today USD',
            'doge': 'dogecoin price today USD',
            'crypto': 'cryptocurrency prices today',
            'bitcoin': 'bitcoin price today USD',
            'ethereum': 'ethereum price today USD'
        }
        
        for symbol, replacement in crypto_symbols.items():
            if symbol in query_lower:
                search_query = replacement
                break
        
        logger.info(f"🔍 Search query: {search_query}")
        
        results = []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(search_query, max_results=max_results + 3))
        except Exception as search_err:
            logger.error(f"DDGS search error: {search_err}")
            # Fallback to basic search
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=max_results))
            except:
                return None
        
        if not results or len(results) == 0:
            logger.warning(f"⚠️ No search results for: {query}")
            return None
        
        # Filter relevant results - prioritize recent/official sources
        filtered_results = []
        query_words = set(query.lower().split())
        
        for result in results:
            title = result.get('title', '').lower()
            body = result.get('body', '').lower()
            link = result.get('href', 'No link')
            
            # Prioritize official sources
            official_sites = ['coinmarketcap', 'coingecko', 'yahoo finance', 'google finance', 'bloomberg']
            is_official = any(site in link.lower() for site in official_sites)
            
            # Skip irrelevant sites
            blocked_sites = ['reddit.com', 'forum', 'discuss', 'twitter.com', 'facebook.com']
            if any(blocked in link for blocked in blocked_sites):
                continue
            
            # For crypto/price queries, strictly filter
            if any(keyword in query_lower for keyword in ['price', 'btc', 'crypto', 'ethereum']):
                # Must contain price/market data
                if any(keyword in title + body for keyword in ['price', 'usd', '$', 'market cap', 'trading', '24h']):
                    # Prioritize official sources first
                    if is_official:
                        filtered_results.insert(0, result)  # Add to front
                    else:
                        filtered_results.append(result)
                else:
                    continue
            else:
                # For other queries, be lenient
                if len(query_words) <= 2:
                    filtered_results.append(result)
                else:
                    matching_words = sum(1 for word in query_words if word in title or word in body)
                    if matching_words >= 1:
                        filtered_results.append(result)
            
            if len(filtered_results) >= max_results:
                break
        
        if not filtered_results:
            logger.warning(f"⚠️ No relevant results after filtering - {len(results)} total results found")
            return None
        
        # Format detailed results with freshness indicator
        summary = f"📡 **Fresh Search Results for '{query}':**\n\n"
        
        for i, result in enumerate(filtered_results[:max_results], 1):
            try:
                title = result.get('title', 'No title')
                body = result.get('body', 'No description')
                link = result.get('href', 'No link')
                
                # Clean up body text
                body = body[:250] if body else "No description available"
                body = re.sub(r'\s+', ' ', body).strip()
                
                # Mark official sources
                is_official = any(site in link.lower() for site in ['coinmarketcap', 'coingecko', 'yahoo', 'google', 'bloomberg'])
                emoji = "💰" if '$' in body or 'USD' in body else "📊"
                official_tag = " ✅ Official" if is_official else ""
                
                summary += f"{emoji} **{i}. {title}**{official_tag}\n"
                summary += f"{body}\n"
                summary += f"🔗 {link}\n\n"
            except Exception as e:
                logger.error(f"Error processing result {i}: {e}")
                continue
        
        logger.info(f"✅ Fresh web search successful - found {len(filtered_results)} relevant results")
        return summary if summary != f"📡 **Fresh Search Results for '{query}':**\n\n" else None
        
    except ImportError:
        logger.error("❌ ddgs package not installed. Run: pip install ddgs")
        return None
    except Exception as e:
        logger.error(f"❌ Web search error: {e}")
        return None


async def perplexity_search(query: str) -> str:
    """Fallback to Perplexity API for real-time data when DDGS insufficient."""
    if not PERPLEXITY_API_KEY:
        logger.warning("⚠️ PERPLEXITY_API_KEY not configured - skipping Perplexity fallback")
        return None
    
    try:
        logger.info(f"🔄 Using Perplexity API (real-time) for: {query}")
        
        # Add context for real-time data
        enhanced_query = f"{query} - provide current/today's data only"
        
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
                        "content": enhanced_query
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
                        logger.info(f"✅ Perplexity API returned real-time results")
                        return f"🌐 **Real-Time Data (Perplexity AI):**\n\n{content}"
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
    """Search the web with real-time focus. Returns None if no results."""
    logger.info(f"📡 Initiating real-time search for: '{query}'")
    
    try:
        # Try DDGS first (fast, fresh)
        result = await asyncio.wait_for(web_search(query), timeout=15.0)
        
        if result:
            logger.info(f"✅ DDGS returned fresh results")
            return result
        else:
            logger.warning(f"⚠️ DDGS insufficient - requesting Perplexity real-time data...")
            # Fallback to Perplexity for real-time data
            perplexity_result = await perplexity_search(query)
            if perplexity_result:
                return perplexity_result
            else:
                logger.warning(f"⚠️ Perplexity also returned no results for: {query}")
                return None
            
    except asyncio.TimeoutError:
        logger.error("⏱️ DDGS timeout - requesting Perplexity real-time data...")
        perplexity_result = await perplexity_search(query)
        if perplexity_result:
            return perplexity_result
        else:
            logger.error("Perplexity API also timed out")
            return None
    except Exception as e:
        logger.error(f"❌ Search error: {e} - requesting Perplexity real-time data...")
        perplexity_result = await perplexity_search(query)
        if perplexity_result:
            return perplexity_result
        else:
            logger.error(f"Perplexity API also failed: {e}")
            return None


async def get_latest_info(query: str) -> str:
    """Get the latest/real-time information. Returns formatted string or empty."""
    try:
        result = await search_and_summarize(query)
        if result:
            return result
        else:
            return ""
    except Exception as e:
        logger.error(f"Error getting latest info: {e}")
        return ""