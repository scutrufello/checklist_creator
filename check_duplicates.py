#!/usr/bin/env python3
"""Check for duplicate entries in the database"""

import sys
from pathlib import Path

# Add the backend directory to the path
sys.path.append(str(Path(__file__).parent / "backend"))

from core.data_manager import PhilliesDataManager

def check_duplicates():
    """Check for duplicate entries in the database"""
    dm = PhilliesDataManager()
    cards = dm.get_cards_by_year(1992, limit=1000)
    
    print(f"Total cards in database: {len(cards)}")
    
    # Check for duplicates using tcdb_url (the actual unique identifier)
    seen = set()
    duplicates = 0
    duplicate_details = []
    
    for card in cards:
        url = card['tcdb_url']
        if url in seen:
            duplicates += 1
            duplicate_details.append(url)
        else:
            seen.add(url)
    
    print(f"Unique cards: {len(seen)}")
    print(f"Duplicates: {duplicates}")
    
    if duplicates > 0:
        print("\nDuplicate entries:")
        for dup in duplicate_details[:10]:  # Show first 10
            print(f"  {dup}")
        if duplicates > 10:
            print(f"  ... and {duplicates - 10} more")

if __name__ == "__main__":
    check_duplicates()
