"""
VPN Manager - Core VPN connection and management system
Handles multiple VPN providers, connection management, and health monitoring
"""

import asyncio
import logging
import subprocess
import time
import json
import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import aiohttp
import psutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VPNStatus(Enum):
    """VPN connection status enumeration"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"
    RECONNECTING = "reconnecting"

class VPNProvider(Enum):
    """Supported VPN providers"""
    NORDVPN = "nordvpn"
    EXPRESSVPN = "expressvpn"
    OPENVPN = "openvpn"
    WIREGUARD = "wireguard"

@dataclass
class VPNConnection:
    """VPN connection information"""
    provider: VPNProvider
    status: VPNStatus
    location: str
    ip_address: str
    connection_time: Optional[float]
    speed: Optional[float]
    ping: Optional[float]
    server: str
    protocol: str

@dataclass
class VPNProviderConfig:
    """VPN provider configuration"""
    name: VPNProvider
    config_path: str
    credentials_path: str
    servers: List[str]
    locations: List[str]
    max_connections: int
    health_check_url: str
    timeout: int

class VPNManager:
    """
    Main VPN management class
    Handles multiple VPN providers, connection management, and health monitoring
    """
    
    def __init__(self, config_path: str = "config/vpn_config.json"):
        self.config_path = config_path
        self.current_connection: Optional[VPNConnection] = None
        self.providers: Dict[VPNProvider, VPNProviderConfig] = {}
        self.connection_history: List[VPNConnection] = []
        self.health_check_interval = 30  # seconds
        self.max_reconnect_attempts = 3
        self.is_health_monitoring = False
        
        # Store original IP address for comparison
        self.original_ip_address: Optional[str] = None
        
        # Load configuration
        self._load_config()
        
        # Initialize providers
        self._initialize_providers()
        
        # Store original IP address on initialization
        asyncio.create_task(self._store_original_ip())
    
    def _load_config(self) -> None:
        """Load VPN configuration from file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config_data = json.load(f)
                    self._parse_config(config_data)
            else:
                logger.warning(f"VPN config file not found: {self.config_path}")
                self._create_default_config()
        except Exception as e:
            logger.error(f"Error loading VPN config: {e}")
            self._create_default_config()
    
    def _create_default_config(self) -> None:
        """Create default VPN configuration"""
        default_config = {
            "providers": {
                "openvpn": {
                    "name": "openvpn",
                    "config_path": "/etc/openvpn",
                    "credentials_path": "/etc/openvpn/auth.txt",
                    "servers": ["us-east", "us-west", "eu-west", "asia-east"],
                    "locations": ["United States", "Europe", "Asia"],
                    "max_connections": 1,
                    "health_check_url": "https://httpbin.org/ip",
                    "timeout": 30
                }
            },
            "health_check_interval": 30,
            "max_reconnect_attempts": 3
        }
        
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        self._parse_config(default_config)
    
    def _parse_config(self, config_data: dict) -> None:
        """Parse configuration data"""
        self.health_check_interval = config_data.get("health_check_interval", 30)
        self.max_reconnect_attempts = config_data.get("max_reconnect_attempts", 3)
        
        for provider_name, provider_data in config_data.get("providers", {}).items():
            try:
                provider = VPNProvider(provider_name)
                self.providers[provider] = VPNProviderConfig(
                    name=provider,
                    config_path=provider_data["config_path"],
                    credentials_path=provider_data["credentials_path"],
                    servers=provider_data["servers"],
                    locations=provider_data["locations"],
                    max_connections=provider_data["max_connections"],
                    health_check_url=provider_data["health_check_url"],
                    timeout=provider_data["timeout"]
                )
            except Exception as e:
                logger.error(f"Error parsing provider config for {provider_name}: {e}")
    
    def _initialize_providers(self) -> None:
        """Initialize VPN providers and check availability"""
        for provider, config in self.providers.items():
            try:
                if self._check_provider_availability(provider):
                    logger.info(f"Provider {provider.value} initialized successfully")
                else:
                    logger.warning(f"Provider {provider.value} not available")
            except Exception as e:
                logger.error(f"Error initializing provider {provider.value}: {e}")
    
    def _check_provider_availability(self, provider: VPNProvider) -> bool:
        """Check if a VPN provider is available and properly configured"""
        try:
            config = self.providers[provider]
            
            # Check if config directory exists
            if not os.path.exists(config.config_path):
                return False
            
            # Check if credentials file exists
            if not os.path.exists(config.credentials_path):
                return False
            
            # Check if OpenVPN is installed (for OpenVPN provider)
            if provider == VPNProvider.OPENVPN:
                result = subprocess.run(["which", "openvpn"], 
                                      capture_output=True, text=True)
                return result.returncode == 0
            
            return True
        except Exception as e:
            logger.error(f"Error checking provider availability: {e}")
            return False
    
    async def connect(self, provider: VPNProvider, location: str = None, 
                     server: str = None) -> bool:
        """
        Connect to VPN using specified provider and location/server
        
        Args:
            provider: VPN provider to use
            location: Preferred location (optional)
            server: Preferred server (optional)
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            if provider not in self.providers:
                logger.error(f"Provider {provider.value} not configured")
                return False
            
            if self.current_connection and self.current_connection.status == VPNStatus.CONNECTED:
                logger.info("Disconnecting from current VPN before connecting to new one")
                await self.disconnect()
            
            # Update connection status
            self.current_connection = VPNConnection(
                provider=provider,
                status=VPNStatus.CONNECTING,
                location=location or "auto",
                ip_address="",
                connection_time=None,
                speed=None,
                ping=None,
                server=server or "auto",
                protocol="openvpn"
            )
            
            logger.info(f"Connecting to {provider.value} VPN...")
            
            # Start connection process
            success = await self._establish_connection(provider, location, server)
            
            if success:
                self.current_connection.status = VPNStatus.CONNECTED
                self.current_connection.connection_time = time.time()
                self.current_connection.ip_address = await self._get_current_ip()
                
                # Add to connection history
                self.connection_history.append(self.current_connection)
                
                logger.info(f"Successfully connected to {provider.value} VPN")
                logger.info(f"IP Address: {self.current_connection.ip_address}")
                
                # Start health monitoring
                if not self.is_health_monitoring:
                    asyncio.create_task(self._start_health_monitoring())
                
                return True
            else:
                self.current_connection.status = VPNStatus.FAILED
                logger.error(f"Failed to connect to {provider.value} VPN")
                return False
                
        except Exception as e:
            logger.error(f"Error during VPN connection: {e}")
            if self.current_connection:
                self.current_connection.status = VPNStatus.FAILED
            return False
    
    async def _establish_connection(self, provider: VPNProvider, 
                                  location: str = None, server: str = None) -> bool:
        """Establish VPN connection using the specified provider"""
        try:
            if provider == VPNProvider.OPENVPN:
                return await self._connect_openvpn(location, server)
            elif provider == VPNProvider.NORDVPN:
                return await self._connect_nordvpn(location, server)
            elif provider == VPNProvider.EXPRESSVPN:
                return await self._connect_expressvpn(location, server)
            else:
                logger.error(f"Unsupported provider: {provider.value}")
                return False
        except Exception as e:
            logger.error(f"Error establishing connection: {e}")
            return False
    
    async def _connect_openvpn(self, location: str = None, server: str = None) -> bool:
        """Connect using OpenVPN"""
        try:
            config = self.providers[VPNProvider.OPENVPN]
            
            # Select configuration file
            config_file = self._select_openvpn_config(location, server)
            if not config_file:
                logger.error("No suitable OpenVPN configuration found")
                return False
            
            # Start OpenVPN process
            cmd = [
                "sudo", "openvpn",
                "--config", config_file,
                "--auth-user-pass", config.credentials_path,
                "--daemon"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Wait a bit for connection to establish
                await asyncio.sleep(5)
                
                # Verify connection
                if await self._verify_connection():
                    return True
                else:
                    logger.error("OpenVPN connection verification failed")
                    return False
            else:
                logger.error(f"OpenVPN connection failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error in OpenVPN connection: {e}")
            return False
    
    def _select_openvpn_config(self, location: str = None, server: str = None) -> Optional[str]:
        """Select appropriate OpenVPN configuration file"""
        try:
            config_dir = self.providers[VPNProvider.OPENVPN].config_path
            
            # Look for .ovpn files
            ovpn_files = [f for f in os.listdir(config_dir) if f.endswith('.ovpn')]
            
            if not ovpn_files:
                return None
            
            # If specific server requested, try to find it
            if server and server != "auto":
                for file in ovpn_files:
                    if server.lower() in file.lower():
                        return os.path.join(config_dir, file)
            
            # If specific location requested, try to find it
            if location and location != "auto":
                for file in ovpn_files:
                    if location.lower() in file.lower():
                        return os.path.join(config_dir, file)
            
            # Return first available config file
            return os.path.join(config_dir, ovpn_files[0])
            
        except Exception as e:
            logger.error(f"Error selecting OpenVPN config: {e}")
            return None
    
    async def _connect_nordvpn(self, location: str = None, server: str = None) -> bool:
        """Connect using NordVPN (placeholder for future implementation)"""
        logger.info("NordVPN integration not yet implemented")
        return False
    
    async def _connect_expressvpn(self, location: str = None, server: str = None) -> bool:
        """Connect using ExpressVPN (placeholder for future implementation)"""
        logger.info("ExpressVPN integration not yet implemented")
        return False
    
    async def disconnect(self) -> bool:
        """Disconnect from current VPN connection"""
        try:
            if not self.current_connection:
                logger.info("No active VPN connection to disconnect")
                return True
            
            logger.info(f"Disconnecting from {self.current_connection.provider.value} VPN...")
            
            # Stop OpenVPN processes
            if self.current_connection.provider == VPNProvider.OPENVPN:
                success = await self._disconnect_openvpn()
            else:
                success = True
            
            if success:
                # Update connection status
                if self.current_connection:
                    self.current_connection.status = VPNStatus.DISCONNECTED
                    self.current_connection.connection_time = None
                
                # Stop health monitoring
                self.is_health_monitoring = False
                
                logger.info("VPN disconnected successfully")
                return True
            else:
                logger.error("Failed to disconnect VPN")
                return False
                
        except Exception as e:
            logger.error(f"Error during VPN disconnection: {e}")
            return False
    
    async def _disconnect_openvpn(self) -> bool:
        """Disconnect OpenVPN connection"""
        try:
            # Kill all OpenVPN processes
            cmd = ["sudo", "pkill", "-f", "openvpn"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Wait for processes to terminate
            await asyncio.sleep(2)
            
            return True
        except Exception as e:
            logger.error(f"Error disconnecting OpenVPN: {e}")
            return False
    
    async def _verify_connection(self) -> bool:
        """Verify that VPN connection is working"""
        try:
            # Check if OpenVPN process is running
            cmd = ["pgrep", "-f", "openvpn"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                return False
            
            # Check if we can get external IP
            ip = await self._get_current_ip()
            if not ip:
                return False
            
            # Check if IP is different from original (basic VPN check)
            original_ip = await self._get_original_ip()
            if ip == original_ip:
                logger.warning("IP address unchanged after VPN connection")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error verifying connection: {e}")
            return False
    
    async def _get_current_ip(self) -> Optional[str]:
        """Get current public IP address"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://httpbin.org/ip", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("origin", "").split(",")[0].strip()
            return None
        except Exception as e:
            logger.error(f"Error getting current IP: {e}")
            return None
    
    async def _get_original_ip(self) -> Optional[str]:
        """Get original public IP address (before VPN)"""
        # Return the stored original IP address
        if self.original_ip_address:
            return self.original_ip_address
        
        # Fallback: try to get current IP if original not stored
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://httpbin.org/ip", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("origin", "").split(",")[0].strip()
            return None
        except Exception as e:
            logger.error(f"Error getting original IP: {e}")
            return None
    
    async def _store_original_ip(self) -> None:
        """Store the original IP address when the VPN manager is initialized"""
        try:
            self.original_ip_address = await self._get_current_ip()
            if self.original_ip_address:
                logger.info(f"Original IP address stored: {self.original_ip_address}")
            else:
                logger.warning("Failed to store original IP address")
        except Exception as e:
            logger.error(f"Error storing original IP address: {e}")
    
    async def _start_health_monitoring(self) -> None:
        """Start VPN health monitoring"""
        self.is_health_monitoring = True
        
        while self.is_health_monitoring:
            try:
                if self.current_connection and self.current_connection.status == VPNStatus.CONNECTED:
                    # Check connection health
                    health_status = await self._check_connection_health()
                    
                    if not health_status:
                        logger.warning("VPN connection health check failed")
                        await self._handle_connection_failure()
                    
                    # Update connection metrics
                    await self._update_connection_metrics()
                
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error(f"Error in health monitoring: {e}")
                await asyncio.sleep(self.health_check_interval)
    
    async def _check_connection_health(self) -> bool:
        """Check the health of the current VPN connection"""
        try:
            # Check if OpenVPN process is still running
            cmd = ["pgrep", "-f", "openvpn"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                return False
            
            # Check if we can still reach external services
            ip = await self._get_current_ip()
            if not ip:
                return False
            
            # Check ping to a reliable host
            ping_result = await self._ping_test("8.8.8.8")
            if ping_result < 0:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking connection health: {e}")
            return False
    
    async def _ping_test(self, host: str) -> float:
        """Test ping to a host"""
        try:
            cmd = ["ping", "-c", "1", "-W", "5", host]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Extract ping time from output
                for line in result.stdout.split('\n'):
                    if 'time=' in line:
                        time_str = line.split('time=')[1].split()[0]
                        return float(time_str)
            
            return -1
        except Exception as e:
            logger.error(f"Error in ping test: {e}")
            return -1
    
    async def _handle_connection_failure(self) -> None:
        """Handle VPN connection failure"""
        try:
            logger.warning("VPN connection failure detected, attempting reconnection...")
            
            if self.current_connection:
                provider = self.current_connection.provider
                location = self.current_connection.location
                server = self.current_connection.server
                
                # Attempt reconnection
                success = await self.connect(provider, location, server)
                
                if not success:
                    logger.error("VPN reconnection failed")
                    self.current_connection.status = VPNStatus.FAILED
                    
        except Exception as e:
            logger.error(f"Error handling connection failure: {e}")
    
    async def _update_connection_metrics(self) -> None:
        """Update connection performance metrics"""
        try:
            if not self.current_connection:
                return
            
            # Update ping
            ping_result = await self._ping_test("8.8.8.8")
            if ping_result > 0:
                self.current_connection.ping = ping_result
            
            # Update speed (basic test)
            speed_result = await self._test_connection_speed()
            if speed_result > 0:
                self.current_connection.speed = speed_result
                
        except Exception as e:
            logger.error(f"Error updating connection metrics: {e}")
    
    async def _test_connection_speed(self) -> float:
        """Test connection speed (basic implementation)"""
        try:
            # This is a simplified speed test
            # In production, you might want to use a proper speed testing service
            start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                async with session.get("https://httpbin.org/bytes/1024", timeout=10) as response:
                    if response.status == 200:
                        await response.read()
                        end_time = time.time()
                        duration = end_time - start_time
                        # Calculate speed in Mbps (1024 bytes = 8.192 kbps)
                        speed = (8.192 / duration) / 1000  # Convert to Mbps
                        return speed
            
            return -1
        except Exception as e:
            logger.error(f"Error testing connection speed: {e}")
            return -1
    
    def get_status(self) -> Dict:
        """Get current VPN status and information"""
        status = {
            "status": VPNStatus.DISCONNECTED.value,
            "provider": None,
            "location": None,
            "ip_address": None,
            "connection_time": None,
            "speed": None,
            "ping": None,
            "server": None,
            "protocol": None,
            "available_providers": [p.value for p in self.providers.keys()],
            "connection_history": len(self.connection_history)
        }
        
        if self.current_connection:
            status.update({
                "status": self.current_connection.status.value,
                "provider": self.current_connection.provider.value,
                "location": self.current_connection.location,
                "ip_address": self.current_connection.ip_address,
                "connection_time": self.current_connection.connection_time,
                "speed": self.current_connection.speed,
                "ping": self.current_connection.ping,
                "server": self.current_connection.server,
                "protocol": self.current_connection.protocol
            })
        
        return status
    
    def get_connection_history(self) -> List[Dict]:
        """Get VPN connection history"""
        return [
            {
                "provider": conn.provider.value,
                "status": conn.status.value,
                "location": conn.location,
                "ip_address": conn.ip_address,
                "connection_time": conn.connection_time,
                "server": conn.server,
                "protocol": conn.protocol
            }
            for conn in self.connection_history
        ]
    
    def get_original_ip(self) -> Optional[str]:
        """Get the stored original IP address"""
        return self.original_ip_address
    
    def get_ip_comparison(self) -> Dict[str, Any]:
        """Get IP address comparison information"""
        comparison = {
            "original_ip": self.original_ip_address,
            "current_ip": None,
            "ip_changed": False,
            "vpn_active": False
        }
        
        if self.current_connection and self.current_connection.ip_address:
            comparison["current_ip"] = self.current_connection.ip_address
            comparison["ip_changed"] = (
                self.original_ip_address != self.current_connection.ip_address
            )
            comparison["vpn_active"] = (
                self.current_connection.status == VPNStatus.CONNECTED
            )
        
        return comparison
    
    async def cleanup(self) -> None:
        """Cleanup VPN manager resources"""
        try:
            if self.current_connection and self.current_connection.status == VPNStatus.CONNECTED:
                await self.disconnect()
            
            self.is_health_monitoring = False
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
