"""
Image Downloader Service for Phillies Cards
Downloads front and back images from TCDB URLs
"""

import asyncio
import aiohttp
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import time
from urllib.parse import urlparse

# Add VPN imports
try:
    from .vpn_connector import VPNConnector
    from .vyprvpn_scraper import VyprVPNServerScraper
except ImportError:
    # For standalone script usage
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from services.vpn_connector import VPNConnector
    from services.vyprvpn_scraper import VyprVPNServerScraper

logger = logging.getLogger(__name__)

class ImageDownloader:
    def __init__(self, base_dir: str = "data/phillies_cards/images", use_vpn: bool = True):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Create year subdirectories
        self.front_dir = self.base_dir / "front"
        self.back_dir = self.base_dir / "back"
        self.front_dir.mkdir(exist_ok=True)
        self.back_dir.mkdir(exist_ok=True)
        
        # Session for HTTP requests
        self.session = None
        self.downloaded_count = 0
        self.failed_count = 0
        
        # VPN integration
        self.use_vpn = use_vpn
        self.vpn_connector = None
        self.vpn_scraper = None
        self.original_ip = None
        self.vpn_ip = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        # Initialize VPN if needed
        if self.use_vpn:
            await self._setup_vpn()
        
        # Use cloudscraper for TCDB compatibility (same as working scraper)
        try:
            import cloudscraper
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                }
            )
            logger.info("✅ Using cloudscraper for TCDB compatibility")
        except ImportError:
            logger.warning("⚠️ cloudscraper not available, falling back to aiohttp")
            self.scraper = None
        
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
        # Use the same headers as the scraper for TCDB compatibility
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
        
        # Disconnect VPN if connected
        if self.use_vpn and self.vpn_connector:
            await self._disconnect_vpn()
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe file system storage"""
        # Remove or replace unsafe characters
        unsafe_chars = '<>:"/\\|?*'
        for char in unsafe_chars:
            filename = filename.replace(char, '_')
        
        # Limit length
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:200-len(ext)] + ext
            
        return filename
    
    async def _setup_vpn(self):
        """Setup VPN connection for image downloading"""
        try:
            logger.info("🔒 Setting up VPN for image downloads...")
            
            # Initialize VPN components
            self.vpn_connector = VPNConnector()
            self.vpn_scraper = VyprVPNServerScraper()
            
            # Get original IP
            self.original_ip = await self.vpn_connector.get_external_ip()
            logger.info(f"🌐 Original IP: {self.original_ip}")
            
            # Get VPN servers
            await self.vpn_scraper.update_server_list()
            servers = self.vpn_scraper.get_all_servers()
            
            if not servers:
                logger.warning("⚠️ No VPN servers available, proceeding without VPN")
                self.use_vpn = False
                return
            
            # Connect to VPN
            logger.info("🔗 Connecting to VPN...")
            success = await self.vpn_connector.connect_to_vyprvpn()
            
            if success:
                # Verify IP changed
                self.vpn_ip = await self.vpn_connector.get_external_ip()
                logger.info(f"🔒 VPN IP: {self.vpn_ip}")
                
                if self.vpn_ip != self.original_ip:
                    logger.info("✅ VPN connection successful - IP changed")
                else:
                    logger.warning("⚠️ VPN connected but IP didn't change")
            else:
                logger.error("❌ Failed to connect to VPN")
                self.use_vpn = False
                
        except Exception as e:
            logger.error(f"❌ Error setting up VPN: {e}")
            self.use_vpn = False
    
    async def _disconnect_vpn(self):
        """Disconnect from VPN"""
        try:
            if self.vpn_connector:
                logger.info("🔌 Disconnecting from VPN...")
                await self.vpn_connector.disconnect()
                
                # Verify IP returned to original
                final_ip = await self.vpn_connector.get_external_ip()
                logger.info(f"🌐 Final IP: {final_ip}")
                
                if final_ip == self.original_ip:
                    logger.info("✅ VPN disconnected successfully - IP restored")
                else:
                    logger.warning("⚠️ VPN disconnected but IP didn't restore")
                    
        except Exception as e:
            logger.error(f"❌ Error disconnecting VPN: {e}")
    
    async def _rotate_vpn_if_needed(self, failed_count: int, max_failures: int = 10):
        """Rotate VPN endpoint if too many failures"""
        if not self.use_vpn or failed_count < max_failures:
            return False
        
        try:
            logger.info(f"🔄 Rotating VPN endpoint after {failed_count} failures...")
            
            # Disconnect current VPN
            await self._disconnect_vpn()
            
            # Wait a moment
            await asyncio.sleep(2)
            
            # Reconnect to a different server
            await self._setup_vpn()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error rotating VPN: {e}")
            return False
    
    def _get_image_filename(self, card_id: int, card_number: str, player_name: str, image_type: str) -> str:
        """Generate filename for card image"""
        # Clean up card number and player name
        clean_number = card_number.replace('/', '_').replace(' ', '_') if card_number else 'NNO'
        clean_player = player_name.replace(' ', '_').replace('/', '_')
        
        filename = f"{card_id}_{clean_number}_{clean_player}_{image_type}.jpg"
        return self._sanitize_filename(filename)
    
    async def download_image(self, url: str, filepath: Path, referer: str = None) -> bool:
        """Download a single image"""
        try:
            # Use cloudscraper if available for TCDB compatibility
            if self.scraper and 'tcdb.com' in url:
                # Use cloudscraper for TCDB URLs
                headers = {}
                if referer:
                    headers['Referer'] = referer
                
                response = self.scraper.get(url, headers=headers)
                if response.status_code == 200:
                    content = response.content
                    
                    # Verify it's actually an image
                    if len(content) > 1000:  # Basic size check
                        filepath.write_bytes(content)
                        logger.info(f"✅ Downloaded with cloudscraper: {filepath.name}")
                        return True
                    else:
                        logger.warning(f"⚠️ Small file, likely not an image: {url}")
                        return False
                else:
                    logger.warning(f"⚠️ Failed to download {url}: HTTP {response.status_code}")
                    return False
            else:
                # Fall back to aiohttp for non-TCDB URLs
                headers = {}
                if referer:
                    headers['Referer'] = referer
                
                async with self.session.get(url, headers=headers) as response:
                    if response.status == 200:
                        content = await response.read()
                        
                        # Verify it's actually an image
                        if len(content) > 1000:  # Basic size check
                            filepath.write_bytes(content)
                            logger.info(f"✅ Downloaded: {filepath.name}")
                            return True
                        else:
                            logger.warning(f"⚠️ Small file, likely not an image: {url}")
                            return False
                    else:
                        logger.warning(f"⚠️ Failed to download {url}: HTTP {response.status}")
                        return False
                    
        except Exception as e:
            logger.error(f"❌ Error downloading {url}: {e}")
            return False
    
    async def download_card_images(self, card_data: Dict) -> Dict[str, Optional[str]]:
        """Download front and back images for a card"""
        card_id = card_data['id']
        card_number = card_data.get('card_number', 'NNO')
        player_name = card_data['player_name']
        
        results = {
            'front_path': None,
            'back_path': None,
            'front_url': card_data.get('front_image_path'),
            'back_url': card_data.get('back_image_path')
        }
        
        # Download front image
        if card_data.get('front_image_path'):
            front_filename = self._get_image_filename(card_id, card_number, player_name, 'front')
            front_path = self.front_dir / front_filename
            
            if not front_path.exists():
                # Use card URL as referer for proper TCDB access
                referer = card_data.get('card_url', 'https://www.tcdb.com/')
                success = await self.download_image(card_data['front_image_path'], front_path, referer)
                if success:
                    results['front_path'] = str(front_path)
                    self.downloaded_count += 1
                else:
                    self.failed_count += 1
            else:
                results['front_path'] = str(front_path)
                logger.info(f"📁 Already exists: {front_filename}")
        
        # Download back image
        if card_data.get('back_image_path'):
            back_filename = self._get_image_filename(card_id, card_number, player_name, 'back')
            back_path = self.back_dir / back_filename
            
            if not back_path.exists():
                # Use card URL as referer for proper TCDB access
                referer = card_data.get('card_url', 'https://www.tcdb.com/')
                success = await self.download_image(card_data['back_image_path'], back_path, referer)
                if success:
                    results['back_path'] = str(back_path)
                    self.downloaded_count += 1
                else:
                    self.failed_count += 1
            else:
                results['back_path'] = str(back_path)
                logger.info(f"📁 Already exists: {back_filename}")
        
        return results
    
    async def download_images_for_year(self, cards: List[Dict], max_concurrent: int = 5) -> Dict:
        """Download images for all cards in a year"""
        logger.info(f"🚀 Starting image download for {len(cards)} cards...")
        
        # Create semaphore to limit concurrent downloads
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def download_with_semaphore(card):
            async with semaphore:
                return await self.download_card_images(card)
        
        # Download images with rate limiting and VPN rotation
        tasks = []
        consecutive_failures = 0
        
        for i, card in enumerate(cards):
            # Add delay between batches to be respectful
            if i % 10 == 0 and i > 0:
                await asyncio.sleep(1)
            
            # Check if we need to rotate VPN
            if consecutive_failures >= 10:
                logger.info(f"🔄 Rotating VPN after {consecutive_failures} consecutive failures...")
                rotated = await self._rotate_vpn_if_needed(consecutive_failures)
                if rotated:
                    consecutive_failures = 0
                    await asyncio.sleep(2)  # Wait for VPN to stabilize
            
            task = asyncio.create_task(download_with_semaphore(card))
            tasks.append(task)
        
        # Wait for all downloads to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        successful_downloads = 0
        failed_downloads = 0
        
        for result in results:
            if isinstance(result, Exception):
                failed_downloads += 1
                consecutive_failures += 1
                logger.error(f"❌ Download task failed: {result}")
            elif result['front_path'] or result['back_path']:
                successful_downloads += 1
                consecutive_failures = 0  # Reset failure counter on success
            else:
                failed_downloads += 1
                consecutive_failures += 1
        
        logger.info(f"🎉 Download complete!")
        logger.info(f"   ✅ Successful: {successful_downloads}")
        logger.info(f"   ❌ Failed: {failed_downloads}")
        logger.info(f"   📊 Total downloaded: {self.downloaded_count}")
        logger.info(f"   📊 Total failed: {self.failed_count}")
        
        return {
            'total_cards': len(cards),
            'successful_downloads': successful_downloads,
            'failed_downloads': failed_downloads,
            'total_downloaded': self.downloaded_count,
            'total_failed': self.failed_count,
            'vpn_used': self.use_vpn,
            'original_ip': self.original_ip,
            'vpn_ip': self.vpn_ip
        }
    
    def get_image_paths(self, card_id: int, card_number: str, player_name: str) -> Dict[str, Optional[str]]:
        """Get image paths for a card (without downloading)"""
        front_filename = self._get_image_filename(card_id, card_number, player_name, 'front')
        back_filename = self._get_image_filename(card_id, card_number, player_name, 'back')
        
        front_path = self.front_dir / front_filename
        back_path = self.back_dir / back_filename
        
        return {
            'front_path': str(front_path) if front_path.exists() else None,
            'back_path': str(back_path) if back_path.exists() else None
        }
    
    def get_statistics(self) -> Dict:
        """Get download statistics"""
        front_count = len(list(self.front_dir.glob('*.jpg')))
        back_count = len(list(self.back_dir.glob('*.jpg')))
        
        # Calculate total size
        total_size = 0
        for file_path in self.front_dir.glob('*.jpg'):
            total_size += file_path.stat().st_size
        for file_path in self.back_dir.glob('*.jpg'):
            total_size += file_path.stat().st_size
        
        return {
            'front_images': front_count,
            'back_images': back_count,
            'total_images': front_count + back_count,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'downloaded_count': self.downloaded_count,
            'failed_count': self.failed_count
        }
