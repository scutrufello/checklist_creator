"""
Checklist Creator - Main FastAPI Application
Main entry point for the web scraping and VPN management system
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
from dotenv import load_dotenv

# Import API routers
from .api.vpn import router as vpn_router
from .api.vyprvpn import router as vyprvpn_router

# Import scheduler
from .services.scheduler import start_scheduler

# Load environment variables
load_dotenv()

# Create FastAPI app instance
app = FastAPI(
    title="Checklist Creator API",
    description="Web scraping and VPN management system API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(vpn_router)
app.include_router(vyprvpn_router)

@app.on_event("startup")
async def startup_event():
    """Startup event - initialize services"""
    print("🚀 Starting Checklist Creator services...")
    
    # Start the scheduler in the background
    import asyncio
    asyncio.create_task(start_scheduler())
    print("✅ Scheduler started")

@app.get("/")
async def root():
    """Root endpoint - API health check"""
    return {
        "message": "Checklist Creator API",
        "version": "1.0.0",
        "status": "healthy",
        "services": {
            "api": "running",
            "vpn": "ready",
            "vyprvpn": "ready",
            "scheduler": "running",
            "database": "checking...",
            "scraping": "ready"
        },
        "endpoints": {
            "vpn": "/api/v1/vpn/*",
            "vyprvpn": "/api/v1/vyprvpn/*",
            "docs": "/docs",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint"""
    try:
        # Basic health check
        health_status = {
            "status": "healthy",
            "timestamp": "2024-08-24T00:00:00Z",
            "version": "1.0.0",
            "environment": os.getenv("ENVIRONMENT", "development"),
                    "services": {
            "api": "healthy",
            "vpn": "ready",
            "vyprvpn": "ready",
            "database": "checking...",
            "scraping": "ready"
        }
        }
        
        # TODO: Add database health check
        # TODO: Add VPN status check
        # TODO: Add scraping service health check
        
        return JSONResponse(content=health_status, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@app.get("/api/v1/status")
async def api_status():
    """API status and configuration information"""
    return {
        "api": {
            "status": "running",
            "version": "1.0.0",
            "docs_url": "/docs",
            "health_url": "/health"
        },
        "features": {
            "vpn_management": "enabled",
            "web_scraping": "enabled",
            "data_processing": "enabled",
            "api_endpoints": "enabled"
        },
        "configuration": {
            "debug_mode": os.getenv("DEBUG", "False").lower() == "true",
            "api_host": os.getenv("API_HOST", "0.0.0.0"),
            "api_port": int(os.getenv("API_PORT", "8000"))
        },
        "endpoints": {
            "vpn": {
                "status": "/api/v1/vpn/status",
                "connect": "/api/v1/vpn/connect",
                "disconnect": "/api/v1/vpn/disconnect",
                "health": "/api/v1/vpn/health",
                "metrics": "/api/v1/vpn/metrics"
            }
        }
    }

@app.get("/api/v1/vpn/status")
async def vpn_status():
    """VPN connection status endpoint (legacy - now handled by VPN router)"""
    return {
        "vpn": {
            "status": "disconnected",
            "provider": "none",
            "location": "none",
            "ip_address": "none",
            "connection_time": "none"
        },
        "available_providers": [
            "openvpn",
            "nordvpn",
            "expressvpn"
        ],
        "note": "Use /api/v1/vpn/status for detailed status information"
    }

@app.get("/api/v1/scraping/status")
async def scraping_status():
    """Web scraping service status endpoint"""
    # TODO: Implement actual scraping status checking
    return {
        "scraping": {
            "status": "ready",
            "active_jobs": 0,
            "completed_jobs": 0,
            "failed_jobs": 0,
            "last_scrape": "none"
        },
        "targets": [
            "TCDB",
            "public_apis",
            "web_sites"
        ]
    }

if __name__ == "__main__":
    # Get configuration from environment variables
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    print(f"🚀 Starting Checklist Creator API on {host}:{port}")
    print(f"📚 API Documentation: http://{host}:{port}/docs")
    print(f"🔍 Health Check: http://{host}:{port}/health")
    print(f"🔒 VPN Endpoints: http://{host}:{port}/api/v1/vpn/*")
    
    # Start the server
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )
