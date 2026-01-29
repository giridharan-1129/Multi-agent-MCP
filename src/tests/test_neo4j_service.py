"""
Tests for Neo4j Service.

Tests database connection, schema creation, and basic operations.
"""

import pytest
from unittest.mock import AsyncMock, patch

from ..shared.neo4j_service import Neo4jService
from ..shared.exceptions import Neo4jConnectionError, Neo4jError


@pytest.fixture
def neo4j_service():
    """Create Neo4j service instance for testing."""
    service = Neo4jService(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="password",
    )
    return service


@pytest.mark.asyncio
async def test_neo4j_service_initialization(neo4j_service):
    """Test Neo4j service initialization."""
    assert neo4j_service.uri == "bolt://localhost:7687"
    assert neo4j_service.username == "neo4j"
    assert neo4j_service.database == "neo4j"
    assert neo4j_service.driver is None


@pytest.mark.asyncio
async def test_create_class_node(neo4j_service):
    """Test creating a class node."""
    with patch.object(neo4j_service, 'execute_query', new_callable=AsyncMock) as mock_query:
        mock_query.return_value = [{"class": {"name": "FastAPI"}}]

        result = await neo4j_service.create_class_node(
            name="FastAPI",
            module="fastapi/main.py",
            docstring="FastAPI class",
        )

        assert result["name"] == "FastAPI"
        mock_query.assert_called_once()


@pytest.mark.asyncio
async def test_create_function_node(neo4j_service):
    """Test creating a function node."""
    with patch.object(neo4j_service, 'execute_query', new_callable=AsyncMock) as mock_query:
        mock_query.return_value = [{"function": {"name": "get_openapi_schema"}}]

        result = await neo4j_service.create_function_node(
            name="get_openapi_schema",
            module="fastapi/openapi.py",
            is_async=False,
        )

        assert result["name"] == "get_openapi_schema"
        mock_query.assert_called_once()


@pytest.mark.asyncio
async def test_find_entity(neo4j_service):
    """Test finding an entity."""
    with patch.object(neo4j_service, 'execute_query', new_callable=AsyncMock) as mock_query:
        mock_query.return_value = [{"entity": {"name": "APIRouter"}}]

        result = await neo4j_service.find_entity("APIRouter", "Class")

        assert result["name"] == "APIRouter"
        mock_query.assert_called_once()


@pytest.mark.asyncio
async def test_get_dependencies(neo4j_service):
    """Test getting dependencies."""
    with patch.object(neo4j_service, 'execute_query', new_callable=AsyncMock) as mock_query:
        mock_query.return_value = [
            {"dependency": {"name": "starlette"}, "relationship_type": "IMPORTS"}
        ]

        result = await neo4j_service.get_dependencies("FastAPI")

        assert len(result) == 1
        assert result[0]["dependency"]["name"] == "starlette"
        mock_query.assert_called_once()
