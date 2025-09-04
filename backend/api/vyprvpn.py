#!/usr/bin/env python3
"""
VyprVPN API endpoints for Checklist Creator
Provides endpoints for managing VyprVPN server information and updates
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime
import logging

# Import our services
from ..services.vyprvpn_scraper import VyprVPNServerScraper
from ..services.scheduler import get_scheduler

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/vyprvpn", tags=["vyprvpn"])

# Initialize scraper
scraper = VyprVPNServerScraper()

# Pydantic models for API responses
class VyprVPNServerResponse(BaseModel):
    region: str
    country: str
    city: str
    hostname: str
    last_verified: datetime

class ServerUpdateResponse(BaseModel):
    status: str
    changes: Dict[str, List[str]]
    timestamp: str
    total_servers: int

class SchedulerStatusResponse(BaseModel):
    scheduler_running: bool
    total_tasks: int
    enabled_tasks: int
    tasks: Dict[str, Any]

class VyprVPNStatusResponse(BaseModel):
    total_servers: int
    last_update: Optional[str]
    regions: List[str]
    countries: List[str]

@router.get("/servers", response_model=List[VyprVPNServerResponse])
async def get_all_servers():
    """Get all available VyprVPN servers"""
    try:
        servers = scraper.get_all_servers()
        return [
            VyprVPNServerResponse(
                region=server.region,
                country=server.country,
                city=server.city,
                hostname=server.hostname,
                last_verified=server.last_verified
            )
            for server in servers
        ]
    except Exception as e:
        logger.error(f"Failed to get servers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve servers: {str(e)}")

@router.get("/servers/region/{region}", response_model=List[VyprVPNServerResponse])
async def get_servers_by_region(region: str):
    """Get VyprVPN servers by region"""
    try:
        servers = scraper.get_servers_by_region(region)
        return [
            VyprVPNServerResponse(
                region=server.region,
                country=server.country,
                city=server.city,
                hostname=server.hostname,
                last_verified=server.last_verified
            )
            for server in servers
        ]
    except Exception as e:
        logger.error(f"Failed to get servers by region {region}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve servers: {str(e)}")

@router.get("/servers/country/{country}", response_model=List[VyprVPNServerResponse])
async def get_servers_by_country(country: str):
    """Get VyprVPN servers by country"""
    try:
        servers = scraper.get_servers_by_country(country)
        return [
            VyprVPNServerResponse(
                region=server.region,
                country=server.country,
                city=server.city,
                hostname=server.hostname,
                last_verified=server.last_verified
            )
            for server in servers
        ]
    except Exception as e:
        logger.error(f"Failed to get servers by country {country}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve servers: {str(e)}")

@router.get("/servers/search/{hostname}")
async def search_server_by_hostname(hostname: str):
    """Search for a VyprVPN server by hostname"""
    try:
        server = scraper.get_server_by_hostname(hostname)
        if server:
            return VyprVPNServerResponse(
                region=server.region,
                country=server.country,
                city=server.city,
                hostname=server.hostname,
                last_verified=server.last_verified
            )
        else:
            raise HTTPException(status_code=404, detail=f"Server with hostname '{hostname}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to search for server {hostname}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search for server: {str(e)}")

@router.get("/servers/count")
async def get_server_count():
    """Get total number of VyprVPN servers"""
    try:
        count = scraper.get_server_count()
        return {"total_servers": count}
    except Exception as e:
        logger.error(f"Failed to get server count: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get server count: {str(e)}")

@router.get("/regions")
async def get_available_regions():
    """Get list of available regions"""
    try:
        servers = scraper.get_all_servers()
        regions = list(set(server.region for server in servers))
        return {"regions": sorted(regions)}
    except Exception as e:
        logger.error(f"Failed to get regions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get regions: {str(e)}")

@router.get("/countries")
async def get_available_countries():
    """Get list of available countries"""
    try:
        servers = scraper.get_all_servers()
        countries = list(set(server.country for server in servers))
        return {"countries": sorted(countries)}
    except Exception as e:
        logger.error(f"Failed to get countries: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get countries: {str(e)}")

@router.post("/update", response_model=ServerUpdateResponse)
async def update_server_list(background_tasks: BackgroundTasks, force: bool = False):
    """Update VyprVPN server list from their support page"""
    try:
        logger.info(f"Starting VyprVPN server update (force={force})")
        
        # Run update in background
        changes = await scraper.update_server_list(force_update=force)
        
        # Get updated server count
        total_servers = scraper.get_server_count()
        
        return ServerUpdateResponse(
            status="success",
            changes=changes,
            timestamp=datetime.now().isoformat(),
            total_servers=total_servers
        )
        
    except Exception as e:
        logger.error(f"Failed to update VyprVPN servers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update servers: {str(e)}")

@router.get("/status", response_model=VyprVPNStatusResponse)
async def get_vyprvpn_status():
    """Get VyprVPN scraper status and statistics"""
    try:
        scheduler = get_scheduler()
        status = scheduler.get_vyprvpn_status()
        
        return VyprVPNStatusResponse(
            total_servers=status['total_servers'],
            last_update=status.get('last_update'),
            regions=status.get('regions', []),
            countries=status.get('countries', [])
        )
        
    except Exception as e:
        logger.error(f"Failed to get VyprVPN status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")

@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status():
    """Get scheduler status and task information"""
    try:
        scheduler = get_scheduler()
        status = scheduler.get_task_status()
        
        return SchedulerStatusResponse(
            scheduler_running=status['scheduler_running'],
            total_tasks=status['total_tasks'],
            enabled_tasks=status['enabled_tasks'],
            tasks=status['tasks']
        )
        
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get scheduler status: {str(e)}")

@router.post("/scheduler/tasks/{task_name}/enable")
async def enable_scheduler_task(task_name: str):
    """Enable a scheduled task"""
    try:
        scheduler = get_scheduler()
        scheduler.enable_task(task_name)
        return {"message": f"Task '{task_name}' enabled successfully"}
    except Exception as e:
        logger.error(f"Failed to enable task {task_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enable task: {str(e)}")

@router.post("/scheduler/tasks/{task_name}/disable")
async def disable_scheduler_task(task_name: str):
    """Disable a scheduled task"""
    try:
        scheduler = get_scheduler()
        scheduler.disable_task(task_name)
        return {"message": f"Task '{task_name}' disabled successfully"}
    except Exception as e:
        logger.error(f"Failed to disable task {task_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disable task: {str(e)}")

@router.get("/health")
async def health_check():
    """Health check endpoint for VyprVPN service"""
    try:
        # Check if scraper is working
        server_count = scraper.get_server_count()
        last_update = scraper.get_last_update_time()
        
        return {
            "status": "healthy",
            "server_count": server_count,
            "last_update": last_update.isoformat() if last_update else None,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Additional utility endpoints
@router.get("/servers/random")
async def get_random_server():
    """Get a random VyprVPN server (useful for testing)"""
    try:
        import random
        servers = scraper.get_all_servers()
        
        if not servers:
            raise HTTPException(status_code=404, detail="No servers available")
        
        server = random.choice(servers)
        return VyprVPNServerResponse(
            region=server.region,
            country=server.country,
            city=server.city,
            hostname=server.hostname,
            last_verified=server.last_verified
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get random server: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get random server: {str(e)}")

@router.get("/servers/fastest")
async def get_fastest_servers(limit: int = 5):
    """Get servers that are typically fastest (US-based servers)"""
    try:
        # Get US servers (typically fastest for US users)
        us_servers = scraper.get_servers_by_country("U.S.")
        
        # Sort by region (prioritize East/West coast)
        us_servers.sort(key=lambda x: x.region)
        
        # Limit results
        fastest_servers = us_servers[:limit]
        
        return [
            VyprVPNServerResponse(
                region=server.region,
                country=server.country,
                city=server.city,
                hostname=server.hostname,
                last_verified=server.last_verified
            )
            for server in fastest_servers
        ]
        
    except Exception as e:
        logger.error(f"Failed to get fastest servers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fastest servers: {str(e)}")
