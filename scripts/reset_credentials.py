#!/usr/bin/env python3
"""
Reset Credentials Script
Clears corrupted credentials and allows fresh setup
"""

import os
import sys
from pathlib import Path

def reset_credentials():
    """Reset all stored credentials"""
    print("🔄 Resetting Credentials")
    print("=" * 50)
    
    try:
        # Get credential directory
        config_dir = Path("~/.checklist_creator").expanduser()
        
        if not config_dir.exists():
            print("✅ No credential directory found - nothing to reset")
            return True
        
        print(f"Found credential directory: {config_dir}")
        
        # List files to be removed
        files_to_remove = []
        for file in config_dir.iterdir():
            if file.is_file():
                files_to_remove.append(file)
                print(f"   📄 {file.name}")
        
        if not files_to_remove:
            print("✅ No credential files found - nothing to reset")
            return True
        
        # Confirm removal
        print(f"\n⚠️  This will remove {len(files_to_remove)} credential files!")
        confirm = input("Are you sure you want to reset all credentials? (y/N): ").strip().lower()
        
        if confirm != 'y':
            print("❌ Reset cancelled")
            return False
        
        # Remove files
        print("\n🗑️  Removing credential files...")
        for file in files_to_remove:
            try:
                file.unlink()
                print(f"   ✅ Removed: {file.name}")
            except Exception as e:
                print(f"   ❌ Failed to remove {file.name}: {e}")
        
        # Remove directory
        try:
            config_dir.rmdir()
            print(f"   ✅ Removed directory: {config_dir}")
        except Exception as e:
            print(f"   ⚠️  Could not remove directory: {e}")
        
        print("\n✅ Credentials reset successfully!")
        print("\n📋 Next steps:")
        print("1. Set up VyprVPN credentials: python3 scripts/manage_credentials.py setup-vyprvpn")
        print("2. Set up OpenVPN credentials (if needed): python3 scripts/manage_credentials.py setup-openvpn")
        print("3. Verify credentials: python3 scripts/manage_credentials.py list")
        
        return True
        
    except Exception as e:
        print(f"❌ Reset failed: {e}")
        return False

def main():
    """Main function"""
    print("🚀 Credential Reset Tool")
    print("=" * 50)
    
    success = reset_credentials()
    
    if success:
        print("\n🎉 Reset completed successfully!")
        sys.exit(0)
    else:
        print("\n💥 Reset failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
