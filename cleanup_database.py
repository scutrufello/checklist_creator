#!/usr/bin/env python3
"""Clean up duplicate entries in the database"""

import sys
from pathlib import Path

# Add the backend directory to the path
sys.path.append(str(Path(__file__).parent / "backend"))

from core.data_manager import PhilliesDataManager

def cleanup_database():
    """Clean up duplicate entries in the database"""
    print("🧹 Starting database cleanup...")
    
    dm = PhilliesDataManager()
    
    # Get initial statistics
    initial_stats = dm.get_statistics()
    print(f"📊 Initial database state:")
    print(f"   Total cards: {initial_stats['summary']['total_cards']}")
    
    # Clean up duplicates
    print("\n🔍 Cleaning up duplicates...")
    cleanup_result = dm.db_manager.cleanup_duplicates()
    
    if 'error' in cleanup_result:
        print(f"❌ Cleanup failed: {cleanup_result['error']}")
        return False
    
    print(f"✅ {cleanup_result['message']}")
    
    # Get final statistics
    final_stats = dm.get_statistics()
    print(f"\n📊 Final database state:")
    print(f"   Total cards: {final_stats['summary']['total_cards']}")
    print(f"   Cards removed: {initial_stats['summary']['total_cards'] - final_stats['summary']['total_cards']}")
    
    return True

def reset_and_remigrate():
    """Reset database and remigrate CSV data"""
    print("🔄 Resetting database and remigrating data...")
    
    dm = PhilliesDataManager()
    
    # Reset database
    print("🗑️ Resetting database...")
    dm.db_manager.reset_database()
    
    # Remigrate CSV data
    csv_path = "data/phillies_cards/phillies_checklist.csv"
    print(f"📥 Migrating CSV data from {csv_path}...")
    
    migration_result = dm.migrate_csv_data(csv_path)
    
    if migration_result['success']:
        print("✅ Migration successful!")
        stats = dm.get_statistics()
        print(f"📊 Final state: {stats['summary']['total_cards']} cards")
        return True
    else:
        print(f"❌ Migration failed: {migration_result['message']}")
        return False

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up Phillies database')
    parser.add_argument('--reset', action='store_true', help='Reset database and remigrate data')
    
    args = parser.parse_args()
    
    if args.reset:
        success = reset_and_remigrate()
    else:
        success = cleanup_database()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
