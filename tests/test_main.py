"""
Test suite for the main Checklist Creator application
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

# Create test client
client = TestClient(app)

def test_root_endpoint():
    """Test the root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Checklist Creator API"
    assert data["version"] == "1.0.0"
    assert data["status"] == "healthy"

def test_health_endpoint():
    """Test the health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["version"] == "1.0.0"

def test_api_status_endpoint():
    """Test the API status endpoint"""
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert data["api"]["status"] == "running"
    assert data["api"]["version"] == "1.0.0"
    assert "docs_url" in data["api"]
    assert "health_url" in data["api"]

def test_vpn_status_endpoint():
    """Test the VPN status endpoint"""
    response = client.get("/api/v1/vpn/status")
    assert response.status_code == 200
    data = response.json()
    assert "vpn" in data
    assert "available_providers" in data
    assert isinstance(data["available_providers"], list)

def test_scraping_status_endpoint():
    """Test the scraping status endpoint"""
    response = client.get("/api/v1/scraping/status")
    assert response.status_code == 200
    data = response.json()
    assert "scraping" in data
    assert "targets" in data
    assert isinstance(data["targets"], list)
    assert "TCDB" in data["targets"]

def test_docs_endpoint():
    """Test that the docs endpoint is accessible"""
    response = client.get("/docs")
    assert response.status_code == 200

def test_redoc_endpoint():
    """Test that the redoc endpoint is accessible"""
    response = client.get("/redoc")
    assert response.status_code == 200

if __name__ == "__main__":
    pytest.main([__file__])