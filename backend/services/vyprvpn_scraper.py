#!/usr/bin/env python3
"""
VyprVPN Server Hostname Scraper Service
Dynamically fetches and updates VyprVPN server hostnames from their support page
"""

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class VyprVPNServer:
    """Represents a VyprVPN server location"""
    region: str
    country: str
    city: str
    hostname: str
    last_verified: datetime

class VyprVPNServerScraper:
    """Scrapes VyprVPN server hostnames from their support page"""
    
    def __init__(self, cache_file: str = "vyprvpn_servers.json"):
        self.cache_file = Path(cache_file)
        self.base_url = "https://support.giganews.com/hc/en-us/articles/360039615432-What-are-the-VyprVPN-Server-Addresses"
        self.servers: Dict[str, VyprVPNServer] = {}
        self.last_update: Optional[datetime] = None
        
    async def fetch_server_list(self) -> str:
        """Fetch the HTML content from VyprVPN support page"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                async with session.get(self.base_url, headers=headers, timeout=30) as response:
                    if response.status == 200:
                        content = await response.text()
                        logger.info(f"Successfully fetched VyprVPN server list from {self.base_url}")
                        return content
                    else:
                        raise Exception(f"HTTP {response.status}: {response.reason}")
                        
        except Exception as e:
            logger.error(f"Failed to fetch VyprVPN server list: {e}")
            raise
    
    def parse_server_list(self, html_content: str) -> Dict[str, VyprVPNServer]:
        """Parse HTML content to extract server information from Giganews table"""
        servers = {}
        
        try:
            # Simple approach: look for specific patterns in the HTML
            # The servers follow a pattern: "Country - City" followed by "server.vpn.giganews.com"
            
            # Find all server entries by looking for the pattern
            server_pattern = r'([A-Za-z\s\.\-]+)\s*-\s*([A-Za-z\s,]+)</td>\s*<td[^>]*>([a-z0-9]+\.<span>vpn\.giganews\.com</span>)'
            matches = re.findall(server_pattern, html_content, re.IGNORECASE | re.DOTALL)
            
            current_region = "Unknown"
            
            for match in matches:
                country, city, hostname_html = match
                
                # Clean up the extracted text
                country = country.strip()
                city = city.strip()
                
                # Extract the clean hostname from the HTML
                hostname = re.sub(r'<[^>]+>', '', hostname_html).strip()
                
                # Skip if no hostname
                if not hostname:
                    continue
                
                # Determine region based on country
                if country in ["U.S.", "Canada", "Mexico"]:
                    current_region = "North America"
                elif country in ["U.K.", "Germany", "France", "Italy", "Spain", "Netherlands", "Switzerland", "Austria", "Belgium", "Denmark", "Finland", "Norway", "Sweden", "Poland", "Czech Republic", "Hungary", "Romania", "Bulgaria", "Greece", "Turkey", "Ukraine", "Russia"]:
                    current_region = "Europe"
                elif country in ["Japan", "South Korea", "China", "India", "Singapore", "Thailand", "Vietnam", "Malaysia", "Indonesia", "Philippines", "Taiwan", "Hong Kong"]:
                    current_region = "Asia"
                elif country in ["Australia", "New Zealand"]:
                    current_region = "Oceania"
                elif country in ["Brazil", "Argentina", "Colombia", "Chile", "Peru"]:
                    current_region = "South America"
                elif country in ["South Africa", "Egypt", "Nigeria"]:
                    current_region = "Africa"
                else:
                    current_region = "Other"
                
                # Create unique key for the server
                key = f"{country}_{city}".replace(" ", "_").replace(",", "").replace(".", "")
                
                # Create server object
                server = VyprVPNServer(
                    region=current_region,
                    country=country,
                    city=city,
                    hostname=hostname,
                    last_verified=datetime.now()
                )
                
                servers[key] = server
                
            logger.info(f"Successfully parsed {len(servers)} VyprVPN servers")
            return servers
            
        except Exception as e:
            logger.error(f"Failed to parse server list: {e}")
            raise
    
    def load_cached_servers(self) -> Dict[str, VyprVPNServer]:
        """Load cached server list from file"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    
                servers = {}
                for key, server_data in data['servers'].items():
                    server = VyprVPNServer(
                        region=server_data['region'],
                        country=server_data['country'],
                        city=server_data['city'],
                        hostname=server_data['hostname'],
                        last_verified=datetime.fromisoformat(server_data['last_verified'])
                    )
                    servers[key] = server
                
                # Update the instance variables
                self.servers = servers
                self.last_update = datetime.fromisoformat(data['last_update'])
                logger.info(f"Loaded {len(servers)} cached servers from {self.cache_file}")
                return servers
            else:
                logger.info("No cached servers found")
                return {}
                
        except Exception as e:
            logger.error(f"Failed to load cached servers: {e}")
            return {}
    
    def save_servers_to_cache(self, servers: Dict[str, VyprVPNServer]):
        """Save server list to cache file"""
        try:
            # Convert dataclass objects to serializable format
            serializable_servers = {}
            for key, server in servers.items():
                serializable_servers[key] = {
                    'region': server.region,
                    'country': server.country,
                    'city': server.city,
                    'hostname': server.hostname,
                    'last_verified': server.last_verified.isoformat()
                }
            
            data = {
                'last_update': datetime.now().isoformat(),
                'servers': serializable_servers
            }
            
            # Ensure directory exists
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Saved {len(servers)} servers to cache file {self.cache_file}")
            
        except Exception as e:
            logger.error(f"Failed to save servers to cache: {e}")
            raise
    
    def get_server_changes(self, new_servers: Dict[str, VyprVPNServer]) -> Dict[str, List[str]]:
        """Compare new servers with cached servers and return changes"""
        old_servers = self.load_cached_servers()
        
        changes = {
            'added': [],
            'removed': [],
            'modified': []
        }
        
        # Check for added and modified servers
        for key, new_server in new_servers.items():
            if key not in old_servers:
                changes['added'].append(f"Added: {new_server.country} - {new_server.city} ({new_server.hostname})")
            elif old_servers[key].hostname != new_server.hostname:
                changes['modified'].append(f"Modified: {new_server.country} - {new_server.city}: {old_servers[key].hostname} -> {new_server.hostname}")
        
        # Check for removed servers
        for key, old_server in old_servers.items():
            if key not in new_servers:
                changes['removed'].append(f"Removed: {old_server.country} - {old_server.city} ({old_server.hostname})")
        
        return changes
    
    async def update_server_list(self, force_update: bool = False) -> Dict[str, List[str]]:
        """Update server list from VyprVPN support page"""
        try:
            # Check if we need to update (once per day unless forced)
            if not force_update and self.last_update:
                time_since_update = datetime.now() - self.last_update
                if time_since_update < timedelta(days=1):
                    logger.info(f"Server list updated recently ({time_since_update.total_seconds() / 3600:.1f} hours ago), skipping update")
                    return {'status': ['No update needed']}
            
            logger.info("Fetching updated VyprVPN server list...")
            
            # Fetch and parse new server list
            html_content = await self.fetch_server_list()
            new_servers = self.parse_server_list(html_content)
            
            # Get changes
            changes = self.get_server_changes(new_servers)
            
            # Update cache if there are changes
            if any(changes.values()):
                self.servers = new_servers
                self.save_servers_to_cache(new_servers)
                self.last_update = datetime.now()
                logger.info(f"Server list updated with changes: {changes}")
            else:
                logger.info("No changes detected in server list")
                # Still update the timestamp
                self.last_update = datetime.now()
                self.save_servers_to_cache(new_servers)
            
            return changes
            
        except Exception as e:
            logger.error(f"Failed to update server list: {e}")
            raise
    
    def get_servers_by_region(self, region: str) -> List[VyprVPNServer]:
        """Get all servers in a specific region"""
        return [server for server in self.servers.values() if server.region.lower() == region.lower()]
    
    def get_servers_by_country(self, country: str) -> List[VyprVPNServer]:
        """Get all servers in a specific country"""
        return [server for server in self.servers.values() if server.country.lower() == country.lower()]
    
    def get_server_by_hostname(self, hostname: str) -> Optional[VyprVPNServer]:
        """Get server by hostname"""
        for server in self.servers.values():
            if server.hostname == hostname:
                return server
        return None
    
    def get_all_servers(self) -> List[VyprVPNServer]:
        """Get all servers as a list"""
        return list(self.servers.values())
    
    def get_server_count(self) -> int:
        """Get total number of servers"""
        return len(self.servers)
    
    def get_last_update_time(self) -> Optional[datetime]:
        """Get when the server list was last updated"""
        return self.last_update

# Example usage and testing
async def main():
    """Test the VyprVPN scraper"""
    scraper = VyprVPNServerScraper()
    
    try:
        # Update server list
        changes = await scraper.update_server_list()
        print(f"Update completed with changes: {changes}")
        
        # Display some server information
        servers = scraper.get_all_servers()
        print(f"\nTotal servers: {len(servers)}")
        
        # Show servers by region
        regions = set(server.region for server in servers)
        for region in sorted(regions):
            region_servers = scraper.get_servers_by_region(region)
            print(f"\n{region}: {len(region_servers)} servers")
            for server in region_servers[:3]:  # Show first 3
                print(f"  - {server.country} - {server.city}: {server.hostname}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
