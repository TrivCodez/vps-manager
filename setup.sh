#!/bin/bash
# VPS Manager - Full Setup Script

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}    VPS Manager - Installation Script${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# Step 1: Install system packages
echo -e "${YELLOW}[1/8] Installing system packages...${NC}"
sudo apt-get update && sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    python3 \
    python3-pip \
    git \
    socat \
    2>&1 | tail -5

# Step 2: Install Docker
echo -e "${YELLOW}[2/8] Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    newgrp docker << EOF
EOF
fi

if ! systemctl is-active --quiet docker; then
    sudo systemctl start docker
    sudo systemctl enable docker
fi

# Step 3: Install Python packages
echo -e "${YELLOW}[3/8] Installing Python packages...${NC}"
if [ -f requirements.txt ]; then
    sudo pip3 install -r requirements.txt
else
    sudo pip3 install flask==3.0.0 docker==7.0.0 requests==2.31.0 flask-limiter==4.1.1 psutil
fi

# Step 4: Build Docker images
echo -e "${YELLOW}[4/8] Building Docker images...${NC}"

if [ -f Dockerfile.ubuntu ]; then
    echo "Building vps-ubuntu:latest..."
    docker build -f Dockerfile.ubuntu -t vps-ubuntu:latest .
fi

if [ -f Dockerfile.ubuntu26 ]; then
    echo "Building vps-ubuntu26:latest..."
    docker build -f Dockerfile.ubuntu26 -t vps-ubuntu26:latest .
fi

if [ -f Dockerfile.debian ]; then
    echo "Building vps-debian:latest..."
    docker build -f Dockerfile.debian -t vps-debian:latest .
fi

if [ -f Dockerfile.debian13 ]; then
    echo "Building vps-debian13:latest..."
    docker build -f Dockerfile.debian13 -t vps-debian13:latest .
fi

# Step 5: Initialize database
echo -e "${YELLOW}[5/8] Initializing database...${NC}"
if [ ! -f database.db ]; then
    python3 -c "
from app import init_db
init_db()
print('Database initialized successfully!')
"
fi

# Step 6: Default admin
echo -e "${YELLOW}[6/8] Checking default admin...${NC}"
python3 -c "
from app import get_db, hash_password
conn = get_db()
admin = conn.execute('SELECT * FROM users WHERE is_admin = 1').fetchone()
if not admin:
    conn.execute('INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, ?)',
                ('admin', 'admin@vps.com', '$(python3 -c "import hashlib; print(hashlib.sha256(b'admin123').hexdigest())")', 1))
    conn.commit()
    print('Default admin created: admin / admin123')
else:
    print(f'Admin already exists: {admin[\"username\"]}')
conn.close()
"

# Step 7: Verification
echo -e "${YELLOW}[7/8] Verifying installation...${NC}"
echo "  - Docker: $(docker --version 2>/dev/null || echo 'NOT INSTALLED')"
echo "  - Python: $(python3 --version 2>/dev/null || echo 'NOT INSTALLED')"
echo "  - Flask: $(python3 -c 'import flask; print("OK")' 2>/dev/null || echo 'NOT INSTALLED')"
echo "  - Docker SDK: $(python3 -c 'import docker; print("OK")' 2>/dev/null || echo 'NOT INSTALLED')"
echo "  - psutil: $(python3 -c 'import psutil; print("OK")' 2>/dev/null || echo 'NOT INSTALLED')"
echo "  - Database: $([ -f database.db ] && echo 'OK' || echo 'MISSING')"

# List Docker images
echo ""
echo "Docker images:"
docker images --format 'table {{.Repository}}:{{.Tag}}' | grep vps || echo "  No VPS images found - run setup again"

# Step 8: Done
echo -e "${YELLOW}[8/8] Setup complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Setup complete! Starting VPS Manager...${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Default Admin: admin / admin123"
echo "  Web Panel: http://$(curl -s ifconfig.me):5000"
echo ""
echo "  Run: python3 app.py"
echo ""

# Auto-start
python3 app.py