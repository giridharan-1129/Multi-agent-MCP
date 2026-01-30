"""
Indexer Agent - MCP Agent for Repository Indexing.

WHAT: MCP agent that indexes GitHub repositories into knowledge graph
WHY: Convert raw repository code into queryable knowledge graph
HOW: Download repo, parse files, extract entities, build relationships, store in Neo4j

Example:
    agent = IndexerAgent()
    await agent.startup()
    
    result = await agent.execute_tool("index_repository", {
        "repo_url": "https://github.com/tiangolo/fastapi",
        "full_index": True
    })
"""

from typing import Any, Dict, Optional

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
    """Tool to index an entire repository."""

    name: str = "index_repository"
    description: str = "Index a GitHub repository into the knowledge graph"
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

            # Download repository
            logger.info("Downloading repository", url=repo_url)
            repo_path = await downloader.download_repo(repo_url, clone_path)

            # Get all Python files
            python_files = downloader.get_all_python_files(repo_path)
            logger.info("Python files found", count=len(python_files))

            # Parse files and extract entities
            all_entities = []
            all_relationships = []
            files_processed = 0
            parsing_errors = 0

            for file_path in python_files:
                try:
                    # Read file content
                    content = downloader.read_file(file_path)

                    # Parse file
                    entities = parser.parse_file(file_path)
                    all_entities.extend(entities)

                    # Get imports
                    imports = parser.extract_imports(entities)

                    # Build relationships
                    relationships = builder.build_relationships(entities, imports, content)
                    all_relationships.extend(relationships)

                    files_processed += 1

                    if files_processed % 10 == 0:
                        logger.info(
                            "Files processed",
                            count=files_processed,
                            total=len(python_files),
                        )

                except FileParsingError as e:
                    parsing_errors += 1
                    logger.error("Error parsing file", file=file_path, error=str(e))
                except Exception as e:
                    parsing_errors += 1
                    logger.error("Unexpected error processing file", file=file_path, error=str(e))

            # Store in Neo4j
            # ============================================================================
            # STEP 2 FIX: Build file-to-package map ONCE, create relationships ONCE
            # ============================================================================
            
            # Build entity lookup ONCE
            entity_lookup = {
                (e["name"], e.get("type")): e.get("module")
                for e in all_entities
            }

            # Extract unique packages and files with deterministic mapping
            packages = set()
            file_to_package = {}  # file_path -> package_name
            
            for entity in all_entities:
                pkg = entity.get("package")
                module = entity.get("module")
                
                # If package is empty, derive from module path
                if not pkg and module:
                    # Extract package from file path: /path/to/module.py → module
                    pkg = module.split("/")[-1].replace(".py", "")
                
                # Only add if we have a valid package and module
                if pkg and module:
                    packages.add(pkg)
                    file_to_package[module] = pkg

            # Create Package nodes first
            logger.info("Creating Package nodes", count=len(packages))
            for pkg in packages:
                await neo4j.create_package_node(pkg)

            # Create File nodes and Package -> File CONTAINS relationships
            # This is deterministic: each file created once, each CONTAINS created once
            logger.info("Creating File nodes and CONTAINS relationships", count=len(file_to_package))
            for file_path, package_name in file_to_package.items():
                # Create file node (with both path and name properties from Step 1)
                await neo4j.create_file_node(file_path)
                
                # Create CONTAINS relationship
                await neo4j.create_relationship(
                    source_name=package_name,
                    source_label="Package",
                    target_name=file_path,
                    target_label="File",
                    rel_type="CONTAINS",
                )



            logger.info("Storing entities in Neo4j", count=len(all_entities))
            for entity in all_entities:
                try:
                    if entity["type"] == "Class":
                        await neo4j.create_class_node(
                            name=entity["name"],
                            module=entity.get("module", ""),
                            docstring=entity.get("docstring"),
                            line_number=entity.get("line_number"),
                        )
                        await neo4j.create_defines_relationship(
                                file_path=entity["module"],
                                target_name=entity["name"],
                                target_module=entity["module"],
                                target_type="Class",
                            )
                    elif entity["type"] == "Function":
                            await neo4j.create_function_node(
                                name=entity["name"],
                                module=entity.get("module", ""),
                                docstring=entity.get("docstring"),
                                line_number=entity.get("line_number"),
                                is_async=entity.get("is_async", False),
                            )
                            await neo4j.create_defines_relationship(
                                file_path=entity["module"],
                                target_name=entity["name"],
                                target_module=entity["module"],
                                target_type="Function",
                            )
                            if entity.get("parent_class"):
                                await neo4j.create_relationship(
                                    source_name=entity["parent_class"],
                                    source_module=entity["module"],
                                    target_name=entity["name"],
                                    target_module=entity["module"],
                                    rel_type="DEFINES",
                                
    )

                except Exception as e:
                    logger.error("Error storing entity", entity=entity["name"], error=str(e))
                # Build entity lookup for module resolution
               

            # Store relationships
            logger.info("Storing relationships in Neo4j", count=len(all_relationships))
            for rel in all_relationships:
                try:
                    source_module = rel.get("source_module")
                    target_module = rel.get("target_module")

                    # Resolve target module if missing
                    if target_module is None:
                        target_module = entity_lookup.get(
                            (rel["target"], "Class")
                            
                        ) or entity_lookup.get(
                            (rel["target"], "Function")
                        )

                    # Skip if we still canâ€™t resolve
                    if not source_module or not target_module:
                        continue

                    LABEL_MAP = {
                        "IMPORTS": ("Package", "Package"),
                        "CONTAINS": ("Package", "File"),
                        "DEFINES": ("File", None),  # handled separately
                        "CALLS": ("Function", "Function"),
                        "INHERITS_FROM": ("Class", "Class"),
                        "DECORATED_BY": ("Function", "Function"),
                    }

                    source_label, target_label = LABEL_MAP.get(rel["type"], (None, None))

                    if not source_label or not target_label:
                        continue

                    # Only create relationship if both nodes exist in the database
                    # This ensures determinism: only successful relationships are created
                    source_exists = await neo4j.find_entity(rel["source"], source_label)
                    target_exists = await neo4j.find_entity(rel["target"], target_label)
                    
                    if not source_exists or not target_exists:
                        logger.debug(
                            "Skipping relationship - node missing",
                            source=rel["source"],
                            target=rel["target"],
                            rel_type=rel["type"],
                        )
                        continue

                    await neo4j.create_relationship(
                        source_name=rel["source"],
                        source_label=source_label,
                        target_name=rel["target"],
                        target_label=target_label,
                        rel_type=rel["type"],
                        properties={"line_number": rel.get("line_number")},
                    )


                except Exception as e:
                    logger.warning("Failed to store relationship", rel=rel, error=str(e))


            # Get final statistics
            stats = await neo4j.get_graph_statistics()

            result_data = {
                "status": "success",
                "repo_url": repo_url,
                "repo_path": repo_path,
                "files_processed": files_processed,
                "parsing_errors": parsing_errors,
                "entities_created": len(all_entities),
                "relationships_created": len(all_relationships),
                "graph_statistics": stats,
            }

            logger.info("Repository indexed successfully", data=result_data)

            return ToolResult(
                success=True,
                data=result_data,
            )

        except Exception as e:
            logger.error("Failed to index repository", url=repo_url, error=str(e))
            return ToolResult(
                success=False,
                error=str(e),
            )

    def get_definition(self) -> ToolDefinition:
        """Get tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="repo_url",
                    description="GitHub repository URL",
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
    """Tool to get indexing status."""

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

            return ToolResult(
                success=True,
                data=stats,
            )

        except Exception as e:
            logger.error("Failed to get index status", error=str(e))
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
    """Tool to clear the knowledge graph."""

    name: str = "clear_index"
    description: str = "Clear all data from the knowledge graph (WARNING: destructive)"
    category: str = "indexing"

    async def execute(self) -> ToolResult:
        """
        Clear the knowledge graph.

        WARNING: This is destructive!

        Returns:
            ToolResult indicating success
        """
        try:
            neo4j = get_neo4j_service()
            await neo4j.clear_database()

            logger.warning("Knowledge graph cleared by request")

            return ToolResult(
                success=True,
                data={"message": "Knowledge graph cleared"},
            )

        except Exception as e:
            logger.error("Failed to clear index", error=str(e))
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

    Provides tools for:
    - Indexing repositories
    - Getting index statistics
    - Clearing index
    """

    name: str = "indexer"
    description: str = "Indexes GitHub repositories into the knowledge graph"
    version = "1.0.0"

    def __init__(self):
        """Initialize indexer agent."""
        super().__init__()

        # Register tools
        self.register_tool(IndexRepositoryTool())
        self.register_tool(GetIndexStatusTool())
        self.register_tool(ClearIndexTool())

        logger.info("IndexerAgent initialized with 3 tools")

    async def initialize(self) -> None:
        """Initialize indexer agent resources."""
        try:
            # Verify Neo4j connection
            neo4j = get_neo4j_service()
            logger.info("Indexer agent ready")
        except Exception as e:
            logger.error("Failed to initialize indexer agent", error=str(e))
            raise

    async def startup(self) -> None:
        """Start the indexer agent."""
        await super().startup()
        await self.initialize()
        logger.info("Indexer agent started")

    async def shutdown(self) -> None:
        """Shut down the indexer agent."""
        await super().shutdown()
        logger.info("Indexer agent shut down")