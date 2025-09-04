#!/usr/bin/env python3
"""
Aria2c Batch Image Downloader for TCDB
Uses aria2c with input files like the working bash script
"""

import asyncio
import subprocess
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
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

class Aria2BatchDownloader:
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
            logger.warning("⚠️ aria2c not found")
    
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
    
    async def download_images_batch(self, cards: List[Dict]) -> Dict:
        """Download images using aria2c with input files (like working bash script)"""
        if not self.aria2c_available:
            logger.error("❌ aria2c not available")
            return {'success': False, 'error': 'aria2c not available'}
        
        try:
            logger.info(f"🚀 Starting batch aria2c download for {len(cards)} cards...")
            
            # Create temporary input files
            with tempfile.NamedTemporaryFile(mode='w', suffix='_front.txt', delete=False) as front_file, \
                 tempfile.NamedTemporaryFile(mode='w', suffix='_back.txt', delete=False) as back_file:
                
                front_input = front_file.name
                back_input = back_file.name
                
                # Write URLs to input files
                front_urls = []
                back_urls = []
                
                for card in cards:
                    card_id = card['id']
                    card_number = card.get('card_number', 'NNO')
                    player_name = card['player_name']
                    
                    # Front image
                    if card.get('front_image_path'):
                        front_filename = self._get_image_filename(card_id, card_number, player_name, 'front')
                        front_path = self.front_dir / front_filename
                        
                        if not front_path.exists():
                            front_urls.append(f"{card['front_image_path']}\n\tout={front_filename}")
                    
                    # Back image
                    if card.get('back_image_path'):
                        back_filename = self._get_image_filename(card_id, card_number, player_name, 'back')
                        back_path = self.back_dir / back_filename
                        
                        if not back_path.exists():
                            back_urls.append(f"{card['back_image_path']}\n\tout={back_filename}")
                
                # Write front URLs
                front_file.write('\n'.join(front_urls))
                front_file.flush()
                
                # Write back URLs
                back_file.write('\n'.join(back_urls))
                back_file.flush()
                
                logger.info(f"📝 Created input files: {len(front_urls)} front URLs, {len(back_urls)} back URLs")
                
                # Download front images
                if front_urls:
                    logger.info("🖼️ Downloading front images...")
                    front_cmd = [
                        'aria2c',
                        '--continue=true',
                        '--max-connection-per-server=1',
                        '--max-concurrent-downloads=2',
                        '--retry-wait=5',
                        '--max-tries=5',
                        '--header=User-Agent: Mozilla/5.0',
                        '--header=Referer: https://www.tcdb.com',
                        '--save-session=front.session',
                        '--input-file=' + front_input,
                        '--auto-file-renaming=false',
                        '--file-allocation=trunc',
                        '--dir=' + str(self.front_dir)
                    ]
                    
                    front_result = await asyncio.create_subprocess_exec(
                        *front_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    front_stdout, front_stderr = await front_result.communicate()
                    logger.info(f"Front download completed with return code: {front_result.returncode}")
                
                # Download back images
                if back_urls:
                    logger.info("🖼️ Downloading back images...")
                    back_cmd = [
                        'aria2c',
                        '--continue=true',
                        '--max-connection-per-server=1',
                        '--max-concurrent-downloads=2',
                        '--retry-wait=5',
                        '--max-tries=5',
                        '--header=User-Agent: Mozilla/5.0',
                        '--header=Referer: https://www.tcdb.com',
                        '--save-session=back.session',
                        '--input-file=' + back_input,
                        '--auto-file-renaming=false',
                        '--file-allocation=trunc',
                        '--dir=' + str(self.back_dir)
                    ]
                    
                    back_result = await asyncio.create_subprocess_exec(
                        *back_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    back_stdout, back_stderr = await back_result.communicate()
                    logger.info(f"Back download completed with return code: {back_result.returncode}")
                
                # Cleanup temporary files
                os.unlink(front_input)
                os.unlink(back_input)
                
                # Count successful downloads
                front_count = len(list(self.front_dir.glob('*.jpg')))
                back_count = len(list(self.back_dir.glob('*.jpg')))
                
                logger.info(f"🎉 Batch download complete!")
                logger.info(f"   🖼️ Front images: {front_count}")
                logger.info(f"   🖼️ Back images: {back_count}")
                logger.info(f"   📊 Total images: {front_count + back_count}")
                
                return {
                    'success': True,
                    'front_images': front_count,
                    'back_images': back_count,
                    'total_images': front_count + back_count,
                    'vpn_used': self.use_vpn,
                    'original_ip': self.original_ip,
                    'vpn_ip': self.vpn_ip
                }
                
        except Exception as e:
            logger.error(f"❌ Error in batch download: {e}")
            return {'success': False, 'error': str(e)}
    
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
