import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# Perplexity API key for fallback
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

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
        "browser is not supported"
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
        
        summary += f"{emoji} **{i}. {title}**{official_tag}\n"
        summary += f"{body}\n"
        summary += f"🔗 {link}\n\n"
        
    return summary

async def web_search(query: str, max_results: int = 5) -> Optional[List[Dict]]:
    """
    Search the web using DDGS. 
    Returns a list of dictionaries if successful and valid, otherwise None.
    """
    try:
        from ddgs import DDGS
        
        logger.info(f"🔍 Starting fresh web search for: {query}")
        
        query_lower = query.lower()
        
        # Real-time/Financial query detection
        is_financial = False
        realtime_keywords = ['price', 'btc', 'ethereum', 'crypto', 'stock', 'rate', 'cost', 'current', 'trading', 'value']
        if any(keyword in query_lower for keyword in realtime_keywords):
            is_financial = True
            today = datetime.now().strftime("%B %d, %Y")
            search_query = f'"{query}" today {today} -cache -old'
        else:
            search_query = query
            
        # Specific crypto overrides (keeping existing logic but safer)
        if 'price' in query_lower:
            if 'btc' in query_lower or 'bitcoin' in query_lower:
                search_query = 'bitcoin price today USD'
            elif 'eth' in query_lower or 'ethereum' in query_lower:
                search_query = 'ethereum price today USD'

        logger.debug(f"🔍 Executing search query: {search_query}")
        
        results = []
        try:
            with DDGS() as ddgs:
                # Fetch slightly more to allow for filtering
                results = list(ddgs.text(search_query, max_results=max_results + 5))
        except Exception as search_err:
            logger.warning(f"DDGS primary search failed: {search_err}")
            # Try fallback without advanced operators
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=max_results + 3))
            except Exception as e:
                logger.error(f"DDGS fallback search failed: {e}")
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
            
            # 1. Validation Check: If content looks like an error, skip it
            if not validate_content(body, query):
                continue

            # 2. Link Filtering
            blocked_sites = ['reddit.com', 'twitter.com', 'facebook.com', 'instagram.com']
            if any(blocked in link for blocked in blocked_sites):
                continue

            # 3. Relevance & Official Scoring
            is_official = any(site in link.lower() for site in official_sites)
            
            # Clean up body text
            body = re.sub(r'\s+', ' ', body).strip()
            if len(body) > 300:
                body = body[:297] + "..."

            entry = {
                'title': title,
                'body': body,
                'href': link,
                'is_official': is_official,
                'is_financial': is_financial
            }

            # Prioritization logic
            if is_official:
                filtered_results.insert(0, entry)
            else:
                filtered_results.append(entry)
                
            if len(filtered_results) >= max_results:
                break
        
        # Final sanity check on the result set
        if not filtered_results:
            logger.warning("⚠️ Results existed but were filtered out as invalid/irrelevant.")
            return None
            
        return filtered_results
        
    except ImportError:
        logger.error("❌ ddgs package not installed. Run: pip install ddgs")
        return None
    except Exception as e:
        logger.error(f"❌ Web search unexpected error: {e}")
        return None


async def perplexity_search(query: str) -> Optional[str]:
    """Fallback to Perplexity API for real-time data."""
    if not PERPLEXITY_API_KEY:
        logger.warning("⚠️ PERPLEXITY_API_KEY not configured - skipping Perplexity fallback")
        return None
    
    try:
        logger.info(f"🔄 Triggering Perplexity API (Fallback/Real-time) for: {query}")
        
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
    1. Tries DDGS (free).
    2. Validates results.
    3. Falls back to Perplexity (paid) if DDGS fails or results are invalid.
    """
    logger.info(f"📡 Initiating search workflow for: '{query}'")
    
    try:
        # Step 1: Try Free Search
        results = await asyncio.wait_for(web_search(query), timeout=15.0)
        
        # Step 2: Validate Results
        if results and len(results) > 0:
            formatted_response = format_search_results(results, query)
            if formatted_response:
                logger.info(f"✅ DDGS returned {len(results)} valid results")
                return formatted_response
            else:
                logger.warning("⚠️ DDGS results formatting failed")
        else:
            logger.warning(f"⚠️ DDGS returned no valid results (incorrect/empty data).")

        # Step 3: Fallback to Perplexity
        logger.info("🔄 Switching to Perplexity API fallback...")
        perplexity_result = await perplexity_search(query)
        
        if perplexity_result:
            return perplexity_result
        else:
            logger.warning(f"⚠️ Perplexity also returned no results for: {query}")
            return None
            
    except asyncio.TimeoutError:
        logger.error("⏱️ DDGS timeout - requesting Perplexity...")
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