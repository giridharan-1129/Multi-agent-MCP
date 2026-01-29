#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Setting up FastAPI Multi-Agent System${NC}"

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

if [[ ! "$python_version" =~ ^3\.1[0-1] ]]; then
    echo -e "${RED}✗ Python 3.10+ required${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python version OK${NC}"

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env from template...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ .env created${NC}"
    echo -e "${YELLOW}Please edit .env with your credentials${NC}"
else
    echo -e "${GREEN}✓ .env already exists${NC}"
fi

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install -e . > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${RED}✗ Failed to install dependencies${NC}"
    exit 1
fi

# Check Neo4j
echo -e "${YELLOW}Checking Neo4j connection...${NC}"

if command -v docker &> /dev/null; then
    if ! docker ps | grep -q neo4j; then
        echo -e "${YELLOW}Starting Neo4j with Docker...${NC}"
        docker run -d \
            --name neo4j-multiagent \
            -p 7687:7687 \
            -p 7474:7474 \
            -e NEO4J_AUTH=neo4j/password \
            neo4j:5.14 > /dev/null 2>&1
        
        echo -e "${YELLOW}Waiting for Neo4j to start...${NC}"
        sleep 5
        echo -e "${GREEN}✓ Neo4j started${NC}"
    else
        echo -e "${GREEN}✓ Neo4j already running${NC}"
    fi
else
    echo -e "${YELLOW}Docker not found. Please start Neo4j manually.${NC}"
fi

echo -e "${GREEN}✓ Setup complete!${NC}"
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Edit .env with your OpenAI API key"
echo "2. Run: uvicorn src.gateway.main:app --reload"
echo "3. Visit: http://localhost:8000/docs"
