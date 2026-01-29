.PHONY: help setup install test run run-dev stop clean docker-build docker-up docker-down

# Default target
help:
	@echo "FastAPI Multi-Agent System - Available Commands"
	@echo "==============================================="
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make setup          - Setup project (install deps, create .env)"
	@echo "  make install        - Install dependencies"
	@echo "  make install-dev    - Install dev dependencies"
	@echo ""
	@echo "Running:"
	@echo "  make run            - Start system with Docker Compose"
	@echo "  make run-dev        - Start system in development mode"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run all tests with coverage"
	@echo "  make test-unit      - Run unit tests only"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build   - Build Docker images"
	@echo "  make docker-up      - Start Docker containers"
	@echo "  make docker-down    - Stop Docker containers"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          - Clean up generated files"
	@echo "  make clean-docker   - Stop and remove Docker containers"

# Setup
setup:
	./scripts/setup.sh

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

# Running
run:
	./scripts/start.sh

run-dev:
	./scripts/start-dev.sh

# Testing
test:
	./scripts/test.sh

test-unit:
	pytest src/tests/ -v

# Docker
docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov build dist *.egg-info

clean-docker:
	docker-compose down -v
	docker ps -a | grep multiagent | awk '{print $$1}' | xargs docker rm 2>/dev/null || true

# Format code
format:
	black src/
	ruff check src/ --fix

# Lint
lint:
	ruff check src/
	mypy src/ --ignore-missing-imports || true
