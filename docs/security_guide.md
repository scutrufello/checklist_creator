# Security Guide for Checklist Creator

## 🔐 **VPN Credential Security**

This guide explains how to securely manage VPN credentials in the Checklist Creator system while keeping your code safe on GitHub.

## ⚠️ **Critical Security Rules**

### 1. **NEVER Commit Credentials to Git**
- ❌ No hardcoded usernames/passwords
- ❌ No credential files in repository
- ❌ No secrets in environment variables (if they might be logged)
- ❌ No API keys in code comments

### 2. **ALWAYS Use Secure Storage**
- ✅ Encrypted credential manager
- ✅ Environment-specific configuration
- ✅ Secure file permissions
- ✅ Master password protection

## 🛡️ **How the System Protects You**

### **Encrypted Credential Storage**
The system uses industry-standard encryption to protect your VPN credentials:

- **Algorithm**: Fernet (AES-128-CBC with HMAC)
- **Key Derivation**: PBKDF2 with 100,000 iterations
- **Salt**: 16-byte random salt for each key
- **File Permissions**: 600 (user-only access)

### **Secure File Locations**
Credentials are stored in your home directory, outside the project folder:

```
~/.checklist_creator/
├── credentials.enc    # Encrypted credentials
├── .key              # Encryption key (derived from master password)
└── credentials.json  # Plain text (if encryption disabled)
```

### **Git Protection**
The `.gitignore` file automatically prevents credential files from being committed:

```gitignore
# Credential files
~/.checklist_creator/
credentials.json
credentials.enc
.key
*.key

# VPN configs
*.ovpn
*.pem
*.crt
auth.txt
```

## 🚀 **Setting Up Secure Credentials**

### **Step 1: Install Dependencies**
```bash
pip install -r requirements.txt
```

### **Step 2: Set Up VyprVPN Credentials**
```bash
python scripts/manage_credentials.py setup-vyprvpn
```

The system will prompt you for:
- VyprVPN username
- VyprVPN password
- Optional .ovpn config file path

### **Step 3: Set Up OpenVPN Credentials (if needed)**
```bash
python scripts/manage_credentials.py setup-openvpn
```

### **Step 4: Verify Security**
```bash
python scripts/manage_credentials.py security
```

## 🔍 **Managing Your Credentials**

### **List All Credentials**
```bash
python scripts/manage_credentials.py list
```

### **Show Specific Credential Details**
```bash
python scripts/manage_credentials.py show vyprvpn
```

### **Test Credentials**
```bash
python scripts/manage_credentials.py test vyprvpn
```

### **Remove Credentials**
```bash
python scripts/manage_credentials.py remove vyprvpn
```

### **Change Master Password**
```bash
python scripts/manage_credentials.py change-password
```

## 🔒 **Security Features Explained**

### **1. Master Password Protection**
- Your master password is never stored
- It's used to derive the encryption key
- Key derivation uses PBKDF2 with 100,000 iterations
- Salt prevents rainbow table attacks

### **2. File Encryption**
- All credentials are encrypted before storage
- Encryption key is derived from your master password
- Files are stored with restrictive permissions (600)
- No plain text passwords in files

### **3. Secure Access**
- Credentials are only decrypted when needed
- Memory is cleared after use
- No credential logging
- Secure input handling (getpass for passwords)

## 📋 **Best Practices**

### **Master Password Security**
- Use a strong, unique master password
- Consider using a password manager
- Never share your master password
- Change it regularly
- Use at least 16 characters with mixed types

### **VPN Credential Security**
- Use unique passwords for each VPN service
- Regularly rotate VPN passwords
- Don't reuse passwords from other services
- Use strong, random passwords

### **File Security**
- Keep your home directory secure
- Don't share credential files
- Backup credentials securely
- Use full disk encryption if possible

### **Network Security**
- Only access credentials from trusted networks
- Use VPN when accessing from public networks
- Monitor for suspicious access patterns
- Keep your system updated

## 🚨 **Security Checklist**

Before pushing to GitHub, verify:

- [ ] No credential files in project directory
- [ ] No hardcoded passwords in code
- [ ] No API keys in comments
- [ ] `.gitignore` includes all sensitive files
- [ ] Configuration template is used (not real config)
- [ ] Environment variables are properly set
- [ ] No secrets in log files
- [ ] Credential manager is working

## 🔧 **Troubleshooting Security Issues**

### **Problem: Credentials Not Loading**
```bash
# Check if credential manager is working
python scripts/manage_credentials.py list

# Verify file permissions
ls -la ~/.checklist_creator/

# Check for encryption errors
python scripts/manage_credentials.py security
```

### **Problem: Master Password Issues**
```bash
# Reset master password (WARNING: This will re-encrypt all credentials)
python scripts/manage_credentials.py change-password
```

### **Problem: File Permission Issues**
```bash
# Fix file permissions
chmod 600 ~/.checklist_creator/.key
chmod 600 ~/.checklist_creator/credentials.enc
chmod 700 ~/.checklist_creator/
```

## 🆘 **Emergency Procedures**

### **If Credentials Are Compromised**
1. **Immediate Actions**:
   - Change all VPN passwords
   - Change master password
   - Remove compromised credential files
   - Check for unauthorized access

2. **Recovery Steps**:
   - Re-enter credentials securely
   - Verify all systems are working
   - Monitor for suspicious activity
   - Update security practices

### **If Master Password Is Lost**
1. **Recovery Options**:
   - Credentials cannot be recovered without master password
   - You must re-enter all credentials
   - This is by design for security

2. **Prevention**:
   - Store master password securely
   - Use password manager
   - Create secure backup
   - Share with trusted family member

## 📚 **Additional Security Resources**

### **Cryptography Standards**
- [NIST Cryptographic Standards](https://www.nist.gov/cryptography)
- [OWASP Security Guidelines](https://owasp.org/)
- [Python Cryptography Documentation](https://cryptography.io/)

### **VPN Security**
- [VPN Security Best Practices](https://www.vpnmentor.com/blog/vpn-security-guide/)
- [OpenVPN Security](https://openvpn.net/community-resources/security-overview/)

### **General Security**
- [GitHub Security Best Practices](https://docs.github.com/en/github/authenticating-to-github/keeping-your-account-and-data-secure)
- [Linux Security](https://wiki.archlinux.org/title/Security)

## 🎯 **Security Summary**

The Checklist Creator system provides enterprise-grade security for your VPN credentials:

✅ **Encrypted Storage**: AES-128-CBC encryption with HMAC  
✅ **Secure Key Derivation**: PBKDF2 with 100,000 iterations  
✅ **File Protection**: Restrictive permissions and secure locations  
✅ **Git Safety**: Automatic protection against credential commits  
✅ **Access Control**: Master password protection for all credentials  
✅ **Audit Trail**: Secure logging and monitoring capabilities  

## 📞 **Getting Help**

If you encounter security issues:

1. **Check the troubleshooting section above**
2. **Review the security information**: `python scripts/manage_credentials.py security`
3. **Verify file permissions and locations**
4. **Check system logs for errors**
5. **Contact the development team if needed**

---

**Remember**: Security is a shared responsibility. Keep your master password secure, use strong credentials, and never share sensitive information.

**Last Updated**: August 24, 2024  
**Version**: 1.0.0  
**Security Level**: Enterprise Grade
