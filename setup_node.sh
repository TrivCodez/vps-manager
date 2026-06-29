#!/bin/bash
# VPS Manager - Node Agent Setup Script
# Run this on a remote machine to make it a VPS node

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  VPS Manager - Node Agent Setup${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

echo -e "${YELLOW}[1/4] Installing system packages...${NC}"
sudo apt-get update && sudo apt-get install -y \
    curl \
    python3 \
    python3-pip \
    socat \
    2>&1 | tail -3

# Step 2: Install Docker
echo -e "${YELLOW}[2/4] Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
fi

if ! systemctl is-active --quiet docker; then
    sudo systemctl start docker
    sudo systemctl enable docker
fi

echo -e "${YELLOW}[3/4] Building Docker images...${NC}"
if [ -f Dockerfile.ubuntu ]; then
    docker build -f Dockerfile.ubuntu -t vps-ubuntu:latest .
fi
if [ -f Dockerfile.ubuntu26 ]; then
    docker build -f Dockerfile.ubuntu26 -t vps-ubuntu26:latest .
fi
if [ -f Dockerfile.debian ]; then
    docker build -f Dockerfile.debian -t vps-debian:latest .
fi
if [ -f Dockerfile.debian13 ]; then
    docker build -f Dockerfile.debian13 -t vps-debian13:latest .
fi

echo -e "${YELLOW}[4/4] Installing Python packages...${NC}"
if [ -f node_requirements.txt ]; then
    pip3 install -r node_requirements.txt
else
    pip3 install flask docker psutil requests
fi

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Node Setup Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Run the node agent:"
echo "    python3 node_agent.py"
echo ""
echo "  The agent will start on port 5001"
echo "  Note the API key shown on first run"
echo ""
echo "  Add this node in the panel at: Settings > Nodes"
echo ""
python3 node_agent.py