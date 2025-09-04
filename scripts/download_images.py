#!/usr/bin/env python3
"""
Standalone Image Downloader Script
Downloads card images from TCDB URLs for specified years
"""

import asyncio
import sys
import os
import argparse
import logging
from pathlib import Path

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from core.data_manager import PhilliesDataManager
from services.image_downloader import ImageDownloader

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def download_images_for_year(year: int, max_concurrent: int = 5, use_vpn: bool = True):
    """Download images for a specific year"""
    try:
        logger.info(f"🚀 Starting image download for year {year}")
        
        # Initialize data manager
        data_manager = PhilliesDataManager()
        
        # Get all cards for the year
        cards = data_manager.get_cards_by_year(year, limit=1000)
        
        if not cards:
            logger.warning(f"⚠️ No cards found for year {year}")
            return {
                'success': False,
                'message': f'No cards found for year {year}',
                'data': {'total_cards': 0}
            }
        
        logger.info(f"📊 Found {len(cards)} cards for year {year}")
        
        # Initialize image downloader with VPN
        async with ImageDownloader(use_vpn=use_vpn) as downloader:
            result = await downloader.download_images_for_year(cards, max_concurrent)
        
        logger.info(f"🎉 Image download completed for year {year}")
        logger.info(f"   ✅ Successful downloads: {result['successful_downloads']}")
        logger.info(f"   ❌ Failed downloads: {result['failed_downloads']}")
        logger.info(f"   📊 Total downloaded: {result['total_downloaded']}")
        logger.info(f"   📊 Total failed: {result['total_failed']}")
        
        if result.get('vpn_used'):
            logger.info(f"   🔒 VPN used: {result['original_ip']} → {result['vpn_ip']}")
        
        return {
            'success': True,
            'message': f'Successfully downloaded images for year {year}',
            'data': result
        }
        
    except Exception as e:
        logger.error(f"❌ Error downloading images for year {year}: {e}")
        return {
            'success': False,
            'message': f'Error downloading images for year {year}: {str(e)}',
            'data': {'error': str(e)}
        }

async def download_images_for_all_years(max_concurrent: int = 5, use_vpn: bool = True):
    """Download images for all available years"""
    try:
        logger.info("🚀 Starting image download for all years")
        
        # Initialize data manager
        data_manager = PhilliesDataManager()
        
        # Get all available years
        stats = data_manager.get_statistics()
        years = [year_data['year'] for year_data in stats.get('database', {}).get('cards_by_year', [])]
        
        if not years:
            logger.warning("⚠️ No years found in database")
            return {
                'success': False,
                'message': 'No years found in database',
                'data': {'total_years': 0}
            }
        
        logger.info(f"📅 Found {len(years)} years: {years}")
        
        # Download images for each year
        results = {}
        for year in years:
            logger.info(f"📥 Processing year {year}...")
            result = await download_images_for_year(year, max_concurrent, use_vpn)
            results[year] = result
            
            # Add delay between years to be respectful
            if year != years[-1]:  # Not the last year
                logger.info("⏳ Waiting 5 seconds before next year...")
                await asyncio.sleep(5)
        
        # Calculate totals
        total_successful = sum(1 for r in results.values() if r['success'])
        total_failed = len(results) - total_successful
        
        logger.info(f"🎉 All downloads completed!")
        logger.info(f"   ✅ Successful years: {total_successful}")
        logger.info(f"   ❌ Failed years: {total_failed}")
        
        return {
            'success': True,
            'message': f'Completed image downloads for {len(years)} years',
            'data': {
                'total_years': len(years),
                'successful_years': total_successful,
                'failed_years': total_failed,
                'year_results': results
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error downloading images for all years: {e}")
        return {
            'success': False,
            'message': f'Error downloading images for all years: {str(e)}',
            'data': {'error': str(e)}
        }

def get_image_statistics():
    """Get current image download statistics"""
    try:
        downloader = ImageDownloader()
        stats = downloader.get_statistics()
        
        logger.info("📊 Image Download Statistics:")
        logger.info(f"   🖼️ Front images: {stats['front_images']}")
        logger.info(f"   🖼️ Back images: {stats['back_images']}")
        logger.info(f"   📊 Total images: {stats['total_images']}")
        logger.info(f"   💾 Total size: {stats['total_size_mb']} MB")
        logger.info(f"   ✅ Downloaded count: {stats['downloaded_count']}")
        logger.info(f"   ❌ Failed count: {stats['failed_count']}")
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error getting image statistics: {e}")
        return None

async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Download card images from TCDB')
    parser.add_argument('--year', type=int, help='Specific year to download images for')
    parser.add_argument('--all-years', action='store_true', help='Download images for all years')
    parser.add_argument('--stats', action='store_true', help='Show current image statistics')
    parser.add_argument('--max-concurrent', type=int, default=5, help='Maximum concurrent downloads (default: 5)')
    parser.add_argument('--no-vpn', action='store_true', help='Disable VPN usage (not recommended)')
    
    args = parser.parse_args()
    
    if args.stats:
        get_image_statistics()
        return
    
    if args.year:
        result = await download_images_for_year(args.year, args.max_concurrent, not args.no_vpn)
        if result['success']:
            logger.info(f"✅ {result['message']}")
        else:
            logger.error(f"❌ {result['message']}")
            sys.exit(1)
    
    elif args.all_years:
        result = await download_images_for_all_years(args.max_concurrent, not args.no_vpn)
        if result['success']:
            logger.info(f"✅ {result['message']}")
        else:
            logger.error(f"❌ {result['message']}")
            sys.exit(1)
    
    else:
        logger.error("❌ Please specify --year, --all-years, or --stats")
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
