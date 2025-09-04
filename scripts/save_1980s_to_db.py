#!/usr/bin/env python3
"""
Save 1980s scraped data to database without image extraction
Scrapes all years from 1980-1989 with automated VPN rotation
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

async def save_1980s_to_database():
    """Save 1980s scraped data to database without image extraction"""
    try:
        scraper = TCDBPhilliesScraper()
        logger.info("🚀 Starting 1980s scraping (1980-1989) without image extraction...")
        logger.info("🔄 Automated VPN rotation enabled for blocking/rate limiting")
        
        # Scrape each year individually for better error handling and progress tracking
        years_to_scrape = list(range(1980, 1990))
        total_cards = 0
        successful_years = 0
        
        for year in years_to_scrape:
            try:
                logger.info(f"📅 Starting {year} scraping...")
                success = await scraper.scrape_phillies_cards(start_year=year, skip_images=True)
                
                if success:
                    successful_years += 1
                    logger.info(f"✅ {year} scraping completed successfully!")
                else:
                    logger.error(f"❌ {year} scraping failed!")
                    
            except Exception as e:
                logger.error(f"❌ Error during {year} scraping: {e}")
                continue
        
        logger.info(f"🎉 1980s scraping completed!")
        logger.info(f"📊 Results: {successful_years}/{len(years_to_scrape)} years successful")
        
        if successful_years > 0:
            logger.info("✅ 1980s data saved to database successfully!")
            return True
        else:
            logger.error("❌ No years were successfully scraped")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error during 1980s scraping: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(save_1980s_to_database())
    if success:
        print("✅ 1980s data saved to database successfully!")
    else:
        print("❌ Failed to save 1980s data to database")
        sys.exit(1)
