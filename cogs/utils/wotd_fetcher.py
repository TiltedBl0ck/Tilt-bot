import aiohttp
from bs4 import BeautifulSoup
import logging
import re
from typing import Optional, Dict

logger = logging.getLogger(__name__)

async def fetch_wotd() -> Optional[Dict[str, str]]:
    """
    Fetches the Word of the Day from Merriam-Webster.
    Returns a dictionary with word, definition, type, and example.
    """
    url = "https://www.merriam-webster.com/word-of-the-day"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch WOTD. Status: {response.status}")
                    return None
                text = await response.text()

        soup = BeautifulSoup(text, 'html.parser')
        
        # --- Extraction Logic ---
        
        # 1. Word
        word_header = soup.select_one('.word-header-txt')
        if not word_header:
            logger.warning("Could not find WOTD word header.")
            return None
        word = word_header.get_text(strip=True)

        # 2. Type (Part of Speech)
        # Usually in .word-attributes .main-attr
        type_elem = soup.select_one('.word-attributes .main-attr')
        word_type = type_elem.get_text(strip=True) if type_elem else "Unknown"

        # 3. Definition
        # Usually in the first paragraph under .wod-definition-container
        def_container = soup.select_one('.wod-definition-container')
        definition = "No definition found."
        if def_container:
            # MW usually puts definitions in paragraphs starting with ": " or inside strong tags
            # We will grab the first paragraph that has text
            paragraphs = def_container.find_all('p')
            for p in paragraphs:
                text = p.get_text(strip=True)
                # Basic check to avoid grabbing headers or empty lines
                if len(text) > 5:
                    definition = text
                    break

        # 4. Example
        # MW has a "See what it means" section or similar. 
        # Often p tags after a specific header, but selectors are tricky.
        # We'll look for the paragraph following the definition logic or specific container.
        example = "No example available."
        # Attempt to find the specific "did you know" or "examples" section if standard extraction fails
        # Simplification: Grab the second substantial paragraph in the definition container as the example
        if def_container and len(paragraphs) > 1:
             for p in paragraphs[1:]:
                 text = p.get_text(strip=True)
                 if len(text) > 10 and "//" in text: # MW often puts examples after //
                      example = text
                      break
                 elif len(text) > 20: # Fallback
                      example = text
                      break

        return {
            "word": word,
            "type": word_type,
            "definition": definition,
            "example": example,
            "url": url
        }

    except Exception as e:
        logger.error(f"Error scraping WOTD: {e}")
        return None