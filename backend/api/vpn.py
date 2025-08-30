"""
VPN API Endpoints
Provides RESTful API access to VPN management functionality
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
import asyncio
import logging

from ..core.vpn_manager import VPNManager, VPNProvider, VPNStatus
from ..schemas.vpn import (
    VPNConnectRequest,
    VPNConnectResponse,
    VPNStatusResponse,
    VPNConnectionHistory,
    VPNProviderInfo,
    VPNHealthCheck
)

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/vpn", tags=["VPN Management"])

# Global VPN manager instance
vpn_manager: Optional[VPNManager] = None

def get_vpn_manager() -> VPNManager:
    """Dependency to get VPN manager instance"""
    global vpn_manager
    if vpn_manager is None:
        vpn_manager = VPNManager()
    return vpn_manager

@router.get("/status", response_model=VPNStatusResponse)
async def get_vpn_status(vpn_mgr: VPNManager = Depends(get_vpn_manager)):
    """
    Get current VPN status and connection information
    
    Returns:
        VPNStatusResponse: Current VPN status and details
    """
    try:
        status = vpn_mgr.get_status()
        return VPNStatusResponse(**status)
    except Exception as e:
        logger.error(f"Error getting VPN status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get VPN status: {str(e)}")

@router.get("/providers", response_model=List[VPNProviderInfo])
async def get_vpn_providers(vpn_mgr: VPNManager = Depends(get_vpn_manager)):
    """
    Get list of available VPN providers and their configurations
    
    Returns:
        List[VPNProviderInfo]: Available VPN providers
    """
    try:
        providers = []
        for provider, config in vpn_mgr.providers.items():
            provider_info = VPNProviderInfo(
                name=provider.value,
                config_path=config.config_path,
                servers=config.servers,
                locations=config.locations,
                max_connections=config.max_connections,
                health_check_url=config.health_check_url,
                timeout=config.timeout
            )
            providers.append(provider_info)
        
        return providers
    except Exception as e:
        logger.error(f"Error getting VPN providers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get VPN providers: {str(e)}")

@router.post("/connect", response_model=VPNConnectResponse)
async def connect_vpn(
    request: VPNConnectRequest,
    background_tasks: BackgroundTasks,
    vpn_mgr: VPNManager = Depends(get_vpn_manager)
):
    """
    Connect to VPN using specified provider and location/server
    
    Args:
        request: VPN connection request parameters
        background_tasks: FastAPI background tasks
        vpn_mgr: VPN manager instance
    
    Returns:
        VPNConnectResponse: Connection result and status
    """
    try:
        # Validate provider
        try:
            provider = VPNProvider(request.provider)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid VPN provider: {request.provider}")
        
        # Check if provider is available
        if provider not in vpn_mgr.providers:
            raise HTTPException(
                status_code=400, 
                detail=f"VPN provider {request.provider} is not configured or available"
            )
        
        # Check if already connected
        if vpn_mgr.current_connection and vpn_mgr.current_connection.status == VPNStatus.CONNECTED:
            return VPNConnectResponse(
                success=True,
                message=f"Already connected to {vpn_mgr.current_connection.provider.value} VPN",
                connection_id=id(vpn_mgr.current_connection),
                status=vpn_mgr.current_connection.status.value
            )
        
        # Start connection in background
        background_tasks.add_task(
            vpn_mgr.connect,
            provider=provider,
            location=request.location,
            server=request.server
        )
        
        return VPNConnectResponse(
            success=True,
            message=f"Connecting to {request.provider} VPN...",
            connection_id=None,
            status="connecting"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error connecting to VPN: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect to VPN: {str(e)}")

@router.post("/disconnect", response_model=Dict[str, str])
async def disconnect_vpn(vpn_mgr: VPNManager = Depends(get_vpn_manager)):
    """
    Disconnect from current VPN connection
    
    Returns:
        Dict[str, str]: Disconnection result message
    """
    try:
        if not vpn_mgr.current_connection:
            return {"message": "No active VPN connection to disconnect"}
        
        if vpn_mgr.current_connection.status == VPNStatus.DISCONNECTED:
            return {"message": "VPN is already disconnected"}
        
        success = await vpn_mgr.disconnect()
        
        if success:
            return {"message": "VPN disconnected successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to disconnect VPN")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting VPN: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disconnect VPN: {str(e)}")

@router.get("/history", response_model=VPNConnectionHistory)
async def get_connection_history(vpn_mgr: VPNManager = Depends(get_vpn_manager)):
    """
    Get VPN connection history
    
    Returns:
        VPNConnectionHistory: List of previous connections
    """
    try:
        history = vpn_mgr.get_connection_history()
        return VPNConnectionHistory(connections=history)
    except Exception as e:
        logger.error(f"Error getting connection history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get connection history: {str(e)}")

@router.get("/health", response_model=VPNHealthCheck)
async def get_vpn_health(vpn_mgr: VPNManager = Depends(get_vpn_manager)):
    """
    Get VPN connection health status
    
    Returns:
        VPNHealthCheck: Health check results
    """
    try:
        if not vpn_mgr.current_connection:
            return VPNHealthCheck(
                is_healthy=False,
                status="disconnected",
                message="No active VPN connection",
                ping=None,
                speed=None,
                uptime=None
            )
        
        connection = vpn_mgr.current_connection
        
        # Calculate uptime
        uptime = None
        if connection.connection_time:
            uptime = time.time() - connection.connection_time
        
        # Determine health status
        is_healthy = (
            connection.status == VPNStatus.CONNECTED and
            connection.ip_address and
            connection.ping is not None and
            connection.ping > 0
        )
        
        return VPNHealthCheck(
            is_healthy=is_healthy,
            status=connection.status.value,
            message="VPN connection is healthy" if is_healthy else "VPN connection has issues",
            ping=connection.ping,
            speed=connection.speed,
            uptime=uptime
        )
        
    except Exception as e:
        logger.error(f"Error getting VPN health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get VPN health: {str(e)}")

@router.post("/reconnect")
async def reconnect_vpn(vpn_mgr: VPNManager = Depends(get_vpn_manager)):
    """
    Reconnect to VPN using current settings
    
    Returns:
        Dict[str, str]: Reconnection result message
    """
    try:
        if not vpn_mgr.current_connection:
            raise HTTPException(status_code=400, detail="No VPN connection to reconnect")
        
        # Store current connection details
        provider = vpn_mgr.current_connection.provider
        location = vpn_mgr.current_connection.location
        server = vpn_mgr.current_connection.server
        
        # Disconnect first
        await vpn_mgr.disconnect()
        
        # Wait a moment
        await asyncio.sleep(2)
        
        # Reconnect
        success = await vpn_mgr.connect(provider, location, server)
        
        if success:
            return {"message": "VPN reconnected successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to reconnect VPN")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reconnecting VPN: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reconnect VPN: {str(e)}")

@router.post("/switch-location")
async def switch_vpn_location(
    location: str,
    vpn_mgr: VPNManager = Depends(get_vpn_manager)
):
    """
    Switch VPN to a different location
    
    Args:
        location: New location to connect to
    
    Returns:
        Dict[str, str]: Switch result message
    """
    try:
        if not vpn_mgr.current_connection:
            raise HTTPException(status_code=400, detail="No active VPN connection to switch")
        
        # Store current provider
        provider = vpn_mgr.current_connection.provider
        
        # Disconnect current connection
        await vpn_mgr.disconnect()
        
        # Wait a moment
        await asyncio.sleep(2)
        
        # Connect to new location
        success = await vpn_mgr.connect(provider, location)
        
        if success:
            return {"message": f"VPN switched to {location} successfully"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to switch VPN to {location}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error switching VPN location: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to switch VPN location: {str(e)}")

@router.get("/metrics")
async def get_vpn_metrics(vpn_mgr: VPNManager = Depends(get_vpn_manager)):
    """
    Get VPN performance metrics
    
    Returns:
        Dict: VPN performance metrics
    """
    try:
        if not vpn_mgr.current_connection:
            return {"message": "No active VPN connection"}
        
        connection = vpn_mgr.current_connection
        
        # Calculate uptime
        uptime = None
        if connection.connection_time:
            uptime = time.time() - connection.connection_time
        
        metrics = {
            "provider": connection.provider.value,
            "location": connection.location,
            "server": connection.server,
            "protocol": connection.protocol,
            "uptime_seconds": uptime,
            "ping_ms": connection.ping,
            "speed_mbps": connection.speed,
            "ip_address": connection.ip_address,
            "status": connection.status.value
        }
        
        return metrics
        
    except Exception as e:
        logger.error(f"Error getting VPN metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get VPN metrics: {str(e)}")

@router.delete("/cleanup")
async def cleanup_vpn(vpn_mgr: VPNManager = Depends(get_vpn_manager)):
    """
    Cleanup VPN manager resources
    
    Returns:
        Dict[str, str]: Cleanup result message
    """
    try:
        await vpn_mgr.cleanup()
        return {"message": "VPN manager cleanup completed"}
    except Exception as e:
        logger.error(f"Error during VPN cleanup: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup VPN manager: {str(e)}")

@router.get("/ip-comparison")
async def get_ip_comparison(vpn_mgr: VPNManager = Depends(get_vpn_manager)):
    """
    Get IP address comparison information
    
    Returns:
        Dict: IP comparison details including original IP, current IP, and change status
    """
    try:
        comparison = vpn_mgr.get_ip_comparison()
        return comparison
    except Exception as e:
        logger.error(f"Error getting IP comparison: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get IP comparison: {str(e)}")

@router.get("/original-ip")
async def get_original_ip(vpn_mgr: VPNManager = Depends(get_vpn_manager)):
    """
    Get the original IP address (before VPN connection)
    
    Returns:
        Dict: Original IP address information
    """
    try:
        original_ip = vpn_mgr.get_original_ip()
        return {
            "original_ip": original_ip,
            "timestamp": "stored_on_initialization",
            "note": "This is the IP address before any VPN connection was established"
        }
    except Exception as e:
        logger.error(f"Error getting original IP: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get original IP: {str(e)}")

# Import time module for uptime calculations
import time
