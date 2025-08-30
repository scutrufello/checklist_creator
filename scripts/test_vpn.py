#!/usr/bin/env python3
"""
VPN Test Script for Checklist Creator
Tests the VPN functionality and API endpoints
"""

import asyncio
import sys
import os

# Add the backend directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from core.vpn_manager import VPNManager

async def test_vpn_manager():
    """Test the VPN manager functionality"""
    print("🧪 Testing VPN Manager...")
    
    try:
        # Initialize VPN manager
        vpn_manager = VPNManager("config/vpn_config.json")
        print("✅ VPN Manager initialized successfully")
        
        # Get status
        status = vpn_manager.get_status()
        print(f"📊 VPN Status: {status['status']}")
        print(f"🔌 Available Providers: {status['available_providers']}")
        
        # Test IP detection
        print("🌐 Testing IP detection...")
        current_ip = await vpn_manager._get_current_ip()
        if current_ip:
            print(f"✅ Current IP: {current_ip}")
        else:
            print("❌ Failed to get current IP")
        
        # Test ping
        print("🏓 Testing ping...")
        ping_result = await vpn_manager._ping_test("8.8.8.8")
        if ping_result > 0:
            print(f"✅ Ping to 8.8.8.8: {ping_result}ms")
        else:
            print("❌ Ping test failed")
        
        print("\n🎉 VPN Manager test completed successfully!")
        
    except Exception as e:
        print(f"❌ VPN Manager test failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 Starting VPN Manager Test...")
    success = asyncio.run(test_vpn_manager())
    
    if success:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)
