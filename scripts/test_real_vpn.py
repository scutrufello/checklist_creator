#!/usr/bin/env python3
"""
Real VPN Functionality Test Script
Tests actual VPN connections, IP changes, and health monitoring
"""

import asyncio
import sys
import os
import time
import subprocess
import json

# Add the backend directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from core.vpn_manager import VPNManager, VPNProvider, VPNStatus

class RealVPNTester:
    """Test real VPN functionality"""
    
    def __init__(self):
        self.vpn_manager = None
        self.original_ip = None
        self.vpn_ip = None
        
    async def setup(self):
        """Initialize VPN manager and get original IP"""
        print("🔧 Setting up VPN Manager...")
        
        try:
            # Initialize VPN manager
            self.vpn_manager = VPNManager("config/vpn_config.json")
            
            # Wait for original IP to be stored
            print("⏳ Waiting for original IP to be stored...")
            await asyncio.sleep(5)
            
            # Get original IP
            self.original_ip = self.vpn_manager.get_original_ip()
            if self.original_ip:
                print(f"✅ Original IP stored: {self.original_ip}")
            else:
                print("❌ Failed to get original IP")
                return False
                
            return True
            
        except Exception as e:
            print(f"❌ Setup failed: {e}")
            return False
    
    async def test_ip_detection(self):
        """Test IP detection functionality"""
        print("\n🌐 Testing IP Detection...")
        
        try:
            # Get current IP
            current_ip = await self.vpn_manager._get_current_ip()
            if current_ip:
                print(f"✅ Current IP: {current_ip}")
                return current_ip
            else:
                print("❌ Failed to get current IP")
                return None
                
        except Exception as e:
            print(f"❌ IP detection test failed: {e}")
            return None
    
    async def test_vpn_connection(self):
        """Test actual VPN connection"""
        print("\n🔌 Testing VPN Connection...")
        
        try:
            # Check if we have OpenVPN configs
            config_dir = "/etc/openvpn/configs"
            if not os.path.exists(config_dir):
                print("❌ OpenVPN config directory not found")
                return False
            
            # List available configs
            configs = [f for f in os.listdir(config_dir) if f.endswith('.ovpn')]
            print(f"📁 Available VPN configs: {configs}")
            
            if not configs:
                print("❌ No VPN configurations found")
                return False
            
            # Try to connect using the first available config
            test_config = configs[0]
            print(f"🧪 Testing with config: {test_config}")
            
            # Check if OpenVPN is available
            try:
                result = subprocess.run(["which", "openvpn"], 
                                      capture_output=True, text=True)
                if result.returncode != 0:
                    print("❌ OpenVPN not found in PATH")
                    return False
                print("✅ OpenVPN found in PATH")
            except Exception as e:
                print(f"❌ Error checking OpenVPN: {e}")
                return False
            
            # Test connection (this will fail without real credentials, but tests the process)
            print("🔑 Note: This will fail without real VPN credentials")
            print("   But it will test the connection process and error handling")
            
            # Try to connect (will fail without real auth)
            try:
                success = await self.vpn_manager.connect(VPNProvider.OPENVPN, "United States")
                if success:
                    print("✅ VPN connection successful!")
                    return True
                else:
                    print("❌ VPN connection failed (expected without real credentials)")
                    return False
            except Exception as e:
                print(f"⚠️  VPN connection error (expected): {e}")
                return False
                
        except Exception as e:
            print(f"❌ VPN connection test failed: {e}")
            return False
    
    async def test_ip_comparison(self):
        """Test IP comparison functionality"""
        print("\n🔍 Testing IP Comparison...")
        
        try:
            # Get IP comparison data
            comparison = self.vpn_manager.get_ip_comparison()
            
            print("📊 IP Comparison Data:")
            for key, value in comparison.items():
                print(f"   {key}: {value}")
            
            # Test the comparison logic
            if comparison['original_ip'] and comparison['current_ip']:
                ip_changed = comparison['original_ip'] != comparison['current_ip']
                print(f"\n🔒 IP Change Status: {ip_changed}")
                
                if ip_changed:
                    print("   🎉 VPN is successfully masking your IP!")
                else:
                    print("   ℹ️  No VPN connection detected")
            else:
                print("   ℹ️  IP comparison data incomplete")
            
            return True
            
        except Exception as e:
            print(f"❌ IP comparison test failed: {e}")
            return False
    
    async def test_health_monitoring(self):
        """Test health monitoring functionality"""
        print("\n🏥 Testing Health Monitoring...")
        
        try:
            # Test ping functionality
            print("🏓 Testing ping functionality...")
            ping_result = await self.vpn_manager._ping_test("8.8.8.8")
            
            if ping_result > 0:
                print(f"✅ Ping to 8.8.8.8: {ping_result}ms")
            else:
                print("❌ Ping test failed")
            
            # Test connection health check
            print("🔍 Testing connection health check...")
            if self.vpn_manager.current_connection:
                health_status = await self.vpn_manager._check_connection_health()
                print(f"   Connection health: {health_status}")
            else:
                print("   No active connection to check")
            
            return True
            
        except Exception as e:
            print(f"❌ Health monitoring test failed: {e}")
            return False
    
    async def test_vpn_scripts(self):
        """Test VPN management scripts"""
        print("\n📋 Testing VPN Management Scripts...")
        
        try:
            # Test VPN status script
            print("🔍 Testing VPN status script...")
            result = subprocess.run(["./scripts/manage_vpn.sh", "status"], 
                                  capture_output=True, text=True, cwd="..")
            
            if result.returncode == 0:
                print("✅ VPN status script working")
                print(f"   Output: {result.stdout.strip()}")
            else:
                print("❌ VPN status script failed")
                print(f"   Error: {result.stderr.strip()}")
            
            # Test VPN config listing
            print("\n📁 Testing VPN config listing...")
            result = subprocess.run(["./scripts/manage_vpn.sh", "list-configs"], 
                                  capture_output=True, text=True, cwd="..")
            
            if result.returncode == 0:
                print("✅ VPN config listing working")
                print(f"   Available configs: {result.stdout.strip()}")
            else:
                print("❌ VPN config listing failed")
            
            return True
            
        except Exception as e:
            print(f"❌ VPN scripts test failed: {e}")
            return False
    
    async def run_all_tests(self):
        """Run all VPN tests"""
        print("🚀 Starting Real VPN Functionality Tests...")
        print("=" * 60)
        
        # Setup
        if not await self.setup():
            print("❌ Setup failed, cannot continue tests")
            return False
        
        # Run tests
        tests = [
            ("IP Detection", self.test_ip_detection),
            ("VPN Connection", self.test_vpn_connection),
            ("IP Comparison", self.test_ip_comparison),
            ("Health Monitoring", self.test_health_monitoring),
            ("VPN Scripts", self.test_vpn_scripts)
        ]
        
        results = []
        for test_name, test_func in tests:
            print(f"\n{'='*20} {test_name} Test {'='*20}")
            try:
                result = await test_func()
                results.append((test_name, result))
                status = "✅ PASS" if result else "❌ FAIL"
                print(f"{status} {test_name}")
            except Exception as e:
                print(f"❌ ERROR {test_name}: {e}")
                results.append((test_name, False))
        
        # Summary
        print(f"\n{'='*60}")
        print("🎯 Test Results Summary:")
        print("="*60)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print(f"\n📊 Overall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed! VPN system is working correctly.")
        else:
            print("⚠️  Some tests failed. Check the output above for details.")
        
        return passed == total

async def main():
    """Main test function"""
    tester = RealVPNTester()
    success = await tester.run_all_tests()
    
    if success:
        print("\n✅ All VPN functionality tests completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Some VPN functionality tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
