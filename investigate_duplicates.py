#!/usr/bin/env python3
"""Investigate duplicate entries in the database"""

import sys
from pathlib import Path

# Add the backend directory to the path
sys.path.append(str(Path(__file__).parent / "backend"))

from core.data_manager import PhilliesDataManager

def investigate_duplicates():
    """Investigate duplicate entries in the database"""
    dm = PhilliesDataManager()
    
    # Get all cards
    cards = dm.get_cards_by_year(1992, limit=1000)
    
    print(f"Total cards in database: {len(cards)}")
    
    # Check for duplicates using tcdb_url
    url_counts = {}
    for card in cards:
        url = card['tcdb_url']
        if url not in url_counts:
            url_counts[url] = []
        url_counts[url].append(card)
    
    # Find URLs with multiple cards
    duplicates = {url: cards for url, cards in url_counts.items() if len(cards) > 1}
    
    if duplicates:
        print(f"\nFound {len(duplicates)} URLs with multiple cards:")
        for url, cards in list(duplicates.items())[:5]:  # Show first 5
            print(f"\nURL: {url}")
            for i, card in enumerate(cards):
                print(f"  {i+1}. ID: {card['id']}, Player: {card['player_name']}, Set: {card.get('main_set_name', 'Unknown')}, Number: {card['card_number']}")
    else:
        print("No duplicates found using tcdb_url")
    
    # Also check the specific "duplicates" from our previous script
    print(f"\nChecking specific 'duplicates' from previous script:")
    specific_cards = []
    for card in cards:
        if (card['player_name'] == 'John Kruk' and 
            card.get('main_set_name') == '1992 Ballstreet' and 
            card['card_number'] == 'NNO'):
            specific_cards.append(card)
    
    if specific_cards:
        print(f"Found {len(specific_cards)} cards matching 'John Kruk-1992 Ballstreet-NNO':")
        for i, card in enumerate(specific_cards):
            print(f"  {i+1}. ID: {card['id']}, URL: {card['tcdb_url']}")
            print(f"     Subset: {card.get('subset_name', 'None')}")
            print(f"     Full set name: {card.get('main_set_name', 'Unknown')}")

if __name__ == "__main__":
    investigate_duplicates()
