#!/usr/bin/env python3
"""
Save 1991 scraped data to database without image extraction
"""
import asyncio
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from services.tcdb_phillies_scraper import TCDBPhilliesScraper
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def save_1991_to_database():
    """Save 1991 scraped data to database without image extraction"""
    try:
        scraper = TCDBPhilliesScraper()
        logger.info("🚀 Starting 1991 scraping without image extraction...")
        success = await scraper.scrape_phillies_cards(start_year=1991, skip_images=True)
        
        if success:
            logger.info("✅ 1991 data saved to database successfully!")
            return True
        else:
            logger.error("❌ Failed to save 1991 data to database")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error during 1991 scraping: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(save_1991_to_database())
    if success:
        print("✅ 1991 data saved to database successfully!")
    else:
        print("❌ Failed to save 1991 data to database")
        sys.exit(1)
