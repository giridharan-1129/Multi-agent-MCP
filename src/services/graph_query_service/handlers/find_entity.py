"""Handler for finding entities in Neo4j."""

from ....shared.mcp_server import ToolResult

from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger

logger = get_logger(__name__)

async def find_entity_relationships_handler(
    neo4j_service: Neo4jService,
    entity_name: str
) -> ToolResult:
    """Find exhaustive relationships - both incoming (dependents) and outgoing (dependencies)."""
    try:
        logger.info(f"🔗 find_entity_relationships_handler called for '{entity_name}'")
        
        # Query to find ALL relationships:
        # 1. Incoming: What depends on this entity (IMPORTS, USES, CALLS, INHERITS_FROM)
        # 2. Outgoing: What this entity depends on
        # 3. Context: Where it's defined, what module contains it
        query = """
        MATCH (e) WHERE toLower(e.name) = toLower($name)
        WITH e
        
        // Get entities that DEPEND ON this entity (incoming relationships)
        OPTIONAL MATCH (dependent)-[rel_in:IMPORTS|USES|CALLS|INHERITS_FROM]->(e)
        WITH e, dependent, rel_in, 
             collect({
                 name: dependent.name,
                 type: labels(dependent)[0],
                 relation: type(rel_in),
                 module: dependent.module
             }) as incoming_deps
        
        // Get entities this entity DEPENDS ON (outgoing relationships)
        OPTIONAL MATCH (e)-[rel_out:IMPORTS|USES|CALLS|INHERITS_FROM]->(dependency)
        WITH e, incoming_deps,
             collect({
                 name: dependency.name,
                 type: labels(dependency)[0],
                 relation: type(rel_out),
                 module: dependency.module
             }) as outgoing_deps
        
        // Get parent context (what contains this entity)
        OPTIONAL MATCH (parent)-[rel_contains:CONTAINS]->(e)
        WITH e, incoming_deps, outgoing_deps,
             collect({
                 name: parent.name,
                 type: labels(parent)[0],
                 relation: type(rel_contains)
             }) as parents
        
        RETURN {
            target: e,
            target_type: labels(e)[0],
            target_module: e.module,
            target_line: e.line_number,
            dependents: [d IN incoming_deps WHERE d.name IS NOT NULL],
            dependencies: [d IN outgoing_deps WHERE d.name IS NOT NULL],
            parents: [p IN parents WHERE p.name IS NOT NULL],
            stats: {
                dependents_count: size([d IN incoming_deps WHERE d.name IS NOT NULL]),
                dependencies_count: size([d IN outgoing_deps WHERE d.name IS NOT NULL]),
                parents_count: size([p IN parents WHERE p.name IS NOT NULL])
            }
        } as result
        """
        
        params = {"name": entity_name}
        logger.info(f"   🔍 Finding exhaustive relationships for: '{entity_name}'")
        logger.info(f"   📊 Getting: incoming (dependents), outgoing (dependencies), parents (context)")
        logger.info(f"   🔄 Executing extended relationship query on Neo4j...")
        
        result = await neo4j_service.execute_query(query, params)
        
        if not result:
            logger.warning(f"   ⚠️  No relationships found for '{entity_name}'")
            return ToolResult(
                success=True,
                data={
                    "entity_name": entity_name,
                    "target_type": "Unknown",
                    "dependents": [],
                    "dependencies": [],
                    "parents": [],
                    "dependents_count": 0,
                    "dependencies_count": 0,
                    "parents_count": 0
                }
            )
        
        logger.info(f"   ✅ Got exhaustive relationship data")
        record = result[0]
        result_data = record.get("result") if isinstance(record, dict) else record["result"]
        
        dependents = result_data.get("dependents", [])
        dependencies = result_data.get("dependencies", [])
        parents = result_data.get("parents", [])
        stats = result_data.get("stats", {})
        
        logger.info(f"   📊 Found {len(dependents)} dependents, {len(dependencies)} dependencies, {len(parents)} parents")
        
        return ToolResult(
            success=True,
            data={
                "entity_name": entity_name,
                "target_type": result_data.get("target_type", "Unknown"),
                "target_module": result_data.get("target_module", "N/A"),
                "target_line": result_data.get("target_line", "N/A"),
                "dependents": dependents,           # What uses this
                "dependencies": dependencies,       # What this uses
                "parents": parents,                 # What contains this
                "dependents_count": stats.get("dependents_count", 0),
                "dependencies_count": stats.get("dependencies_count", 0),
                "parents_count": stats.get("parents_count", 0)
            }
        )
    except Exception as e:
        logger.error(f"❌ Exception in find_entity_relationships_handler: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ToolResult(success=False, error=str(e))

async def find_entity_handler(
    neo4j_service: Neo4jService,
    name: str,
    entity_type: str = None
) -> ToolResult:
    """Find entity by name and optional type."""
    try:
        logger.info(f"🔍 find_entity_handler called with name='{name}', entity_type='{entity_type}'")
        
                # Use case-insensitive comparison with better matching
        # Query prioritizes: Class > Function > Method > Parameter > Decorator > Import > Module
        query = """
        MATCH (e) WHERE toLower(e.name) = toLower($name)
        RETURN e, labels(e) as types
        ORDER BY 
        CASE labels(e)[0]
            WHEN 'Class' THEN 1
            WHEN 'Function' THEN 2
            WHEN 'Method' THEN 3
            WHEN 'Parameter' THEN 4
            WHEN 'Decorator' THEN 5
            WHEN 'Type' THEN 6
            WHEN 'Import' THEN 7
            WHEN 'Module' THEN 8
            WHEN 'File' THEN 9
            ELSE 10
        END
        LIMIT 1
        """
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
