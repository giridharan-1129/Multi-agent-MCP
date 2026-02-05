"""Handler for finding entities in Neo4j."""

from ....shared.mcp_server import ToolResult

from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def find_entity_handler(
    neo4j_service: Neo4jService,
    name: str,
    entity_type: str = None
) -> ToolResult:
    """Find entity by name and optional type."""
    try:
        logger.info(f"🔍 find_entity_handler called with name='{name}', entity_type='{entity_type}'")
        
                # Use case-insensitive comparison with better matching
        query = "MATCH (e) WHERE toLower(e.name) = toLower($name) RETURN e, labels(e) as types LIMIT 1"
        params = {"name": name}
        logger.info(f"   🔍 Query: {query}")
        logger.info(f"   📍 Searching for entity: '{name}'")

        if entity_type:
            # Add type filter but keep it flexible
            query = "MATCH (e) WHERE toLower(e.name) = toLower($name) AND $type IN labels(e) RETURN e, labels(e) as types LIMIT 1"
            params["type"] = entity_type
            logger.info(f"   🔍 With type filter: {entity_type}")
        logger.debug(f"   Final query: {query}")
        
        logger.info(f"   🔄 Executing query on Neo4j...")
        result = await neo4j_service.execute_query(query, params)
        logger.info(f"   📦 Query result type: {type(result)}, content: {result}")
        
        if not result:
            logger.error(f"   ❌ Query returned empty result for name='{name}'")
            return ToolResult(success=False, error=f"Entity not found: {name}")
        
        logger.info(f"   ✅ Got {len(result)} result(s)")
        record = result[0]
        logger.info(f"   📄 Record type: {type(record)}")
        logger.info(f"   📄 Record content: {record}")
        
        # Handle both dict and object-like access patterns
        if isinstance(record, dict):
            logger.info(f"   ✓ Record is a dictionary")
            entity = record.get("e")
            entity_types = record.get("types", [])
            logger.info(f"     entity={entity}, entity_types={entity_types}")
        else:
            logger.info(f"   ✓ Record is an object")
            entity = record["e"]
            entity_types = record["types"]
            logger.info(f"     entity={entity}, entity_types={entity_types}")

        if not entity:
            logger.error(f"   ❌ Entity is None/empty after extraction")
            return ToolResult(success=False, error=f"Entity not found: {name}")
        
        logger.info(f"   ✅ Entity extracted successfully: {entity}")
        
        logger.info(f"Entity found: {name}")
        
        logger.info(f"   Converting entity to dict...")
        # entity is a Neo4j Node object with properties attribute
        try:
            if hasattr(entity, 'properties'):
                # Neo4j Node object - access properties directly
                entity_dict = dict(entity.properties)
                logger.info(f"   ✅ Extracted from Neo4j Node.properties: {entity_dict}")
            elif isinstance(entity, dict):
                # Already a dict
                entity_dict = entity
                logger.info(f"   ✅ Entity is already dict: {entity_dict}")
            else:
                # Try direct conversion
                entity_dict = dict(entity) if hasattr(entity, '__iter__') else {}
                logger.info(f"   ⚠️  Fallback conversion: {entity_dict}")
        except Exception as conv_err:
            logger.error(f"   ❌ Conversion failed: {conv_err}")
            entity_dict = {}
        
        result_data = {
            "name": entity_dict.get("name", name),  # Fallback to input name
            "type": entity_types[0] if entity_types else "Unknown",
            "properties": entity_dict
        }
        logger.info(f"   📤 Returning result: {result_data}")
        
        return ToolResult(success=True, data=result_data)
    except Exception as e:
        logger.error(f"❌ Exception in find_entity_handler: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ToolResult(success=False, error=str(e))
