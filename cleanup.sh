#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}FastAPI Multi-Agent MCP - Repository Cleanup${NC}"
echo -e "${BLUE}==================================================${NC}\n"

# Check if we're in a git repo
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Not in a git repository${NC}"
    exit 1
fi

# Count operations
DELETED=0
MOVED=0
CREATED=0

# ============================================
# Step 1: Delete backup files
# ============================================
echo -e "${YELLOW}[1/8] Deleting backup files (.bak)...${NC}"
for file in src/agents/*.bak; do
    if [ -f "$file" ]; then
        git rm "$file" 2>/dev/null && echo -e "${GREEN}✓${NC} Deleted: $file" && ((DELETED++))
    fi
done

# ============================================
# Step 2: Delete Python cache files
# ============================================
echo -e "\n${YELLOW}[2/8] Removing Python cache files...${NC}"
for cache_dir in src/__pycache__ src/shared/__pycache__ src/gateway/__pycache__ src/agents/__pycache__; do
    if [ -d "$cache_dir" ]; then
        git rm -r "$cache_dir" 2>/dev/null && echo -e "${GREEN}✓${NC} Removed: $cache_dir" && ((DELETED++))
    fi
done

# Delete .pyc files
if find . -name "*.pyc" -type f 2>/dev/null | grep -q .; then
    find . -name "*.pyc" -type f -delete && echo -e "${GREEN}✓${NC} Removed all .pyc files"
fi

# Delete .DS_Store files
if find . -name ".DS_Store" -type f 2>/dev/null | grep -q .; then
    find . -name ".DS_Store" -type f -delete && echo -e "${GREEN}✓${NC} Removed .DS_Store files"
fi

# ============================================
# Step 3: Remove egg-info
# ============================================
echo -e "\n${YELLOW}[3/8] Removing Python egg-info...${NC}"
if [ -d "src/fastapi_multiagent_chat.egg-info" ]; then
    git rm -r "src/fastapi_multiagent_chat.egg-info" 2>/dev/null && echo -e "${GREEN}✓${NC} Removed egg-info" && ((DELETED++))
fi

# ============================================
# Step 4: Remove setuptools artifacts
# ============================================
echo -e "\n${YELLOW}[4/8] Removing setuptools artifacts...${NC}"
for file in dependency_links.txt SOURCES.txt requires.txt top_level.txt; do
    if [ -f "$file" ]; then
        git rm "$file" 2>/dev/null && echo -e "${GREEN}✓${NC} Removed: $file" && ((DELETED++))
    fi
done

# ============================================
# Step 5: Create proper directory structure
# ============================================
echo -e "\n${YELLOW}[5/8] Creating proper directory structure...${NC}"
mkdir -p src/utils
mkdir -p src/streamlit
mkdir -p src/tests
mkdir -p docker
mkdir -p scripts
mkdir -p docs
echo -e "${GREEN}✓${NC} Directory structure created"
((CREATED+=6))

# ============================================
# Step 6: Move root Python files to src/utils
# ============================================
echo -e "\n${YELLOW}[6/8] Reorganizing Python utility files...${NC}"
for file in mermaid_renderer.py network_graph_renderer.py; do
    if [ -f "$file" ]; then
        git mv "$file" "src/utils/$file" 2>/dev/null && echo -e "${GREEN}✓${NC} Moved: $file → src/utils/" && ((MOVED++))
    fi
done

if [ -f "relationship_mappings.py" ]; then
    git mv "relationship_mappings.py" "src/utils/relationship_mappings.py" 2>/dev/null && echo -e "${GREEN}✓${NC} Moved: relationship_mappings.py → src/utils/" && ((MOVED++))
fi

if [ -f "streamlit_app.py" ]; then
    git mv "streamlit_app.py" "src/streamlit/app.py" 2>/dev/null && echo -e "${GREEN}✓${NC} Moved: streamlit_app.py → src/streamlit/app.py" && ((MOVED++))
fi

# ============================================
# Step 7: Move test files
# ============================================
echo -e "\n${YELLOW}[7/8] Reorganizing test files...${NC}"
if [ -f "test_ws.py" ]; then
    git mv "test_ws.py" "src/tests/test_ws.py" 2>/dev/null && echo -e "${GREEN}✓${NC} Moved: test_ws.py → src/tests/" && ((MOVED++))
fi

if [ -f "verify_all_steps.sh" ]; then
    git mv "verify_all_steps.sh" "scripts/verify_all_steps.sh" 2>/dev/null && echo -e "${GREEN}✓${NC} Moved: verify_all_steps.sh → scripts/" && ((MOVED++))
fi

if [ -f "reindex_fastapi.py" ]; then
    git mv "reindex_fastapi.py" "scripts/reindex_fastapi.py" 2>/dev/null && echo -e "${GREEN}✓${NC} Moved: reindex_fastapi.py → scripts/" && ((MOVED++))
fi

# ============================================
# Step 8: Move docs
# ============================================
echo -e "\n${YELLOW}[8/8] Organizing documentation...${NC}"
for doc in ARCHITECTURE.md API.md DEPLOYMENT_GUIDE.md QUICK_START.md; do
    if [ -f "$doc" ]; then
        git mv "$doc" "docs/$doc" 2>/dev/null && echo -e "${GREEN}✓${NC} Moved: $doc → docs/" && ((MOVED++))
    fi
done

# ============================================
# Create/Update .gitignore
# ============================================
echo -e "\n${YELLOW}Updating .gitignore...${NC}"

# Backup existing .gitignore if it exists
if [ -f ".gitignore" ]; then
    cp .gitignore .gitignore.backup
fi

cat > .gitignore << 'EOF'
# Build artifacts
*.egg-info/
*.dist-info/
build/
dist/
*.egg

# Python cache
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so

# IDE
.vscode/
.idea/
*.swp
*.swo
*~
.project
.pydevproject
*.sublime-project
*.sublime-workspace

# OS
.DS_Store
Thumbs.db
.Spotlight-V100
.Trashes

# Environment
.env
.env.local
*.env.local
.venv
venv/
env/
ENV/

# Dependencies
pip-log.txt
pip-delete-this-directory.txt

# Backup files
*.bak
*.backup
*.orig

# Logs
*.log
logs/
*.log.*

# Test coverage
.coverage
.coverage.*
htmlcov/
.pytest_cache/
.tox/
.hypothesis/

# Neo4j data
neo4j_data/
data/

# Temporary files
tmp/
temp/
*.tmp

# IDE specific
.vscode/settings.json

# Docker
docker-compose.override.yml

# OS specific
.AppleDouble
.LSOverride
EOF

echo -e "${GREEN}✓${NC} .gitignore updated"

# ============================================
# Summary
# ============================================
echo -e "\n${BLUE}==================================================${NC}"
echo -e "${GREEN}✓ Cleanup Complete!${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "Files deleted: ${GREEN}${DELETED}${NC}"
echo -e "Files moved: ${GREEN}${MOVED}${NC}"
echo -e "Directories created: ${GREEN}${CREATED}${NC}"

# ============================================
# Final checks
# ============================================
echo -e "\n${YELLOW}Final checks...${NC}"

# Check for remaining unwanted files
echo -e "\n${YELLOW}Checking for remaining unwanted files:${NC}"
UNWANTED_COUNT=0

# Check for .bak files
if find . -name "*.bak" -type f 2>/dev/null | grep -q .; then
    echo -e "${RED}✗${NC} Found .bak files:"
    find . -name "*.bak" -type f
    ((UNWANTED_COUNT++))
else
    echo -e "${GREEN}✓${NC} No .bak files"
fi

# Check for __pycache__
if find . -type d -name "__pycache__" 2>/dev/null | grep -q .; then
    echo -e "${RED}✗${NC} Found __pycache__ directories (will be cleaned on commit)"
else
    echo -e "${GREEN}✓${NC} No __pycache__ directories"
fi

# Check for .pyc files
if find . -name "*.pyc" -type f 2>/dev/null | grep -q .; then
    echo -e "${RED}✗${NC} Found .pyc files (will be cleaned on commit)"
else
    echo -e "${GREEN}✓${NC} No .pyc files"
fi

# ============================================
# Next steps
# ============================================
echo -e "\n${BLUE}==================================================${NC}"
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "1. Review changes: ${GREEN}git status${NC}"
echo -e "2. Stage changes: ${GREEN}git add -A${NC}"
echo -e "3. Commit changes: ${GREEN}git commit -m \"chore: cleanup repo structure\"${NC}"
echo -e "4. Verify Docker: ${GREEN}docker-compose config${NC}"
echo -e "5. Test build: ${GREEN}docker-compose build${NC}"
echo -e "\n${GREEN}Your repository is now ready for submission!${NC}\n"