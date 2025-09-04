#!/usr/bin/env python3
"""
Migration script to convert CSV data to SQLite database
"""

import sys
import csv
import logging
from pathlib import Path
from datetime import datetime

# Add the backend directory to the path
sys.path.append(str(Path(__file__).parent.parent / "backend"))

try:
    from database.database_manager import DatabaseManager
except ImportError:
    # Handle direct execution
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent / "backend"))
    from database.database_manager import DatabaseManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def migrate_csv_to_database(csv_path: str, db_path: str = "data/phillies_cards.db"):
    """Migrate CSV data to SQLite database"""
    
    csv_file = Path(csv_path)
    if not csv_file.exists():
        logger.error(f"❌ CSV file not found: {csv_path}")
        return False
    
    try:
        # Initialize database
        db_manager = DatabaseManager(db_path)
        logger.info(f"✅ Database initialized at {db_path}")
        
        # Read CSV data
        cards_processed = 0
        cards_skipped = 0
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 since row 1 is header
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
                    card_id = db_manager.insert_card(card_data)
                    cards_processed += 1
                    
                    if cards_processed % 100 == 0:
                        logger.info(f"📊 Processed {cards_processed} cards...")
                
                except Exception as e:
                    logger.error(f"❌ Error processing row {row_num}: {e}")
                    cards_skipped += 1
                    continue
        
        # Get final statistics
        stats = db_manager.get_statistics()
        
        logger.info(f"🎉 Migration completed!")
        logger.info(f"📊 Cards processed: {cards_processed}")
        logger.info(f"⚠️ Cards skipped: {cards_skipped}")
        logger.info(f"📈 Total cards in database: {stats.get('total_cards', 0)}")
        
        # Show some sample data
        if stats.get('cards_by_year'):
            logger.info("📅 Cards by year:")
            for year_data in stats['cards_by_year'][:5]:  # Show first 5 years
                logger.info(f"   {year_data['year']}: {year_data['count']} cards")
        
        if stats.get('top_sets'):
            logger.info("🏆 Top sets:")
            for set_data in stats['top_sets'][:5]:  # Show first 5 sets
                logger.info(f"   {set_data['display_name']}: {set_data['count']} cards")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate CSV data to SQLite database')
    parser.add_argument('csv_file', help='Path to the CSV file to migrate')
    parser.add_argument('--db-path', default='data/phillies_cards.db', 
                       help='Path for the SQLite database (default: data/phillies_cards.db)')
    
    args = parser.parse_args()
    
    success = migrate_csv_to_database(args.csv_file, args.db_path)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
