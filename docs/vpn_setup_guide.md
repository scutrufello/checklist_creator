# VPN Setup Guide for Checklist Creator

## Overview

This guide explains how to set up and configure VPN connections for the Checklist Creator project.

## Prerequisites

- Ubuntu 22.04 LTS
- OpenVPN installed
- Sudo privileges
- VPN provider credentials

## Configuration Files

### 1. OpenVPN Configuration Files

Configuration files are stored in `/etc/openvpn/configs/` and should have the `.ovpn` extension.

Example configuration structure:
```
/etc/openvpn/configs/
├── us-east.ovpn      # US East Coast
├── us-west.ovpn      # US West Coast
├── eu-west.ovpn      # Europe West
└── asia-east.ovpn    # Asia East
```

### 2. Authentication File

The authentication file `/etc/openvpn/auth.txt` contains your VPN credentials:
```
username
password
```

**Important**: Keep this file secure and set proper permissions (600).

## Usage

### Basic Commands

1. **Check VPN Status**:
   ```bash
   ./scripts/manage_vpn.sh status
   ```

2. **Connect to VPN**:
   ```bash
   ./scripts/manage_vpn.sh connect us-east
   ```

3. **Disconnect from VPN**:
   ```bash
   ./scripts/manage_vpn.sh disconnect
   ```

4. **Test VPN Connection**:
   ```bash
   ./scripts/manage_vpn.sh test
   ```

### API Endpoints

Once the application is running, you can use these API endpoints:

- `GET /api/v1/vpn/status` - Get VPN status
- `POST /api/v1/vpn/connect` - Connect to VPN
- `POST /api/v1/vpn/disconnect` - Disconnect from VPN
- `GET /api/v1/vpn/health` - Check VPN health
- `GET /api/v1/vpn/metrics` - Get performance metrics

## Adding New VPN Configurations

1. **Obtain Configuration File**: Download `.ovpn` file from your VPN provider
2. **Install Configuration**:
   ```bash
   ./scripts/manage_vpn.sh install-config ~/Downloads/my-vpn.ovpn
   ```
3. **Update Configuration**: Edit the configuration file if needed
4. **Test Connection**: Use the test command to verify

## Troubleshooting

### Common Issues

1. **Permission Denied**: Ensure proper file permissions
2. **Connection Failed**: Check credentials and configuration
3. **DNS Issues**: Verify DNS configuration in OpenVPN config

### Logs

Check VPN logs for detailed error information:
```bash
./scripts/manage_vpn.sh logs
```

### Health Monitoring

Run regular health checks:
```bash
./scripts/vpn_health_check.sh
```

## Security Considerations

- Keep authentication files secure
- Use strong passwords
- Regularly update OpenVPN
- Monitor connection logs
- Use firewall rules appropriately

## Next Steps

After setting up VPN configurations:

1. Test basic connectivity
2. Configure the application
3. Set up automated health monitoring
4. Test failover scenarios
