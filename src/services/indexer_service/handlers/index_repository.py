"""
Index Repository Handler - Neo4j knowledge graph population.

Handles:
- Repository download
- Python file parsing
- Entity and relationship creation in Neo4j
"""

from typing import Any, Dict
from ....shared.mcp_server import ToolResult

from ....shared.neo4j_service import Neo4jService
from ....shared.ast_parser import ASTParser
from ....shared.repo_downloader import RepositoryDownloader
from ....shared.relationship_builder import RelationshipBuilder
from ....shared.logger import get_logger
from .ast_utils import parse_and_extract_entities, count_entity_types

logger = get_logger(__name__)

def _infer_source_type(rel_type: str, source_name: str) -> str:
    """Infer source node type from relationship type."""
    mapping = {
        "INHERITS_FROM": "Class",
        "CONTAINS": "Class",  # Class contains Method
        "DECORATED_BY": "Function",
        "CALLS": "Function",
        "HAS_PARAM": "Function",
        "RETURNS": "Function",
        "HAS_METHOD": "Class",
        "IMPORTS": "Package",
        "DEFINES": "File",
        "DOCUMENTED_BY": "Function",
    }
    return mapping.get(rel_type, "Unknown")


def _infer_target_type(rel_type: str, target_name: str) -> str:
    """Infer target node type from relationship type."""
    mapping = {
        "INHERITS_FROM": "Class",
        "CONTAINS": "Method",  # Class contains Method
        "DECORATED_BY": "Function",
        "CALLS": "Function",
        "HAS_PARAM": "Parameter",
        "RETURNS": "Type",
        "HAS_METHOD": "Method",
        "IMPORTS": "Package",
        "DEFINES": "Class",  # or Function
        "DOCUMENTED_BY": "Docstring",
    }
    return mapping.get(rel_type, "Unknown")

    
async def index_repository_handler(
    repo_url: str,
    branch: str,
    neo4j_service: Neo4jService,
    ast_parser: ASTParser,
    repo_downloader: RepositoryDownloader
) -> ToolResult:
    """
    Full repository indexing:
    1. Clone repo
    2. Parse Python files
    3. Extract entities & relationships
    4. Populate Neo4j
    """
    try:
        logger.info(f"🚀 Starting repository indexing: {repo_url}")
        
        # Step 1: Download repository
        logger.info(f"📥 Downloading repository...")
        repo_path = await repo_downloader.download_repo(repo_url)
        logger.info(f"✅ Downloaded to {repo_path}")
        
        # Step 2: Get all Python files
        py_files = repo_downloader.get_all_python_files(repo_path)
        logger.info(f"📁 Found {len(py_files)} Python files")
        
        if not py_files:
            return ToolResult(
                success=False,
                error="No Python files found in repository"
            )
        
        # Step 3: Parse and index
        stats = {
            "files_indexed": 0,
            "entities_created": 0,
            "relationships_created": 0,
            "entity_breakdown": {}
        }
        
        relationship_builder = RelationshipBuilder()
        
        for idx, py_file in enumerate(py_files, 1):
            try:
                logger.debug(f"Parsing {idx}/{len(py_files)}: {py_file}")
                
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Parse and extract
                entities, imports, relationships = await parse_and_extract_entities(
                    py_file, content, ast_parser
                )
                
                # Create entity nodes in Neo4j
                for entity in entities:
                    try:
                        entity_type = entity.get("type")
                        
                        if entity_type == "Class":
                            await neo4j_service.create_class_node(
                                name=entity["name"],
                                module=entity.get("module"),
                                docstring=entity.get("docstring"),
                                line_number=entity.get("line_number")
                            )
                        elif entity_type == "Function":
                            await neo4j_service.create_function_node(
                                name=entity["name"],
                                module=entity.get("module"),
                                docstring=entity.get("docstring"),
                                line_number=entity.get("line_number"),
                                is_async=entity.get("is_async", False)
                            )
                        elif entity_type == "Method":
                            await neo4j_service.create_method_node(
                                name=entity["name"],
                                module=entity.get("module"),
                                docstring=entity.get("docstring"),
                                line_number=entity.get("line_number"),
                                is_async=entity.get("is_async", False)
                            )
                        elif entity_type == "Parameter":
                            await neo4j_service.create_parameter_node(
                                name=entity["name"],
                                param_name=entity.get("param_name"),
                                module=entity.get("module", "")
                            )
                        elif entity_type == "Type":
                            await neo4j_service.create_type_node(entity["name"])
                        elif entity_type == "Docstring":
                            await neo4j_service.create_docstring_node(
                                name=entity["name"],
                                content=entity.get("content"),
                                scope=entity.get("scope"),
                                module=entity.get("module"),
                                package=entity.get("package")
                            )
                    except Exception as e:
                        logger.debug(f"Skipping entity {entity.get('name')}: {e}")
                        continue
                
                # Create relationships in Neo4j
                for rel in relationships:
                    try:
                        # Infer source/target types from relationship type
                        source_type = _infer_source_type(rel["type"], rel.get("source"))
                        target_type = _infer_target_type(rel["type"], rel.get("target"))
                        
                        await neo4j_service.create_relationship(
                            source_name=rel["source"],
                            source_label=source_type,
                            target_name=rel["target"],
                            target_label=target_type,
                            rel_type=rel["type"]
                        )
                    except Exception as e:
                        logger.debug(f"Skipping relationship {rel.get('type')}: {e}")
                        continue
                
                stats["files_indexed"] += 1
                stats["entities_created"] += len(entities)
                stats["relationships_created"] += len(relationships)
                
                if idx % 10 == 0:
                    logger.info(f"Progress: {idx}/{len(py_files)} files indexed")
                    
            except Exception as e:
                logger.warning(f"Failed to index {py_file}: {e}")
                continue
        
        # Get entity breakdown
        graph_stats = await neo4j_service.get_graph_statistics()
        
        logger.info(f"✅ Indexing complete: {stats}")
        
        return ToolResult(
            success=True,
            data={
                "repo_url": repo_url,
                "branch": branch,
                "repo_path": repo_path,
                "statistics": stats,
                "graph_statistics": graph_stats
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Repository indexing failed: {e}")
        return ToolResult(success=False, error=str(e))


