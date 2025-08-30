#!/bin/bash

# VPN Health Check Script
# Monitors VPN connection health and reports status

echo "🔍 VPN Health Check - $(date)"

# Check if OpenVPN is running
if pgrep -f "openvpn" > /dev/null; then
    echo "✅ OpenVPN process: RUNNING"
    
    # Check connection status
    if curl -s --connect-timeout 10 https://httpbin.org/ip > /dev/null; then
        echo "✅ Internet connectivity: OK"
        
        # Get current IP
        CURRENT_IP=$(curl -s https://httpbin.org/ip | grep -o '"origin":"[^"]*"' | cut -d'"' -f4)
        echo "🌐 Current IP: $CURRENT_IP"
        
        # Test ping
        if ping -c 1 8.8.8.8 > /dev/null 2>&1; then
            echo "✅ Ping test: OK"
        else
            echo "❌ Ping test: FAILED"
        fi
        
    else
        echo "❌ Internet connectivity: FAILED"
    fi
    
else
    echo "❌ OpenVPN process: NOT RUNNING"
fi

echo "---"
