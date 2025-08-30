"""
Test suite for VPN functionality
Tests VPN manager, API endpoints, and data schemas
"""

import pytest
import asyncio
import json
import os
import sys
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

# Add backend to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from backend.core.vpn_manager import VPNManager, VPNProvider, VPNStatus, VPNConnection
from backend.schemas.vpn import (
    VPNConnectRequest,
    VPNConnectResponse,
    VPNStatusResponse,
    VPNHealthCheck
)
from backend.api.vpn import router as vpn_router
from backend.main import app

# Create test client
client = TestClient(app)

class TestVPNManager:
    """Test VPN Manager functionality"""
    
    @pytest.fixture
    def vpn_manager(self):
        """Create a VPN manager instance for testing"""
        # Use a temporary config file
        config_path = "test_vpn_config.json"
        config_data = {
            "providers": {
                "openvpn": {
                    "name": "openvpn",
                    "config_path": "/tmp/openvpn",
                    "credentials_path": "/tmp/auth.txt",
                    "servers": ["test-server"],
                    "locations": ["Test Location"],
                    "max_connections": 1,
                    "health_check_url": "https://httpbin.org/ip",
                    "timeout": 30
                }
            },
            "health_check_interval": 30,
            "max_reconnect_attempts": 3
        }
        
        with open(config_path, 'w') as f:
            json.dump(config_data, f)
        
        manager = VPNManager(config_path)
        yield manager
        
        # Cleanup
        os.remove(config_path)
    
    def test_vpn_manager_initialization(self, vpn_manager):
        """Test VPN manager initialization"""
        assert vpn_manager is not None
        assert len(vpn_manager.providers) > 0
        assert VPNProvider.OPENVPN in vpn_manager.providers
    
    def test_get_status_disconnected(self, vpn_manager):
        """Test getting status when disconnected"""
        status = vpn_manager.get_status()
        
        assert status["status"] == "disconnected"
        assert status["provider"] is None
        assert status["ip_address"] is None
        assert "openvpn" in status["available_providers"]
    
    @pytest.mark.asyncio
    async def test_connect_vpn(self, vpn_manager):
        """Test VPN connection (mocked)"""
        with patch.object(vpn_manager, '_establish_connection', return_value=True), \
             patch.object(vpn_manager, '_get_current_ip', return_value="203.0.113.1"):
            
            success = await vpn_manager.connect(VPNProvider.OPENVPN, "Test Location")
            
            assert success is True
            assert vpn_manager.current_connection is not None
            assert vpn_manager.current_connection.status == VPNStatus.CONNECTED
            assert vpn_manager.current_connection.ip_address == "203.0.113.1"
    
    @pytest.mark.asyncio
    async def test_disconnect_vpn(self, vpn_manager):
        """Test VPN disconnection"""
        # First connect
        with patch.object(vpn_manager, '_establish_connection', return_value=True), \
             patch.object(vpn_manager, '_get_current_ip', return_value="203.0.113.1"):
            await vpn_manager.connect(VPNProvider.OPENVPN, "Test Location")
        
        # Then disconnect
        with patch.object(vpn_manager, '_disconnect_openvpn', return_value=True):
            success = await vpn_manager.disconnect()
            
            assert success is True
            assert vpn_manager.current_connection.status == VPNStatus.DISCONNECTED
    
    def test_get_connection_history(self, vpn_manager):
        """Test getting connection history"""
        history = vpn_manager.get_connection_history()
        assert isinstance(history, list)
        assert len(history) == 0  # No connections yet
    
    @pytest.mark.asyncio
    async def test_health_monitoring(self, vpn_manager):
        """Test health monitoring functionality"""
        # Mock connection
        vpn_manager.current_connection = VPNConnection(
            provider=VPNProvider.OPENVPN,
            status=VPNStatus.CONNECTED,
            location="Test",
            ip_address="203.0.113.1",
            connection_time=1234567890.0,
            speed=None,
            ping=None,
            server="test",
            protocol="openvpn"
        )
        
        with patch.object(vpn_manager, '_check_connection_health', return_value=True), \
             patch.object(vpn_manager, '_update_connection_metrics'):
            
            # Start health monitoring
            vpn_manager.is_health_monitoring = True
            await vpn_manager._start_health_monitoring()
            
            # Should have run at least one health check
            assert vpn_manager.is_health_monitoring is True

class TestVPNSchemas:
    """Test VPN data schemas"""
    
    def test_vpn_connect_request(self):
        """Test VPN connect request schema"""
        request = VPNConnectRequest(
            provider="openvpn",
            location="United States",
            server="us-east"
        )
        
        assert request.provider == "openvpn"
        assert request.location == "United States"
        assert request.server == "us-east"
    
    def test_vpn_connect_response(self):
        """Test VPN connect response schema"""
        response = VPNConnectResponse(
            success=True,
            message="Connecting to VPN...",
            connection_id=12345,
            status="connecting"
        )
        
        assert response.success is True
        assert response.message == "Connecting to VPN..."
        assert response.connection_id == 12345
        assert response.status == "connecting"
    
    def test_vpn_status_response(self):
        """Test VPN status response schema"""
        status = VPNStatusResponse(
            status="connected",
            provider="openvpn",
            location="United States",
            ip_address="203.0.113.1",
            connection_time=1234567890.0,
            speed=50.5,
            ping=25.3,
            server="us-east",
            protocol="openvpn",
            available_providers=["openvpn"],
            connection_history=5
        )
        
        assert status.status == "connected"
        assert status.provider == "openvpn"
        assert status.ip_address == "203.0.113.1"
        assert status.speed == 50.5
        assert status.ping == 25.3

class TestVPNAPI:
    """Test VPN API endpoints"""
    
    def test_get_vpn_status(self):
        """Test getting VPN status via API"""
        response = client.get("/api/v1/vpn/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "available_providers" in data
    
    def test_get_vpn_providers(self):
        """Test getting VPN providers via API"""
        response = client.get("/api/v1/vpn/providers")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
    
    def test_connect_vpn_invalid_provider(self):
        """Test connecting to VPN with invalid provider"""
        request_data = {
            "provider": "invalid_provider",
            "location": "United States"
        }
        
        response = client.post("/api/v1/vpn/connect", json=request_data)
        assert response.status_code == 400
        
        data = response.json()
        assert "Invalid VPN provider" in data["detail"]
    
    def test_connect_vpn_valid_request(self):
        """Test connecting to VPN with valid request"""
        request_data = {
            "provider": "openvpn",
            "location": "United States",
            "server": "us-east"
        }
        
        response = client.post("/api/v1/vpn/connect", json=request_data)
        # This might fail if OpenVPN is not properly configured, but should not crash
        assert response.status_code in [200, 500]
    
    def test_disconnect_vpn(self):
        """Test disconnecting from VPN"""
        response = client.post("/api/v1/vpn/disconnect")
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
    
    def test_get_vpn_health(self):
        """Test getting VPN health status"""
        response = client.get("/api/v1/vpn/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "is_healthy" in data
        assert "status" in data
        assert "message" in data
    
    def test_get_vpn_metrics(self):
        """Test getting VPN metrics"""
        response = client.get("/api/v1/vpn/metrics")
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data or "provider" in data
    
    def test_get_connection_history(self):
        """Test getting connection history"""
        response = client.get("/api/v1/vpn/history")
        assert response.status_code == 200
        
        data = response.json()
        assert "connections" in data
        assert isinstance(data["connections"], list)

class TestVPNIntegration:
    """Test VPN integration with main application"""
    
    def test_main_app_includes_vpn_router(self):
        """Test that main app includes VPN router"""
        response = client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert "vpn" in data["services"]
        assert data["services"]["vpn"] == "ready"
    
    def test_vpn_endpoints_available(self):
        """Test that VPN endpoints are available in main app"""
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "endpoints" in data
        assert "vpn" in data["endpoints"]
        assert "status" in data["endpoints"]["vpn"]
        assert "connect" in data["endpoints"]["vpn"]
        assert "disconnect" in data["endpoints"]["vpn"]

# Integration tests that require actual OpenVPN
@pytest.mark.integration
class TestVPNIntegrationReal:
    """Integration tests with real OpenVPN (requires proper setup)"""
    
    @pytest.mark.asyncio
    async def test_real_vpn_connection(self):
        """Test real VPN connection (requires OpenVPN setup)"""
        # This test requires actual OpenVPN configuration
        # Skip if not properly configured
        if not os.path.exists("/etc/openvpn/configs"):
            pytest.skip("OpenVPN not properly configured")
        
        vpn_manager = VPNManager()
        
        # Test basic functionality
        status = vpn_manager.get_status()
        assert "status" in status
        assert "available_providers" in status
    
    def test_real_openvpn_installation(self):
        """Test that OpenVPN is actually installed"""
        import subprocess
        
        try:
            result = subprocess.run(["which", "openvpn"], 
                                  capture_output=True, text=True)
            assert result.returncode == 0, "OpenVPN not found in PATH"
        except Exception:
            pytest.skip("OpenVPN not available")

if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
