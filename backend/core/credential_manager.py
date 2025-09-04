#!/usr/bin/env python3
"""
Secure Credential Manager for Checklist Creator
Handles VPN credentials securely without exposing them in code
"""

import os
import json
import base64
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import getpass

logger = logging.getLogger(__name__)

class CredentialManager:
    """Secure credential management for VPN and other sensitive data"""
    
    def __init__(self, config_dir: str = None):
        self.config_dir = Path(config_dir or "~/.checklist_creator").expanduser()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Credential files (gitignored)
        self.credentials_file = self.config_dir / "credentials.json"
        self.encrypted_file = self.config_dir / "credentials.enc"
        self.key_file = self.config_dir / ".key"
        
        # Initialize encryption lazily (only when needed)
        self.fernet = None
        self._encryption_initialized = False
    
    def _ensure_encryption_initialized(self):
        """Ensure encryption is initialized when needed"""
        if not self._encryption_initialized:
            self._init_encryption()
            self._encryption_initialized = True
    
    def _init_encryption(self):
        """Initialize encryption key"""
        if not self.key_file.exists():
            # Generate new encryption key
            self._generate_key()
        else:
            # Load existing key
            self._load_key()
    
    def _generate_key(self):
        """Generate new encryption key"""
        try:
            # Get master password from user
            master_password = getpass.getpass("Enter master password for credential encryption: ")
            if not master_password:
                raise ValueError("Master password cannot be empty")
            
            # Generate salt and key
            salt = os.urandom(16)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
            
            # Store salt and encrypted key
            key_data = {
                "salt": base64.b64encode(salt).decode(),
                "key": base64.b64encode(key).decode()
            }
            
            with open(self.key_file, 'w') as f:
                json.dump(key_data, f)
            
            # Set file permissions to user-only
            self.key_file.chmod(0o600)
            
            self.fernet = Fernet(key)
            logger.info("New encryption key generated successfully")
            
        except Exception as e:
            logger.error(f"Failed to generate encryption key: {e}")
            raise
    
    def _load_key(self):
        """Load existing encryption key"""
        try:
            # Try to get master password from automation storage first
            master_password = self._get_master_password_for_automation()
            if not master_password:
                # Fall back to user input
                master_password = getpass.getpass("Enter master password: ")
                if not master_password:
                    raise ValueError("Master password cannot be empty")
            
            # Load salt and key data
            with open(self.key_file, 'r') as f:
                key_data = json.load(f)
            
            # Reconstruct key from password
            salt = base64.b64decode(key_data["salt"])
            stored_key = base64.b64decode(key_data["key"])
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            derived_key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
            
            # Verify key matches
            if derived_key != stored_key:
                raise ValueError("Invalid master password")
            
            self.fernet = Fernet(derived_key)
            logger.info("Encryption key loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load encryption key: {e}")
            raise
    
    def store_credentials(self, service: str, credentials: Dict[str, Any], encrypt: bool = True):
        """Store credentials for a service"""
        try:
            if encrypt:
                # Ensure encryption is initialized
                self._ensure_encryption_initialized()
                
                # Load existing encrypted credentials
                all_credentials = {}
                if self.encrypted_file.exists():
                    try:
                        with open(self.encrypted_file, 'rb') as f:
                            encrypted_data = f.read()
                        
                        decrypted_data = self.fernet.decrypt(encrypted_data)
                        all_credentials = json.loads(decrypted_data.decode())
                    except Exception as e:
                        logger.warning(f"Could not load existing encrypted credentials: {e}")
                        all_credentials = {}
                
                # Add/update the new credentials
                all_credentials[service] = credentials
                
                # Encrypt and store all credentials
                encrypted_data = self.fernet.encrypt(json.dumps(all_credentials).encode())
                
                with open(self.encrypted_file, 'wb') as f:
                    f.write(encrypted_data)
                
                logger.info(f"Credentials for {service} stored securely (encrypted)")
            else:
                # Store in plain JSON (not recommended for production)
                if not self.credentials_file.exists():
                    all_credentials = {}
                else:
                    with open(self.credentials_file, 'r') as f:
                        all_credentials = json.load(f)
                
                all_credentials[service] = credentials
                
                with open(self.credentials_file, 'w') as f:
                    json.dump(all_credentials, f, indent=2)
                
                # Set restrictive permissions
                self.credentials_file.chmod(0o600)
                
                logger.info(f"Credentials for {service} stored (plain text)")
                
        except Exception as e:
            logger.error(f"Failed to store credentials for {service}: {e}")
            raise
    
    def get_credentials(self, service: str, decrypt: bool = True) -> Optional[Dict[str, Any]]:
        """Retrieve credentials for a service"""
        try:
            if decrypt and self.encrypted_file.exists():
                # Ensure encryption is initialized
                self._ensure_encryption_initialized()
                
                # Load and decrypt credentials
                with open(self.encrypted_file, 'rb') as f:
                    encrypted_data = f.read()
                
                decrypted_data = self.fernet.decrypt(encrypted_data)
                all_credentials = json.loads(decrypted_data.decode())
                
                # Return the specific service credentials
                if service in all_credentials:
                    return all_credentials[service]
                else:
                    logger.warning(f"Service '{service}' not found in stored credentials")
                    return None
                
            elif not decrypt and self.credentials_file.exists():
                # Load plain text credentials
                with open(self.credentials_file, 'r') as f:
                    all_credentials = json.load(f)
                
                if service in all_credentials:
                    return all_credentials[service]
                else:
                    logger.warning(f"Service '{service}' not found in stored credentials")
                    return None
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to retrieve credentials for {service}: {e}")
            return None
    
    def list_services(self) -> list:
        """List all available credential services"""
        try:
            services = []
            
            if self.encrypted_file.exists():
                # Try to decrypt and list services
                try:
                    # Ensure encryption is initialized
                    self._ensure_encryption_initialized()
                    
                    with open(self.encrypted_file, 'rb') as f:
                        encrypted_data = f.read()
                    
                    decrypted_data = self.fernet.decrypt(encrypted_data)
                    credentials = json.loads(decrypted_data.decode())
                    services.extend(credentials.keys())
                except Exception:
                    logger.warning("Could not decrypt credentials file")
            
            if self.credentials_file.exists():
                # List plain text services
                try:
                    with open(self.credentials_file, 'r') as f:
                        all_credentials = json.load(f)
                    services.extend(all_credentials.keys())
                except Exception:
                    logger.warning("Could not read plain text credentials file")
            
            return list(set(services))
            
        except Exception as e:
            logger.error(f"Failed to list services: {e}")
            return []
    
    def remove_credentials(self, service: str):
        """Remove credentials for a service"""
        try:
            # For encrypted storage, we need to decrypt, modify, and re-encrypt
            if self.encrypted_file.exists():
                credentials = self.get_credentials(service)
                if credentials:
                    # Get all services and remove the specified one
                    all_services = self.list_services()
                    all_services.remove(service)
                    
                    # Re-encrypt remaining credentials
                    remaining_credentials = {}
                    for srv in all_services:
                        creds = self.get_credentials(srv)
                        if creds:
                            remaining_credentials[srv] = creds
                    
                    # Store updated credentials
                    encrypted_data = self.fernet.encrypt(json.dumps(remaining_credentials).encode())
                    with open(self.encrypted_file, 'wb') as f:
                        f.write(encrypted_data)
                    
                    logger.info(f"Credentials for {service} removed")
            
            # For plain text storage
            if self.credentials_file.exists():
                with open(self.credentials_file, 'r') as f:
                    all_credentials = json.load(f)
                
                if service in all_credentials:
                    del all_credentials[service]
                    
                    with open(self.credentials_file, 'w') as f:
                        json.dump(all_credentials, f, indent=2)
                    
                    logger.info(f"Credentials for {service} removed")
                    
        except Exception as e:
            logger.error(f"Failed to remove credentials for {service}: {e}")
            raise
    
    def change_master_password(self):
        """Change the master password"""
        try:
            # Get current password
            current_password = getpass.getpass("Enter current master password: ")
            
            # Verify current password
            self._load_key()
            
            # Get new password
            new_password = getpass.getpass("Enter new master password: ")
            if not new_password:
                raise ValueError("New password cannot be empty")
            
            # Generate new key
            salt = os.urandom(16)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            new_key = base64.urlsafe_b64encode(kdf.derive(new_password.encode()))
            
            # Re-encrypt all credentials with new key
            if self.encrypted_file.exists():
                old_fernet = self.fernet
                
                # Decrypt with old key
                with open(self.encrypted_file, 'rb') as f:
                    encrypted_data = f.read()
                
                decrypted_data = old_fernet.decrypt(encrypted_data)
                credentials = json.loads(decrypted_data.decode())
                
                # Encrypt with new key
                new_fernet = Fernet(new_key)
                encrypted_data = new_fernet.encrypt(json.dumps(credentials).encode())
                
                # Store re-encrypted data
                with open(self.encrypted_file, 'wb') as f:
                    f.write(encrypted_data)
            
            # Update key file
            key_data = {
                "salt": base64.b64encode(salt).decode(),
                "key": base64.b64encode(new_key).decode()
            }
            
            with open(self.key_file, 'w') as f:
                json.dump(key_data, f)
            
            self.fernet = new_fernet
            logger.info("Master password changed successfully")
            
        except Exception as e:
            logger.error(f"Failed to change master password: {e}")
            raise
    
    def get_credential_file_paths(self) -> Dict[str, str]:
        """Get paths to credential files for security review"""
        return {
            'credentials_file': str(self.credentials_file),
            'key_file': str(self.key_file),
            'master_password_env_var': 'CHECKLIST_CREATOR_MASTER_PASSWORD'
        }
    
    def _get_master_password_for_automation(self) -> Optional[str]:
        """Get master password from environment variable for automated jobs"""
        try:
            # Check environment variable first
            env_password = os.environ.get('CHECKLIST_CREATOR_MASTER_PASSWORD')
            if env_password:
                logger.info("Using master password from environment variable")
                return env_password
            
            # Check for a secure file (only readable by the user)
            secure_file = Path("~/.checklist_creator/.master_password").expanduser()
            if secure_file.exists() and secure_file.stat().st_mode & 0o777 == 0o600:
                with open(secure_file, 'r') as f:
                    stored_password = f.read().strip()
                logger.info("Using master password from secure file")
                return stored_password
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get master password for automation: {e}")
            return None
    
    def store_master_password_for_automation(self, password: str, method: str = 'env') -> bool:
        """Store master password for automated jobs
        
        Args:
            password: The master password to store
            method: 'env' for environment variable, 'file' for secure file
        """
        try:
            if method == 'env':
                # Set environment variable (this will only persist for current session)
                os.environ['CHECKLIST_CREATOR_MASTER_PASSWORD'] = password
                logger.info("Master password stored in environment variable")
                return True
                
            elif method == 'file':
                # Store in secure file
                secure_file = Path("~/.checklist_creator/.master_password").expanduser()
                secure_file.parent.mkdir(parents=True, exist_ok=True)
                
                with open(secure_file, 'w') as f:
                    f.write(password)
                
                # Set restrictive permissions (600 = user read/write only)
                secure_file.chmod(0o600)
                logger.info(f"Master password stored in secure file: {secure_file}")
                return True
                
            else:
                logger.error(f"Invalid storage method: {method}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to store master password for automation: {e}")
            return False
    
    def remove_master_password_for_automation(self, method: str = 'file') -> bool:
        """Remove stored master password for automated jobs"""
        try:
            if method == 'env':
                # Remove environment variable
                if 'CHECKLIST_CREATOR_MASTER_PASSWORD' in os.environ:
                    del os.environ['CHECKLIST_CREATOR_MASTER_PASSWORD']
                logger.info("Master password removed from environment variable")
                return True
                
            elif method == 'file':
                # Remove secure file
                secure_file = Path("~/.checklist_creator/.master_password").expanduser()
                if secure_file.exists():
                    secure_file.unlink()
                    logger.info("Master password file removed")
                return True
                
            else:
                logger.error(f"Invalid removal method: {method}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to remove master password for automation: {e}")
            return False

# VPN-specific credential manager
class VPNCredentialManager(CredentialManager):
    """Specialized credential manager for VPN services"""
    
    def __init__(self, config_dir: str = None):
        super().__init__(config_dir)
    
    def store_vyprvpn_credentials(self, username: str, password: str, config_file: str = None):
        """Store VyprVPN credentials securely"""
        credentials = {
            "username": username,
            "password": password,
            "config_file": config_file,
            "provider": "vyprvpn",
            "created_at": self._get_timestamp()
        }
        
        self.store_credentials("vyprvpn", credentials)
    
    def get_vyprvpn_credentials(self) -> Optional[Dict[str, Any]]:
        """Get VyprVPN credentials"""
        return self.get_credentials("vyprvpn")
    
    def store_openvpn_credentials(self, service_name: str, username: str, password: str, 
                                 config_file: str = None, ca_cert: str = None):
        """Store OpenVPN credentials for a specific service"""
        credentials = {
            "username": username,
            "password": password,
            "config_file": config_file,
            "ca_cert": ca_cert,
            "provider": "openvpn",
            "service_name": service_name,
            "created_at": self._get_timestamp()
        }
        
        self.store_credentials(f"openvpn_{service_name}", credentials)
    
    def get_openvpn_credentials(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get OpenVPN credentials for a specific service"""
        return self.get_credentials(f"openvpn_{service_name}")
    
    def list_vpn_providers(self) -> list:
        """List all configured VPN providers"""
        services = self.list_services()
        vpn_services = [s for s in services if s.startswith(('vyprvpn', 'openvpn_'))]
        return vpn_services
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()

# Global credential manager instance
credential_manager = VPNCredentialManager()

def get_credential_manager() -> VPNCredentialManager:
    """Get the global credential manager instance"""
    return credential_manager
