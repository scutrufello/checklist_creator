#!/usr/bin/env python3
"""
IP Comparison Test Script for Checklist Creator
Tests the IP comparison functionality before and after VPN connection
"""

import asyncio
import sys
import os
import time

# Add the backend directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from core.vpn_manager import VPNManager, VPNProvider

async def test_ip_comparison():
    """Test IP comparison functionality"""
    print("🔍 Testing IP Comparison Functionality...")
    print("=" * 50)
    
    try:
        # Initialize VPN manager
        print("1️⃣ Initializing VPN Manager...")
        vpn_manager = VPNManager("config/vpn_config.json")
        
        # Wait a moment for original IP to be stored
        print("⏳ Waiting for original IP to be stored...")
        await asyncio.sleep(3)
        
        # Get original IP
        print("\n2️⃣ Getting Original IP Address...")
        original_ip = vpn_manager.get_original_ip()
        print(f"   Original IP: {original_ip}")
        
        # Get IP comparison before VPN
        print("\n3️⃣ IP Comparison BEFORE VPN Connection...")
        comparison_before = vpn_manager.get_ip_comparison()
        print(f"   Original IP: {comparison_before['original_ip']}")
        print(f"   Current IP: {comparison_before['current_ip']}")
        print(f"   IP Changed: {comparison_before['ip_changed']}")
        print(f"   VPN Active: {comparison_before['vpn_active']}")
        
        # Get current IP
        print("\n4️⃣ Getting Current IP Address...")
        current_ip = await vpn_manager._get_current_ip()
        print(f"   Current IP: {current_ip}")
        
        # Show the comparison
        print("\n5️⃣ IP Address Summary:")
        print(f"   Original IP: {original_ip}")
        print(f"   Current IP: {current_ip}")
        print(f"   IPs Match: {original_ip == current_ip}")
        
        if original_ip == current_ip:
            print("   ✅ IP addresses match - no VPN active")
        else:
            print("   🔒 IP addresses differ - VPN may be active")
        
        # Test connection verification
        print("\n6️⃣ Testing Connection Verification...")
        if original_ip and current_ip:
            is_vpn_working = original_ip != current_ip
            print(f"   VPN Working: {is_vpn_working}")
            
            if is_vpn_working:
                print("   🎉 VPN is successfully masking your IP address!")
            else:
                print("   ℹ️  No VPN connection detected")
        else:
            print("   ❌ Could not determine IP addresses")
        
        print("\n" + "=" * 50)
        print("🎯 IP Comparison Test Complete!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during IP comparison test: {e}")
        return False

async def test_vpn_connection_simulation():
    """Simulate VPN connection and show IP changes"""
    print("\n🔒 Testing VPN Connection Simulation...")
    print("=" * 50)
    
    try:
        # Initialize VPN manager
        vpn_manager = VPNManager("config/vpn_config.json")
        
        # Wait for original IP to be stored
        await asyncio.sleep(3)
        
        print("1️⃣ Before VPN Connection:")
        original_ip = vpn_manager.get_original_ip()
        current_ip = await vpn_manager._get_current_ip()
        print(f"   Original IP: {original_ip}")
        print(f"   Current IP: {current_ip}")
        
        # Simulate VPN connection (this would normally change the IP)
        print("\n2️⃣ Simulating VPN Connection...")
        print("   Note: This is a simulation - no actual VPN connection is made")
        print("   In a real scenario, the IP would change here")
        
        # Show what the comparison would look like after VPN
        print("\n3️⃣ After VPN Connection (Simulated):")
        print(f"   Original IP: {original_ip}")
        print(f"   Current IP: {current_ip} (would be different with real VPN)")
        print(f"   IP Changed: {original_ip != current_ip}")
        
        # Show the full comparison data
        print("\n4️⃣ Full IP Comparison Data:")
        comparison = vpn_manager.get_ip_comparison()
        for key, value in comparison.items():
            print(f"   {key}: {value}")
        
        print("\n" + "=" * 50)
        print("🎯 VPN Connection Simulation Complete!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during VPN simulation: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting IP Comparison Tests...")
    print("This script tests the IP comparison functionality of the VPN Manager")
    print()
    
    # Run tests
    success1 = asyncio.run(test_ip_comparison())
    success2 = asyncio.run(test_vpn_connection_simulation())
    
    if success1 and success2:
        print("\n✅ All IP comparison tests passed!")
        print("\n📋 Summary of IP Comparison Features:")
        print("   • Original IP is stored when VPN Manager initializes")
        print("   • Current IP is checked during VPN operations")
        print("   • IP comparison shows before/after differences")
        print("   • Connection verification uses IP comparison")
        print("   • New API endpoints: /ip-comparison and /original-ip")
        sys.exit(0)
    else:
        print("\n❌ Some IP comparison tests failed!")
        sys.exit(1)
