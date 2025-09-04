"""
Main data manager for Phillies cards
Combines database and image management functionality
"""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

try:
    from ..database.database_manager import DatabaseManager
    from ..storage.image_manager import ImageManager
except ImportError:
    # Handle direct execution
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from database.database_manager import DatabaseManager
    from storage.image_manager import ImageManager

logger = logging.getLogger(__name__)

class PhilliesDataManager:
    def __init__(self, db_path: str = "data/phillies_cards.db", 
                 images_path: str = "data/images"):
        """Initialize the data manager"""
        self.db_manager = DatabaseManager(db_path)
        self.image_manager = ImageManager(images_path)
        logger.info("✅ Phillies Data Manager initialized")
    
    def migrate_csv_data(self, csv_path: str) -> Dict[str, Any]:
        """Migrate CSV data to database"""
        try:
            import csv
            from datetime import datetime
            
            logger.info(f"📥 Starting CSV migration from {csv_path}")
            
            # Read CSV data
            cards_processed = 0
            cards_skipped = 0
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row_num, row in enumerate(reader, start=2):
                    try:
                        # Clean and validate data
                        if not row.get('year') or not row.get('fullName'):
                            logger.warning(f"⚠️ Skipping row {row_num}: Missing year or player name")
                            cards_skipped += 1
                            continue
                        
                        # Convert year to integer
                        try:
                            year = int(row['year'])
                        except ValueError:
                            logger.warning(f"⚠️ Skipping row {row_num}: Invalid year '{row['year']}'")
                            cards_skipped += 1
                            continue
                        
                        # Prepare card data
                        card_data = {
                            'year': year,
                            'main_set': row.get('main_set', '').strip(),
                            'subset': row.get('subset', '').strip(),
                            'number': row.get('number', '').strip(),
                            'fullName': row.get('fullName', '').strip(),
                            'card': row.get('card', '').strip(),
                            'type': row.get('type', '').strip(),
                            'front_photo_url': row.get('front_photo_url', '').strip(),
                            'back_photo_url': row.get('back_photo_url', '').strip(),
                            'card_url': row.get('card_url', '').strip(),
                            'scraped_at': row.get('scraped_at', datetime.now().isoformat())
                        }
                        
                        # Insert card into database
                        card_id = self.db_manager.insert_card(card_data)
                        cards_processed += 1
                        
                        if cards_processed % 100 == 0:
                            logger.info(f"📊 Processed {cards_processed} cards...")
                    
                    except Exception as e:
                        logger.error(f"❌ Error processing row {row_num}: {e}")
                        cards_skipped += 1
                        continue
            
            # Get final statistics
            stats = self.db_manager.get_statistics()
            
            logger.info(f"🎉 Migration completed!")
            logger.info(f"📊 Cards processed: {cards_processed}")
            logger.info(f"⚠️ Cards skipped: {cards_skipped}")
            
            return {
                'success': True,
                'message': f'CSV data migrated successfully. {cards_processed} cards processed, {cards_skipped} skipped.',
                'statistics': stats
            }
                
        except Exception as e:
            logger.error(f"❌ Error during CSV migration: {e}")
            return {
                'success': False,
                'message': f'Migration error: {str(e)}'
            }
    
    def download_all_images(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """Download images for all cards in the database"""
        try:
            # Get all cards from database
            all_cards = []
            stats = self.db_manager.get_statistics()
            
            for year_data in stats.get('cards_by_year', []):
                year = year_data['year']
                cards = self.db_manager.get_cards_by_year(year, limit=1000)
                all_cards.extend(cards)
            
            if limit:
                all_cards = all_cards[:limit]
            
            logger.info(f"🖼️ Starting image download for {len(all_cards)} cards...")
            
            results = {
                'total_cards': len(all_cards),
                'front_downloaded': 0,
                'back_downloaded': 0,
                'errors': 0
            }
            
            for i, card in enumerate(all_cards):
                try:
                    if i % 10 == 0:
                        logger.info(f"📥 Processing card {i+1}/{len(all_cards)}...")
                    
                    # Download images for this card
                    image_results = self.image_manager.download_card_images(card)
                    
                    if image_results['front_downloaded']:
                        results['front_downloaded'] += 1
                    if image_results['back_downloaded']:
                        results['back_downloaded'] += 1
                    
                except Exception as e:
                    logger.error(f"❌ Error downloading images for card {card.get('id')}: {e}")
                    results['errors'] += 1
            
            logger.info(f"🎉 Image download completed!")
            logger.info(f"📊 Front images: {results['front_downloaded']}")
            logger.info(f"📊 Back images: {results['back_downloaded']}")
            logger.info(f"❌ Errors: {results['errors']}")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error during image download: {e}")
            return {
                'success': False,
                'message': f'Image download error: {str(e)}'
            }
    
    def get_cards_by_year(self, year: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Get cards for a specific year with image information"""
        try:
            cards = self.db_manager.get_cards_by_year(year, limit)
            
            # Add image information to each card
            for card in cards:
                card['images'] = self._get_card_images(card)
            
            return cards
            
        except Exception as e:
            logger.error(f"❌ Error getting cards by year: {e}")
            return []
    
    def search_cards(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search cards with image information"""
        try:
            cards = self.db_manager.search_cards(query, limit)
            
            # Add image information to each card
            for card in cards:
                card['images'] = self._get_card_images(card)
            
            return cards
            
        except Exception as e:
            logger.error(f"❌ Error searching cards: {e}")
            return []
    
    def _get_card_images(self, card: Dict[str, Any]) -> Dict[str, Any]:
        """Get image information for a card"""
        try:
            year = int(card['year'])
            set_name = card.get('main_set_name', card.get('main_set', 'unknown'))
            card_number = card.get('card_number', 'unknown')
            player_name = card.get('player_name', 'unknown')
            
            front_path = self.image_manager.get_image_path(year, set_name, card_number, player_name, "front")
            back_path = self.image_manager.get_image_path(year, set_name, card_number, player_name, "back")
            
            return {
                'front': self.image_manager.get_image_info(front_path),
                'back': self.image_manager.get_image_info(back_path)
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting card images: {e}")
            return {'front': {'exists': False}, 'back': {'exists': False}}
    
    def get_card_details(self, card_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific card"""
        try:
            # This would require implementing a method in DatabaseManager
            # For now, return None
            logger.warning("⚠️ get_card_details not yet implemented")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting card details: {e}")
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        try:
            db_stats = self.db_manager.get_statistics()
            image_stats = self.image_manager.get_storage_statistics()
            
            # Combine statistics
            combined_stats = {
                'database': db_stats,
                'images': image_stats,
                'summary': {
                    'total_cards': db_stats.get('total_cards', 0),
                    'total_images': image_stats.get('total_images', 0),
                    'total_size_mb': round(image_stats.get('total_size', 0) / (1024 * 1024), 2)
                }
            }
            
            return combined_stats
            
        except Exception as e:
            logger.error(f"❌ Error getting statistics: {e}")
            return {}
    
    def cleanup_data(self) -> Dict[str, Any]:
        """Clean up orphaned data and images"""
        try:
            results = {
                'database_cleaned': 0,
                'images_cleaned': 0,
                'errors': 0
            }
            
            # Clean up orphaned images
            image_cleanup = self.image_manager.cleanup_orphaned_images(self.db_manager)
            results['images_cleaned'] = image_cleanup.get('cleaned', 0)
            results['errors'] += image_cleanup.get('errors', 0)
            
            logger.info(f"🧹 Cleanup completed: {results['images_cleaned']} images cleaned")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")
            return {'errors': 1}
    
    def export_data(self, format: str = 'json', output_path: str = None) -> Dict[str, Any]:
        """Export data in various formats"""
        try:
            if format.lower() == 'json':
                return self._export_json(output_path)
            elif format.lower() == 'csv':
                return self._export_csv(output_path)
            else:
                return {
                    'success': False,
                    'message': f'Unsupported export format: {format}'
                }
                
        except Exception as e:
            logger.error(f"❌ Error during export: {e}")
            return {
                'success': False,
                'message': f'Export error: {str(e)}'
            }
    
    def _export_json(self, output_path: str = None) -> Dict[str, Any]:
        """Export data as JSON"""
        try:
            import json
            
            if not output_path:
                output_path = "data/phillies_cards_export.json"
            
            # Get all data
            all_data = []
            stats = self.db_manager.get_statistics()
            
            for year_data in stats.get('cards_by_year', []):
                year = year_data['year']
                cards = self.db_manager.get_cards_by_year(year, limit=10000)
                
                for card in cards:
                    card['images'] = self._get_card_images(card)
                    all_data.append(card)
            
            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, indent=2, ensure_ascii=False)
            
            return {
                'success': True,
                'message': f'Data exported to {output_path}',
                'cards_exported': len(all_data)
            }
            
        except Exception as e:
            logger.error(f"❌ Error during JSON export: {e}")
            return {
                'success': False,
                'message': f'JSON export error: {str(e)}'
            }
    
    def _export_csv(self, output_path: str = None) -> Dict[str, Any]:
        """Export data as CSV"""
        try:
            import csv
            
            if not output_path:
                output_path = "data/phillies_cards_export.csv"
            
            # Get all data
            all_data = []
            stats = self.db_manager.get_statistics()
            
            for year_data in stats.get('cards_by_year', []):
                year = year_data['year']
                cards = self.db_manager.get_cards_by_year(year, limit=10000)
                all_data.extend(cards)
            
            # Write to CSV
            if all_data:
                fieldnames = all_data[0].keys()
                
                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(all_data)
            
            return {
                'success': True,
                'message': f'Data exported to {output_path}',
                'cards_exported': len(all_data)
            }
            
        except Exception as e:
            logger.error(f"❌ Error during CSV export: {e}")
            return {
                'success': False,
                'message': f'CSV export error: {str(e)}'
            }
