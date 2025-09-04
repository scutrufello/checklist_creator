#!/usr/bin/env python3
"""
TCDB Phillies Card Scraper with VPN Integration
Adapted from existing successful scraper code
"""

import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup
import time
import re
import csv
import os
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from tqdm import tqdm
from typing import Dict, List, Optional, Tuple
import aiohttp
import json

# Import our VPN infrastructure and database
try:
    from ..core.credential_manager import get_credential_manager
    from .vpn_connector import VPNConnector
    from .vyprvpn_scraper import VyprVPNServerScraper
    from ..database.database_manager import DatabaseManager
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from core.credential_manager import get_credential_manager
    from services.vpn_connector import VPNConnector
    from services.vyprvpn_scraper import VyprVPNServerScraper
    from database.database_manager import DatabaseManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TCDBPhilliesScraper:
    """TCDB Phillies Card Scraper with VPN Integration"""
    
    def __init__(self, output_dir: str = "data/phillies_cards", db_path: str = "data/phillies_cards.db"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize database manager
        self.db_manager = DatabaseManager(db_path)
        
        # Initialize VPN system
        self.vpn_connector = VPNConnector()
        self.vyprvpn_scraper = VyprVPNServerScraper()
        
        # Cloudflare-bypassing scraper
        self.scraper = cloudscraper.create_scraper()
        
        # Output files (for logging only)
        self.log_csv = self.output_dir / "phillies_scraped_years.csv"
        self.failed_csv = self.output_dir / "phillies_failed_years.csv"
        
        # Initialize files
        self._init_files()
        
        # Load existing data for deduplication
        self.seen = self._load_existing_data()
        self.done_years = self._load_completed_years()
        
        # VPN connection tracking
        self.current_vpn_connection = None
        self.vpn_rotation_count = 0
        self.max_vpn_rotations = 5
        
    def _init_files(self):
        """Initialize output files with headers"""
        # Log CSV for completed years
        if not self.log_csv.exists() or self.log_csv.stat().st_size == 0:
            with open(self.log_csv, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["year", "timestamp", "vpn_endpoint", "cards_found"])
        
        # Failed attempts CSV
        if not self.failed_csv.exists() or self.failed_csv.stat().st_size == 0:
            with open(self.failed_csv, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["year", "error", "vpn_endpoint", "timestamp"])
    
    def _load_existing_data(self) -> set:
        """Load existing data for deduplication from database"""
        try:
            # Get all existing cards from database
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute("SELECT year, main_set, subset, card_number, player_name FROM cards")
                rows = cursor.fetchall()
                
                seen = set(
                    (str(row['year']), row['main_set'], row['card_number'], row['player_name'])
                    for row in rows
                )
                logger.info(f"Loaded {len(seen)} existing cards for deduplication")
                return seen
        except Exception as e:
            logger.warning(f"Could not load existing data: {e}")
            return set()
    
    def _load_completed_years(self) -> set:
        """Load completed years from log"""
        try:
            df_log = pd.read_csv(self.log_csv, dtype=str)
            if {"year"}.issubset(df_log.columns):
                done = set(df_log.year.tolist())
                logger.info(f"Loaded {len(done)} completed years")
                return done
        except (pd.errors.EmptyDataError, pd.errors.ParserError, FileNotFoundError):
            pass
        return set()
    
    async def ensure_vpn_connection(self) -> bool:
        """Ensure VPN is connected, rotate if needed"""
        try:
            # Check if VPN is already working by checking IP
            logger.info("🔍 Checking current VPN status...")

            # Use subprocess to check if VyprVPN is connected
            import subprocess
            try:
                # Check if there's a tun0 interface (VPN interface)
                result = subprocess.run(['ip', 'route', 'show'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0 and 'tun0' in result.stdout:
                    logger.info("✅ VPN interface detected, checking IP...")

                    # Check if IP has changed
                    try:
                        import requests
                        response = requests.get('https://ifconfig.me', timeout=10)
                        current_ip = response.text.strip()
                        logger.info(f"Current IP: {current_ip}")

                        # If IP is not the original (77.175.120.124), VPN is working
                        if current_ip != "77.175.120.124":
                            logger.info("✅ VPN is working - IP has changed")
                            return True
                        else:
                            logger.info("⚠️ VPN interface exists but IP hasn't changed")
                    except Exception as e:
                        logger.warning(f"Could not check IP: {e}")

                # If we get here, need to connect VPN
                logger.info("🔌 Establishing VPN connection...")

                # Use direct VyprVPN CLI command
                target_server = "us3.vpn.giganews.com"  # Use the server we know works

                connect_cmd = ['vyprvpn', 'connect', '--servername', target_server]
                result = subprocess.run(connect_cmd, capture_output=True, text=True, timeout=30)

                if result.returncode == 0 and "Success" in result.stdout:
                    logger.info(f"✅ VPN connected to {target_server}")

                    # Wait for connection to stabilize
                    await asyncio.sleep(3)

                    # Verify IP changed
                    try:
                        import requests
                        response = requests.get('https://ifconfig.me', timeout=10)
                        new_ip = response.text.strip()
                        logger.info(f"New IP: {new_ip}")

                        if new_ip != "77.175.120.124":
                            logger.info("✅ IP verification successful")
                            return True
                        else:
                            logger.warning("⚠️ VPN connected but IP didn't change")
                            return False
                    except Exception as e:
                        logger.warning(f"Could not verify IP: {e}")
                        return False
                else:
                    logger.error(f"❌ VPN connection failed: {result.stderr}")
                    return False

            except Exception as e:
                logger.error(f"❌ VPN connection error: {e}")
                return False
                
        except Exception as e:
            logger.error(f"❌ VPN connection error: {e}")
            return False
    
    async def rotate_vpn_endpoint(self) -> bool:
        """Rotate to a different VPN endpoint"""
        try:
            if self.vpn_rotation_count >= self.max_vpn_rotations:
                logger.error(f"❌ Maximum VPN rotations ({self.max_vpn_rotations}) reached")
                return False
            
            logger.info(f"🔄 Rotating VPN endpoint (attempt {self.vpn_rotation_count + 1})")
            
            # Disconnect current connection
            if self.current_vpn_connection:
                await self.vpn_connector.disconnect(self.current_vpn_connection)
                self.current_vpn_connection = None
            
            # Wait before reconnecting
            await asyncio.sleep(5)
            
            # Try to connect to a different server
            servers = self.vyprvpn_scraper.get_all_servers()
            if not servers:
                logger.error("❌ No VPN servers available for rotation")
                return False
            
            # Pick a different server (avoid the last one)
            available_servers = [s for s in servers if s.hostname != getattr(self, '_last_server', None)]
            if not available_servers:
                available_servers = servers
            
            target_server = available_servers[0]
            self._last_server = target_server.hostname
            
            result = await self.vpn_connector.connect_to_vyprvpn(
                server_hostname=target_server.hostname
            )
            
            if result['success']:
                self.current_vpn_connection = result['connection_id']
                self.vpn_rotation_count += 1
                logger.info(f"✅ VPN rotated to {target_server.hostname}")
                return True
            else:
                logger.error(f"❌ VPN rotation failed: {result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"❌ VPN rotation error: {e}")
            return False
    
    def should_rotate_vpn(self, error: Exception) -> bool:
        """Check if an error should trigger VPN rotation"""
        error_str = str(error).lower()
        return any(trigger in error_str for trigger in [
            '429', 'rate limit', 'too many requests', 'banned', 'blocked', 
            'forbidden', 'cloudflare', 'just a moment', 'checking your browser'
        ])
    
    def get_phillies_team_url(self) -> str:
        """Get the Phillies team page URL on TCDB"""
        return "https://www.tcdb.com/Team.cfm/tid/21/col/1/Philadelphia-Phillies"
    
    def extract_year_links(self, html_content: str) -> List[Tuple[str, str]]:
        """Extract year links from Phillies team page"""
        soup = BeautifulSoup(html_content, "html.parser")
        year_links = []
        
        # Debug: Look for any links first
        all_links = soup.find_all("a")
        logger.info(f"Found {len(all_links)} total links on page")
        
        # Show first 10 links to understand the structure
        logger.info("First 10 links on page:")
        for i, link in enumerate(all_links[:10]):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            logger.info(f"  {i+1}. '{text}' -> {href}")
        
        # Look for actual year links in the HTML content
        logger.info("Looking for year-related links...")
        
        # Try to find year links in the actual content
        # Look for the correct pattern from the HTML: /yea/{YEAR_RANGE}/
        year_patterns = [
            r'/yea/([^/]+)/',  # /yea/1982/ or /yea/1987-90/
            r'yea=([^&]+)',    # yea=1982 or yea=1987-90
        ]
        
        for pattern in year_patterns:
            matches = re.findall(pattern, html_content)
            if matches:
                logger.info(f"  Pattern '{pattern}' found {len(matches)} matches: {matches[:5]}")
                for year_range in matches:
                    # Handle year ranges like "1987-90", "1901-17", etc.
                    if '-' in year_range:
                        # Extract the start year from ranges like "1987-90" -> "1987"
                        start_year = year_range.split('-')[0]
                        if start_year.isdigit() and 1900 <= int(start_year) <= 2030:
                            year_url = f"https://www.tcdb.com/Team.cfm/tid/21/col/1/yea/{year_range}/Philadelphia-Phillies"
                            year_links.append((start_year, year_url))
                            logger.info(f"    Added year range: {year_range} (start: {start_year}) -> {year_url}")
                    else:
                        # Single year like "1982"
                        if year_range.isdigit() and 1900 <= int(year_range) <= 2030:
                            year_url = f"https://www.tcdb.com/Team.cfm/tid/21/col/1/yea/{year_range}/Philadelphia-Phillies"
                            year_links.append((year_range, year_url))
                            logger.info(f"    Added single year: {year_range} -> {year_url}")
        
        # Also check for any links that might contain years
        for i, link in enumerate(all_links):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Check if link text or href contains a year
            if (text.isdigit() and 1900 <= int(text) <= 2030) or \
               any(year in href for year in ['1982', '1981', '1983', '1980', '1984', '1985']) or \
               any(year in text for year in ['1982', '1981', '1983', '1980', '1984', '1985']):
                logger.info(f"  Found year link: '{text}' -> {href}")
                
                # Extract year
                if text.isdigit() and 1900 <= int(text) <= 2030:
                    year = text
                else:
                    # Try to extract year from href
                    year_match = re.search(r'(\d{4})', href)
                    if year_match:
                        year = year_match.group(1)
                    else:
                        continue
                
                full_url = href if href.startswith('http') else f"https://www.tcdb.com{href}"
                year_links.append((year, full_url))
        
        # If no year links found, try to construct them based on the working script pattern
        if not year_links:
            logger.info("No year links found, trying to construct them...")
            # Based on the working script, year URLs might be in format: /yea/1982/
            for year in range(1970, 2025):
                year_url = f"https://www.tcdb.com/Teams/TeamsByYear.html?tid=121&yea={year}"
                year_links.append((str(year), year_url))
                logger.info(f"  Constructed year link: {year} -> {year_url}")
        
        # Remove duplicates by URL (not just by year name)
        seen_urls = set()
        unique_links = []
        
        for year, url in year_links:
            if url not in seen_urls:
                seen_urls.add(url)
                unique_links.append((year, url))
        
        logger.info(f"Found {len(unique_links)} unique year links after URL deduplication")
        
        # Debug: Show what we found
        logger.info("Unique year links found:")
        for i, (year, url) in enumerate(unique_links[:10]):
            logger.info(f"  {i+1}. {year} -> {url}")
        
        return unique_links
    
    def extract_cards_from_year_page(self, html_content: str, year: str) -> List[Dict]:
        """Extract card information from a year page"""
        soup = BeautifulSoup(html_content, "html.parser")
        cards = []
        
        logger.info(f"🔍 Parsing HTML for {year} - Length: {len(html_content)} chars")
        
        # Look for table rows first
        table_rows = soup.find_all("tr")
        logger.info(f"  Found {len(table_rows)} table rows")
        
        # Debug: Show first few table rows
        for i, row in enumerate(table_rows[:5]):
            logger.info(f"    Row {i+1}: {row.get_text(strip=True)[:100]}...")
        
        # Use the same approach as the working reference script
        card_cells = soup.select("td.vertical")
        logger.info(f"  Found {len(card_cells)} card cells (td.vertical)")
        
        # If no td.vertical cells, try alternative selectors
        if not card_cells:
            logger.info("  No td.vertical cells found, trying alternatives...")
            
            # Try different table cell selectors
            all_td = soup.find_all("td")
            logger.info(f"    Found {len(all_td)} total td elements")
            
            # Look for any td with links
            td_with_links = [td for td in all_td if td.find("a")]
            logger.info(f"    Found {len(td_with_links)} td elements with links")
            
            # Show first few td elements with links
            for i, td in enumerate(td_with_links[:3]):
                link = td.find("a")
                logger.info(f"      TD {i+1}: '{link.get_text(strip=True)}' -> {link.get('href', '')}")
            
            # Use td elements with links as card cells
            card_cells = td_with_links
        
        # If we have card cells, extract from those
        if card_cells:
            for cell in card_cells:
                try:
                    a = cell.find("a")
                    if not a:
                        continue
                    
                    title = (a.get("title", "") or a.text).strip()
                    href = a.get('href', '')
                    
                    # Skip navigation links
                    if any(nav in title.lower() for nav in ['browse', 'baseball', 'basketball', 'football', 'hockey']):
                        continue
                    
                    # Parse card number and player name like the working script
                    mnum = re.search(r"#(\S+)\s+(.*)", title)
                    if mnum:
                        number = mnum.group(1).strip()
                        fullName = mnum.group(2).strip()
                        
                        # Parse set name and subset/parallel
                        set_name = title.split(f"#{number}")[0].strip()
                        
                        # Check if this is a subset/parallel (contains dash after set name)
                        main_set = set_name
                        subset = ""
                        
                        # Look for subset indicators like "- Gold", "- Silver", "- Refractor", etc.
                        if " - " in set_name:
                            parts = set_name.split(" - ", 1)
                            main_set = parts[0].strip()
                            subset = parts[1].strip()
                        elif " -" in set_name:
                            parts = set_name.split(" -", 1)
                            main_set = parts[0].strip()
                            subset = parts[1].strip()
                        
                        # Fix duplicate year in set names (e.g., "2025 2025 Topps" -> "2025 Topps")
                        if main_set.startswith(f"{year} {year}"):
                            main_set = main_set.replace(f"{year} {year}", year, 1)
                        
                        # Extract metadata from the HTML cell content (not just the title)
                        metadata = []
                        
                        # Get the full text content of the cell to find metadata
                        cell_text = cell.get_text(separator='\n', strip=True)
                        logger.debug(f"Cell text: {cell_text}")
                        
                        # Look for metadata patterns in the cell content
                        # Common metadata indicators that appear on separate lines
                        metadata_patterns = [
                            r'\bRC\b',           # Rookie Card
                            r'\bAU\b',           # Autograph
                            r'\bRELIC\b',        # Relic
                            r'\bGU\b',           # Game Used
                            r'\bPATCH\b',        # Patch
                            r'\bSN(\d+)\b',      # Serial Numbered (e.g., SN25)
                            r'\b(\d+)/(\d+)\b',  # Numbered cards (e.g., 1/25)
                            r'\bGOLD\b',         # Gold parallel
                            r'\bSILVER\b',       # Silver parallel
                            r'\bBRONZE\b',       # Bronze parallel
                            r'\bBLACK\b',        # Black parallel
                            r'\bRED\b',          # Red parallel
                            r'\bBLUE\b',         # Blue parallel
                            r'\bGREEN\b',        # Green parallel
                            r'\bORANGE\b',       # Orange parallel
                            r'\bPURPLE\b',       # Purple parallel
                            r'\bPINK\b',         # Pink parallel
                            r'\bYELLOW\b',       # Yellow parallel
                            r'\bREFRACTOR\b',    # Refractor
                            r'\bXFRACTOR\b',     # Xfractor
                            r'\bSUPERFRACTOR\b', # Superfractor
                            r'\bAQUA\b',         # Aqua
                            r'\bBURGUNDY\b',     # Burgundy
                            r'\bFUCHSIA\b',      # Fuchsia
                            r'\bNAVY\b',         # Navy
                            r'\bROSE GOLD\b',    # Rose Gold
                            r'\bSHIMMER\b',      # Shimmer
                            r'\bMINI DIAMOND\b', # Mini Diamond
                            r'\bINSERT\b',       # Insert
                            r'\bCHROME\b',       # Chrome
                            r'\bMOJO\b',         # Mojo
                            r'\bANIME\b',        # Anime
                            r'\bLIMITED\b',      # Limited
                            r'\bEXCLUSIVE\b',    # Exclusive
                            r'\bPREMIUM\b',      # Premium
                            r'\bDELUXE\b',       # Deluxe
                            r'\bHOLOGRAPHIC\b',  # Holographic
                            r'\bFOIL\b',         # Foil
                            r'\bEMBOSSED\b',     # Embossed
                        ]
                        
                        # Check for metadata in the cell text
                        for pattern in metadata_patterns:
                            matches = re.findall(pattern, cell_text, re.IGNORECASE)
                            if matches:
                                if pattern == r'\bSN(\d+)\b':
                                    # Handle serial numbered cards
                                    for match in matches:
                                        metadata.append(f"SN{match}")
                                elif pattern == r'\b(\d+)/(\d+)\b':
                                    # Handle numbered cards
                                    for match in matches:
                                        metadata.append(f"{match[0]}/{match[1]}")
                                else:
                                    # Handle other metadata
                                    for match in matches:
                                        if match.upper() not in [m.upper() for m in metadata]:
                                            metadata.append(match.upper())
                        
                        # Also check the title for any additional metadata
                        title_metadata = []
                        
                        # Look for serial numbers in title
                        sn_match = re.search(r'SN(\d+)', title, re.IGNORECASE)
                        if sn_match:
                            title_metadata.append(f"SN{sn_match.group(1)}")
                        
                        # Look for numbered cards in title
                        numbered_match = re.search(r'(\d+)/(\d+)', title)
                        if numbered_match:
                            title_metadata.append(f"{numbered_match.group(1)}/{numbered_match.group(2)}")
                        
                        # Add title metadata if not already present
                        for tm in title_metadata:
                            if tm not in metadata:
                                metadata.append(tm)
                        
                        # Combine metadata into type field
                        card_type = ' | '.join(metadata) if metadata else ''
                        
                        # Extract card ID from URL for image URLs (will be updated with real URLs later)
                        front_photo_url = back_photo_url = ""
                        if 'sid/' in href:
                            sid_match = re.search(r'sid/(\d+)', href)
                            if sid_match:
                                sid = sid_match.group(1)
                                num_clean = re.sub(r"[^A-Za-z0-9]", "", number)
                                # Generate placeholder URLs (will be replaced with real ones)
                                front_photo_url = f"https://www.tcdb.com/Images/Cards/Baseball/{sid}/{sid}-{num_clean}Fr.jpg"
                                back_photo_url = f"https://www.tcdb.com/Images/Cards/Baseball/{sid}/{sid}-{num_clean}Bk.jpg"
                        
                        # Create card info with proper set structure
                        card_info = {
                            'year': year,
                            'main_set': main_set,
                            'subset': subset,
                            'set': set_name,  # Keep original for backward compatibility
                            'number': number,
                            'fullName': fullName,
                            'card': title,
                            'type': card_type,
                            'front_photo_url': front_photo_url,
                            'back_photo_url': back_photo_url,
                            'card_url': f"https://www.tcdb.com{href}" if href.startswith('/') else href,
                            'scraped_at': datetime.now().isoformat()
                        }
                        
                        cards.append(card_info)
                        logger.info(f"    Found card: #{number} {fullName} ({main_set}{' - ' + subset if subset else ''}){f' [{card_type}]' if card_type else ''}")
                    else:
                        logger.debug(f"    Skipping card with no number pattern: {title}")
                
                except Exception as e:
                    logger.warning(f"Error parsing card cell: {e}")
                    continue
        
        # If no cards found, create a placeholder team card
        if not cards:
            logger.info(f"  No specific cards found for {year}, creating team card placeholder")
            card_info = {
                'year': year,
                'set': f"{year} Phillies Team",
                'number': '1',
                'fullName': f"{year} Philadelphia Phillies Team Card",
                'card': f"{year} Philadelphia Phillies Team Card",
                'type': 'Team',
                'front_photo_url': '',
                'back_photo_url': '',
                'card_url': f"https://www.tcdb.com/Teams/TeamsByYear.html?tid=121&yea={year}",
                'scraped_at': datetime.now().isoformat()
            }
            cards.append(card_info)
        
        logger.info(f"  Total cards extracted for {year}: {len(cards)}")
        return cards
    
    def determine_pagination(self, html_content: str, year: str) -> int:
        """Determine the number of pages for a year, following the working reference script pattern"""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Look for pagination links like the working script
            pagination_links = soup.select("ul.pagination a[href*='PageIndex']")
            
            if pagination_links:
                # Extract page numbers from href attributes
                page_numbers = []
                for link in pagination_links:
                    page_match = re.search(r"PageIndex=(\d+)", link.get('href', ''))
                    if page_match:
                        page_numbers.append(int(page_match.group(1)))
                
                if page_numbers:
                    max_page = max(page_numbers)
                    logger.info(f"  📄 Found pagination: {max_page} pages for {year}")
                    return max_page
            
            # If no pagination found, assume single page
            logger.info(f"  📄 No pagination found for {year}, assuming single page")
            return 1
            
        except Exception as e:
            logger.warning(f"  Error determining pagination for {year}: {e}")
            return 1

    async def scrape_phillies_cards(self, start_year: int = 1970, skip_images: bool = False) -> bool:
        """Main scraping function for Phillies cards"""
        try:
            logger.info("🚀 Starting Phillies card scraping...")
            
            # Ensure VPN connection
            if not await self.ensure_vpn_connection():
                logger.error("❌ Failed to establish VPN connection")
                return False
            
            # Get Phillies team page
            team_url = self.get_phillies_team_url()
            logger.info(f"📄 Fetching Phillies team page: {team_url}")
            
            try:
                # Use cloudscraper with same approach as working script
                response = self.scraper.get(team_url, timeout=10)
                response.raise_for_status()
                
                # Check if we got a Cloudflare page
                if "Just a moment" in response.text or "Checking your browser" in response.text:
                    logger.warning("⚠️ Got Cloudflare challenge page, attempting VPN rotation...")
                    
                    # Try VPN rotation first
                    if await self.rotate_vpn_endpoint():
                        logger.info("✅ VPN rotated, retrying team page...")
                        await asyncio.sleep(3)
                        response = self.scraper.get(team_url, timeout=10)
                        response.raise_for_status()
                    else:
                        logger.warning("⚠️ VPN rotation failed, waiting and retrying...")
                        await asyncio.sleep(5)
                        response = self.scraper.get(team_url, timeout=10)
                        response.raise_for_status()
                    
                    if "Just a moment" in response.text or "Checking your browser" in response.text:
                        logger.error("❌ Still getting Cloudflare page after VPN rotation and retry")
                        return False
                        
            except Exception as e:
                if self.should_rotate_vpn(e):
                    logger.warning(f"⚠️ Detected blocking on team page: {e}")
                    logger.info("🔄 Attempting VPN rotation...")
                    
                    if await self.rotate_vpn_endpoint():
                        logger.info("✅ VPN rotated, retrying team page...")
                        await asyncio.sleep(3)
                        try:
                            response = self.scraper.get(team_url, timeout=10)
                            response.raise_for_status()
                        except Exception as retry_e:
                            logger.error(f"❌ Still failed after VPN rotation: {retry_e}")
                            return False
                    else:
                        logger.error(f"❌ VPN rotation failed: {e}")
                        return False
                else:
                    logger.error(f"❌ Failed to fetch team page: {e}")
                    return False
            
            # Extract year links
            logger.info(f"📄 Response length: {len(response.text)} characters")
            logger.info(f"📄 First 500 chars: {response.text[:500]}")
            
            year_links = self.extract_year_links(response.text)
            if not year_links:
                logger.error("❌ No year links found")
                return False
            
            # Filter by start year
            filtered_years = [
                (year, url) for year, url in year_links
                if year.split('-')[0].isdigit() and int(year.split('-')[0]) >= start_year
            ]
            
            logger.info(f"📅 Found {len(filtered_years)} years to scrape (from {start_year})")
            
            # FOR TESTING: Scrape years that start with start_year (both exact years and set-years)
            test_years = []
            for year, url in filtered_years:
                if year.startswith(str(start_year)):  # This will match both "1982" and "1982-1988"
                    test_years.append((year, url))
            
            if not test_years:
                logger.error(f"❌ No years starting with {start_year} found in available years")
                return False
            
            logger.info(f"🧪 TESTING: Will scrape {len(test_years)} years starting with {start_year}: {[year for year, _ in test_years]}")
            
            # Scrape each year (both exact years and set-years)
            total_cards = 0
            for year, url in tqdm(test_years, desc="Scraping Years", unit="year"):
                # Use URL as unique identifier since year names might be duplicated
                if url in self.done_years:
                    logger.info(f"⚠️ Skipping {year} (URL already completed: {url[:50]}...)")
                    continue
                
                logger.info(f"🔍 Scraping {year}: {url}")
                
                try:
                    # Use the new pagination method instead of single page
                    cards = await self.scrape_year_with_pagination(year, url)
                    
                    if not cards:
                        logger.warning(f"⚠️ No cards found for {year}")
                        continue
                    
                    logger.info(f"📊 Found {len(cards)} total cards for {year} (with pagination)")
                    
                    # Update cards with real image URLs from their pages (if not skipped)
                    if not skip_images:
                        logger.info(f"🖼️ Extracting real image URLs for {len(cards)} cards...")
                        cards_with_images = await self.update_cards_with_images(cards)
                    else:
                        logger.info(f"⏭️ Skipping image extraction for {len(cards)} cards...")
                        cards_with_images = cards
                    
                    # Save cards
                    new_cards = self._save_cards(cards_with_images, year)
                    total_cards += new_cards
                    
                    # Log completion using URL as identifier
                    self._log_completed_year(year, new_cards)
                    self.done_years.add(url)  # Track by URL instead of year name
                    
                except Exception as e:
                    logger.error(f"❌ Error scraping {year}: {e}")
                    self._log_failed_year(year, str(e))
                    continue
            
            logger.info(f"🎉 Scraping completed! Total cards: {total_cards}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Scraping failed: {e}")
            return False
        finally:
            # Disconnect VPN
            if self.current_vpn_connection:
                await self.vpn_connector.disconnect(self.current_vpn_connection)
                self.current_vpn_connection = None

    def _log_failed_year(self, year: str, error: str):
        """Log a failed year attempt"""
        with open(self.failed_csv, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                year, error, 
                getattr(self, '_last_server', 'Unknown'), 
                datetime.now().isoformat()
            ])
    
    def _log_completed_year(self, year: str, cards_found: int):
        """Log a completed year"""
        with open(self.log_csv, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                year, datetime.now().isoformat(), 
                getattr(self, '_last_server', 'Unknown'), cards_found
            ])
    
    def _save_cards(self, cards: List[Dict], year: str) -> int:
        """Save cards to database and return count of new cards"""
        new_cards = 0
        
        for card in cards:
            try:
                # Check for duplicates
                card_key = (str(card['year']), card['main_set'], card['number'], card['fullName'])
                if card_key not in self.seen:
                    # Insert card (this handles set insertion internally)
                    card_id = self.db_manager.insert_card({
                        'year': int(card['year']),
                        'main_set': card['main_set'],
                        'subset': card.get('subset', ''),
                        'number': card['number'],
                        'fullName': card['fullName'],
                        'card': card['card'],
                        'type': card.get('type', ''),
                        'front_photo_url': card.get('front_photo_url', ''),
                        'back_photo_url': card.get('back_photo_url', ''),
                        'card_url': card['card_url'],
                        'scraped_at': card['scraped_at']
                    })
                    
                    self.seen.add(card_key)
                    new_cards += 1
                    
            except Exception as e:
                logger.error(f"❌ Error saving card {card.get('fullName', 'Unknown')}: {e}")
                continue
        
        logger.info(f"💾 Saved {new_cards} new cards for {year} to database")
        return new_cards

    async def scrape_year_with_pagination(self, year: str, base_url: str, max_pages: int = 10) -> List[Dict]:
        """
        Scrape a single year page with pagination.
        This function is not directly called by the main scrape_phillies_cards,
        but is a helper for the pagination logic.
        """
        try:
            logger.info(f"🔄 Scraping {year} with pagination (max {max_pages} pages)...")
            
            # Ensure VPN connection
            if not await self.ensure_vpn_connection():
                logger.error("❌ Failed to establish VPN connection for pagination")
                return []
            
            # Fetch the first page
            logger.info(f"📄 Fetching first page of {year}: {base_url}")
            response = self.scraper.get(base_url, timeout=10)
            response.raise_for_status()
            
            # Check for Cloudflare challenge
            if "Just a moment" in response.text or "Checking your browser" in response.text:
                logger.warning(f"⚠️ Got Cloudflare challenge for {year}, attempting VPN rotation...")
                
                # Try VPN rotation first
                if await self.rotate_vpn_endpoint():
                    logger.info(f"✅ VPN rotated, retrying {year}...")
                    await asyncio.sleep(3)
                    response = self.scraper.get(base_url, timeout=10)
                    response.raise_for_status()
                else:
                    logger.warning(f"⚠️ VPN rotation failed for {year}, waiting and retrying...")
                    await asyncio.sleep(5)
                    response = self.scraper.get(base_url, timeout=10)
                    response.raise_for_status()
                
                if "Just a moment" in response.text or "Checking your browser" in response.text:
                    logger.error(f"❌ Still getting Cloudflare page for {year} after VPN rotation and retry")
                    return []
            
            # Extract cards from the first page
            cards = self.extract_cards_from_year_page(response.text, year)
            logger.info(f"📊 Found {len(cards)} cards on first page for {year}")
            
            # Determine total pages
            total_pages = self.determine_pagination(response.text, year)
            
            # Limit to max_pages for testing
            pages_to_scrape = min(total_pages, max_pages)
            logger.info(f"📄 Found {total_pages} total pages, limiting to first {pages_to_scrape} pages for testing")
            
            if pages_to_scrape > 1:
                logger.info(f"📄 Scraping {pages_to_scrape - 1} additional pages...")
                
                # Iterate through subsequent pages (limited by max_pages)
                for page_num in range(2, pages_to_scrape + 1):
                    # Handle different URL formats for pagination
                    if '?' in base_url:
                        page_url = f"{base_url}&PageIndex={page_num}"
                    else:
                        page_url = f"{base_url}?PageIndex={page_num}"
                    
                    logger.info(f"📄 Fetching page {page_num} of {year}: {page_url}")
                    
                    try:
                        response = self.scraper.get(page_url, timeout=10)
                        response.raise_for_status()
                        
                        # Check for Cloudflare challenge
                        if "Just a moment" in response.text or "Checking your browser" in response.text:
                            logger.warning(f"⚠️ Got Cloudflare challenge for {year} page {page_num}, attempting VPN rotation...")
                            
                            # Try VPN rotation first
                            if await self.rotate_vpn_endpoint():
                                logger.info(f"✅ VPN rotated, retrying {year} page {page_num}...")
                                await asyncio.sleep(3)
                                response = self.scraper.get(page_url, timeout=10)
                                response.raise_for_status()
                            else:
                                logger.warning(f"⚠️ VPN rotation failed for {year} page {page_num}, waiting and retrying...")
                                await asyncio.sleep(5)
                                response = self.scraper.get(page_url, timeout=10)
                                response.raise_for_status()
                            
                            if "Just a moment" in response.text or "Checking your browser" in response.text:
                                logger.error(f"❌ Still getting Cloudflare page for {year} page {page_num} after VPN rotation and retry")
                                break # Stop on Cloudflare challenge
                        
                        # Add delay like working script
                        await asyncio.sleep(1.5)
                        
                        # Extract cards from subsequent pages
                        page_cards = self.extract_cards_from_year_page(response.text, year)
                        cards.extend(page_cards)
                        logger.info(f"📊 Found {len(page_cards)} cards on page {page_num} for {year}")
                        
                    except Exception as e:
                        if self.should_rotate_vpn(e):
                            logger.warning(f"⚠️ Detected blocking on {year} page {page_num}: {e}")
                            logger.info("🔄 Attempting VPN rotation...")
                            
                            if await self.rotate_vpn_endpoint():
                                logger.info(f"✅ VPN rotated, retrying {year} page {page_num}...")
                                await asyncio.sleep(3)
                                try:
                                    response = self.scraper.get(page_url, timeout=10)
                                    response.raise_for_status()
                                    
                                    # Extract cards from retry
                                    page_cards = self.extract_cards_from_year_page(response.text, year)
                                    cards.extend(page_cards)
                                    logger.info(f"📊 Found {len(page_cards)} cards on page {page_num} for {year} (after VPN rotation)")
                                    continue
                                except Exception as retry_e:
                                    logger.warning(f"❌ Still failed after VPN rotation: {retry_e}")
                                    break
                            else:
                                logger.warning(f"❌ VPN rotation failed for {year} page {page_num}: {e}")
                                break
                        else:
                            logger.warning(f"❌ Error fetching page {page_num} for {year}: {e}")
                            break # Stop on error
            
            logger.info(f"🎉 Scraping {year} with pagination completed! Total cards: {len(cards)} (from {pages_to_scrape} pages)")
            return cards
            
        except Exception as e:
            logger.error(f"❌ Scraping {year} with pagination failed: {e}")
            return []
        finally:
            # Disconnect VPN
            if self.current_vpn_connection:
                await self.vpn_connector.disconnect(self.current_vpn_connection)
                self.current_vpn_connection = None

    async def extract_image_urls_from_card_page(self, card_url: str, max_retries: int = 3) -> Dict[str, str]:
        """Extract real image URLs from a card page with retry logic for rate limiting and auto VPN rotation"""
        for attempt in range(max_retries):
            try:
                logger.debug(f"🔍 Extracting images from card page: {card_url} (attempt {attempt + 1})")
                
                # Use cloudscraper to access the card page
                response = self.scraper.get(card_url, timeout=15)
                response.raise_for_status()
                
                # Parse the HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Look for image elements with TCDB card image patterns
                card_images = soup.find_all('img', src=lambda x: x and 'Images/Cards' in x)
                
                front_image_url = ""
                back_image_url = ""
                
                for img in card_images:
                    src = img.get('src', '')
                    if 'Fr.jpg' in src:
                        front_image_url = src if src.startswith('http') else f"https://www.tcdb.com{src}"
                    elif 'Bk.jpg' in src:
                        back_image_url = src if src.startswith('http') else f"https://www.tcdb.com{src}"
                
                logger.debug(f"  Found front: {front_image_url}")
                logger.debug(f"  Found back: {back_image_url}")
                
                return {
                    'front_image_url': front_image_url,
                    'back_image_url': back_image_url
                }
                
            except Exception as e:
                if self.should_rotate_vpn(e) and attempt < max_retries - 1:
                    logger.warning(f"⚠️ Detected blocking/rate limiting on {card_url}: {e}")
                    logger.info(f"🔄 Attempting VPN rotation (attempt {attempt + 1})...")
                    
                    # Try to rotate VPN
                    if await self.rotate_vpn_endpoint():
                        logger.info(f"✅ VPN rotated successfully, retrying {card_url}...")
                        # Wait a bit before retrying with new VPN
                        await asyncio.sleep(3)
                        continue
                    else:
                        logger.warning(f"⚠️ VPN rotation failed, waiting before retry...")
                        wait_time = (attempt + 1) * 5  # 5, 10, 15 seconds
                        await asyncio.sleep(wait_time)
                        continue
                elif attempt < max_retries - 1:
                    # Regular retry for other errors
                    wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                    logger.warning(f"⚠️ Error on {card_url}, waiting {wait_time}s before retry: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.warning(f"❌ Error extracting images from {card_url}: {e}")
                    return {
                        'front_image_url': "",
                        'back_image_url': ""
                    }
        
        # If we get here, all retries failed
        logger.warning(f"❌ Failed to extract images from {card_url} after {max_retries} attempts")
        return {
            'front_image_url': "",
            'back_image_url': ""
        }
    
    async def update_cards_with_images(self, cards: List[Dict]) -> List[Dict]:
        """Update cards with real image URLs from their pages"""
        logger.info(f"🖼️ Updating {len(cards)} cards with real image URLs...")
        
        updated_cards = []
        for i, card in enumerate(cards):
            try:
                # Add progressive delay to avoid overwhelming the server
                if i > 0:
                    # Base delay of 2 seconds between requests
                    base_delay = 2.0
                    # Additional delay every 5 requests to be more conservative
                    if i % 5 == 0:
                        base_delay += 3.0
                    # Extra delay every 20 requests
                    if i % 20 == 0:
                        base_delay += 5.0
                    
                    logger.debug(f"  Waiting {base_delay:.1f}s before next request...")
                    await asyncio.sleep(base_delay)
                
                card_url = card.get('card_url', '')
                if card_url:
                    image_urls = await self.extract_image_urls_from_card_page(card_url)
                    
                    # Update card with real image URLs
                    card['front_photo_url'] = image_urls['front_image_url']
                    card['back_photo_url'] = image_urls['back_image_url']
                    
                    logger.debug(f"  Updated card {i+1}/{len(cards)}: {card.get('fullName', 'Unknown')}")
                else:
                    logger.warning(f"  No card URL for card {i+1}")
                
                updated_cards.append(card)
                
            except Exception as e:
                logger.error(f"❌ Error updating card {i+1}: {e}")
                updated_cards.append(card)
        
        logger.info(f"✅ Updated {len(updated_cards)} cards with image URLs")
        return updated_cards

async def main():
    """Main function for command-line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape TCDB Phillies cards with VPN")
    parser.add_argument(
        "--start-year",
        type=int,
        default=1970,
        help="Only scrape from this year onward"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/phillies_cards",
        help="Output directory for CSV files"
    )
    
    args = parser.parse_args()
    
    scraper = TCDBPhilliesScraper(output_dir=args.output_dir)
    success = await scraper.scrape_phillies_cards(start_year=args.start_year)
    
    if success:
        print("✅ Scraping completed successfully!")
    else:
        print("❌ Scraping failed!")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
