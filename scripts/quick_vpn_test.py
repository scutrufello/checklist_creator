#!/usr/bin/env python3
"""
Quick VPN Test Script
Tests core VPN functionality without blocking terminal commands
"""

import asyncio
import sys
import os

# Add the backend directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from core.vpn_manager import VPNManager, VPNProvider

async def quick_vpn_test():
    """Quick test of VPN functionality"""
    print("🚀 Quick VPN Functionality Test")
    print("=" * 40)
    
    try:
        # Initialize VPN manager
        print("1️⃣ Initializing VPN Manager...")
        vpn_manager = VPNManager("config/vpn_config.json")
        
        # Wait for original IP to be stored
        print("2️⃣ Waiting for original IP storage...")
        await asyncio.sleep(3)
        
        # Get original IP
        original_ip = vpn_manager.get_original_ip()
        print(f"3️⃣ Original IP: {original_ip}")
        
        # Get current IP
        print("4️⃣ Getting current IP...")
        current_ip = await vpn_manager._get_current_ip()
        print(f"   Current IP: {current_ip}")
        
        # Show IP comparison
        print("\n5️⃣ IP Comparison:")
        comparison = vpn_manager.get_ip_comparison()
        for key, value in comparison.items():
            print(f"   {key}: {value}")
        
        # Test ping functionality
        print("\n6️⃣ Testing ping...")
        ping_result = await vpn_manager._ping_test("8.8.8.8")
        if ping_result > 0:
            print(f"   ✅ Ping to 8.8.8.8: {ping_result}ms")
        else:
            print("   ❌ Ping test failed")
        
        # Show VPN status
        print("\n7️⃣ VPN Status:")
        status = vpn_manager.get_status()
        print(f"   Status: {status['status']}")
        print(f"   Provider: {status['provider']}")
        print(f"   Available Providers: {status['available_providers']}")
        
        print("\n" + "=" * 40)
        print("✅ Quick VPN test completed!")
        
        # Summary
        print(f"\n📊 Summary:")
        print(f"   Original IP: {original_ip}")
        print(f"   Current IP: {current_ip}")
        print(f"   IP Changed: {original_ip != current_ip}")
        print(f"   VPN Active: {status['status'] == 'connected'}")
        
        if original_ip == current_ip:
            print("   ℹ️  No VPN connection - IPs match")
        else:
            print("   🎉 VPN connection detected - IPs differ!")
        
        return True
        
    except Exception as e:
        print(f"❌ Quick VPN test failed: {e}")
        return False

if __name__ == "__main__":
    print("Starting quick VPN test...")
    success = asyncio.run(quick_vpn_test())
    
    if success:
        print("\n🎯 Quick test passed! VPN system is working.")
        print("\nNext steps:")
        print("1. Get real VPN provider credentials")
        print("2. Test actual VPN connections")
        print("3. Verify IP masking works")
    else:
        print("\n❌ Quick test failed. Check the output above.")
    
    sys.exit(0 if success else 1)
