#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}FastAPI Multi-Agent System - Startup${NC}"

# Wait for Neo4j to be ready
echo -e "${YELLOW}Waiting for Neo4j to be ready...${NC}"
until curl -s http://neo4j:7474 > /dev/null 2>&1; do
  echo "Neo4j not ready, waiting..."
  sleep 2
done
echo -e "${GREEN}✓ Neo4j is ready${NC}"

# Verify environment variables
echo -e "${YELLOW}Checking configuration...${NC}"

if [ -z "$OPENAI_API_KEY" ]; then
  echo -e "${RED}✗ OPENAI_API_KEY not set${NC}"
  exit 1
fi
echo -e "${GREEN}✓ OPENAI_API_KEY is set${NC}"

if [ -z "$NEO4J_PASSWORD" ]; then
  echo -e "${RED}✗ NEO4J_PASSWORD not set${NC}"
  exit 1
fi
echo -e "${GREEN}✓ NEO4J_PASSWORD is set${NC}"

# Start the application
echo -e "${YELLOW}Starting FastAPI Gateway...${NC}"
exec "$@"
