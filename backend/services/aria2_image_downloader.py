#!/usr/bin/env python3
"""
Aria2c-based Image Downloader for TCDB
Uses aria2c for better handling of Cloudflare protection
"""

import asyncio
import subprocess
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
import tempfile
import json

# VPN imports
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

class Aria2ImageDownloader:
    def __init__(self, base_dir: str = "data/phillies_cards/images", use_vpn: bool = True):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.front_dir = self.base_dir / "front"
        self.back_dir = self.base_dir / "back"
        self.front_dir.mkdir(exist_ok=True)
        self.back_dir.mkdir(exist_ok=True)
        
        self.use_vpn = use_vpn
        self.vpn_connector = None
        self.vpn_scraper = None
        self.original_ip = None
        self.vpn_ip = None
        
        self.downloaded_count = 0
        self.failed_count = 0
        
        # Check if aria2c is available
        self.aria2c_available = self._check_aria2c()
        if not self.aria2c_available:
            logger.warning("⚠️ aria2c not found, falling back to requests")
    
    def _check_aria2c(self) -> bool:
        """Check if aria2c is available on the system"""
        try:
            result = subprocess.run(['aria2c', '--version'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    async def __aenter__(self):
        """Async context manager entry"""
        if self.use_vpn:
            await self._setup_vpn()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.use_vpn and self.vpn_connector:
            await self._disconnect_vpn()
    
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
    
    def _get_image_filename(self, card_id: int, card_number: str, player_name: str, image_type: str) -> str:
        """Generate filename for image"""
        # Clean card number
        clean_number = re.sub(r"[^A-Za-z0-9]", "", card_number) if card_number else "NNO"
        
        # Clean player name
        clean_player = re.sub(r"[^A-Za-z0-9\s]", "", player_name).strip()
        clean_player = re.sub(r"\s+", "_", clean_player)
        
        # Generate filename
        filename = f"{card_id}_{clean_number}_{clean_player}_{image_type}.jpg"
        return self._sanitize_filename(filename)
    
    async def download_image_with_aria2c(self, url: str, filepath: Path, referer: str = None) -> bool:
        """Download image using aria2c with proven working parameters"""
        try:
            # aria2c command matching the working bash script
            cmd = [
                'aria2c',
                '--continue=true',
                '--max-connection-per-server=1',  # Key: Use only 1 connection per server
                '--max-concurrent-downloads=1',
                '--retry-wait=5',
                '--max-tries=5',
                '--timeout=30',
                '--connect-timeout=10',
                '--header=User-Agent: Mozilla/5.0',  # Simple User-Agent like working script
                '--header=Referer: https://www.tcdb.com',  # Always use TCDB referer
                '--auto-file-renaming=false',
                '--file-allocation=trunc',
                '--out=' + str(filepath),
                url
            ]
            
            # Run aria2c
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0 and filepath.exists() and filepath.stat().st_size > 1000:
                logger.info(f"✅ Downloaded with aria2c: {filepath.name}")
                return True
            else:
                logger.warning(f"⚠️ aria2c failed for {url}: returncode={result.returncode}, size={filepath.stat().st_size if filepath.exists() else 0}")
                if stderr:
                    logger.debug(f"aria2c stderr: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error with aria2c download {url}: {e}")
            return False
    
    async def download_image_with_requests(self, url: str, filepath: Path, referer: str = None) -> bool:
        """Fallback download using requests"""
        try:
            import requests
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'image',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'same-origin'
            }
            
            if referer:
                headers['Referer'] = referer
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200 and len(response.content) > 1000:
                filepath.write_bytes(response.content)
                logger.info(f"✅ Downloaded with requests: {filepath.name}")
                return True
            else:
                logger.warning(f"⚠️ requests failed for {url}: status={response.status_code}, size={len(response.content)}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error with requests download {url}: {e}")
            return False
    
    async def download_card_images(self, card_data: Dict) -> Dict:
        """Download images for a single card"""
        card_id = card_data['id']
        card_number = card_data.get('card_number', 'NNO')
        player_name = card_data['player_name']
        
        results = {
            'card_id': card_id,
            'front_path': None,
            'back_path': None
        }
        
        # Download front image
        if card_data.get('front_image_path'):
            front_filename = self._get_image_filename(card_id, card_number, player_name, 'front')
            front_path = self.front_dir / front_filename
            
            if not front_path.exists():
                referer = card_data.get('card_url', 'https://www.tcdb.com/')
                
                if self.aria2c_available:
                    success = await self.download_image_with_aria2c(card_data['front_image_path'], front_path, referer)
                else:
                    success = await self.download_image_with_requests(card_data['front_image_path'], front_path, referer)
                
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
                referer = card_data.get('card_url', 'https://www.tcdb.com/')
                
                if self.aria2c_available:
                    success = await self.download_image_with_aria2c(card_data['back_image_path'], back_path, referer)
                else:
                    success = await self.download_image_with_requests(card_data['back_image_path'], back_path, referer)
                
                if success:
                    results['back_path'] = str(back_path)
                    self.downloaded_count += 1
                else:
                    self.failed_count += 1
            else:
                results['back_path'] = str(back_path)
                logger.info(f"📁 Already exists: {back_filename}")
        
        return results
    
    async def download_images_for_year(self, cards: List[Dict], max_concurrent: int = 2) -> Dict:
        """Download images for all cards in a year"""
        logger.info(f"🚀 Starting aria2c image download for {len(cards)} cards...")
        
        # Process cards with concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def download_with_semaphore(card):
            async with semaphore:
                return await self.download_card_images(card)
        
        tasks = []
        for i, card in enumerate(cards):
            # Add delay between batches to avoid overwhelming the server
            if i % 10 == 0 and i > 0:
                await asyncio.sleep(1)
            
            task = asyncio.create_task(download_with_semaphore(card))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_downloads = 0
        failed_downloads = 0
        
        for result in results:
            if isinstance(result, Exception):
                failed_downloads += 1
                logger.error(f"❌ Download task failed: {result}")
            elif result['front_path'] or result['back_path']:
                successful_downloads += 1
            else:
                failed_downloads += 1
        
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
            'vpn_ip': self.vpn_ip,
            'aria2c_used': self.aria2c_available
        }
    
    def get_image_paths(self, card_id: int, card_number: str, player_name: str) -> Dict:
        """Get local image paths for a card"""
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
        
        return {
            'front_images': front_count,
            'back_images': back_count,
            'total_images': front_count + back_count,
            'downloaded_count': self.downloaded_count,
            'failed_count': self.failed_count
        }
