import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime
from typing import Optional, List, Dict

# Updated import to the correct async client
try:
    from duckduckgo_search import AsyncDDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False

logger = logging.getLogger(__name__)

# Perplexity API key for fallback
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

# Browser-like User-Agent to avoid immediate 403s when scraping
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"

def validate_content(content: str, query: str) -> bool:
    """
    Validates if the scraped content is useful.
    Returns False if the content looks like an error, captcha, or is too short.
    """
    if not content or len(content) < 50:
        return False
    
    content_lower = content.lower()
    
    # Common error messages from scraping
    error_phrases = [
        "access denied", 
        "security check", 
        "enable javascript", 
        "captcha", 
        "robot", 
        "403 forbidden", 
        "404 not found",
        "turn on cookies",
        "browser is not supported",
        "please wait...",
        "ddos-guard"
    ]
    
    if any(phrase in content_lower for phrase in error_phrases):
        return False

    return True

def format_search_results(results: List[Dict], query: str) -> str:
    """Formats structured search results into a display string."""
    if not results:
        return None
        
    summary = f"📡 **Fresh Search Results for '{query}':**\n\n"
    
    for i, result in enumerate(results, 1):
        title = result.get('title', 'No title')
        body = result.get('body', 'No description')
        link = result.get('href', 'No link')
        is_official = result.get('is_official', False)
        
        emoji = "💰" if result.get('is_financial', False) else "📊"
        official_tag = " ✅ Official" if is_official else ""
        
        # Check if we have deep scraped content
        if "**[Full Content]**" in body:
            emoji = "📑" # Different emoji for deep read content
        
        summary += f"{emoji} **{i}. {title}**{official_tag}\n"
        # Truncate body for the UI display, but the full text is in the dict for the AI
        display_body = body[:300] + "..." if len(body) > 300 else body
        summary += f"{display_body}\n"
        summary += f"🔗 {link}\n\n"
        
    return summary

async def fetch_url_content(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """
    Deep Search: Visits a URL and extracts the main text content.
    """
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=5) as response:
            if response.status != 200:
                return None
            
            # Read content with a size limit (1MB) to prevent hanging on large files
            content = await response.read()
            if len(content) > 1_000_000:
                return None
            
            text = content.decode('utf-8', errors='ignore')
            soup = BeautifulSoup(text, 'html.parser')
            
            # Remove clutter (scripts, styles, navs, footers)
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe', 'noscript', 'form']):
                tag.decompose()
            
            # Extract text
            clean_text = soup.get_text(separator=' ')
            
            # Normalize whitespace
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            
            # Return valid content or None
            if len(clean_text) > 100:
                # Limit to ~2500 chars to respect token limits while giving good context
                return clean_text[:2500]
            return None
            
    except (asyncio.TimeoutError, aiohttp.ClientError):
        # Fail silently for network errors, just fallback to snippet
        return None
    except Exception as e:
        logger.warning(f"Scrape error for {url}: {e}")
        return None

async def web_search(query: str, max_results: int = 5) -> Optional[List[Dict]]:
    """
    Search the web using AsyncDDGS with Deep Search capabilities.
    """
    if not HAS_DDGS:
        # Changed from ERROR to WARNING as requested
        logger.warning("⚠️ duckduckgo_search package not installed. Skipping free search.")
        return None

    try:
        logger.info(f"🔍 Starting fresh web search for: {query}")
        
        query_lower = query.lower()
        is_financial = False
        realtime_keywords = ['price', 'btc', 'ethereum', 'crypto', 'stock', 'rate', 'cost', 'current', 'trading', 'value']
        
        if any(keyword in query_lower for keyword in realtime_keywords):
            is_financial = True
            today = datetime.now().strftime("%B %d, %Y")
            search_query = f'"{query}" today {today} -cache -old'
        else:
            search_query = query
            
        if 'price' in query_lower:
            if 'btc' in query_lower or 'bitcoin' in query_lower:
                search_query = 'bitcoin price today USD'
            elif 'eth' in query_lower or 'ethereum' in query_lower:
                search_query = 'ethereum price today USD'

        logger.debug(f"🔍 Executing search query: {search_query}")
        
        results = []
        
        async with AsyncDDGS() as ddgs:
            try:
                # Try to get results
                results = await ddgs.text(search_query, max_results=max_results + 5)
            except Exception as search_err:
                logger.warning(f"AsyncDDGS primary search failed: {search_err}")
                try:
                    results = await ddgs.text(query, max_results=max_results + 3)
                except Exception as e:
                    logger.error(f"AsyncDDGS fallback search failed: {e}")
                    return None
        
        if not results:
            logger.warning(f"⚠️ No results returned from DDGS for: {query}")
            return None
        
        filtered_results = []
        official_sites = ['coinmarketcap.com', 'coingecko.com', 'finance.yahoo.com', 'google.com/finance', 'bloomberg.com', 'cnbc.com']
        
        for result in results:
            title = result.get('title', '')
            body = result.get('body', '')
            link = result.get('href', '')
            
            if not validate_content(body, query):
                continue

            blocked_sites = ['reddit.com', 'twitter.com', 'facebook.com', 'instagram.com']
            if any(blocked in link for blocked in blocked_sites):
                continue

            is_official = any(site in link.lower() for site in official_sites)
            
            # Basic cleanup of the snippet
            body = re.sub(r'\s+', ' ', body).strip()
            if len(body) > 300:
                body = body[:297] + "..."

            entry = {
                'title': title,
                'body': body,
                'href': link,
                'is_official': is_official,
                'is_financial': is_financial,
                'scraped': False
            }

            if is_official:
                filtered_results.insert(0, entry)
            else:
                filtered_results.append(entry)
                
            if len(filtered_results) >= max_results:
                break
        
        # --- DEEP SEARCH: SCRAPING LAYER ---
        if filtered_results:
            logger.info(f"🕵️ Deep Search: Attempting to read top 2 results...")
            
            async with aiohttp.ClientSession() as session:
                tasks = []
                # Only scrape the top 2 results to balance speed vs info
                targets = filtered_results[:2]
                
                for res in targets:
                    tasks.append(fetch_url_content(session, res['href']))
                
                # Fetch concurrently
                scraped_contents = await asyncio.gather(*tasks, return_exceptions=True)
                
                for i, content in enumerate(scraped_contents):
                    if isinstance(content, str) and validate_content(content, query):
                        # Successful scrape! Update the entry.
                        filtered_results[i]['body'] = f"**[Full Content]** {content}"
                        filtered_results[i]['scraped'] = True
                        logger.info(f"✅ Successfully scraped {len(content)} chars from {filtered_results[i]['href']}")
                    else:
                        logger.debug(f"⏩ Scraping skipped/failed for result {i+1}")

        if not filtered_results:
            return None
            
        return filtered_results
        
    except Exception as e:
        logger.error(f"❌ Web search unexpected error: {e}", exc_info=True)
        return None


async def perplexity_search(query: str) -> Optional[str]:
    """Fallback to Perplexity API for real-time data."""
    if not PERPLEXITY_API_KEY:
        logger.warning("⚠️ PERPLEXITY_API_KEY not configured - skipping Perplexity fallback")
        return None
    
    try:
        logger.info(f"🔄 Triggering Perplexity API (Fallback/Real-time) for: {query}")
        
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
                        "role": "system",
                        "content": "You are a helpful search assistant. Provide current, up-to-date information."
                    },
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
                        logger.info(f"✅ Perplexity API returned valid results")
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


async def search_and_summarize(query: str) -> str:
    """
    Main entry point. 
    1. Tries AsyncDDGS with Deep Search.
    2. Validates results.
    3. Falls back to Perplexity if DDGS fails.
    """
    logger.info(f"📡 Initiating search workflow for: '{query}'")
    
    try:
        # Step 1: Try Free Search (with timeout extended for scraping)
        # Increased timeout to 20s to account for scraping time
        results = await asyncio.wait_for(web_search(query), timeout=20.0)
        
        # Step 2: Validate Results
        if results and len(results) > 0:
            formatted_response = format_search_results(results, query)
            if formatted_response:
                logger.info(f"✅ DDGS returned {len(results)} valid results")
                return formatted_response
            else:
                logger.warning("⚠️ DDGS results formatting failed")
        else:
            logger.warning(f"⚠️ DDGS returned no valid results.")

        # Step 3: Fallback to Perplexity
        logger.info("🔄 Switching to Perplexity API fallback...")
        perplexity_result = await perplexity_search(query)
        
        if perplexity_result:
            return perplexity_result
        else:
            logger.warning(f"⚠️ Perplexity also returned no results for: {query}")
            return None
            
    except asyncio.TimeoutError:
        logger.error("⏱️ DDGS/Scraping timeout - requesting Perplexity...")
        perplexity_result = await perplexity_search(query)
        if perplexity_result:
            return perplexity_result
        return None
    except Exception as e:
        logger.error(f"❌ Search workflow error: {e}")
        perplexity_result = await perplexity_search(query)
        return perplexity_result

async def get_latest_info(query: str) -> str:
    """Wrapper for external calls."""
    try:
        result = await search_and_summarize(query)
        return result if result else ""
    except Exception as e:
        logger.error(f"Error getting latest info: {e}")
        return ""