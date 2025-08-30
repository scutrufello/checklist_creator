"""
VPN Data Schemas
Pydantic models for VPN-related data structures and API requests/responses
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class VPNConnectRequest(BaseModel):
    """VPN connection request model"""
    provider: str = Field(..., description="VPN provider to use (e.g., 'openvpn', 'nordvpn')")
    location: Optional[str] = Field(None, description="Preferred location for connection")
    server: Optional[str] = Field(None, description="Preferred server for connection")
    
    class Config:
        schema_extra = {
            "example": {
                "provider": "openvpn",
                "location": "United States",
                "server": "us-east"
            }
        }

class VPNConnectResponse(BaseModel):
    """VPN connection response model"""
    success: bool = Field(..., description="Whether the connection request was successful")
    message: str = Field(..., description="Response message")
    connection_id: Optional[int] = Field(None, description="Unique connection identifier")
    status: str = Field(..., description="Current connection status")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Connecting to openvpn VPN...",
                "connection_id": 12345,
                "status": "connecting"
            }
        }

class VPNStatusResponse(BaseModel):
    """VPN status response model"""
    status: str = Field(..., description="Current VPN connection status")
    provider: Optional[str] = Field(None, description="Current VPN provider")
    location: Optional[str] = Field(None, description="Current connection location")
    ip_address: Optional[str] = Field(None, description="Current public IP address")
    connection_time: Optional[float] = Field(None, description="Connection timestamp")
    speed: Optional[float] = Field(None, description="Connection speed in Mbps")
    ping: Optional[float] = Field(None, description="Ping time in milliseconds")
    server: Optional[str] = Field(None, description="Current server")
    protocol: Optional[str] = Field(None, description="VPN protocol being used")
    available_providers: List[str] = Field(..., description="List of available VPN providers")
    connection_history: int = Field(..., description="Number of previous connections")
    
    class Config:
        schema_extra = {
            "example": {
                "status": "connected",
                "provider": "openvpn",
                "location": "United States",
                "ip_address": "203.0.113.1",
                "connection_time": 1640995200.0,
                "speed": 50.5,
                "ping": 25.3,
                "server": "us-east",
                "protocol": "openvpn",
                "available_providers": ["openvpn", "nordvpn"],
                "connection_history": 5
            }
        }

class VPNConnectionHistory(BaseModel):
    """VPN connection history model"""
    connections: List[Dict[str, Any]] = Field(..., description="List of previous connections")
    
    class Config:
        schema_extra = {
            "example": {
                "connections": [
                    {
                        "provider": "openvpn",
                        "status": "disconnected",
                        "location": "United States",
                        "ip_address": "203.0.113.1",
                        "connection_time": 1640995200.0,
                        "server": "us-east",
                        "protocol": "openvpn"
                    }
                ]
            }
        }

class VPNProviderInfo(BaseModel):
    """VPN provider information model"""
    name: str = Field(..., description="Provider name")
    config_path: str = Field(..., description="Configuration file path")
    servers: List[str] = Field(..., description="Available servers")
    locations: List[str] = Field(..., description="Available locations")
    max_connections: int = Field(..., description="Maximum concurrent connections")
    health_check_url: str = Field(..., description="Health check endpoint URL")
    timeout: int = Field(..., description="Connection timeout in seconds")
    
    class Config:
        schema_extra = {
            "example": {
                "name": "openvpn",
                "config_path": "/etc/openvpn",
                "servers": ["us-east", "us-west", "eu-west"],
                "locations": ["United States", "Europe"],
                "max_connections": 1,
                "health_check_url": "https://httpbin.org/ip",
                "timeout": 30
            }
        }

class VPNHealthCheck(BaseModel):
    """VPN health check model"""
    is_healthy: bool = Field(..., description="Whether the VPN connection is healthy")
    status: str = Field(..., description="Current connection status")
    message: str = Field(..., description="Health status message")
    ping: Optional[float] = Field(None, description="Current ping time in milliseconds")
    speed: Optional[float] = Field(None, description="Current connection speed in Mbps")
    uptime: Optional[float] = Field(None, description="Connection uptime in seconds")
    
    class Config:
        schema_extra = {
            "example": {
                "is_healthy": True,
                "status": "connected",
                "message": "VPN connection is healthy",
                "ping": 25.3,
                "speed": 50.5,
                "uptime": 3600.0
            }
        }

class VPNMetrics(BaseModel):
    """VPN performance metrics model"""
    provider: str = Field(..., description="VPN provider")
    location: str = Field(..., description="Connection location")
    server: str = Field(..., description="Server being used")
    protocol: str = Field(..., description="VPN protocol")
    uptime_seconds: Optional[float] = Field(None, description="Connection uptime in seconds")
    ping_ms: Optional[float] = Field(None, description="Ping time in milliseconds")
    speed_mbps: Optional[float] = Field(None, description="Connection speed in Mbps")
    ip_address: Optional[str] = Field(None, description="Current public IP address")
    status: str = Field(..., description="Current connection status")
    
    class Config:
        schema_extra = {
            "example": {
                "provider": "openvpn",
                "location": "United States",
                "server": "us-east",
                "protocol": "openvpn",
                "uptime_seconds": 3600.0,
                "ping_ms": 25.3,
                "speed_mbps": 50.5,
                "ip_address": "203.0.113.1",
                "status": "connected"
            }
        }

class VPNLocation(BaseModel):
    """VPN location model"""
    name: str = Field(..., description="Location name")
    country: str = Field(..., description="Country name")
    city: Optional[str] = Field(None, description="City name")
    servers: List[str] = Field(..., description="Available servers in this location")
    ping: Optional[float] = Field(None, description="Average ping time to this location")
    
    class Config:
        schema_extra = {
            "example": {
                "name": "United States",
                "country": "US",
                "city": "New York",
                "servers": ["us-east", "us-nyc"],
                "ping": 25.3
            }
        }

class VPNServer(BaseModel):
    """VPN server model"""
    name: str = Field(..., description="Server name")
    location: str = Field(..., description="Server location")
    ip_address: str = Field(..., description="Server IP address")
    port: int = Field(..., description="Server port")
    protocol: str = Field(..., description="VPN protocol")
    load: Optional[float] = Field(None, description="Server load percentage")
    ping: Optional[float] = Field(None, description="Ping time to server")
    
    class Config:
        schema_extra = {
            "example": {
                "name": "us-east",
                "location": "United States",
                "ip_address": "203.0.113.1",
                "port": 1194,
                "protocol": "openvpn",
                "load": 45.2,
                "ping": 25.3
            }
        }

class VPNConnectionStats(BaseModel):
    """VPN connection statistics model"""
    total_connections: int = Field(..., description="Total number of connections made")
    successful_connections: int = Field(..., description="Number of successful connections")
    failed_connections: int = Field(..., description="Number of failed connections")
    total_uptime: float = Field(..., description="Total connection uptime in seconds")
    average_ping: Optional[float] = Field(None, description="Average ping time")
    average_speed: Optional[float] = Field(None, description="Average connection speed")
    last_connection: Optional[datetime] = Field(None, description="Timestamp of last connection")
    
    class Config:
        schema_extra = {
            "example": {
                "total_connections": 25,
                "successful_connections": 23,
                "failed_connections": 2,
                "total_uptime": 86400.0,
                "average_ping": 28.5,
                "average_speed": 45.2,
                "last_connection": "2024-08-24T12:00:00Z"
            }
        }
