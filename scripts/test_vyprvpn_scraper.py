#!/usr/bin/env python3
"""
Test script for VyprVPN Server Scraper
Tests the functionality of the VyprVPN server hostname scraper
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the backend directory to the Python path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from services.vyprvpn_scraper import VyprVPNServerScraper

async def test_vyprvpn_scraper():
    """Test the VyprVPN scraper functionality"""
    print("🧪 Testing VyprVPN Server Scraper...")
    print("=" * 50)
    
    # Initialize scraper
    scraper = VyprVPNServerScraper()
    
    try:
        # Test 1: Load cached servers (if any)
        print("\n1️⃣ Testing cached server loading...")
        cached_servers = scraper.load_cached_servers()
        print(f"   Loaded {len(cached_servers)} cached servers")
        
        # Test 2: Fetch server list from VyprVPN
        print("\n2️⃣ Testing server list fetching...")
        print("   Fetching from: https://support.vyprvpn.com/hc/en-us/articles/360037728912-What-are-the-VyprVPN-server-addresses")
        
        html_content = await scraper.fetch_server_list()
        print(f"   ✅ Successfully fetched HTML content ({len(html_content)} characters)")
        
        # Test 3: Parse server list
        print("\n3️⃣ Testing server list parsing...")
        servers = scraper.parse_server_list(html_content)
        print(f"   ✅ Successfully parsed {len(servers)} servers")
        
        # Test 4: Display server information
        print("\n4️⃣ Server Information:")
        print(f"   Total servers: {len(servers)}")
        
        # Group servers by region
        regions = {}
        for server in servers.values():
            if server.region not in regions:
                regions[server.region] = []
            regions[server.region].append(server)
        
        # Display servers by region
        for region, region_servers in sorted(regions.items()):
            print(f"\n   📍 {region} ({len(region_servers)} servers):")
            for server in region_servers[:5]:  # Show first 5 per region
                print(f"      • {server.country} - {server.city}: {server.hostname}")
            if len(region_servers) > 5:
                print(f"      ... and {len(region_servers) - 5} more")
        
        # Test 5: Test server queries
        print("\n5️⃣ Testing server queries...")
        
        # Test region query
        us_servers = scraper.get_servers_by_region("North America")
        print(f"   US servers: {len(us_servers)}")
        
        # Test country query
        us_country_servers = scraper.get_servers_by_country("U.S.")
        print(f"   U.S. country servers: {len(us_country_servers)}")
        
        # Test hostname search
        if us_country_servers:
            sample_server = us_country_servers[0]
            found_server = scraper.get_server_by_hostname(sample_server.hostname)
            if found_server:
                print(f"   ✅ Hostname search works: {found_server.hostname}")
            else:
                print(f"   ❌ Hostname search failed for: {sample_server.hostname}")
        
        # Test 6: Test caching
        print("\n6️⃣ Testing caching...")
        scraper.servers = servers
        scraper.save_servers_to_cache(servers)
        print("   ✅ Servers saved to cache")
        
        # Reload from cache
        reloaded_servers = scraper.load_cached_servers()
        print(f"   ✅ Reloaded {len(reloaded_servers)} servers from cache")
        
        # Test 7: Test change detection
        print("\n7️⃣ Testing change detection...")
        changes = scraper.get_server_changes(servers)
        print(f"   Changes detected: {changes}")
        
        # Test 8: Test update process
        print("\n8️⃣ Testing update process...")
        update_result = await scraper.update_server_list(force_update=True)
        print(f"   Update result: {update_result}")
        
        print("\n" + "=" * 50)
        print("✅ All tests completed successfully!")
        print(f"🎯 Total VyprVPN servers available: {len(servers)}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_scheduler_integration():
    """Test scheduler integration"""
    print("\n🔄 Testing Scheduler Integration...")
    print("=" * 50)
    
    try:
        from services.scheduler import TaskScheduler
        
        # Create scheduler instance
        scheduler = TaskScheduler()
        
        # Test task addition
        print("1️⃣ Testing task addition...")
        scheduler.add_task("test_task", lambda: "test", "daily")
        print(f"   ✅ Added test task. Total tasks: {len(scheduler.tasks)}")
        
        # Test task status
        print("\n2️⃣ Testing task status...")
        status = scheduler.get_task_status()
        print(f"   Scheduler running: {status['scheduler_running']}")
        print(f"   Total tasks: {status['total_tasks']}")
        print(f"   Enabled tasks: {status['enabled_tasks']}")
        
        # Test VyprVPN status
        print("\n3️⃣ Testing VyprVPN status...")
        vyprvpn_status = scheduler.get_vyprvpn_status()
        print(f"   Total servers: {vyprvpn_status['total_servers']}")
        print(f"   Last update: {vyprvpn_status.get('last_update', 'Never')}")
        
        print("\n✅ Scheduler integration tests completed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Scheduler test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function"""
    print("🚀 Starting VyprVPN Scraper Tests")
    print("=" * 60)
    
    # Test scraper
    scraper_success = await test_vyprvpn_scraper()
    
    # Test scheduler
    scheduler_success = await test_scheduler_integration()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"VyprVPN Scraper: {'✅ PASSED' if scraper_success else '❌ FAILED'}")
    print(f"Scheduler Integration: {'✅ PASSED' if scheduler_success else '❌ FAILED'}")
    
    if scraper_success and scheduler_success:
        print("\n🎉 All tests passed! The VyprVPN scraper is working correctly.")
        print("\n📋 Next steps:")
        print("   1. The scraper will automatically update server list daily at 2 AM")
        print("   2. You can manually trigger updates via API: POST /api/v1/vyprvpn/update")
        print("   3. View server status via: GET /api/v1/vyprvpn/status")
        print("   4. Check scheduler status via: GET /api/v1/vyprvpn/scheduler/status")
        return 0
    else:
        print("\n💥 Some tests failed. Please check the error messages above.")
        return 1

if __name__ == "__main__":
    # Run the tests
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
