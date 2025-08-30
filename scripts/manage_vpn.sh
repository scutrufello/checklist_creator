#!/bin/bash

# VPN Management Script for Checklist Creator
# This script provides easy VPN management commands

VPN_CONFIG_DIR="/etc/openvpn/configs"
VPN_LOG_DIR="/var/log/openvpn"

case "$1" in
    "status")
        echo "🔍 Checking VPN status..."
        if pgrep -f "openvpn" > /dev/null; then
            echo "✅ OpenVPN is running"
            ps aux | grep openvpn | grep -v grep
        else
            echo "❌ OpenVPN is not running"
        fi
        
        # Check current IP
        echo "🌐 Current IP address:"
        curl -s https://httpbin.org/ip | grep -o '"origin":"[^"]*"' | cut -d'"' -f4
        ;;
    
    "connect")
        if [ -z "$2" ]; then
            echo "Usage: $0 connect <config-name>"
            echo "Available configs:"
            ls -1 $VPN_CONFIG_DIR/*.ovpn | sed 's/.*\///' | sed 's/\.ovpn$//'
            exit 1
        fi
        
        CONFIG_FILE="$VPN_CONFIG_DIR/$2.ovpn"
        if [ ! -f "$CONFIG_FILE" ]; then
            echo "❌ Configuration file $CONFIG_FILE not found"
            exit 1
        fi
        
        echo "🔌 Connecting to VPN using $2 configuration..."
        sudo openvpn --config "$CONFIG_FILE" --daemon
        sleep 3
        
        if pgrep -f "openvpn" > /dev/null; then
            echo "✅ VPN connected successfully"
        else
            echo "❌ VPN connection failed"
        fi
        ;;
    
    "disconnect")
        echo "🔌 Disconnecting VPN..."
        sudo pkill -f "openvpn"
        sleep 2
        
        if pgrep -f "openvpn" > /dev/null; then
            echo "❌ Failed to disconnect VPN"
        else
            echo "✅ VPN disconnected successfully"
        fi
        ;;
    
    "logs")
        echo "📋 VPN logs:"
        if [ -f "$VPN_LOG_DIR/client.log" ]; then
            tail -20 "$VPN_LOG_DIR/client.log"
        else
            echo "No VPN logs found"
        fi
        ;;
    
    "test")
        echo "🧪 Testing VPN connection..."
        
        # Test basic connectivity
        if ping -c 1 8.8.8.8 > /dev/null 2>&1; then
            echo "✅ Basic connectivity: OK"
        else
            echo "❌ Basic connectivity: FAILED"
        fi
        
        # Test DNS resolution
        if nslookup google.com > /dev/null 2>&1; then
            echo "✅ DNS resolution: OK"
        else
            echo "❌ DNS resolution: FAILED"
        fi
        
        # Test external IP
        echo "🌐 External IP address:"
        curl -s https://httpbin.org/ip | grep -o '"origin":"[^"]*"' | cut -d'"' -f4
        ;;
    
    "install-config")
        if [ -z "$2" ]; then
            echo "Usage: $0 install-config <config-file>"
            echo "This will install a new OpenVPN configuration file"
            exit 1
        fi
        
        if [ ! -f "$2" ]; then
            echo "❌ File $2 not found"
            exit 1
        fi
        
        CONFIG_NAME=$(basename "$2" .ovpn)
        echo "📁 Installing configuration: $CONFIG_NAME"
        sudo cp "$2" "$VPN_CONFIG_DIR/"
        sudo chown root:root "$VPN_CONFIG_DIR/$CONFIG_NAME.ovpn"
        sudo chmod 644 "$VPN_CONFIG_DIR/$CONFIG_NAME.ovpn"
        echo "✅ Configuration installed successfully"
        ;;
    
    "list-configs")
        echo "📁 Available VPN configurations:"
        ls -1 $VPN_CONFIG_DIR/*.ovpn | sed 's/.*\///' | sed 's/\.ovpn$//'
        ;;
    
    *)
        echo "Usage: $0 {status|connect|disconnect|logs|test|install-config|list-configs}"
        echo ""
        echo "Commands:"
        echo "  status          - Check VPN status"
        echo "  connect <name>  - Connect to VPN using specified config"
        echo "  disconnect      - Disconnect from VPN"
        echo "  logs            - Show VPN logs"
        echo "  test            - Test VPN connection"
        echo "  install-config  - Install new OpenVPN configuration"
        echo "  list-configs    - List available configurations"
        echo ""
        echo "Examples:"
        echo "  $0 status"
        echo "  $0 connect us-east"
        echo "  $0 disconnect"
        echo "  $0 install-config ~/Downloads/my-vpn.ovpn"
        exit 1
        ;;
esac
