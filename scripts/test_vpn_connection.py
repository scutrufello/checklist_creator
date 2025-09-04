#!/usr/bin/env python3
"""
Test script for VyprVPN CLI connections
"""

import asyncio
import sys
import os
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from services.vpn_connector import VPNConnector
from core.credential_manager import get_credential_manager

async def test_vyprvpn_connection():
    """Test VyprVPN connection with IP verification"""
    try:
        connector = VPNConnector()
        
        print("🔌 Testing VyprVPN connection with IP verification...")
        
        # Get IP before connection
        print("📡 Getting IP address before VPN connection...")
        pre_ip_info = await connector.get_external_ip()
        if pre_ip_info['success']:
            print(f"   Original IP: {pre_ip_info['ip']}")
            if 'country' in pre_ip_info:
                print(f"   Location: {pre_ip_info.get('country', 'Unknown')}, {pre_ip_info.get('city', 'Unknown')}")
        else:
            print(f"   ⚠️  Failed to get original IP: {pre_ip_info['error']}")
        
        # Connect to VPN
        print("\n🔌 Connecting to VyprVPN...")
        result = await connector.connect_to_vyprvpn()
        
        if result['success']:
            print(f"✅ Connected successfully to {result['server']}")
            print(f"   Connection ID: {result['connection_id']}")
            print(f"   Message: {result['message']}")
            
            # Show IP verification results
            if 'ip_verification' in result:
                ip_ver = result['ip_verification']
                print(f"\n📊 IP Verification Results:")
                print(f"   Original IP: {ip_ver.get('original_ip', 'Unknown')}")
                print(f"   New IP: {ip_ver.get('new_ip', 'Unknown')}")
                print(f"   IP Changed: {'✅ Yes' if ip_ver.get('ip_changed') else '❌ No'}")
                print(f"   Original Location: {ip_ver.get('original_location', 'Unknown')}")
                print(f"   New Location: {ip_ver.get('new_location', 'Unknown')}")
                
                if ip_ver.get('ip_changed'):
                    print("   🎯 VPN is working correctly - IP address changed!")
                else:
                    print("   ⚠️  VPN connection may not be working - IP didn't change")
            else:
                print("   ⚠️  No IP verification data available")
        else:
            print(f"❌ Connection failed: {result.get('error', 'Unknown error')}")
        
        return result
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return {'success': False, 'error': str(e)}

async def test_vyprvpn_status():
    """Test VyprVPN status"""
    try:
        connector = VPNConnector()
        
        print("📊 Getting VyprVPN status...")
        status = await connector.get_connection_status()
        
        if status['success']:
            print(f"✅ Status retrieved successfully")
            print(f"   Total connections: {status['total_connections']}")
            print(f"   VyprVPN CLI status: {status['vyprvpn_cli_status']}")
            
            if status['active_connections']:
                print("   Active connections:")
                for conn_id, conn_info in status['active_connections'].items():
                    print(f"     - {conn_id}: {conn_info['status']} to {conn_info['server']}")
            else:
                print("   No active connections")
        else:
            print(f"❌ Status check failed: {status.get('error', 'Unknown error')}")
        
        return status
        
    except Exception as e:
        print(f"❌ Status check failed: {e}")
        return {'success': False, 'error': str(e)}

async def test_vyprvpn_disconnect():
    """Test VyprVPN disconnection with IP verification"""
    try:
        connector = VPNConnector()
        
        print("🔌 Testing VyprVPN disconnection with IP verification...")
        
        # Check current connections first
        status = await connector.get_connection_status()
        if not status['success']:
            print("❌ Failed to get connection status")
            return False
        
        active_connections = status['active_connections']
        if not active_connections:
            print("❌ No active VPN connections to disconnect")
            print("   Please connect to VPN first using: python3 scripts/test_vpn_connection.py vyprvpn")
            return False
        
        print(f"✅ Found {len(active_connections)} active connection(s) to disconnect")
        
        # Disconnect each connection
        for conn_id in active_connections.keys():
            print(f"\n🔌 Disconnecting: {conn_id}")
            result = await connector.disconnect(conn_id)
            
            if result['success']:
                print("   ✅ Disconnected successfully")
                
                # Show IP verification results
                if 'ip_verification' in result:
                    ip_ver = result['ip_verification']
                    print(f"   📊 IP Verification Results:")
                    print(f"      IP before disconnect: {ip_ver.get('pre_disconnect_ip', 'Unknown')}")
                    print(f"      IP after disconnect: {ip_ver.get('post_disconnect_ip', 'Unknown')}")
                    print(f"      IP changed during disconnect: {'✅ Yes' if ip_ver.get('ip_changed_during_disconnect') else '❌ No'}")
                    
                    if ip_ver.get('original_ip') != 'Unknown':
                        print(f"      Original IP: {ip_ver.get('original_ip', 'Unknown')}")
                        print(f"      IP restored to original: {'✅ Yes' if ip_ver.get('ip_restored') else '❌ No'}")
                    else:
                        print(f"      IP restoration status: {ip_ver.get('ip_restored', 'Unknown')}")
                    
                    # Summary
                    if ip_ver.get('ip_changed_during_disconnect'):
                        print("      🎯 VPN disconnection successful - IP address changed!")
                    else:
                        print("      ⚠️  VPN disconnection may not be working - IP didn't change")
                else:
                    print("   ⚠️  No IP verification data available")
            else:
                print(f"   ❌ Disconnect failed: {result.get('error', 'Unknown error')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Disconnect test failed: {e}")
        return {'success': False, 'error': str(e)}

async def test_credentials():
    """Test credential retrieval"""
    try:
        cred_manager = get_credential_manager()
        
        print("🔑 Testing credential retrieval...")
        credentials = cred_manager.get_vyprvpn_credentials()
        
        if credentials:
            print("✅ Credentials found:")
            print(f"   Username: {credentials.get('username', 'Not set')}")
            print(f"   Password: {'*' * len(credentials.get('password', '')) if credentials.get('password') else 'Not set'}")
            print(f"   Provider: {credentials.get('provider', 'Not set')}")
        else:
            print("❌ No VyprVPN credentials found")
        
        return credentials
        
    except Exception as e:
        print(f"❌ Credential test failed: {e}")
        return None

async def test_server_list():
    """Test server list retrieval"""
    try:
        from services.vyprvpn_scraper import VyprVPNServerScraper
        
        print("🌐 Testing server list retrieval...")
        scraper = VyprVPNServerScraper()
        
        # Load cached servers first
        servers = scraper.load_cached_servers()
        if servers:
            print(f"✅ Found {len(servers)} cached servers")
            print("   Sample servers:")
            for i, (key, server) in enumerate(list(servers.items())[:3]):
                print(f"     - {server.country} - {server.city}: {server.hostname}")
        else:
            print("   No cached servers found, updating...")
            changes = await scraper.update_server_list(force_update=True)
            servers = scraper.get_all_servers()
            if servers:
                print(f"✅ Updated server list: {len(servers)} servers")
                print("   Sample servers:")
                for i, server in enumerate(servers[:3]):
                    print(f"     - {server.country} - {server.city}: {server.hostname}")
            else:
                print("❌ Failed to retrieve servers")
        
        return servers
        
    except Exception as e:
        print(f"❌ Server list test failed: {e}")
        return None

async def test_ip_check():
    """Test IP address checking"""
    try:
        connector = VPNConnector()
        
        print("📡 Testing external IP address checking...")
        ip_info = await connector.get_external_ip()
        
        if ip_info['success']:
            print(f"✅ IP address retrieved successfully")
            print(f"   IP: {ip_info['ip']}")
            print(f"   Service: {ip_info['service']}")
            
            if 'country' in ip_info:
                print(f"   Location: {ip_info['country']}, {ip_info['city']}")
            else:
                print("   Location: Not available")
        else:
            print(f"❌ IP check failed: {ip_info['error']}")
        
        return ip_info
        
    except Exception as e:
        print(f"❌ IP check test failed: {e}")
        return {'success': False, 'error': str(e)}

async def test_vpn_verification():
    """Test VPN connection verification"""
    try:
        connector = VPNConnector()
        
        print("🔍 Testing VPN connection verification...")
        
        # Check if there are any active connections
        status = await connector.get_connection_status()
        if not status['success']:
            print("❌ Failed to get connection status")
            return False
        
        active_connections = status['active_connections']
        if not active_connections:
            print("❌ No active VPN connections to verify")
            print("   Please connect to VPN first using: python3 scripts/test_vpn_connection.py vyprvpn")
            return False
        
        # Find connected VPN connections
        connected_vpns = [conn_id for conn_id, conn_info in active_connections.items() 
                         if conn_info.get('status') == 'connected']
        
        if not connected_vpns:
            print("❌ No connected VPN connections found")
            return False
        
        print(f"✅ Found {len(connected_vpns)} connected VPN connection(s)")
        
        # Verify each connection
        for conn_id in connected_vpns:
            print(f"\n🔍 Verifying connection: {conn_id}")
            verification = await connector.verify_vpn_connection(conn_id)
            
            if verification['success']:
                print("   ✅ VPN connection verified!")
                print(f"   Original IP: {verification['original_ip']}")
                print(f"   Current IP: {verification['current_ip']}")
                print(f"   IP Changed: {'✅ Yes' if verification['ip_changed'] else '❌ No'}")
                
                if verification.get('country'):
                    print(f"   Current Location: {verification['country']}, {verification['city']}")
            else:
                print(f"   ❌ Verification failed: {verification['error']}")
        
        return True
        
    except Exception as e:
        print(f"❌ VPN verification test failed: {e}")
        return False

def show_help():
    """Show help information"""
    print("""
🔌 VyprVPN Connection Test Script

Usage: python3 scripts/test_vpn_connection.py [command]

Commands:
  vyprvpn     - Test VyprVPN connection with IP verification
  status      - Check connection status
  disconnect  - Disconnect from VPN with IP verification
  credentials - Test credential retrieval
  servers     - Test server list retrieval
  ip-check    - Check current external IP address
  verify      - Verify VPN connection is working (IP changed)
  help        - Show this help message

Examples:
  python3 scripts/test_vpn_connection.py vyprvpn
  python3 scripts/test_vpn_connection.py status
  python3 scripts/test_vpn_connection.py disconnect
  python3 scripts/test_vpn_connection.py ip-check
  python3 scripts/test_vpn_connection.py verify
""")

async def main():
    """Main function"""
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == "vyprvpn":
        await test_vyprvpn_connection()
    elif command == "status":
        await test_vyprvpn_status()
    elif command == "disconnect":
        await test_vyprvpn_disconnect()
    elif command == "credentials":
        await test_credentials()
    elif command == "servers":
        await test_server_list()
    elif command == "ip-check":
        await test_ip_check()
    elif command == "verify":
        await test_vpn_verification()
    elif command == "help":
        show_help()
    else:
        print(f"❌ Unknown command: {command}")
        show_help()

if __name__ == "__main__":
    asyncio.run(main())
