#!/bin/bash

# Development Environment Setup Script for Checklist Creator
# This script sets up the complete development environment on Ubuntu 22.04 LTS

set -e  # Exit on any error

echo "🚀 Setting up Checklist Creator Development Environment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Update system packages
print_status "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install essential system packages
print_status "Installing essential system packages..."
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

# Install Python 3.11 if not available
if ! command -v python3.11 &> /dev/null; then
    print_status "Python 3.11 not found, adding deadsnakes PPA..."
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update
    sudo apt install -y python3.11 python3.11-venv python3.11-dev
fi

# Configure PostgreSQL
print_status "Configuring PostgreSQL..."
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Create database user and database
sudo -u postgres psql -c "CREATE USER checklist_user WITH PASSWORD 'checklist_password';"
sudo -u postgres psql -c "CREATE DATABASE checklist_db OWNER checklist_user;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE checklist_db TO checklist_user;"

# Configure Redis
print_status "Configuring Redis..."
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Configure SSH
print_status "Configuring SSH server..."
sudo systemctl enable ssh
sudo systemctl start ssh

# Configure firewall
print_status "Configuring firewall..."
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw allow 8000  # FastAPI development server
sudo ufw --force enable

# Create project directory structure
print_status "Creating project directory structure..."
mkdir -p ~/checklist_creator/{backend,frontend,docs,scripts,tests,logs}

# Set up Python virtual environment
print_status "Setting up Python virtual environment..."
cd ~/checklist_creator
python3.11 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install Python dependencies
print_status "Installing Python dependencies..."
pip install -r requirements.txt

# Install development tools
print_status "Installing development tools..."
pip install \
    black \
    flake8 \
    isort \
    mypy \
    pytest \
    pytest-cov \
    pytest-asyncio

# Configure Git
print_status "Configuring Git..."
git config --global user.name "Checklist Creator Developer"
git config --global user.email "developer@checklistcreator.local"

# Create .env file
print_status "Creating environment configuration..."
cat > ~/checklist_creator/.env << EOF
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

# Create development scripts
print_status "Creating development scripts..."

# Start development server script
cat > ~/checklist_creator/scripts/start_dev.sh << 'EOF'
#!/bin/bash
cd ~/checklist_creator
source venv/bin/activate
echo "🚀 Starting Checklist Creator development server..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
EOF

# Database management script
cat > ~/checklist_creator/scripts/manage_db.sh << 'EOF'
#!/bin/bash
cd ~/checklist_creator
source venv/bin/activate

case "$1" in
    "start")
        sudo systemctl start postgresql
        sudo systemctl start redis-server
        echo "✅ Database services started"
        ;;
    "stop")
        sudo systemctl stop postgresql
        sudo systemctl stop redis-server
        echo "🛑 Database services stopped"
        ;;
    "status")
        echo "PostgreSQL: $(systemctl is-active postgresql)"
        echo "Redis: $(systemctl is-active redis-server)"
        ;;
    "reset")
        sudo -u postgres psql -c "DROP DATABASE IF EXISTS checklist_db;"
        sudo -u postgres psql -c "CREATE DATABASE checklist_db OWNER checklist_user;"
        echo "🔄 Database reset complete"
        ;;
    *)
        echo "Usage: $0 {start|stop|status|reset}"
        exit 1
        ;;
esac
EOF

# VPN management script
cat > ~/checklist_creator/scripts/manage_vpn.sh << 'EOF'
#!/bin/bash
cd ~/checklist_creator
source venv/bin/activate

case "$1" in
    "status")
        echo "🔍 Checking VPN status..."
        # Add VPN status checking logic here
        ;;
    "connect")
        echo "🔌 Connecting to VPN..."
        # Add VPN connection logic here
        ;;
    "disconnect")
        echo "🔌 Disconnecting from VPN..."
        # Add VPN disconnection logic here
        ;;
    *)
        echo "Usage: $0 {status|connect|disconnect}"
        exit 1
        ;;
esac
EOF

# Make scripts executable
chmod +x ~/checklist_creator/scripts/*.sh

# Create basic backend structure
print_status "Creating basic backend structure..."
mkdir -p ~/checklist_creator/backend/{api,core,db,models,schemas,services,utils}

# Create basic frontend structure
print_status "Creating basic frontend structure..."
mkdir -p ~/checklist_creator/frontend/{src,public,components,pages,styles}

# Create basic test structure
print_status "Creating basic test structure..."
mkdir -p ~/checklist_creator/tests/{unit,integration,e2e}

# Create basic documentation
print_status "Creating basic documentation..."
mkdir -p ~/checklist_creator/docs/{api,deployment,development,user}

# Set up VS Code Server (if available)
if command -v code-server &> /dev/null; then
    print_status "VS Code Server is already installed"
else
    print_status "Installing VS Code Server..."
    curl -fsSL https://code-server.dev/install.sh | sh
    sudo systemctl enable --now code-server@$USER
fi

# Final configuration
print_status "Finalizing setup..."

# Create a simple health check script
cat > ~/checklist_creator/scripts/health_check.sh << 'EOF'
#!/bin/bash
echo "🔍 Health Check for Checklist Creator Environment"

echo "✅ Python: $(python3.11 --version)"
echo "✅ PostgreSQL: $(systemctl is-active postgresql)"
echo "✅ Redis: $(systemctl is-active redis-server)"
echo "✅ SSH: $(systemctl is-active ssh)"
echo "✅ UFW: $(ufw status | grep Status)"

echo "✅ Virtual Environment: $(source venv/bin/activate && which python)"
echo "✅ Dependencies: $(pip list | wc -l) packages installed"
EOF

chmod +x ~/checklist_creator/scripts/health_check.sh

# Print completion message
print_success "Development environment setup completed successfully!"
echo ""
echo "🎉 Your Checklist Creator development environment is ready!"
echo ""
echo "📁 Project location: ~/checklist_creator"
echo "🐍 Python virtual environment: ~/checklist_creator/venv"
echo "🗄️  Database: PostgreSQL (checklist_db)"
echo "🔴 Cache: Redis"
echo "🌐 Web server: Nginx"
echo "🔒 Firewall: UFW (configured)"
echo ""
echo "🚀 Quick start commands:"
echo "  cd ~/checklist_creator"
echo "  source venv/bin/activate"
echo "  ./scripts/start_dev.sh"
echo ""
echo "🔍 Health check:"
echo "  ./scripts/health_check.sh"
echo ""
echo "📚 Next steps:"
echo "  1. Review and customize .env file"
echo "  2. Set up VPN configurations"
echo "  3. Configure web scraping targets"
echo "  4. Start developing!"
echo ""
print_success "Setup complete! Happy coding! 🚀"
