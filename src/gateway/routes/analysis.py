"""
Code analysis endpoints.

WHAT: /api/analysis/* endpoints
WHY: Deep code understanding and pattern detection
HOW: Use Code Analyst Agent to analyze code entities
"""

from typing import Optional
from fastapi import APIRouter, HTTPException

from ...shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ..dependencies import get_code_analyst

logger = get_logger(__name__)
router = APIRouter(tags=["analysis"], prefix="/api/analysis")


@router.post("/function")
async def analyze_function(payload: dict):
    """
    Analyze a function.

    Args:
        payload: {"name": "function_name", "module": "optional_module"}

    Returns:
        Function analysis including signature, logic, and usage
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        name = payload.get("name")
        module = payload.get("module")
        
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        
        code_analyst = get_code_analyst()

        result = await code_analyst.execute_tool(
            "analyze_function",
            {
                "name": name,
                "module": module,
            },
        )

        if not result.success:
            raise HTTPException(status_code=404, detail=result.error)

        logger.info("Function analyzed", name=name, module=module)
        return {
            "analysis": result.data,
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to analyze function", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/class")
async def analyze_class(payload: dict):
    """
    Analyze a class.

    Args:
        payload: {"name": "class_name", "module": "optional_module"}

    Returns:
        Class analysis including methods, inheritance, and patterns
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        name = payload.get("name")
        module = payload.get("module")
        
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        
        code_analyst = get_code_analyst()

        result = await code_analyst.execute_tool(
            "analyze_class",
            {
                "name": name,
                "module": module,
            },
        )

        if not result.success:
            raise HTTPException(status_code=404, detail=result.error)

        logger.info("Class analyzed", name=name, module=module)
        return {
            "analysis": result.data,
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to analyze class", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/patterns")
async def find_patterns(payload: dict):
    """
    Find design patterns in code.

    Args:
        payload: {"pattern_type": "optional_pattern_type"}

    Returns:
        Detected patterns with locations and descriptions
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        pattern_type = payload.get("pattern_type")
        
        code_analyst = get_code_analyst()

        result = await code_analyst.execute_tool(
            "find_patterns",
            {
                "pattern_type": pattern_type,
            },
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        logger.info("Patterns found", pattern_type=pattern_type)
        return {
            "patterns": result.data.get("patterns", []),
            "count": result.data.get("total", 0),
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to find patterns", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare")
async def compare_implementations(payload: dict):
    """
    Compare two code implementations.

    Args:
        payload: {"entity1": "first_entity", "entity2": "second_entity"}

    Returns:
        Comparison analysis showing similarities and differences
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        entity1 = payload.get("entity1")
        entity2 = payload.get("entity2")
        
        if not entity1 or not entity2:
            raise HTTPException(status_code=400, detail="entity1 and entity2 are required")
        
        code_analyst = get_code_analyst()

        result = await code_analyst.execute_tool(
            "compare_implementations",
            {
                "entity1": entity1,
                "entity2": entity2,
            },
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        logger.info("Implementations compared", entity1=entity1, entity2=entity2)
        return {
            "comparison": result.data,
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to compare implementations", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))