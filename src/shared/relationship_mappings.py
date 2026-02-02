"""
Relationship mappings for different node types in the knowledge graph.

This module defines which relationships are valid for each node type,
enabling intelligent Cypher query generation.
"""

# Relationship mappings: what relationships each node type can have
NODE_RELATIONSHIPS = {
    "Class": {
        "outgoing": ["CONTAINS", "INHERITS_FROM", "DECORATED_BY", "DEFINES"],
        "incoming": ["INHERITS_FROM", "CONTAINS", "HAS_METHOD"],
        "description": "Classes can inherit from other classes, contain methods/functions, and be decorated"
    },
    "Function": {
        "outgoing": ["CALLS", "DECORATED_BY", "DEFINES", "RETURNS", "HAS_PARAM"],
        "incoming": ["CALLS", "CONTAINS"],
        "description": "Functions can call other functions, be decorated, define parameters and return types"
    },
    "Method": {
        "outgoing": ["CALLS", "DECORATED_BY", "DEFINES", "RETURNS", "HAS_PARAM"],
        "incoming": ["CALLS", "HAS_METHOD"],
        "description": "Methods are similar to functions but belong to classes"
    },
    "Package": {
        "outgoing": ["CONTAINS", "IMPORTS"],
        "incoming": ["IMPORTS", "CONTAINS"],
        "description": "Packages contain files and import other packages"
    },
    "File": {
        "outgoing": ["CONTAINS", "DEFINES", "IMPORTS"],
        "incoming": ["CONTAINS", "DEFINES"],
        "description": "Files contain classes/functions and define entities"
    },
    "Parameter": {
        "outgoing": [],
        "incoming": ["HAS_PARAM", "DEFINES"],
        "description": "Parameters are defined by functions"
    },
    "Type": {
        "outgoing": [],
        "incoming": ["RETURNS", "DEFINES"],
        "description": "Types are return types or annotations"
    },
    "Docstring": {
        "outgoing": [],
        "incoming": ["DOCUMENTED_BY"],
        "description": "Docstrings document entities"
    }
}


def get_cypher_query_templates(node_type: str, entity_name: str) -> list:
    """
    Generate Cypher query templates optimized for relationship discovery.
    
    Query 1 (PRIMARY): Multi-level OPTIONAL MATCH pattern that works perfectly
    This explores all relationships and connections:
    
    MATCH (c:Class {name: "Dependant"})
    OPTIONAL MATCH (c)-[:DOCUMENTED_BY]->(cd)
    OPTIONAL MATCH (c)-[:CONTAINS]->(f:Function)
    OPTIONAL MATCH (f)-[:DOCUMENTED_BY]->(fd)
    RETURN c, cd, f, fd;
    
    Queries 2-4: Fallback patterns for additional context
    """
    
    if node_type not in NODE_RELATIONSHIPS:
        # Fallback for unknown types
        return [
            f'MATCH (n {{name: "{entity_name}"}}) OPTIONAL MATCH (n)-[r]-(related) '
            f'RETURN n, r, related LIMIT 50'
        ]
    
    queries = []
    rel_info = NODE_RELATIONSHIPS[node_type]
    
    # ========================================================================
    # QUERY 1: PRIMARY - Multi-level OPTIONAL MATCH (The Pattern That Works!)
    # ========================================================================
    # This is the proven pattern from your manual queries
    # It explores: Entity -> Related entities -> Their relationships
    query1 = f'MATCH (c:{node_type} {{name: "{entity_name}"}}) '
    query1 += 'OPTIONAL MATCH (c)-[:DOCUMENTED_BY]->(cd) '
    query1 += 'OPTIONAL MATCH (c)-[:CONTAINS]->(f) '
    query1 += 'OPTIONAL MATCH (c)-[:DEFINES]->(d) '
    query1 += 'OPTIONAL MATCH (c)-[:INHERITS_FROM]->(parent) '
    query1 += 'OPTIONAL MATCH (c)-[:CALLS]->(calls_target) '
    query1 += 'OPTIONAL MATCH (c)-[:HAS_METHOD]->(method) '
    query1 += 'OPTIONAL MATCH (f)-[:DOCUMENTED_BY]->(fd) '
    query1 += 'OPTIONAL MATCH (method)-[:DOCUMENTED_BY]->(md) '
    query1 += 'RETURN c, cd, f, d, parent, calls_target, method, fd, md LIMIT 100'
    queries.append(query1)
    
    # ========================================================================
    # QUERY 2: All incoming relationships (what depends on this)
    # ========================================================================
    if rel_info["incoming"]:
        rel_types = "|".join(rel_info["incoming"])
        queries.append(
            f'MATCH (source)-[r:{rel_types}]->(n:{node_type} {{name: "{entity_name}"}}) '
            f'RETURN source, r, n LIMIT 50'
        )
    
    # ========================================================================
    # QUERY 3: Multi-hop transitive relationships
    # ========================================================================
    if rel_info["outgoing"] and len(rel_info["outgoing"]) > 0:
        first_rel = rel_info["outgoing"][0]
        queries.append(
            f'MATCH (n:{node_type} {{name: "{entity_name}"}})-[r1:{first_rel}]->(intermediate) '
            f'OPTIONAL MATCH (intermediate)-[r2]->(final) '
            f'RETURN n, r1, intermediate, r2, final LIMIT 50'
        )
    
    # ========================================================================
    # QUERY 4: Bidirectional neighborhood summary
    # ========================================================================
    queries.append(
        f'MATCH (n:{node_type} {{name: "{entity_name}"}}) '
        f'OPTIONAL MATCH (n)-[out_rel]->(out_node) '
        f'OPTIONAL MATCH (in_node)-[in_rel]->(n) '
        f'RETURN n, out_rel, out_node, in_rel, in_node LIMIT 100'
    )
    
    return queries


def get_query_description(node_type: str) -> str:
    """Get a human-readable description of what relationships this node type has."""
    if node_type in NODE_RELATIONSHIPS:
        return NODE_RELATIONSHIPS[node_type]["description"]
    return "Unknown node type"


def validate_relationship(source_type: str, relationship: str, target_type: str) -> bool:
    """
    Check if a relationship is valid between two node types.
    
    Args:
        source_type: Type of source node
        relationship: Type of relationship
        target_type: Type of target node
    
    Returns:
        True if the relationship is valid, False otherwise
    """
    if source_type not in NODE_RELATIONSHIPS:
        return False
    
    outgoing_rels = NODE_RELATIONSHIPS[source_type]["outgoing"]
    return relationship in outgoing_rels