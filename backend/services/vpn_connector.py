#!/usr/bin/env python3
"""
VPN Connection Service for Checklist Creator
Establishes VyprVPN connections using the official CLI
"""

import asyncio
import logging
import subprocess
import time
import os
import aiohttp
from pathlib import Path
from typing import Dict, Optional, Any, List
from datetime import datetime

# Import our credential manager
try:
    from ..core.credential_manager import get_credential_manager
except ImportError:
    # Fallback for direct script execution
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core.credential_manager import get_credential_manager

logger = logging.getLogger(__name__)

class VPNConnector:
    """Manages VyprVPN connections using the official CLI"""
    
    def __init__(self):
        self.credential_manager = get_credential_manager()
        self.active_connections: Dict[str, Dict[str, Any]] = {}
        
    async def connect_to_vyprvpn(self, server_hostname: str = None, region: str = None, country: str = None) -> Dict[str, Any]:
        """Connect to VyprVPN using the official CLI"""
        try:
            logger.info(f"Attempting VyprVPN connection to {server_hostname or region or country or 'default'}")
            
            # Get VyprVPN credentials
            credentials = self.credential_manager.get_vyprvpn_credentials()
            if not credentials:
                raise Exception("No VyprVPN credentials found. Please set them up first.")
            
            username = credentials.get('username')
            password = credentials.get('password')
            
            if not username or not password:
                raise Exception("Incomplete VyprVPN credentials")
            
            # Get original IP before connecting
            logger.info("Getting original IP address...")
            original_ip_info = await self.get_external_ip()
            if not original_ip_info['success']:
                logger.warning(f"Failed to get original IP: {original_ip_info['error']}")
                original_ip = "Unknown"
                original_country = "Unknown"
                original_city = "Unknown"
            else:
                original_ip = original_ip_info['ip']
                original_country = original_ip_info.get('country', 'Unknown')
                original_city = original_ip_info.get('city', 'Unknown')
                logger.info(f"Original IP: {original_ip} ({original_country}, {original_city})")
            
            # Get server list if not specified
            if not server_hostname:
                try:
                    from .vyprvpn_scraper import VyprVPNServerScraper
                except ImportError:
                    from vyprvpn_scraper import VyprVPNServerScraper
                scraper = VyprVPNServerScraper()
                server = await self._select_vyprvpn_server(scraper, region, country)
                if not server:
                    raise Exception(f"No suitable VyprVPN server found for {region or country or 'default'}")
                server_hostname = server.hostname
            
            # Connect using VyprVPN CLI
            connection_id = f"vyprvpn_{server_hostname}"
            result = await self._connect_vyprvpn_cli(connection_id, server_hostname, username, password)
            
            if result['success']:
                # Wait a moment for connection to stabilize
                logger.info("Waiting for VPN connection to stabilize...")
                await asyncio.sleep(3)
                
                # Get new IP after connection
                logger.info("Getting new IP address after VPN connection...")
                new_ip_info = await self.get_external_ip()
                if new_ip_info['success']:
                    new_ip = new_ip_info['ip']
                    new_country = new_ip_info.get('country', 'Unknown')
                    new_city = new_ip_info.get('city', 'Unknown')
                    logger.info(f"New IP: {new_ip} ({new_country}, {new_city})")
                    
                    # Check if IP actually changed
                    if new_ip != original_ip:
                        logger.info("✅ IP address changed successfully!")
                        ip_changed = True
                    else:
                        logger.warning("⚠️ IP address did not change after VPN connection")
                        ip_changed = False
                else:
                    logger.warning(f"Failed to get new IP: {new_ip_info['error']}")
                    new_ip = "Unknown"
                    new_country = "Unknown"
                    new_city = "Unknown"
                    ip_changed = False
                
                # Store connection info with IP details
                self.active_connections[connection_id] = {
                    'provider': 'vyprvpn',
                    'server': server_hostname,
                    'connected_at': datetime.now().isoformat(),
                    'status': 'connected',
                    'original_ip': original_ip,
                    'original_country': original_country,
                    'original_city': original_city,
                    'current_ip': new_ip,
                    'current_country': new_country,
                    'current_city': new_city,
                    'ip_changed': ip_changed
                }
                
                # Add IP verification to result
                result['ip_verification'] = {
                    'original_ip': original_ip,
                    'new_ip': new_ip,
                    'ip_changed': ip_changed,
                    'original_location': f"{original_country}, {original_city}",
                    'new_location': f"{new_country}, {new_city}"
                }
            else:
                # Store failed connection info
                self.active_connections[connection_id] = {
                    'provider': 'vyprvpn',
                    'server': server_hostname,
                    'connected_at': datetime.now().isoformat(),
                    'status': 'failed',
                    'original_ip': original_ip,
                    'original_country': original_country,
                    'original_city': original_city
                }
            
            return {
                'success': result['success'],
                'connection_id': connection_id,
                'server': server_hostname,
                'message': result['message'],
                'ip_verification': result.get('ip_verification', {})
            }
            
        except Exception as e:
            logger.error(f"VyprVPN connection failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def disconnect(self, connection_id: str) -> Dict[str, Any]:
        """Disconnect from VyprVPN"""
        try:
            logger.info(f"Disconnecting from {connection_id}")
            
            if connection_id not in self.active_connections:
                return {
                    'success': False,
                    'error': f'Connection {connection_id} not found'
                }
            
            # Get current IP before disconnecting
            connection_info = self.active_connections[connection_id]
            if connection_info.get('status') == 'connected':
                logger.info("Getting IP address before disconnection...")
                pre_disconnect_ip_info = await self.get_external_ip()
                if pre_disconnect_ip_info['success']:
                    pre_disconnect_ip = pre_disconnect_ip_info['ip']
                    logger.info(f"IP before disconnection: {pre_disconnect_ip}")
                else:
                    pre_disconnect_ip = "Unknown"
                    logger.warning(f"Failed to get IP before disconnection: {pre_disconnect_ip_info['error']}")
            else:
                pre_disconnect_ip = "Unknown"
            
            # Disconnect using VyprVPN CLI
            disconnect_cmd = ['vyprvpn', 'disconnect']
            result = subprocess.run(
                disconnect_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # Wait for disconnection to complete
                logger.info("Waiting for disconnection to complete...")
                await asyncio.sleep(3)
                
                # Get IP after disconnection
                logger.info("Getting IP address after disconnection...")
                post_disconnect_ip_info = await self.get_external_ip()
                if post_disconnect_ip_info['success']:
                    post_disconnect_ip = post_disconnect_ip_info['ip']
                    original_ip = connection_info.get('original_ip', 'Unknown')
                    
                    # Check if IP actually changed during disconnection
                    ip_changed_during_disconnect = (pre_disconnect_ip != post_disconnect_ip)
                    
                    # Check if IP returned to original (if we have it)
                    if original_ip != 'Unknown':
                        if post_disconnect_ip == original_ip:
                            logger.info("✅ IP address returned to original after disconnection")
                            ip_restored = True
                        else:
                            logger.warning(f"⚠️ IP address did not return to original: {post_disconnect_ip} vs {original_ip}")
                            ip_restored = False
                    else:
                        # We don't have original IP, just check if IP changed
                        if ip_changed_during_disconnect:
                            logger.info("✅ IP address changed during disconnection (original IP unknown)")
                            ip_restored = 'Unknown - IP changed'
                        else:
                            logger.warning("⚠️ IP address did not change during disconnection")
                            ip_restored = False
                    
                    # Update connection info with disconnection details
                    self.active_connections[connection_id].update({
                        'status': 'disconnected',
                        'disconnected_at': datetime.now().isoformat(),
                        'pre_disconnect_ip': pre_disconnect_ip,
                        'post_disconnect_ip': post_disconnect_ip,
                        'ip_changed_during_disconnect': ip_changed_during_disconnect,
                        'ip_restored': ip_restored
                    })
                    
                    return {
                        'success': True,
                        'connection_id': connection_id,
                        'message': 'Disconnected successfully',
                        'ip_verification': {
                            'pre_disconnect_ip': pre_disconnect_ip,
                            'post_disconnect_ip': post_disconnect_ip,
                            'original_ip': original_ip,
                            'ip_changed_during_disconnect': ip_changed_during_disconnect,
                            'ip_restored': ip_restored
                        }
                    }
                else:
                    logger.warning(f"Failed to get IP after disconnection: {post_disconnect_ip_info['error']}")
                    # Update connection info without IP verification
                    self.active_connections[connection_id].update({
                        'status': 'disconnected',
                        'disconnected_at': datetime.now().isoformat(),
                        'pre_disconnect_ip': pre_disconnect_ip,
                        'post_disconnect_ip': 'Unknown',
                        'ip_restored': 'Unknown'
                    })
                    
                    return {
                        'success': True,
                        'connection_id': connection_id,
                        'message': 'Disconnected successfully (IP verification failed)'
                    }
            else:
                return {
                    'success': False,
                    'error': f'Disconnect failed: {result.stderr}'
                }
            
        except Exception as e:
            logger.error(f"Disconnect failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def disconnect_all(self) -> Dict[str, Any]:
        """Disconnect from all VyprVPN connections"""
        try:
            logger.info("Disconnecting from all VyprVPN connections")
            
            results = []
            for connection_id in list(self.active_connections.keys()):
                result = await self.disconnect(connection_id)
                results.append(result)
            
            return {
                'success': True,
                'message': f'Disconnected from {len(results)} connections',
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Disconnect all failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_connection_status(self) -> Dict[str, Any]:
        """Get status of all VyprVPN connections"""
        try:
            # Check VyprVPN CLI status
            status_cmd = ['vyprvpn', 'status']
            result = subprocess.run(
                status_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                cli_status = result.stdout.strip()
            else:
                cli_status = "Unknown"
            
            return {
                'success': True,
                'active_connections': self.active_connections,
                'vyprvpn_cli_status': cli_status,
                'total_connections': len(self.active_connections)
            }
            
        except Exception as e:
            logger.error(f"Failed to get connection status: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_external_ip(self) -> Dict[str, Any]:
        """Get current external IP address"""
        try:
            # Try multiple IP checking services for reliability
            # Start with ifconfig.me since we know it works with VyprVPN
            ip_services = [
                'https://ifconfig.me',
                'https://httpbin.org/ip',
                'https://api.ipify.org?format=json',
                'https://ipinfo.io/json',
                'https://icanhazip.com'
            ]
            
            async with aiohttp.ClientSession() as session:
                for service_url in ip_services:
                    try:
                        async with session.get(service_url, timeout=10) as response:
                            if response.status == 200:
                                content = await response.text()
                                
                                # Parse different response formats
                                if 'ifconfig.me' in service_url:
                                    # Plain text IP
                                    ip = content.strip()
                                elif 'httpbin.org' in service_url:
                                    # {"origin": "1.2.3.4"}
                                    import json
                                    data = json.loads(content)
                                    ip = data.get('origin', '').split(',')[0].strip()
                                elif 'ipify.org' in service_url:
                                    # {"ip": "1.2.3.4"}
                                    import json
                                    data = json.loads(content)
                                    ip = data.get('ip', '').strip()
                                elif 'ipinfo.io' in service_url:
                                    # {"ip": "1.2.3.4", "country": "US", ...}
                                    import json
                                    data = json.loads(content)
                                    ip = data.get('ip', '').strip()
                                    country = data.get('country', '').strip()
                                    city = data.get('city', '').strip()
                                    return {
                                        'success': True,
                                        'ip': ip,
                                        'country': country,
                                        'city': city,
                                        'service': service_url
                                    }
                                else:
                                    # Plain text IP
                                    ip = content.strip()
                                
                                if ip and ip.replace('.', '').isdigit():
                                    return {
                                        'success': True,
                                        'ip': ip,
                                        'service': service_url
                                    }
                                    
                    except Exception as e:
                        logger.debug(f"IP service {service_url} failed: {e}")
                        continue
            
            return {
                'success': False,
                'error': 'All IP checking services failed'
            }
            
        except Exception as e:
            logger.error(f"Failed to get external IP: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def verify_vpn_connection(self, connection_id: str) -> Dict[str, Any]:
        """Verify that VPN connection is working by checking IP changes"""
        try:
            if connection_id not in self.active_connections:
                return {
                    'success': False,
                    'error': f'Connection {connection_id} not found'
                }
            
            connection_info = self.active_connections[connection_id]
            
            # Get current IP
            current_ip_info = await self.get_external_ip()
            if not current_ip_info['success']:
                return {
                    'success': False,
                    'error': f'Failed to get current IP: {current_ip_info["error"]}'
                }
            
            # Check if IP changed from original
            if 'original_ip' in connection_info:
                original_ip = connection_info['original_ip']
                current_ip = current_ip_info['ip']
                
                if original_ip == current_ip:
                    return {
                        'success': False,
                        'error': 'IP address did not change after VPN connection',
                        'original_ip': original_ip,
                        'current_ip': current_ip,
                        'ip_changed': False
                    }
                else:
                    return {
                        'success': True,
                        'message': 'VPN connection verified - IP address changed',
                        'original_ip': original_ip,
                        'current_ip': current_ip,
                        'ip_changed': True,
                        'country': current_ip_info.get('country'),
                        'city': current_ip_info.get('city')
                    }
            else:
                return {
                    'success': False,
                    'error': 'No original IP recorded for this connection'
                }
                
        except Exception as e:
            logger.error(f"VPN connection verification failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _select_vyprvpn_server(self, scraper, region: str = None, country: str = None):
        """Select appropriate VyprVPN server"""
        try:
            servers = scraper.get_all_servers()
            
            if not servers:
                # Try to update server list
                await scraper.update_server_list(force_update=True)
                servers = scraper.get_all_servers()
            
            if not servers:
                raise Exception("No VyprVPN servers available")
            
            # Filter by preferences
            if region:
                servers = [s for s in servers if s.region.lower() == region.lower()]
            elif country:
                servers = [s for s in servers if s.country.lower() == country.lower()]
            
            if not servers:
                # Fallback to any server
                servers = scraper.get_all_servers()
            
            # Prefer US servers for better performance
            us_servers = [s for s in servers if s.country == "U.S."]
            if us_servers:
                return us_servers[0]  # Return first US server
            
            return servers[0]  # Return first available server
            
        except Exception as e:
            logger.error(f"Failed to select VyprVPN server: {e}")
            return None
    
    async def _connect_vyprvpn_cli(self, connection_id: str, server_hostname: str, username: str, password: str) -> Dict[str, Any]:
        """Establish VyprVPN connection using the official CLI"""
        try:
            logger.info(f"Connecting to VyprVPN using CLI to {server_hostname}")
            
            # Check if VyprVPN CLI is installed
            try:
                subprocess.run(['vyprvpn', '--version'], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                return {
                    'success': False,
                    'error': 'VyprVPN CLI is not installed. Please install it first.'
                }
            
            # First, authenticate with VyprVPN
            auth_cmd = ['vyprvpn', 'login', '--username', username, '--password', password]
            auth_process = subprocess.run(
                auth_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if auth_process.returncode != 0:
                error_msg = auth_process.stderr if auth_process.stderr else "Authentication failed"
                return {
                    'success': False,
                    'error': f'VyprVPN authentication failed: {error_msg}'
                }
            
            logger.info("VyprVPN authentication successful")
            
            # Connect to the specified server
            connect_cmd = ['vyprvpn', 'connect', '--server', server_hostname]
            connect_process = subprocess.run(
                connect_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if connect_process.returncode != 0:
                error_msg = connect_process.stderr if connect_process.stderr else "Connection failed"
                return {
                    'success': False,
                    'error': f'VyprVPN connection failed: {error_msg}'
                }
            
            logger.info(f"VyprVPN connection established to {server_hostname}")
            return {
                'success': True,
                'message': f'Connected to VyprVPN server {server_hostname}'
            }
                
        except Exception as e:
            logger.error(f"VyprVPN CLI connection failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def cleanup(self):
        """Clean up and disconnect all connections"""
        try:
            # Disconnect all connections
            asyncio.run(self.disconnect_all())
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

# Global VPN connector instance
vpn_connector = VPNConnector()

def get_vpn_connector() -> VPNConnector:
    """Get the global VPN connector instance"""
    return vpn_connector
