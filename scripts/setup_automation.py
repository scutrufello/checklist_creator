#!/usr/bin/env python3
"""
Setup script for automated credential access
Sets up master password storage for scheduled jobs
"""

import sys
import os
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from core.credential_manager import get_credential_manager

def setup_automation():
    """Set up automated password storage"""
    print("🔐 Setting up automated credential access for scheduled jobs")
    print("=" * 60)
    
    try:
        cred_manager = get_credential_manager()
        
        print("\n📋 Available storage methods:")
        print("  1. Environment variable (session only)")
        print("  2. Secure file (persistent)")
        print("  3. Remove stored password")
        print("  4. Show current setup")
        
        choice = input("\nSelect option (1-4): ").strip()
        
        if choice == "1":
            # Environment variable method
            password = input("Enter master password: ").strip()
            if not password:
                print("❌ Password cannot be empty")
                return
            
            if cred_manager.store_master_password_for_automation(password, 'env'):
                print("✅ Master password stored in environment variable")
                print("   Note: This will only persist for the current session")
                print("   For persistent storage, use option 2")
            else:
                print("❌ Failed to store password")
                
        elif choice == "2":
            # Secure file method
            password = input("Enter master password: ").strip()
            if not password:
                print("❌ Password cannot be empty")
                return
            
            if cred_manager.store_master_password_for_automation(password, 'file'):
                print("✅ Master password stored in secure file")
                print("   File: ~/.checklist_creator/.master_password")
                print("   Permissions: 600 (user read/write only)")
                print("   This is persistent and secure for scheduled jobs")
            else:
                print("❌ Failed to store password")
                
        elif choice == "3":
            # Remove stored password
            method = input("Remove from file or environment? (file/env): ").strip().lower()
            if method in ['file', 'env']:
                if cred_manager.remove_master_password_for_automation(method):
                    print(f"✅ Master password removed from {method}")
                else:
                    print(f"❌ Failed to remove password from {method}")
            else:
                print("❌ Invalid method. Use 'file' or 'env'")
                
        elif choice == "4":
            # Show current setup
            print("\n📊 Current automation setup:")
            
            # Check environment variable
            env_password = os.environ.get('CHECKLIST_CREATOR_MASTER_PASSWORD')
            if env_password:
                print("   Environment variable: ✅ Set")
            else:
                print("   Environment variable: ❌ Not set")
            
            # Check secure file
            secure_file = Path("~/.checklist_creator/.master_password").expanduser()
            if secure_file.exists():
                try:
                    stat = secure_file.stat()
                    permissions = oct(stat.st_mode)[-3:]
                    print(f"   Secure file: ✅ Exists (permissions: {permissions})")
                    
                    if permissions == '600':
                        print("   File permissions: ✅ Secure (600)")
                    else:
                        print("   File permissions: ⚠️  Insecure (should be 600)")
                        
                except Exception as e:
                    print(f"   Secure file: ❌ Error checking: {e}")
            else:
                print("   Secure file: ❌ Not found")
                
            # Show file paths
            paths = cred_manager.get_credential_file_paths()
            print(f"\n📁 Credential file paths:")
            for key, path in paths.items():
                print(f"   {key}: {path}")
                
        else:
            print("❌ Invalid choice")
            
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        return

def show_usage():
    """Show usage information"""
    print("""
🔐 Automated Credential Setup Script

This script helps you set up secure password storage for automated/scheduled jobs.

Usage: python3 scripts/setup_automation.py

Options:
  1. Environment variable - Store password in current session
  2. Secure file - Store password in encrypted file (recommended for cron jobs)
  3. Remove stored password - Clean up stored passwords
  4. Show current setup - Display current configuration

Security Notes:
  - Environment variables are only available in the current session
  - Secure files are stored with 600 permissions (user read/write only)
  - Never commit passwords to version control
  - Use secure files for persistent automation (cron jobs, systemd services)

Example for cron job:
  # Add to your crontab
  0 2 * * * cd /path/to/checklist_creator && python3 scripts/setup_automation.py 2
  # Then run your scheduled tasks
  0 3 * * * cd /path/to/checklist_creator && python3 -c "from backend.services.vyprvpn_scraper import VyprVPNServerScraper; import asyncio; scraper = VyprVPNServerScraper(); asyncio.run(scraper.update_server_list())"
""")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help', 'help']:
        show_usage()
    else:
        setup_automation()
