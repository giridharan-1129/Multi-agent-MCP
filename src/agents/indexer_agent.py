"""
Indexer Agent - MCP Agent for Repository Indexing.

WHAT: Parses GitHub repositories and builds Neo4j knowledge graph
WHY: Convert raw code into queryable entities and relationships
HOW: Clone repo → Parse AST → Extract entities → Store in Neo4j

Example:
    agent = IndexerAgent()
    await agent.startup()
    
    result = await agent.execute_tool("index_repository", {
        "repo_url": "https://github.com/tiangolo/fastapi",
        "full_index": True
    })
"""

from typing import Any, Dict, Optional, List
import logging

from ..shared.ast_parser import get_parser
from ..shared.base_agent import BaseAgent
from ..shared.exceptions import (
    RepositoryIndexingError,
    FileParsingError,
)
from ..shared.logger import get_logger
from ..shared.mcp_types import MCPTool, ToolResult, ToolParameter, ToolDefinition
from ..shared.neo4j_service import get_neo4j_service
from ..shared.relationship_builder import get_relationship_builder
from ..shared.repo_downloader import get_downloader

logger = get_logger(__name__)


class IndexRepositoryTool(MCPTool):
    """Tool to index an entire repository into Neo4j knowledge graph."""

    name: str = "index_repository"
    description: str = "Clone and index a GitHub repository into the knowledge graph"
    category: str = "indexing"

    async def execute(
        self,
        repo_url: str,
        full_index: bool = True,
        clone_path: Optional[str] = None,
    ) -> ToolResult:
        """
        Index a repository.

        Args:
            repo_url: GitHub repository URL
            full_index: Whether to do full index or incremental
            clone_path: Custom clone path

        Returns:
            ToolResult with indexing statistics
        """
        try:
            downloader = get_downloader()
            parser = get_parser()
            neo4j = get_neo4j_service()
            builder = get_relationship_builder()

            logger.info(f"🚀 Starting repository indexing", url=repo_url)

            # Step 1: Download repository
            logger.info(f"📥 Downloading repository from {repo_url}")
            repo_path = await downloader.download_repo(repo_url, clone_path)
            logger.info(f"✅ Repository downloaded to {repo_path}")

            # Step 2: Get all Python files
            python_files = downloader.get_all_python_files(repo_path)
            logger.info(f"📁 Found {len(python_files)} Python files to index")

            if not python_files:
                logger.warning(f"⚠️ No Python files found in {repo_url}")
                return ToolResult(
                    success=False,
                    error="No Python files found in repository",
                    data={"repo_url": repo_url}
                )

            # Step 3: Parse files and extract entities
            logger.info(f"🔍 Parsing {len(python_files)} Python files for AST")
            all_entities = []
            all_relationships = []
            files_processed = 0
            parsing_errors = 0
            skipped_test_files = 0

            for idx, file_path in enumerate(python_files, 1):
                # Skip test files
                if "/tests/" in file_path or "/test_" in file_path:
                    skipped_test_files += 1
                    continue

                try:
                    # Parse file
                    logger.debug(f"Parsing file {idx}/{len(python_files)}: {file_path}")
                    entities = parser.parse_file(file_path)
                    all_entities.extend(entities)

                    # Get imports
                    imports = parser.extract_imports(entities)

                    # Build relationships
                    content = downloader.read_file(file_path)
                    relationships = builder.build_relationships(entities, imports, content)
                    all_relationships.extend(relationships)

                    files_processed += 1

                    # Progress logging every 10 files
                    if files_processed % 10 == 0:
                        logger.info(
                            f"Progress: {files_processed}/{len(python_files)} files parsed, "
                            f"{len(all_entities)} entities extracted"
                        )

                except FileParsingError as e:
                    parsing_errors += 1
                    logger.warning(f"⚠️ Parsing error in {file_path}: {str(e)}")
                except Exception as e:
                    parsing_errors += 1
                    logger.warning(f"⚠️ Unexpected error processing {file_path}: {str(e)}")

            logger.info(
                f"✅ Parsing complete: {files_processed} files parsed, "
                f"{skipped_test_files} test files skipped, {parsing_errors} errors"
            )
            logger.info(
                f"📊 Extracted entities: {len(all_entities)}, "
                f"Relationships: {len(all_relationships)}"
            )

            if not all_entities:
                logger.error("❌ No entities extracted from files")
                return ToolResult(
                    success=False,
                    error="No entities could be extracted from Python files",
                    data={
                        "repo_url": repo_url,
                        "files_processed": files_processed,
                        "parsing_errors": parsing_errors
                    }
                )

            # Step 4: Create Package nodes and hierarchy
            logger.info(f"📦 Creating Package hierarchy in Neo4j")
            
            # Build package set
            packages = set()
            for entity in all_entities:
                pkg = entity.get("package")
                if pkg and pkg.startswith("fastapi"):
                    parts = pkg.split(".")
                    for i in range(1, len(parts) + 1):
                        packages.add(".".join(parts[:i]))

            # Create package nodes
            for pkg in sorted(packages):
                await neo4j.create_package_node(pkg)

            # Create Package->Package hierarchy (parent contains child)
            for pkg in sorted(packages):
                if "." in pkg and pkg.startswith("fastapi."):
                    parent = pkg.rsplit(".", 1)[0]
                    await neo4j.create_relationship(
                        source_name=parent,
                        source_label="Package",
                        target_name=pkg,
                        target_label="Package",
                        rel_type="CONTAINS",
                    )

            logger.info(f"✅ Created {len(packages)} Package nodes")

            # Step 5: Create File nodes and Package->File relationships
            logger.info(f"📄 Creating File nodes and Package->File relationships")
            
            file_to_package = {}
            for entity in all_entities:
                module = entity.get("module")
                pkg = entity.get("package")
                
                if module and pkg and pkg.startswith("fastapi"):
                    file_to_package[module] = pkg

            for file_path, package_name in file_to_package.items():
                # Create file node (with path and name properties)
                await neo4j.create_file_node(file_path)
                
                # Create CONTAINS relationship
                await neo4j.create_relationship(
                    source_name=package_name,
                    source_label="Package",
                    target_name=file_path,
                    target_label="File",
                    rel_type="CONTAINS",
                )

            logger.info(f"✅ Created {len(file_to_package)} File nodes and relationships")

            # Step 6: Create entity nodes
            logger.info(f"🎯 Creating entity nodes (Classes, Functions, etc.)")
            
            entity_type_index = {}
            
            for entity in all_entities:
                try:
                    entity_type = entity.get("type")
                    entity_name = entity.get("name")
                    
                    if not entity_name:
                        continue
                    
                    # Index for later relationship creation
                    entity_type_index[(entity_name, entity_type)] = entity

                    if entity_type == "Parameter":
                        await neo4j.create_parameter_node(
                            name=entity["name"],
                            param_name=entity.get("param_name", entity["name"]),
                            module=entity.get("module", ""),
                        )
                    elif entity_type == "Type":
                        await neo4j.create_type_node(entity["name"])
                    elif entity_type == "Class":
                        await neo4j.create_class_node(
                            name=entity["name"],
                            module=entity.get("module", ""),
                            docstring=entity.get("docstring"),
                            line_number=entity.get("line_number"),
                        )
                        # File DEFINES Class
                        await neo4j.create_defines_relationship(
                            file_path=entity["module"],
                            target_name=entity["name"],
                            target_module=entity["module"],
                            target_type="Class",
                        )
                    elif entity_type == "Docstring":
                        await neo4j.create_docstring_node(
                            name=entity["name"],
                            content=entity.get("content"),
                            scope=entity.get("scope"),
                            module=entity.get("module"),
                            package=entity.get("package"),
                        )
                    elif entity_type == "Method":
                        await neo4j.create_method_node(
                            name=entity["name"],
                            module=entity["module"],
                            docstring=entity.get("docstring"),
                            line_number=entity.get("line_number"),
                            is_async=entity.get("is_async", False),
                        )
                        # File DEFINES Method
                        await neo4j.create_defines_relationship(
                            file_path=entity["module"],
                            target_name=entity["name"],
                            target_module=entity["module"],
                            target_type="Method",
                        )
                        # Class HAS_METHOD
                        if entity.get("parent_class"):
                            await neo4j.create_relationship(
                                source_name=entity["parent_class"],
                                source_label="Class",
                                target_name=entity["name"],
                                target_label="Method",
                                rel_type="HAS_METHOD",
                            )
                    elif entity_type == "Function":
                        await neo4j.create_function_node(
                            name=entity["name"],
                            module=entity.get("module", ""),
                            docstring=entity.get("docstring"),
                            line_number=entity.get("line_number"),
                            is_async=entity.get("is_async", False),
                        )
                        # File DEFINES Function
                        await neo4j.create_defines_relationship(
                            file_path=entity["module"],
                            target_name=entity["name"],
                            target_module=entity["module"],
                            target_type="Function",
                        )
                        # Class CONTAINS Function (if parent exists)
                        if entity.get("parent_class"):
                            await neo4j.create_relationship(
                                source_name=entity["parent_class"],
                                source_label="Class",
                                target_name=entity["name"],
                                target_label="Function",
                                rel_type="CONTAINS",
                            )

                except Exception as e:
                    logger.debug(f"⚠️ Skipping entity {entity.get('name')}: {str(e)}")
                    continue

            logger.info(f"✅ Created {len(all_entities)} entity nodes")

            # Step 7: Create relationships
            logger.info(f"🔗 Creating relationships between entities")
            
            relationships_created = 0
            
            for rel in all_relationships:
                try:
                    rel_type = rel.get("type")
                    
                    if rel_type == "IMPORTS":
                        await neo4j.create_relationship(
                            source_name=rel["source"],
                            source_label="Package",
                            target_name=rel["target"],
                            target_label="Package",
                            rel_type="IMPORTS",
                        )
                        relationships_created += 1
                    elif rel_type == "INHERITS_FROM":
                        await neo4j.create_relationship(
                            source_name=rel["source"],
                            source_label="Class",
                            target_name=rel["target"],
                            target_label="Class",
                            rel_type="INHERITS_FROM",
                        )
                        relationships_created += 1
                    elif rel_type == "CALLS":
                        source_is_func = (rel["source"], "Function") in entity_type_index
                        source_label = "Function" if source_is_func else "Method"
                        
                        target_is_func = (rel["target"], "Function") in entity_type_index
                        target_label = "Function" if target_is_func else "Method"
                        
                        await neo4j.create_relationship(
                            source_name=rel["source"],
                            source_label=source_label,
                            target_name=rel["target"],
                            target_label=target_label,
                            rel_type="CALLS",
                        )
                        relationships_created += 1
                    elif rel_type == "DECORATED_BY":
                        source_is_func = (rel["source"], "Function") in entity_type_index
                        source_label = "Function" if source_is_func else "Method"
                        
                        await neo4j.create_relationship(
                            source_name=rel["source"],
                            source_label=source_label,
                            target_name=rel["target"],
                            target_label="Function",
                            rel_type="DECORATED_BY",
                        )
                        relationships_created += 1
                    elif rel_type == "CONTAINS":
                        # Class->Function/Method CONTAINS relationships
                        await neo4j.create_relationship(
                            source_name=rel["source"],
                            source_label="Class",
                            target_name=rel["target"],
                            target_label="Function" if "Function" in str(rel.get("target_type")) else "Method",
                            rel_type="CONTAINS",
                        )
                        relationships_created += 1

                except Exception as e:
                    logger.debug(f"⚠️ Skipping relationship {rel.get('type')}: {str(e)}")
                    continue

            logger.info(f"✅ Created {relationships_created} relationships")

            # Step 8: Get final statistics
            logger.info(f"📊 Retrieving final graph statistics")
            stats = await neo4j.get_graph_statistics()

            logger.info(
                f"🎉 Repository indexing complete!\n"
                f"   Files: {files_processed}\n"
                f"   Entities: {len(all_entities)}\n"
                f"   Relationships: {relationships_created}\n"
                f"   Packages: {len(packages)}"
            )

            result_data = {
                "status": "success",
                "repo_url": repo_url,
                "repo_path": repo_path,
                "files_processed": files_processed,
                "files_skipped": skipped_test_files,
                "parsing_errors": parsing_errors,
                "entities_created": len(all_entities),
                "packages_created": len(packages),
                "relationships_created": relationships_created,
                "graph_statistics": stats,
            }

            return ToolResult(
                success=True,
                data=result_data,
            )

        except Exception as e:
            logger.error(f"❌ Repository indexing failed: {str(e)}")
            return ToolResult(
                success=False,
                error=str(e),
            )

    def get_definition(self) -> ToolDefinition:
        """Get tool definition for MCP protocol."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="repo_url",
                    description="GitHub repository URL (e.g., https://github.com/tiangolo/fastapi)",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="full_index",
                    description="Whether to do full index or incremental",
                    type="boolean",
                    required=False,
                    default=True,
                ),
                ToolParameter(
                    name="clone_path",
                    description="Custom path to clone repository",
                    type="string",
                    required=False,
                ),
            ],
            category=self.category,
        )


class GetIndexStatusTool(MCPTool):
    """Tool to get current indexing statistics."""

    name: str = "get_index_status"
    description: str = "Get statistics about the indexed knowledge graph"
    category: str = "indexing"

    async def execute(self) -> ToolResult:
        """
        Get index status.

        Returns:
            ToolResult with graph statistics
        """
        try:
            neo4j = get_neo4j_service()
            stats = await neo4j.get_graph_statistics()

            logger.info(f"📊 Index status retrieved")
            
            # Format for display
            formatted_stats = {
                "nodes": stats.get("nodes", {}),
                "relationships": stats.get("relationships", {}),
                "summary": f"Total nodes: {sum(stats.get('nodes', {}).values())}, "
                           f"Total relationships: {sum(stats.get('relationships', {}).values())}"
            }

            return ToolResult(
                success=True,
                data=formatted_stats,
            )

        except Exception as e:
            logger.error(f"Failed to get index status: {str(e)}")
            return ToolResult(
                success=False,
                error=str(e),
            )

    def get_definition(self) -> ToolDefinition:
        """Get tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[],
            category=self.category,
        )


class ClearIndexTool(MCPTool):
    """Tool to clear the knowledge graph (WARNING: destructive)."""

    name: str = "clear_index"
    description: str = "⚠️ Clear all data from the knowledge graph (WARNING: DESTRUCTIVE)"
    category: str = "indexing"

    async def execute(self) -> ToolResult:
        """
        Clear the knowledge graph.

        WARNING: This is destructive and cannot be undone!

        Returns:
            ToolResult indicating success
        """
        try:
            neo4j = get_neo4j_service()
            await neo4j.clear_database()

            logger.warning(f"⚠️ Knowledge graph cleared by indexer agent")

            return ToolResult(
                success=True,
                data={"message": "Knowledge graph cleared. Ready for fresh indexing."},
            )

        except Exception as e:
            logger.error(f"Failed to clear index: {str(e)}")
            return ToolResult(
                success=False,
                error=str(e),
            )

    def get_definition(self) -> ToolDefinition:
        """Get tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[],
            category=self.category,
        )


class IndexerAgent(BaseAgent):
    """
    Indexer Agent - Indexes repositories into knowledge graph.

    MCP Agent that handles:
    1. Repository downloading from GitHub
    2. Python file parsing using AST
    3. Entity extraction (Classes, Functions, Methods, etc.)
    4. Relationship building (Imports, Inheritance, Calls, etc.)
    5. Neo4j knowledge graph population

    Provides tools for:
    - Indexing repositories
    - Getting index statistics
    - Clearing index
    """

    name: str = "indexer"
    description: str = "🏗️ Indexes GitHub repositories into the knowledge graph"
    version = "1.0.0"

    def __init__(self):
        """Initialize indexer agent."""
        super().__init__()

        # Register MCP tools
        self.register_tool(IndexRepositoryTool())
        self.register_tool(GetIndexStatusTool())
        self.register_tool(ClearIndexTool())

        logger.info(f"✅ IndexerAgent initialized with 3 MCP tools")

    async def initialize(self) -> None:
        """Initialize indexer agent resources."""
        try:
            # Verify Neo4j connection
            neo4j = get_neo4j_service()
            logger.info(f"✅ Indexer agent Neo4j connection verified")
        except Exception as e:
            logger.error(f"❌ Failed to initialize indexer agent: {str(e)}")
            raise

    async def startup(self) -> None:
        """Start the indexer agent."""
        await super().startup()
        await self.initialize()
        logger.info(f"✅ Indexer agent started and ready")

    async def shutdown(self) -> None:
        """Shut down the indexer agent."""
        await super().shutdown()
        logger.info(f"✅ Indexer agent shut down")