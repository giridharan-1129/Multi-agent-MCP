#!/bin/bash

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Running tests for FastAPI Multi-Agent System${NC}"

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}pytest not found. Installing...${NC}"
    pip install pytest pytest-asyncio pytest-cov
fi

# Run tests with coverage
echo -e "${YELLOW}Running tests...${NC}"
pytest \
    --cov=src \
    --cov-report=html \
    --cov-report=term-missing \
    -v

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo -e "${YELLOW}Coverage report: htmlcov/index.html${NC}"
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
