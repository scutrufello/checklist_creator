# Development Environment Setup Guide

## Overview

This guide provides step-by-step instructions for setting up the complete development environment for the Checklist Creator project on Ubuntu 22.04 LTS.

## Prerequisites

### System Requirements
- **OS**: Ubuntu 22.04 LTS (Desktop or Server)
- **RAM**: Minimum 20GB (Recommended: 32GB+)
- **CPU**: Minimum 8 cores (Recommended: 16 cores+)
- **Storage**: Minimum 200GB (Recommended: 512GB+)
- **Network**: Direct internet access (bridged networking for VPN functionality)

### Hyper-V Configuration (Windows Host)
- Windows 10/11 Pro with Hyper-V enabled
- External network switch configured
- VM resources allocated as specified above

## Quick Setup

### Option 1: Automated Setup (Recommended)
```bash
# Clone the repository
git clone <repository-url>
cd checklist_creator

# Make setup script executable
chmod +x scripts/setup_dev_environment.sh

# Run automated setup
./scripts/setup_dev_environment.sh
```

### Option 2: Manual Setup
Follow the detailed steps below if you prefer manual configuration.

## Detailed Setup Steps

### 1. System Package Installation

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install essential packages
sudo apt install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    git \
    curl \
    wget \
    build-essential \
    postgresql \
    postgresql-contrib \
    redis-server \
    nodejs \
    npm \
    nginx \
    ufw \
    openssh-server \
    htop \
    vim \
    tree
```

### 2. Python 3.11 Setup

If Python 3.11 is not available in the default repositories:

```bash
# Add deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

### 3. Database Configuration

#### PostgreSQL Setup
```bash
# Enable and start PostgreSQL
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Create database user and database
sudo -u postgres psql -c "CREATE USER checklist_user WITH PASSWORD 'checklist_password';"
sudo -u postgres psql -c "CREATE DATABASE checklist_db OWNER checklist_user;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE checklist_db TO checklist_user;"
```

#### Redis Setup
```bash
# Enable and start Redis
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Verify Redis is running
redis-cli ping
# Should return: PONG
```

### 4. Security Configuration

#### SSH Configuration
```bash
# Enable and start SSH
sudo systemctl enable ssh
sudo systemctl start ssh

# Verify SSH is running
sudo systemctl status ssh
```

#### Firewall Configuration
```bash
# Configure UFW firewall
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw allow 8000  # FastAPI development server
sudo ufw --force enable

# Verify firewall status
sudo ufw status
```

### 5. Project Setup

#### Clone Repository
```bash
# Navigate to home directory
cd ~

# Clone the repository
git clone <repository-url> checklist_creator
cd checklist_creator
```

#### Python Environment
```bash
# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

#### Environment Configuration
```bash
# Create .env file
cat > .env << EOF
# Database Configuration
DATABASE_URL=postgresql://checklist_user:checklist_password@localhost:5432/checklist_db
REDIS_URL=redis://localhost:6379

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=True

# Security
SECRET_KEY=your-secret-key-here-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# VPN Configuration
VPN_CONFIG_PATH=/etc/openvpn
VPN_LOG_PATH=/var/log/openvpn

# Scraping Configuration
SCRAPING_DELAY=1
SCRAPING_TIMEOUT=30
USER_AGENT=Mozilla/5.0 (compatible; ChecklistCreator/1.0)

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
EOF
```

### 6. Development Tools

#### Code Quality Tools
```bash
# Install development tools
pip install black flake8 isort mypy pytest pytest-cov pytest-asyncio

# Configure Git
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

#### VS Code Server (Optional)
```bash
# Install VS Code Server
curl -fsSL https://code-server.dev/install.sh | sh

# Enable and start VS Code Server
sudo systemctl enable --now code-server@$USER

# Access VS Code Server at: http://your-vm-ip:8080
```

### 7. Project Structure Creation

```bash
# Create project directories
mkdir -p backend/{api,core,db,models,schemas,services,utils}
mkdir -p frontend/{src,public,components,pages,styles}
mkdir -p tests/{unit,integration,e2e}
mkdir -p docs/{api,deployment,development,user}
mkdir -p scripts logs
```

## Verification

### Health Check
```bash
# Run health check script
./scripts/health_check.sh
```

### Test the Application
```bash
# Activate virtual environment
source venv/bin/activate

# Run tests
pytest tests/

# Start development server
python backend/main.py
```

### API Endpoints
- **Health Check**: http://localhost:8000/health
- **API Status**: http://localhost:8000/api/v1/status
- **VPN Status**: http://localhost:8000/api/v1/vpn/status
- **Scraping Status**: http://localhost:8000/api/v1/scraping/status
- **API Documentation**: http://localhost:8000/docs

## Troubleshooting

### Common Issues

#### Python 3.11 Not Found
```bash
# Add deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

#### PostgreSQL Connection Issues
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*.log

# Verify database exists
sudo -u postgres psql -l
```

#### Redis Connection Issues
```bash
# Check Redis status
sudo systemctl status redis-server

# Check Redis logs
sudo tail -f /var/log/redis/redis-server.log

# Test Redis connection
redis-cli ping
```

#### Port Already in Use
```bash
# Check what's using port 8000
sudo netstat -tlnp | grep :8000

# Kill process if necessary
sudo kill -9 <PID>
```

### Performance Optimization

#### Memory Optimization
```bash
# Check memory usage
free -h

# Optimize PostgreSQL memory settings
sudo nano /etc/postgresql/*/main/postgresql.conf
# Adjust shared_buffers, effective_cache_size, etc.
```

#### CPU Optimization
```bash
# Check CPU usage
htop

# Optimize Python processes
# Use multiprocessing for CPU-intensive tasks
```

## Next Steps

After successful setup:

1. **VPN Configuration**: Set up VPN providers and configurations
2. **Web Scraping**: Configure target websites and scraping parameters
3. **Database Schema**: Implement database models and migrations
4. **API Development**: Build out RESTful API endpoints
5. **Frontend Development**: Create user interface components
6. **Testing**: Implement comprehensive test suite
7. **Deployment**: Prepare for production deployment

## Support

For additional support:
- Check the troubleshooting section above
- Review the project documentation
- Create an issue in the GitHub repository
- Check the logs in the `logs/` directory

## Security Notes

⚠️ **Important Security Considerations**:

- Change default passwords in production
- Configure proper firewall rules
- Use HTTPS in production
- Implement proper authentication and authorization
- Regular security updates
- Monitor system logs for suspicious activity

This is a development environment setup. For production deployment, additional security hardening is required.
