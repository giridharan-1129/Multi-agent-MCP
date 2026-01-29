#!/bin/bash

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Starting FastAPI Multi-Agent System${NC}"

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found. Run scripts/setup.sh first."
    exit 1
fi

# Load environment
export $(cat .env | grep -v '#' | xargs)

# Start with Docker Compose
if command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}Starting with Docker Compose...${NC}"
    docker-compose up
else
    echo -e "${YELLOW}Starting Gateway directly...${NC}"
    uvicorn src.gateway.main:app --host 0.0.0.0 --port 8000 --reload
fi
