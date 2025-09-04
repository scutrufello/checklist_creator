#!/usr/bin/env python3
"""
VyprVPN Management Script for Checklist Creator
Provides command-line interface for managing VyprVPN server updates and configuration
"""

import asyncio
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add the backend directory to the Python path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from services.vyprvpn_scraper import VyprVPNServerScraper
from services.scheduler import get_scheduler

class VyprVPNManager:
    """Command-line manager for VyprVPN services"""
    
    def __init__(self):
        self.scraper = VyprVPNServerScraper()
        self.scheduler = get_scheduler()
    
    async def status(self):
        """Show VyprVPN system status"""
        print("🔍 VyprVPN System Status")
        print("=" * 50)
        
        try:
            # Get server information
            servers = self.scraper.get_all_servers()
            last_update = self.scraper.get_last_update_time()
            
            print(f"📊 Total Servers: {len(servers)}")
            print(f"🕒 Last Update: {last_update.isoformat() if last_update else 'Never'}")
            
            # Get scheduler status
            scheduler_status = self.scheduler.get_task_status()
            print(f"⏰ Scheduler Running: {scheduler_status['scheduler_running']}")
            print(f"📋 Total Tasks: {scheduler_status['total_tasks']}")
            print(f"✅ Enabled Tasks: {scheduler_status['enabled_tasks']}")
            
            # Show regions
            regions = set(server.region for server in servers)
            print(f"\n🌍 Available Regions ({len(regions)}):")
            for region in sorted(regions):
                region_servers = [s for s in servers if s.region == region]
                print(f"   • {region}: {len(region_servers)} servers")
            
            # Show countries
            countries = set(server.country for server in servers)
            print(f"\n🏳️ Available Countries ({len(countries)}):")
            for country in sorted(countries)[:20]:  # Show first 20
                country_servers = [s for s in servers if s.country == country]
                print(f"   • {country}: {len(country_servers)} servers")
            
            if len(countries) > 20:
                print(f"   ... and {len(countries) - 20} more countries")
                
        except Exception as e:
            print(f"❌ Error getting status: {e}")
    
    async def update(self, force=False):
        """Update VyprVPN server list"""
        print("🔄 Updating VyprVPN Server List...")
        print("=" * 50)
        
        try:
            changes = await self.scraper.update_server_list(force_update=force)
            
            if 'status' in changes and changes['status'] == ['No update needed']:
                print("✅ No update needed - server list is current")
                return
            
            print("📊 Update Results:")
            if changes.get('added'):
                print(f"   ➕ Added: {len(changes['added'])} servers")
                for change in changes['added'][:5]:  # Show first 5
                    print(f"      • {change}")
                if len(changes['added']) > 5:
                    print(f"      ... and {len(changes['added']) - 5} more")
            
            if changes.get('removed'):
                print(f"   ➖ Removed: {len(changes['removed'])} servers")
                for change in changes['removed'][:5]:  # Show first 5
                    print(f"      • {change}")
                if len(changes['removed']) > 5:
                    print(f"      ... and {len(changes['removed']) - 5} more")
            
            if changes.get('modified'):
                print(f"   🔄 Modified: {len(changes['modified'])} servers")
                for change in changes['modified'][:5]:  # Show first 5
                    print(f"      • {change}")
                if len(changes['modified']) > 5:
                    print(f"      ... and {len(changes['modified']) - 5} more")
            
            # Show final count
            total_servers = self.scraper.get_server_count()
            print(f"\n🎯 Total servers after update: {total_servers}")
            
        except Exception as e:
            print(f"❌ Update failed: {e}")
    
    async def list_servers(self, region=None, country=None, limit=20):
        """List VyprVPN servers with optional filtering"""
        try:
            if region:
                servers = self.scraper.get_servers_by_region(region)
                print(f"📍 Servers in {region} ({len(servers)} total):")
            elif country:
                servers = self.scraper.get_servers_by_country(country)
                print(f"🏳️ Servers in {country} ({len(servers)} total):")
            else:
                servers = self.scraper.get_all_servers()
                print(f"🌐 All VyprVPN Servers ({len(servers)} total):")
            
            print("=" * 60)
            
            # Display servers
            for i, server in enumerate(servers[:limit]):
                print(f"{i+1:3d}. {server.country:15} - {server.city:20} | {server.hostname}")
            
            if len(servers) > limit:
                print(f"\n... and {len(servers) - limit} more servers")
                print(f"Use --limit {len(servers)} to see all servers")
            
        except Exception as e:
            print(f"❌ Error listing servers: {e}")
    
    async def search(self, hostname):
        """Search for a specific server by hostname"""
        print(f"🔍 Searching for server: {hostname}")
        print("=" * 50)
        
        try:
            server = self.scraper.get_server_by_hostname(hostname)
            
            if server:
                print("✅ Server found:")
                print(f"   🌍 Region: {server.region}")
                print(f"   🏳️ Country: {server.country}")
                print(f"   🏙️ City: {server.city}")
                print(f"   🌐 Hostname: {server.hostname}")
                print(f"   🕒 Last Verified: {server.last_verified.isoformat()}")
            else:
                print(f"❌ Server with hostname '{hostname}' not found")
                print("\n💡 Try listing all servers to see available hostnames:")
                print("   python manage_vyprvpn.py list")
                
        except Exception as e:
            print(f"❌ Search failed: {e}")
    
    async def scheduler_status(self):
        """Show detailed scheduler status"""
        print("⏰ Scheduler Status")
        print("=" * 50)
        
        try:
            status = self.scheduler.get_task_status()
            
            print(f"🔄 Scheduler Running: {status['scheduler_running']}")
            print(f"📋 Total Tasks: {status['total_tasks']}")
            print(f"✅ Enabled Tasks: {status['enabled_tasks']}")
            
            if status['tasks']:
                print("\n📝 Task Details:")
                for task_name, task_info in status['tasks'].items():
                    print(f"\n   🎯 {task_name}:")
                    print(f"      Status: {'✅ Enabled' if task_info['enabled'] else '❌ Disabled'}")
                    print(f"      Schedule: {task_info['schedule']}")
                    print(f"      Last Run: {task_info['last_run'] or 'Never'}")
                    print(f"      Next Run: {task_info['next_run'] or 'Not scheduled'}")
            
        except Exception as e:
            print(f"❌ Error getting scheduler status: {e}")
    
    async def test_connection(self):
        """Test VyprVPN server connectivity"""
        print("🧪 Testing VyprVPN Server Connectivity...")
        print("=" * 50)
        
        try:
            # Get a random server to test
            import random
            servers = self.scraper.get_all_servers()
            
            if not servers:
                print("❌ No servers available for testing")
                return
            
            # Pick a US server for testing (typically more reliable)
            us_servers = [s for s in servers if s.country == "U.S."]
            test_server = random.choice(us_servers) if us_servers else random.choice(servers)
            
            print(f"🎯 Testing server: {test_server.hostname}")
            print(f"📍 Location: {test_server.country} - {test_server.city}")
            
            # Test basic connectivity (ping)
            import subprocess
            try:
                result = subprocess.run(
                    ['ping', '-c', '3', test_server.hostname],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    print("✅ Ping test: PASSED")
                else:
                    print("❌ Ping test: FAILED")
                    print(f"   Output: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                print("⏰ Ping test: TIMEOUT")
            except FileNotFoundError:
                print("⚠️ Ping command not available (skipping ping test)")
            
            # Test DNS resolution
            try:
                import socket
                ip_address = socket.gethostbyname(test_server.hostname)
                print(f"✅ DNS resolution: PASSED ({test_server.hostname} -> {ip_address})")
            except socket.gaierror as e:
                print(f"❌ DNS resolution: FAILED - {e}")
            
            print(f"\n🎯 Server {test_server.hostname} is ready for VPN configuration")
            
        except Exception as e:
            print(f"❌ Connection test failed: {e}")
    
    async def export_configs(self, output_file="vyprvpn_servers.json"):
        """Export server configurations to JSON file"""
        print(f"📤 Exporting VyprVPN servers to {output_file}")
        print("=" * 50)
        
        try:
            servers = self.scraper.get_all_servers()
            
            # Convert to exportable format
            export_data = {
                "export_date": datetime.now().isoformat(),
                "total_servers": len(servers),
                "servers": []
            }
            
            for server in servers.values():
                export_data["servers"].append({
                    "region": server.region,
                    "country": server.country,
                    "city": server.city,
                    "hostname": server.hostname,
                    "last_verified": server.last_verified.isoformat()
                })
            
            # Write to file
            with open(output_file, 'w') as f:
                json.dump(export_data, f, indent=2)
            
            print(f"✅ Successfully exported {len(servers)} servers to {output_file}")
            print(f"📁 File size: {Path(output_file).stat().st_size} bytes")
            
        except Exception as e:
            print(f"❌ Export failed: {e}")

def main():
    """Main CLI function"""
    parser = argparse.ArgumentParser(
        description="VyprVPN Management Script for Checklist Creator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage_vyprvpn.py status                    # Show system status
  python manage_vyprvpn.py update                    # Update server list
  python manage_vyprvpn.py update --force            # Force update
  python manage_vyprvpn.py list                      # List all servers
  python manage_vyprvpn.py list --region "North America"  # List by region
  python manage_vyprvpn.py list --country "U.S."     # List by country
  python manage_vyprvpn.py search us1.vyprvpn.com    # Search for server
  python manage_vyprvpn.py scheduler                 # Show scheduler status
  python manage_vyprvpn.py test                      # Test server connectivity
  python manage_vyprvpn.py export                    # Export to JSON
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    subparsers.add_parser('status', help='Show VyprVPN system status')
    
    # Update command
    update_parser = subparsers.add_parser('update', help='Update VyprVPN server list')
    update_parser.add_argument('--force', action='store_true', help='Force update even if not needed')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List VyprVPN servers')
    list_parser.add_argument('--region', help='Filter by region')
    list_parser.add_argument('--country', help='Filter by country')
    list_parser.add_argument('--limit', type=int, default=20, help='Limit number of servers shown')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search for server by hostname')
    search_parser.add_argument('hostname', help='Hostname to search for')
    
    # Scheduler command
    subparsers.add_parser('scheduler', help='Show scheduler status')
    
    # Test command
    subparsers.add_parser('test', help='Test server connectivity')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export servers to JSON')
    export_parser.add_argument('--output', default='vyprvpn_servers.json', help='Output file name')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Create manager and run command
    manager = VyprVPNManager()
    
    async def run_command():
        if args.command == 'status':
            await manager.status()
        elif args.command == 'update':
            await manager.update(force=args.force)
        elif args.command == 'list':
            await manager.list_servers(region=args.region, country=args.country, limit=args.limit)
        elif args.command == 'search':
            await manager.search(args.hostname)
        elif args.command == 'scheduler':
            await manager.scheduler_status()
        elif args.command == 'test':
            await manager.test_connection()
        elif args.command == 'export':
            await manager.export_configs(args.output)
    
    # Run the command
    try:
        asyncio.run(run_command())
    except KeyboardInterrupt:
        print("\n\n⏹️ Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
