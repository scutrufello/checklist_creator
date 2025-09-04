"""
Image storage manager for Phillies cards
Handles local image storage and organization
"""

import os
import logging
import requests
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse
import hashlib

logger = logging.getLogger(__name__)

class ImageManager:
    def __init__(self, base_path: str = "data/images"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.years_path = self.base_path / "years"
        self.sets_path = self.base_path / "sets"
        self.players_path = self.base_path / "players"
        
        for path in [self.years_path, self.sets_path, self.players_path]:
            path.mkdir(exist_ok=True)
    
    def get_image_path(self, year: int, set_name: str, card_number: str, 
                      player_name: str, image_type: str = "front") -> Path:
        """Generate organized image path structure"""
        
        # Clean names for filesystem
        safe_set = self._sanitize_filename(set_name)
        safe_player = self._sanitize_filename(player_name)
        safe_number = self._sanitize_filename(str(card_number))
        
        # Create path: data/images/years/1992/bowman/104_braulio_castillo_front.jpg
        image_path = self.years_path / str(year) / safe_set / f"{safe_number}_{safe_player}_{image_type}.jpg"
        
        # Ensure directory exists
        image_path.parent.mkdir(parents=True, exist_ok=True)
        
        return image_path
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem compatibility"""
        # Replace problematic characters
        filename = filename.replace('/', '_').replace('\\', '_').replace(':', '_')
        filename = filename.replace('*', '_').replace('?', '_').replace('"', '_')
        filename = filename.replace('<', '_').replace('>', '_').replace('|', '_')
        filename = filename.replace(' ', '_').replace('-', '_')
        
        # Remove multiple underscores
        while '__' in filename:
            filename = filename.replace('__', '_')
        
        # Remove leading/trailing underscores
        filename = filename.strip('_')
        
        # Limit length
        if len(filename) > 100:
            filename = filename[:100]
        
        return filename.lower()
    
    def download_image(self, url: str, local_path: Path, 
                      timeout: int = 30) -> bool:
        """Download image from URL to local path"""
        try:
            # Check if image already exists
            if local_path.exists():
                logger.debug(f"🔄 Image already exists: {local_path}")
                return True
            
            # Download image
            response = requests.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            
            # Save image
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"✅ Downloaded image: {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to download image {url}: {e}")
            return False
    
    def download_card_images(self, card_data: Dict[str, Any]) -> Dict[str, Any]:
        """Download both front and back images for a card"""
        results = {
            'front_downloaded': False,
            'back_downloaded': False,
            'front_path': None,
            'back_path': None
        }
        
        try:
            year = int(card_data['year'])
            set_name = card_data.get('main_set', 'unknown')
            card_number = card_data.get('number', 'unknown')
            player_name = card_data.get('fullName', 'unknown')
            
            # Download front image
            if card_data.get('front_photo_url'):
                front_path = self.get_image_path(year, set_name, card_number, player_name, "front")
                if self.download_image(card_data['front_photo_url'], front_path):
                    results['front_downloaded'] = True
                    results['front_path'] = str(front_path)
            
            # Download back image
            if card_data.get('back_photo_url'):
                back_path = self.get_image_path(year, set_name, card_number, player_name, "back")
                if self.download_image(card_data['back_photo_url'], back_path):
                    results['back_downloaded'] = True
                    results['back_path'] = str(back_path)
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error downloading card images: {e}")
            return results
    
    def get_image_info(self, image_path: Path) -> Dict[str, Any]:
        """Get information about an image file"""
        try:
            if not image_path.exists():
                return {'exists': False}
            
            stat = image_path.stat()
            return {
                'exists': True,
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'path': str(image_path)
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting image info: {e}")
            return {'exists': False}
    
    def cleanup_orphaned_images(self, db_manager) -> Dict[str, Any]:
        """Remove images that no longer have corresponding database records"""
        try:
            # This would require implementing a method to get all image paths from database
            # For now, just return a placeholder
            logger.info("🧹 Cleanup functionality not yet implemented")
            return {'cleaned': 0, 'errors': 0}
            
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")
            return {'cleaned': 0, 'errors': 0}
    
    def get_storage_statistics(self) -> Dict[str, Any]:
        """Get statistics about image storage"""
        try:
            stats = {
                'total_images': 0,
                'total_size': 0,
                'years': {},
                'sets': {}
            }
            
            # Count images by year
            for year_dir in self.years_path.iterdir():
                if year_dir.is_dir() and year_dir.name.isdigit():
                    year = int(year_dir.name)
                    year_stats = {'count': 0, 'size': 0}
                    
                    # Count images in this year
                    for image_file in year_dir.rglob('*.jpg'):
                        if image_file.is_file():
                            year_stats['count'] += 1
                            year_stats['size'] += image_file.stat().st_size
                    
                    stats['years'][year] = year_stats
                    stats['total_images'] += year_stats['count']
                    stats['total_size'] += year_stats['size']
            
            # Count images by set
            for set_dir in self.sets_path.iterdir():
                if set_dir.is_dir():
                    set_name = set_dir.name
                    set_stats = {'count': 0, 'size': 0}
                    
                    for image_file in set_dir.rglob('*.jpg'):
                        if image_file.is_file():
                            set_stats['count'] += 1
                            set_stats['size'] += image_file.stat().st_size
                    
                    stats['sets'][set_name] = set_stats
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error getting storage statistics: {e}")
            return {}
    
    def optimize_storage(self) -> Dict[str, Any]:
        """Optimize image storage (placeholder for future compression/optimization)"""
        try:
            logger.info("🔧 Storage optimization not yet implemented")
            return {'optimized': 0, 'saved_space': 0}
            
        except Exception as e:
            logger.error(f"❌ Error during optimization: {e}")
            return {'optimized': 0, 'saved_space': 0}
