#!/usr/bin/env python3
"""
Resume image extraction for 1993 Phillies cards with improved rate limiting
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from services.tcdb_phillies_scraper import TCDBPhilliesScraper
import pandas as pd
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def resume_image_extraction():
    """Resume image extraction for 1993 cards"""
    try:
        # Initialize scraper
        scraper = TCDBPhilliesScraper()
        
        # Check if 1993 CSV exists
        csv_path = Path("data/phillies_cards/1993_phillies_cards.csv")
        if not csv_path.exists():
            logger.error(f"❌ CSV file not found: {csv_path}")
            return False
        
        # Load existing cards
        logger.info(f"📄 Loading existing cards from {csv_path}")
        df = pd.read_csv(csv_path)
        cards = df.to_dict('records')
        
        logger.info(f"📊 Found {len(cards)} cards to process")
        
        # Check how many already have images
        cards_with_images = [c for c in cards if c.get('front_image_url') and c.get('front_image_url').strip()]
        cards_without_images = [c for c in cards if not c.get('front_image_url') or not c.get('front_image_url').strip()]
        
        logger.info(f"📊 Cards with images: {len(cards_with_images)}")
        logger.info(f"📊 Cards without images: {len(cards_without_images)}")
        
        if not cards_without_images:
            logger.info("✅ All cards already have images!")
            return True
        
        # Process only cards without images
        logger.info(f"🖼️ Processing {len(cards_without_images)} cards without images...")
        
        # Update cards with images using improved rate limiting
        updated_cards = await scraper.update_cards_with_images(cards_without_images)
        
        # Merge back with existing cards
        updated_dict = {c['card_url']: c for c in updated_cards}
        for card in cards:
            if card['card_url'] in updated_dict:
                card.update(updated_dict[card['card_url']])
        
        # Save updated CSV
        updated_df = pd.DataFrame(cards)
        updated_df.to_csv(csv_path, index=False)
        
        # Count final results
        final_with_images = [c for c in cards if c.get('front_image_url') and c.get('front_image_url').strip()]
        logger.info(f"✅ Image extraction completed!")
        logger.info(f"📊 Final cards with images: {len(final_with_images)}/{len(cards)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error during image extraction: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(resume_image_extraction())
    if success:
        print("✅ Image extraction completed successfully!")
    else:
        print("❌ Image extraction failed!")
        sys.exit(1)
