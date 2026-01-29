#!/bin/bash

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Starting FastAPI Multi-Agent System (Development)${NC}"

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found. Run scripts/setup.sh first."
    exit 1
fi

# Load environment
export $(cat .env | grep -v '#' | xargs)

# Start with development docker-compose
echo -e "${YELLOW}Starting with Docker Compose (dev)...${NC}"
docker-compose -f docker-compose.dev.yml up
