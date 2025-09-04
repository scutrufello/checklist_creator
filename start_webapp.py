#!/usr/bin/env python3
"""
Startup script for Phillies Cards Webapp
"""

import uvicorn
import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

if __name__ == "__main__":
    print("🚀 Starting Phillies Cards Webapp...")
    print("📱 Open your browser to: http://localhost:8000")
    print("🔧 API docs available at: http://localhost:8000/docs")
    print("⏹️  Press Ctrl+C to stop the server")
    print()
    
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload for development
        reload_dirs=["backend/api", "static"],  # Only watch webapp files
        log_level="info"
    )
