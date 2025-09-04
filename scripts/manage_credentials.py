#!/usr/bin/env python3
"""
Secure Credential Management CLI for Checklist Creator
Provides command-line interface for managing VPN credentials securely
"""

import asyncio
import sys
import argparse
import getpass
from pathlib import Path

# Add the backend directory to the Python path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from core.credential_manager import get_credential_manager

class CredentialCLI:
    """Command-line interface for credential management"""
    
    def __init__(self):
        self.manager = get_credential_manager()
    
    def setup_vyprvpn(self):
        """Set up VyprVPN credentials"""
        print("🔐 Setting up VyprVPN Credentials")
        print("=" * 50)
        
        try:
            # Get credentials from user
            username = input("Enter VyprVPN username: ").strip()
            if not username:
                print("❌ Username cannot be empty")
                return False
            
            password = getpass.getpass("Enter VyprVPN password: ").strip()
            if not password:
                print("❌ Password cannot be empty")
                return False
            
            # Optional config file
            config_file = input("Enter path to VyprVPN .ovpn config file (optional): ").strip()
            if config_file and not Path(config_file).exists():
                print(f"⚠️ Warning: Config file {config_file} does not exist")
                proceed = input("Continue anyway? (y/N): ").strip().lower()
                if proceed != 'y':
                    return False
            
            # Store credentials
            self.manager.store_vyprvpn_credentials(username, password, config_file)
            
            print("✅ VyprVPN credentials stored securely!")
            return True
            
        except Exception as e:
            print(f"❌ Failed to store VyprVPN credentials: {e}")
            return False
    
    def setup_openvpn(self):
        """Set up OpenVPN credentials for a service"""
        print("🔐 Setting up OpenVPN Credentials")
        print("=" * 50)
        
        try:
            # Get service details
            service_name = input("Enter service name (e.g., 'us-east', 'eu-west'): ").strip()
            if not service_name:
                print("❌ Service name cannot be empty")
                return False
            
            username = input("Enter OpenVPN username: ").strip()
            if not username:
                print("❌ Username cannot be empty")
                return False
            
            password = getpass.getpass("Enter OpenVPN password: ").strip()
            if not password:
                print("❌ Password cannot be empty")
                return False
            
            # Optional config file
            config_file = input("Enter path to OpenVPN .ovpn config file (optional): ").strip()
            if config_file and not Path(config_file).exists():
                print(f"⚠️ Warning: Config file {config_file} does not exist")
                proceed = input("Continue anyway? (y/N): ").strip().lower()
                if proceed != 'y':
                    return False
            
            # Optional CA certificate
            ca_cert = input("Enter path to CA certificate file (optional): ").strip()
            if ca_cert and not Path(ca_cert).exists():
                print(f"⚠️ Warning: CA certificate {ca_cert} does not exist")
                proceed = input("Continue anyway? (y/N): ").strip().lower()
                if proceed != 'y':
                    return False
            
            # Store credentials
            self.manager.store_openvpn_credentials(service_name, username, password, config_file, ca_cert)
            
            print(f"✅ OpenVPN credentials for '{service_name}' stored securely!")
            return True
            
        except Exception as e:
            print(f"❌ Failed to store OpenVPN credentials: {e}")
            return False
    
    def list_credentials(self):
        """List all stored credentials"""
        print("📋 Stored Credentials")
        print("=" * 50)
        
        try:
            services = self.manager.list_services()
            
            if not services:
                print("ℹ️ No credentials stored yet")
                return True
            
            print(f"Found {len(services)} credential service(s):")
            print()
            
            for service in sorted(services):
                print(f"🔑 {service}")
                
                # Try to get credential details (without showing sensitive data)
                try:
                    creds = self.manager.get_credentials(service)
                    if creds:
                        provider = creds.get('provider', 'unknown')
                        created = creds.get('created_at', 'unknown')
                        print(f"   Provider: {provider}")
                        print(f"   Created: {created}")
                        
                        if 'username' in creds:
                            print(f"   Username: {creds['username']}")
                        
                        if 'config_file' in creds and creds['config_file']:
                            print(f"   Config: {creds['config_file']}")
                        
                        if 'ca_cert' in creds and creds['ca_cert']:
                            print(f"   CA Cert: {creds['ca_cert']}")
                        
                        print()
                except Exception as e:
                    print(f"   Error reading details: {e}")
                    print()
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to list credentials: {e}")
            return False
    
    def show_credential_details(self, service: str):
        """Show detailed information about a specific credential service"""
        print(f"🔍 Credential Details for: {service}")
        print("=" * 50)
        
        try:
            creds = self.manager.get_credentials(service)
            
            if not creds:
                print(f"❌ No credentials found for service '{service}'")
                return False
            
            print("✅ Credentials found!")
            print()
            print(f"Provider: {creds.get('provider', 'unknown')}")
            print(f"Created: {creds.get('created_at', 'unknown')}")
            print(f"Username: {creds.get('username', 'not set')}")
            
            if 'config_file' in creds and creds['config_file']:
                config_path = Path(creds['config_file'])
                print(f"Config File: {creds['config_file']}")
                print(f"Config Exists: {'✅ Yes' if config_path.exists() else '❌ No'}")
            
            if 'ca_cert' in creds and creds['ca_cert']:
                ca_path = Path(creds['ca_cert'])
                print(f"CA Certificate: {creds['ca_cert']}")
                print(f"CA Cert Exists: {'✅ Yes' if ca_path.exists() else '❌ No'}")
            
            if 'service_name' in creds:
                print(f"Service Name: {creds['service_name']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to show credential details: {e}")
            return False
    
    def remove_credentials(self, service: str):
        """Remove credentials for a service"""
        print(f"🗑️ Removing Credentials for: {service}")
        print("=" * 50)
        
        try:
            # Confirm removal
            confirm = input(f"Are you sure you want to remove credentials for '{service}'? (y/N): ").strip().lower()
            if confirm != 'y':
                print("❌ Operation cancelled")
                return False
            
            # Remove credentials
            self.manager.remove_credentials(service)
            
            print(f"✅ Credentials for '{service}' removed successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Failed to remove credentials: {e}")
            return False
    
    def change_master_password(self):
        """Change the master password"""
        print("🔐 Change Master Password")
        print("=" * 50)
        
        try:
            print("⚠️ This will re-encrypt all stored credentials with a new master password.")
            confirm = input("Continue? (y/N): ").strip().lower()
            if confirm != 'y':
                print("❌ Operation cancelled")
                return False
            
            # Change master password
            self.manager.change_master_password()
            
            print("✅ Master password changed successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Failed to change master password: {e}")
            return False
    
    def show_security_info(self):
        """Show security information and file paths"""
        print("🔒 Security Information")
        print("=" * 50)
        
        try:
            file_paths = self.manager.get_credential_file_paths()
            
            print("Credential files are stored in:")
            print(f"Config Directory: {file_paths['config_dir']}")
            print(f"Credentials File: {file_paths['credentials_file']}")
            print(f"Encrypted File: {file_paths['encrypted_file']}")
            print(f"Key File: {file_paths['key_file']}")
            print()
            
            print("Security Features:")
            print("✅ Credentials are encrypted using Fernet (AES-128-CBC)")
            print("✅ Master password is derived using PBKDF2 with 100,000 iterations")
            print("✅ Key file has restricted permissions (600)")
            print("✅ All credential files are gitignored")
            print()
            
            print("⚠️ Security Recommendations:")
            print("• Keep your master password secure and don't share it")
            print("• Regularly change your master password")
            print("• Backup your credential files securely")
            print("• Use strong, unique passwords for each VPN service")
            print("• Consider using a password manager for the master password")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to show security info: {e}")
            return False
    
    def test_credentials(self, service: str):
        """Test if credentials for a service are valid"""
        print(f"🧪 Testing Credentials for: {service}")
        print("=" * 50)
        
        try:
            creds = self.manager.get_credentials(service)
            
            if not creds:
                print(f"❌ No credentials found for service '{service}'")
                return False
            
            print("✅ Credentials loaded successfully!")
            print()
            
            # Test config file existence
            if 'config_file' in creds and creds['config_file']:
                config_path = Path(creds['config_file'])
                if config_path.exists():
                    print(f"✅ Config file exists: {creds['config_file']}")
                    
                    # Check if it's a valid OpenVPN config
                    try:
                        with open(config_path, 'r') as f:
                            content = f.read()
                            if 'client' in content and 'remote' in content:
                                print("✅ Config file appears to be valid OpenVPN configuration")
                            else:
                                print("⚠️ Config file may not be valid OpenVPN configuration")
                    except Exception as e:
                        print(f"❌ Error reading config file: {e}")
                else:
                    print(f"❌ Config file not found: {creds['config_file']}")
            
            # Test CA certificate existence
            if 'ca_cert' in creds and creds['ca_cert']:
                ca_path = Path(creds['ca_cert'])
                if ca_path.exists():
                    print(f"✅ CA certificate exists: {creds['ca_cert']}")
                else:
                    print(f"❌ CA certificate not found: {creds['ca_cert']}")
            
            print()
            print("🎯 Credentials are ready for use!")
            return True
            
        except Exception as e:
            print(f"❌ Failed to test credentials: {e}")
            return False

def main():
    """Main CLI function"""
    parser = argparse.ArgumentParser(
        description="Secure Credential Management for Checklist Creator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage_credentials.py setup-vyprvpn          # Set up VyprVPN credentials
  python manage_credentials.py setup-openvpn          # Set up OpenVPN credentials
  python manage_credentials.py list                   # List all credentials
  python manage_credentials.py show vyprvpn           # Show VyprVPN details
  python manage_credentials.py remove vyprvpn         # Remove VyprVPN credentials
  python manage_credentials.py test vyprvpn           # Test VyprVPN credentials
  python manage_credentials.py change-password        # Change master password
  python manage_credentials.py security               # Show security information
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Setup commands
    subparsers.add_parser('setup-vyprvpn', help='Set up VyprVPN credentials')
    subparsers.add_parser('setup-openvpn', help='Set up OpenVPN credentials')
    
    # Management commands
    subparsers.add_parser('list', help='List all stored credentials')
    show_parser = subparsers.add_parser('show', help='Show credential details')
    show_parser.add_argument('service', help='Service name to show details for')
    
    remove_parser = subparsers.add_parser('remove', help='Remove credentials')
    remove_parser.add_argument('service', help='Service name to remove credentials for')
    
    test_parser = subparsers.add_parser('test', help='Test credentials')
    test_parser.add_argument('service', help='Service name to test credentials for')
    
    # Security commands
    subparsers.add_parser('change-password', help='Change master password')
    subparsers.add_parser('security', help='Show security information')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Create CLI manager
    cli = CredentialCLI()
    
    # Execute command
    try:
        if args.command == 'setup-vyprvpn':
            success = cli.setup_vyprvpn()
        elif args.command == 'setup-openvpn':
            success = cli.setup_openvpn()
        elif args.command == 'list':
            success = cli.list_credentials()
        elif args.command == 'show':
            success = cli.show_credential_details(args.service)
        elif args.command == 'remove':
            success = cli.remove_credentials(args.service)
        elif args.command == 'test':
            success = cli.test_credentials(args.service)
        elif args.command == 'change-password':
            success = cli.change_master_password()
        elif args.command == 'security':
            success = cli.show_security_info()
        else:
            print(f"❌ Unknown command: {args.command}")
            success = False
        
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⏹️ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
