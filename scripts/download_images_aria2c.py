#!/usr/bin/env python3
"""
Aria2c-based Image Downloader Script
Downloads card images from TCDB URLs for specified years using aria2c
"""

import asyncio
import sys
import os
import argparse
import logging
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from core.data_manager import PhilliesDataManager
from services.aria2_image_downloader import Aria2ImageDownloader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def download_images_for_year(year: int, max_concurrent: int = 3, use_vpn: bool = True):
    """Download images for a specific year"""
    try:
        logger.info(f"📊 Starting aria2c image download for year {year}")
        
        # Get data manager
        data_manager = PhilliesDataManager()
        
        # Get cards for the year
        cards = data_manager.db_manager.get_cards_by_year(year)
        logger.info(f"📊 Found {len(cards)} cards for year {year}")
        
        if not cards:
            logger.warning(f"⚠️ No cards found for year {year}")
            return
        
        # Download images using aria2c
        async with Aria2ImageDownloader(use_vpn=use_vpn) as downloader:
            result = await downloader.download_images_for_year(cards, max_concurrent)
        
        # Log results
        logger.info(f"🎉 Download complete for year {year}!")
        logger.info(f"   📊 Total cards: {result['total_cards']}")
        logger.info(f"   ✅ Successful downloads: {result['successful_downloads']}")
        logger.info(f"   ❌ Failed downloads: {result['failed_downloads']}")
        logger.info(f"   📊 Total downloaded: {result['total_downloaded']}")
        logger.info(f"   📊 Total failed: {result['total_failed']}")
        
        if result['vpn_used']:
            logger.info(f"🔒 VPN used: {result['original_ip']} -> {result['vpn_ip']}")
        
        if result['aria2c_used']:
            logger.info("⚡ aria2c was used for downloads")
        else:
            logger.info("📡 requests was used as fallback")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error downloading images for year {year}: {e}")
        return None

async def download_images_for_all_years(start_year: int = 1970, max_concurrent: int = 3, use_vpn: bool = True):
    """Download images for all years"""
    try:
        logger.info(f"🚀 Starting aria2c image download for all years from {start_year}")
        
        # Get data manager
        data_manager = PhilliesDataManager()
        
        # Get all years with cards
        years = data_manager.db_manager.get_years_with_cards()
        years = [y for y in years if y >= start_year]
        
        logger.info(f"📊 Found {len(years)} years with cards: {years}")
        
        total_stats = {
            'total_cards': 0,
            'successful_downloads': 0,
            'failed_downloads': 0,
            'total_downloaded': 0,
            'total_failed': 0
        }
        
        for year in years:
            logger.info(f"🔄 Processing year {year}...")
            result = await download_images_for_year(year, max_concurrent, use_vpn)
            
            if result:
                for key in total_stats:
                    total_stats[key] += result.get(key, 0)
            
            # Add delay between years
            await asyncio.sleep(2)
        
        logger.info(f"🎉 All downloads complete!")
        logger.info(f"   📊 Total cards processed: {total_stats['total_cards']}")
        logger.info(f"   ✅ Total successful: {total_stats['successful_downloads']}")
        logger.info(f"   ❌ Total failed: {total_stats['failed_downloads']}")
        logger.info(f"   📊 Total downloaded: {total_stats['total_downloaded']}")
        logger.info(f"   📊 Total failed: {total_stats['total_failed']}")
        
        return total_stats
        
    except Exception as e:
        logger.error(f"❌ Error downloading images for all years: {e}")
        return None

def get_image_statistics():
    """Get current image download statistics"""
    try:
        downloader = Aria2ImageDownloader()
        stats = downloader.get_statistics()
        
        logger.info("📊 Current image statistics:")
        logger.info(f"   🖼️  Front images: {stats['front_images']}")
        logger.info(f"   🖼️  Back images: {stats['back_images']}")
        logger.info(f"   📊 Total images: {stats['total_images']}")
        logger.info(f"   ✅ Downloaded count: {stats['downloaded_count']}")
        logger.info(f"   ❌ Failed count: {stats['failed_count']}")
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error getting image statistics: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Download card images using aria2c')
    parser.add_argument('--year', type=int, help='Specific year to download')
    parser.add_argument('--all-years', action='store_true', help='Download all years')
    parser.add_argument('--start-year', type=int, default=1970, help='Start year for all-years download')
    parser.add_argument('--max-concurrent', type=int, default=2, help='Maximum concurrent downloads')
    parser.add_argument('--no-vpn', action='store_true', help='Disable VPN usage')
    parser.add_argument('--stats', action='store_true', help='Show current image statistics')
    
    args = parser.parse_args()
    
    if args.stats:
        get_image_statistics()
        return
    
    if not args.year and not args.all_years:
        parser.error("Please specify --year or --all-years")
        return
    
    use_vpn = not args.no_vpn
    
    if use_vpn:
        logger.info("🔒 VPN will be used for downloads")
    else:
        logger.info("🌐 Downloads will proceed without VPN")
    
    if args.year:
        asyncio.run(download_images_for_year(args.year, args.max_concurrent, use_vpn))
    elif args.all_years:
        asyncio.run(download_images_for_all_years(args.start_year, args.max_concurrent, use_vpn))

if __name__ == '__main__':
    main()
