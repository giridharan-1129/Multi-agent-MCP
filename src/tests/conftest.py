"""
Pytest configuration and fixtures.

Provides shared fixtures for all tests.
"""

import pytest
import asyncio
from typing import Generator

from ..shared.config import config
from ..shared.logger import get_logger

logger = get_logger(__name__)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config():
    """Provide test configuration."""
    return config


@pytest.fixture
def test_logger():
    """Provide logger for tests."""
    return get_logger("test")
