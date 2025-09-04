"""
Database manager for Phillies cards database
Handles SQLite operations and data management
"""

import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = "data/phillies_cards.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()
    
    def init_database(self):
        """Initialize the database with schema"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Read and execute schema
                schema_path = Path(__file__).parent / "schema.sql"
                with open(schema_path, 'r') as f:
                    schema = f.read()
                
                conn.executescript(schema)
                conn.commit()
                logger.info(f"✅ Database initialized at {self.db_path}")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            raise
    
    def get_connection(self):
        """Get a database connection"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)  # Increase timeout
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    
    def insert_set(self, year: int, name: str, set_type: str, display_name: str) -> int:
        """Insert a set and return its ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO sets (year, name, type, display_name)
                    VALUES (?, ?, ?, ?)
                """, (year, name, set_type, display_name))
                
                # Get the ID (either newly inserted or existing)
                cursor = conn.execute("""
                    SELECT id FROM sets WHERE year = ? AND name = ? AND type = ?
                """, (year, name, set_type))
                
                result = cursor.fetchone()
                if result:
                    return result['id']
                else:
                    raise Exception(f"Failed to insert set: {year} {name} {set_type}")
                    
        except Exception as e:
            logger.error(f"❌ Failed to insert set: {e}")
            raise
    
    def insert_card(self, card_data: Dict[str, Any]) -> int:
        """Insert a card and return its ID"""
        try:
            with self.get_connection() as conn:
                # Insert main set if not exists
                main_set_id = self.insert_set(
                    card_data['year'], 
                    card_data['main_set'], 
                    'main_set', 
                    card_data['main_set']
                )
                
                # Insert subset if exists
                subset_id = None
                if card_data.get('subset'):
                    subset_id = self.insert_set(
                        card_data['year'], 
                        card_data['subset'], 
                        'subset', 
                        f"{card_data['main_set']} - {card_data['subset']}"
                    )
                
                # Check if card already exists (using tcdb_url as the unique identifier)
                existing_card = conn.execute("""
                    SELECT id FROM cards 
                    WHERE tcdb_url = ?
                """, (card_data['card_url'],)).fetchone()
                
                if existing_card:
                    logger.debug(f"🔄 Card already exists: {card_data['fullName']} - {card_data['main_set']}")
                    return existing_card['id']
                
                # Insert card
                cursor = conn.execute("""
                    INSERT INTO cards (
                        year, main_set_id, subset_id, card_number, player_name,
                        card_title, card_type, front_image_path, back_image_path,
                        tcdb_url, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    card_data['year'], main_set_id, subset_id, card_data['number'],
                    card_data['fullName'], card_data['card'], card_data['type'],
                    card_data.get('front_photo_url'), card_data.get('back_photo_url'),
                    card_data['card_url'], card_data['scraped_at']
                ))
                
                card_id = cursor.lastrowid
                conn.commit()
                
                # Insert metadata in a separate transaction
                if card_data.get('type'):
                    self._insert_card_metadata(card_id, card_data['type'])
                
                return card_id
                
        except Exception as e:
            logger.error(f"❌ Failed to insert card: {e}")
            raise
    
    def _insert_card_metadata(self, card_id: int, metadata_string: str):
        """Parse and insert card metadata"""
        if not metadata_string:
            return
        
        metadata_parts = [part.strip() for part in metadata_string.split('|')]
        
        try:
            with self.get_connection() as conn:
                for part in metadata_parts:
                    part = part.strip()
                    if not part:
                        continue
                    
                    # Determine metadata type and value
                    metadata_type, metadata_value = self._parse_metadata(part)
                    
                    if metadata_type:
                        conn.execute("""
                            INSERT OR IGNORE INTO card_metadata (card_id, metadata_type, metadata_value)
                            VALUES (?, ?, ?)
                        """, (card_id, metadata_type, metadata_value))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"❌ Failed to insert metadata: {e}")
    
    def _parse_metadata(self, metadata: str) -> Tuple[str, str]:
        """Parse metadata string into type and value"""
        metadata = metadata.strip().upper()
        
        # Serial numbered cards
        if metadata.startswith('SN'):
            return 'SN', metadata[2:]  # Extract the number
        
        # Numbered cards (e.g., "1/25")
        if '/' in metadata and metadata.replace('/', '').isdigit():
            return 'NUMBERED', metadata
        
        # Parallel colors
        parallel_colors = ['GOLD', 'SILVER', 'BRONZE', 'BLACK', 'RED', 'BLUE', 
                          'GREEN', 'ORANGE', 'PURPLE', 'PINK', 'YELLOW', 'AQUA', 
                          'BURGUNDY', 'FUCHSIA', 'NAVY', 'ROSE GOLD', 'SHIMMER']
        
        if metadata in parallel_colors:
            return 'PARALLEL', metadata
        
        # Special types
        special_types = ['RC', 'AU', 'RELIC', 'GU', 'PATCH', 'INSERT', 'CHROME', 
                        'MOJO', 'ANIME', 'LIMITED', 'EXCLUSIVE', 'PREMIUM', 
                        'DELUXE', 'HOLOGRAPHIC', 'FOIL', 'EMBOSSED', 'REFRACTOR', 
                        'XFRACTOR', 'SUPERFRACTOR', 'MINI DIAMOND']
        
        if metadata in special_types:
            return metadata, ''
        
        # Default case
        return 'OTHER', metadata
    
    def get_cards_by_year(self, year: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Get cards for a specific year"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT 
                        c.*,
                        ms.display_name as main_set_name,
                        ss.display_name as subset_name
                    FROM cards c
                    JOIN sets ms ON c.main_set_id = ms.id
                    LEFT JOIN sets ss ON c.subset_id = ss.id
                    WHERE c.year = ?
                    ORDER BY c.main_set_id, c.card_number
                    LIMIT ?
                """, (year, limit))
                
                cards = [dict(row) for row in cursor.fetchall()]
                
                # Add metadata and image paths to each card
                for card in cards:
                    # Get metadata
                    metadata = self.get_card_metadata(card['id'])
                    card['card_type'] = '|'.join([m['metadata_value'] for m in metadata])
                    
                    # Get image info
                    images = self._get_card_images(card['id'])
                    card['images'] = images
                    
                    # Add local image paths if they exist
                    try:
                        # Try relative import first, then absolute
                        try:
                            from ..services.image_downloader import ImageDownloader
                        except ImportError:
                            import sys
                            import os
                            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
                            from backend.services.image_downloader import ImageDownloader
                        
                        downloader = ImageDownloader()
                        local_images = downloader.get_image_paths(
                            card['id'], 
                            card.get('card_number', 'NNO'), 
                            card['player_name']
                        )
                        card['local_front_image'] = local_images['front_path']
                        card['local_back_image'] = local_images['back_path']
                    except Exception as e:
                        logger.warning(f"Could not get local image paths for card {card['id']}: {e}")
                        card['local_front_image'] = None
                        card['local_back_image'] = None
                
                return cards
                
        except Exception as e:
            logger.error(f"❌ Failed to get cards by year: {e}")
            return []
    
    def search_cards(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search cards by player name or set"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT 
                        c.*,
                        ms.display_name as main_set_name,
                        ss.display_name as subset_name
                    FROM cards c
                    JOIN sets ms ON c.main_set_id = ms.id
                    LEFT JOIN sets ss ON c.subset_id = ss.id
                    WHERE c.player_name LIKE ? OR ms.display_name LIKE ? OR ss.display_name LIKE ?
                    ORDER BY c.year DESC, c.main_set_id
                    LIMIT ?
                """, (f'%{query}%', f'%{query}%', f'%{query}%', limit))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"❌ Failed to search cards: {e}")
            return []
    
    def get_card_metadata(self, card_id: int) -> List[Dict[str, Any]]:
        """Get metadata for a specific card"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT metadata_type, metadata_value
                    FROM card_metadata
                    WHERE card_id = ?
                    ORDER BY metadata_type
                """, (card_id,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"❌ Failed to get card metadata: {e}")
            return []
    
    def _get_card_images(self, card_id: int) -> Dict[str, Any]:
        """Get image information for a specific card"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT image_type, file_path, file_size
                    FROM images
                    WHERE card_id = ?
                    ORDER BY image_type
                """, (card_id,))
                
                images = {}
                for row in cursor.fetchall():
                    image_data = dict(row)
                    images[image_data['image_type']] = {
                        'exists': True,
                        'path': image_data['file_path'],
                        'size': image_data['file_size']
                    }
                
                # Ensure both front and back are present (even if None)
                if 'front' not in images:
                    images['front'] = {'exists': False}
                if 'back' not in images:
                    images['back'] = {'exists': False}
                
                return images
                
        except Exception as e:
            logger.error(f"❌ Failed to get card images: {e}")
            return {'front': {'exists': False}, 'back': {'exists': False}}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            with self.get_connection() as conn:
                stats = {}
                
                # Total cards
                cursor = conn.execute("SELECT COUNT(*) as count FROM cards")
                stats['total_cards'] = cursor.fetchone()['count']
                
                # Cards by year
                cursor = conn.execute("""
                    SELECT year, COUNT(*) as count 
                    FROM cards 
                    GROUP BY year 
                    ORDER BY year DESC
                """)
                stats['cards_by_year'] = [dict(row) for row in cursor.fetchall()]
                
                # Cards by set type
                cursor = conn.execute("""
                    SELECT ms.display_name, COUNT(*) as count
                    FROM cards c
                    JOIN sets ms ON c.main_set_id = ms.id
                    GROUP BY ms.id
                    ORDER BY count DESC
                    LIMIT 10
                """)
                stats['top_sets'] = [dict(row) for row in cursor.fetchall()]
                
                # Metadata counts
                cursor = conn.execute("""
                    SELECT metadata_type, COUNT(*) as count
                    FROM card_metadata
                    GROUP BY metadata_type
                    ORDER BY count DESC
                """)
                stats['metadata_counts'] = [dict(row) for row in cursor.fetchall()]
                
                return stats
                
        except Exception as e:
            logger.error(f"❌ Failed to get statistics: {e}")
            return {}
    
    def cleanup_duplicates(self) -> Dict[str, Any]:
        """Clean up duplicate card entries"""
        try:
            with self.get_connection() as conn:
                # Find duplicates (using tcdb_url as the unique identifier)
                duplicates = conn.execute("""
                    SELECT tcdb_url, COUNT(*) as count
                    FROM cards 
                    GROUP BY tcdb_url
                    HAVING COUNT(*) > 1
                    ORDER BY count DESC
                """).fetchall()
                
                total_duplicates = sum(dup['count'] - 1 for dup in duplicates)
                logger.info(f"🔍 Found {len(duplicates)} duplicate groups with {total_duplicates} total duplicate entries")
                
                if not duplicates:
                    return {'duplicates_removed': 0, 'message': 'No duplicates found'}
                
                # Remove duplicates, keeping the first occurrence
                removed_count = 0
                for dup in duplicates:
                    # Get all IDs for this duplicate group
                    card_ids = conn.execute("""
                        SELECT id FROM cards 
                        WHERE tcdb_url = ?
                        ORDER BY id
                    """, (dup['tcdb_url'],)).fetchall()
                    
                    # Keep the first one, remove the rest
                    if len(card_ids) > 1:
                        ids_to_remove = [row['id'] for row in card_ids[1:]]
                        
                        # Remove metadata for duplicates first
                        for card_id in ids_to_remove:
                            conn.execute("DELETE FROM card_metadata WHERE card_id = ?", (card_id,))
                        
                        # Remove duplicate cards
                        placeholders = ','.join('?' * len(ids_to_remove))
                        conn.execute(f"DELETE FROM cards WHERE id IN ({placeholders})", ids_to_remove)
                        
                        removed_count += len(ids_to_remove)
                
                conn.commit()
                logger.info(f"✅ Removed {removed_count} duplicate entries")
                
                return {
                    'duplicates_removed': removed_count,
                    'message': f'Successfully removed {removed_count} duplicate entries'
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to cleanup duplicates: {e}")
            return {'duplicates_removed': 0, 'error': str(e)}
    
    def reset_database(self):
        """Reset the database (drop all tables and recreate)"""
        try:
            with self.get_connection() as conn:
                # Drop all tables
                conn.execute("DROP TABLE IF EXISTS card_metadata")
                conn.execute("DROP TABLE IF EXISTS images")
                conn.execute("DROP TABLE IF EXISTS cards")
                conn.execute("DROP TABLE IF EXISTS sets")
                conn.commit()
                
                # Recreate schema
                self.init_database()
                logger.info("✅ Database reset completed")
                
        except Exception as e:
            logger.error(f"❌ Failed to reset database: {e}")
            raise
