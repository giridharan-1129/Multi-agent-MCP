"""
RAG (Retrieval-Augmented Generation) Chat endpoint.

Retrieves relevant context from BOTH embeddings AND graph in parallel,
then generates responses using unified context.
"""

from fastapi import APIRouter, HTTPException
from openai import OpenAI
import os
import asyncio
from pydantic import BaseModel, ConfigDict
from typing import Optional
from ...shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ...shared.neo4j_service import get_neo4j_service

logger = get_logger(__name__)
router = APIRouter(tags=["rag_chat"], prefix="/api")


class RAGChatRequest(BaseModel):
    """RAG chat request."""
    query: str
    session_id: Optional[str] = None
    retrieve_limit: int = 5

    model_config = ConfigDict(extra="ignore")


class RAGChatResponse(BaseModel):
    """RAG chat response with retrieved context."""
    session_id: str
    response: str
    retrieved_context: list
    agents_used: list
    correlation_id: str


async def get_embeddings_context(query: str, repo_id: str = None) -> list:
    """
    Retrieve code chunks from Pinecone embeddings.
    
    Args:
        query: Search query
        repo_id: Optional repository ID
        
    Returns:
        List of code chunk citations
    """
    try:
        # Check if Pinecone is configured first
        if not os.getenv("PINECONE_API_KEY"):
            logger.info("⚠️ PINECONE_API_KEY not set - skipping embeddings search")
            return []
        
        from ...shared.pinecone_embeddings_service import get_embeddings_service
        
        embeddings_service = get_embeddings_service()
        
        # Verify service initialized
        if embeddings_service is None or not hasattr(embeddings_service, 'index'):
            logger.warning("⚠️ Embeddings service not initialized - skipping")
            return []
        
        if not embeddings_service.index:
            logger.warning("⚠️ Embeddings service index not available - skipping")
            return []
        
        # Use repo_id if available, otherwise use default
        search_repo_id = repo_id or "fastapi"
        
        logger.info(f"Searching embeddings for: {query[:100]}")
        
        # Semantic search with reranking
        results = await embeddings_service.search_with_reranking(
            query=query,
            repo_id=search_repo_id,
            top_k=5
        )
        
        logger.info(f"Found {len(results)} code chunks from embeddings")
        return results
        
    except Exception as e:
        logger.warning(f"⚠️ Embeddings search failed: {str(e)}")
        logger.info("✅ Falling back to Neo4j graph-only search")
        return []


async def get_graph_context(query: str, repo_id: str = None, limit: int = 5) -> list:
    """
    Retrieve entities and relationships from Neo4j graph.
    
    Args:
        query: Search query
        repo_id: Optional repository ID
        limit: Max results per query
        
    Returns:
        List of entity relationships
    """
    try:
        neo4j = get_neo4j_service()
        
        logger.info(f"Searching graph for: {query[:100]}")
        
        # Extract keywords from query
        try:
            import requests
            keyword_response = requests.post(
                "http://localhost:8000/api/query/extract-keywords",
                json={"query": query},
                timeout=5
            )
            if keyword_response.ok:
                keywords = keyword_response.json().get("keywords", [])
                logger.info(f"Keywords extracted via API: {keywords}")
            else:
                # Fallback to simple extraction
                keywords = [w.strip().lower() for w in query.split() if len(w) > 4]
        except Exception as e:
            logger.debug(f"Keyword extraction API failed: {e}, using fallback")
            keywords = [w.strip().lower() for w in query.split() if len(w) > 4]
        
        if not keywords:
            logger.warning("No keywords extracted from query")
            return []
        
        relationships = []
        
        # Search for matching entities
        for keyword in keywords[:3]:  # Limit to first 3 keywords
            try:
                # Search for entities matching keyword
                cypher = """
    MATCH (e)
    WHERE e.name IS NOT NULL 
    AND toLower(e.name) CONTAINS toLower($keyword)
    WITH e, labels(e)[0] as entity_type LIMIT $limit

    OPTIONAL MATCH (e)-[dep_rel]->(dependency)
    WITH e, entity_type, collect(DISTINCT dependency.name) as deps

    OPTIONAL MATCH (dependent)-[dep_rel2]->(e)
    WITH e, entity_type, deps, collect(DISTINCT dependent.name) as dependents

    OPTIONAL MATCH (file:File)-[:DEFINES]->(e)
    WITH e, entity_type, deps, dependents, file.path as file_path

    RETURN {
        type: "relationship",
        entity: e.name,
        entity_type: entity_type,
        dependencies: deps,
        dependents: dependents,
        docstring: e.docstring,
        module: e.module,
        file_path: CASE WHEN file_path IS NOT NULL THEN file_path ELSE e.module END,
        line_number: e.line_number
    } as relationship
    """
                results = await neo4j.execute_query(cypher, {"keyword": keyword, "limit": limit})
                
                for result in results:
                    rel = result.get("relationship", {})
                    if rel and rel not in relationships:
                        relationships.append(rel)
                
                if len(relationships) >= limit:
                    break
                    
            except Exception as e:
                logger.debug(f"Error searching for keyword '{keyword}': {str(e)}")
                continue
        
        logger.info(f"Found {len(relationships)} relationships from graph")

        # Log retrieved relationships
        for i, rel in enumerate(relationships[:3], 1):
            deps = rel.get('dependencies', [])
            dependents = rel.get('dependents', [])
            logger.info(f"  [{i}] {rel.get('entity_type', 'Unknown')}: {rel.get('entity', 'unknown')} | Dependencies: {len(deps)} | Dependents: {len(dependents)}")

        return relationships
        
    except Exception as e:
        logger.warning(f"Graph search failed: {str(e)} - continuing with embeddings only")
        return []

async def retrieve_parallel_context(query: str, session_id: str, retrieve_limit: int = 5) -> tuple:
    """
    Retrieve context from BOTH embeddings AND graph in parallel.
    
    Args:
        query: User query
        session_id: Session ID
        retrieve_limit: Max results per source
        
    Returns:
        Tuple of (embeddings_results, graph_results)
    """
    logger.info(f"🔍 Starting parallel retrieval for: {query[:100]}")
    logger.info("🔄 Parallel execution: [Embeddings Agent] + [Graph Query Agent]")

    # Execute both retrievals in parallel
    embeddings_results, graph_results = await asyncio.gather(
        get_embeddings_context(query, repo_id="fastapi"),
        get_graph_context(query, repo_id="fastapi", limit=retrieve_limit),
        return_exceptions=True
    )

    # Handle any failures - convert exceptions to empty lists
    if isinstance(embeddings_results, Exception):
        logger.warning(f"Embeddings retrieval failed: {embeddings_results}")
        embeddings_results = []
    
    if isinstance(graph_results, Exception):
        logger.warning(f"Graph retrieval failed: {graph_results}")
        graph_results = []
    
    # Ensure we have lists
    embeddings_results = embeddings_results if isinstance(embeddings_results, list) else []
    graph_results = graph_results if isinstance(graph_results, list) else []
    
    # Log results safely
    logger.info(f"\n📊 EMBEDDINGS RETRIEVED:")
    if embeddings_results:
        for i, chunk in enumerate(embeddings_results, 1):
            try:
                relevance = float(chunk.get('relevance', 0)) if chunk.get('relevance') else 0
                logger.info(f"  [{i}] File: {chunk.get('file', 'N/A')} | Lines: {chunk.get('lines', 'N/A')} | Relevance: {relevance:.1%}")
            except Exception as e:
                logger.debug(f"Error logging chunk {i}: {str(e)}")
    else:
        logger.info("  No embeddings found")

    logger.info(f"\n🔗 NEO4J RELATIONSHIPS RETRIEVED:")
    if graph_results:
        for i, rel in enumerate(graph_results, 1):
            try:
                deps = rel.get('dependencies', []) if rel.get('dependencies') else []
                dependents = rel.get('dependents', []) if rel.get('dependents') else []
                logger.info(f"  [{i}] Entity: {rel.get('entity', 'N/A')} | Type: {rel.get('entity_type', 'N/A')} | Dependencies: {len(deps)} | Dependents: {len(dependents)}")
            except Exception as e:
                logger.debug(f"Error logging relationship {i}: {str(e)}")
    else:
        logger.info("  No relationships found")

    logger.info(f"\n✅ Parallel retrieval complete: {len(embeddings_results)} chunks + {len(graph_results)} relationships")

    return embeddings_results, graph_results


def format_unified_context(embeddings: list, relationships: list) -> str:
    """
    Format both embeddings and relationships into unified context.
    
    Args:
        embeddings: Code chunk citations
        relationships: Entity relationships
        
    Returns:
        Formatted context string
    """
    context_parts = []
    
    # Section 1: Code Chunks (WHAT)
    if embeddings and len(embeddings) > 0:
        context_parts.append("\n📝 CODE CHUNKS (Semantic Search - WHAT the code does):\n")
        
        for i, chunk in enumerate(embeddings[:5], 1):
            try:
                file_path = chunk.get('file_path', 'unknown') if chunk.get('file_path') else 'unknown'
                lines = chunk.get('lines', 'unknown') if chunk.get('lines') else 'unknown'
                relevance = float(chunk.get('relevance', 0)) if chunk.get('relevance') else 0
                preview = str(chunk.get('preview', 'N/A'))[:300] if chunk.get('preview') else 'N/A'
                
                context_parts.append(f"\n{i}. File: {file_path}")
                context_parts.append(f"   Lines: {lines}")
                context_parts.append(f"   Relevance: {relevance:.1%}")
                context_parts.append(f"   Preview: {preview}...")
            except Exception as e:
                logger.debug(f"Error formatting chunk {i}: {str(e)}")
                continue
    
    # Section 2: Relationships (WHERE/HOW)
    if relationships and len(relationships) > 0:
        context_parts.append("\n\n🔗 CODE RELATIONSHIPS (Graph - WHERE/HOW code is used):\n")
        
        for i, rel in enumerate(relationships[:5], 1):
            try:
                entity = rel.get('entity', 'unknown') if rel.get('entity') else 'unknown'
                entity_type = rel.get('entity_type', 'unknown') if rel.get('entity_type') else 'unknown'
                deps = rel.get('dependencies', []) if rel.get('dependencies') else []
                dependents = rel.get('dependents', []) if rel.get('dependents') else []
                
                deps = deps[:3] if isinstance(deps, list) else []
                dependents = dependents[:3] if isinstance(dependents, list) else []
                
                context_parts.append(f"\n{i}. {entity_type}: {entity}")
                
                if deps and len(deps) > 0:
                    deps_str = ', '.join([str(d) for d in deps])
                    context_parts.append(f"   Dependencies: {deps_str}")
                if dependents and len(dependents) > 0:
                    dependents_str = ', '.join([str(d) for d in dependents])
                    context_parts.append(f"   Used by: {dependents_str}")
                
                docstring = rel.get('docstring')
                if docstring:
                    docstring_str = str(docstring)[:200] if docstring else 'N/A'
                    context_parts.append(f"   Documentation: {docstring_str}...")
            except Exception as e:
                logger.debug(f"Error formatting relationship {i}: {str(e)}")
                continue
    
    result = "".join(context_parts)
    return result if result.strip() else "No context available from embeddings or graph."

@router.post("/rag-chat", response_model=RAGChatResponse)
async def rag_chat(request: RAGChatRequest):
    """
    RAG-enhanced chat endpoint with parallel retrieval.
    
    Retrieves context from BOTH:
    1. Pinecone embeddings (semantic search for code chunks)
    2. Neo4j graph (relationships and dependencies)
    
    Then generates response using unified context.
    
    Args:
        request: RAG chat request with query and optional session_id
    
    Returns:
        RAG chat response with unified context and response
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)
    
    try:
        # Validate request
        if not request.query or len(request.query.strip()) == 0:
            raise HTTPException(status_code=400, detail="query cannot be empty")
        
        logger.info(
            "RAG chat request received",
            query=request.query[:100],
            session_id=request.session_id,
        )
        
        # Step 1: Parallel retrieval from embeddings AND graph
        logger.info("Step 1: Parallel retrieval from embeddings and graph")
        embeddings_context, graph_context = await retrieve_parallel_context(
            query=request.query,
            session_id=request.session_id,
            retrieve_limit=request.retrieve_limit
        )
        
        # Step 2: Format unified context
        logger.info("Step 2: Formatting unified context")
        unified_context = format_unified_context(embeddings_context, graph_context)
        
        if not unified_context.strip():
            logger.warning("No context retrieved from either source")
            unified_context = "No relevant code context found in repository."
        
        # Step 3: Prepare context for LLM
        logger.info("Step 3: Generating response with LLM")
        
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Determine if using embeddings or graph-only
        has_embeddings = len(embeddings_context) > 0
        source_type = "Embeddings + Graph" if has_embeddings else "Graph (Neo4j)"

        system_prompt = (
            f"You are a software engineering tutor explaining FastAPI codebase.\n"
            f"Context Source: {source_type}\n\n"
            f"IMPORTANT: Explain code clearly for students learning FastAPI architecture.\n\n"
            f"You have access to:\n"
            f"1. CODE CHUNKS: Actual code from files (what happens)\n"
            f"2. CODE RELATIONSHIPS: Dependencies, imports, inheritance (how things connect)\n\n"
            f"Response Guidelines:\n"
            f"- Start with WHAT (what does this code do)\n"
            f"- Then explain WHERE (where is it used, what calls it)\n"
            f"- Finally show HOW (design pattern, best practices)\n"
            f"- Reference file paths and line numbers\n"
            f"- Use analogies for complex concepts\n"
            f"- Keep explanations accessible to students\n\n"
            f"Only use the provided context. Do NOT add external knowledge."
        )
        
        # Safely handle context
        context_str = unified_context if (unified_context and unified_context.strip()) else "No relevant context found in repository."
        
        user_prompt = f"""
User Question:
{request.query}

Retrieved Context:
{context_str}
"""
        
        logger.info("Calling OpenAI API for response generation")
        
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=1500,
            )
            
            response_text = completion.choices[0].message.content
            
            if not response_text:
                logger.warning("LLM returned empty response")
                response_text = "Unable to generate response. Please try again."
                
        except Exception as e:
            logger.error(f"LLM API call failed: {str(e)}")
            response_text = f"Error generating response: {str(e)[:100]}"
        
        logger.info(
            "RAG chat response generated",
            session_id=request.session_id or "no-session",
            embeddings_count=len(embeddings_context) if embeddings_context else 0,
            relationships_count=len(graph_context) if graph_context else 0,
        )
        
        # Step 4: Create session if needed
        session_id = request.session_id
        if not session_id:
            session_id = f"session-{correlation_id}"
        
        # Ensure session_id is never None
        session_id = session_id if session_id else "no-session"
        
        # Step 5: Build retrieved context for response
        all_context = []

        # Add embeddings with FULL metadata
        if embeddings_context and len(embeddings_context) > 0:
            for i, chunk in enumerate(embeddings_context):
                try:
                    if chunk is None:
                        logger.debug(f"Skipping None chunk at index {i}")
                        continue
                    
                    relevance_val = float(chunk.get('relevance', 0)) if chunk and chunk.get('relevance') else 0
                    
                    all_context.append({
                        "type": "code_chunk",
                        "source": "Semantic Search (Pinecone)",
                        "file_path": str(chunk.get('file', 'unknown')) if chunk.get('file') else 'unknown',
                        "file_name": str(chunk.get('file_name', 'unknown')) if chunk.get('file_name') else 'unknown',
                        "lines": str(chunk.get('lines', 'unknown')) if chunk.get('lines') else 'unknown',
                        "language": str(chunk.get('language', 'python')) if chunk.get('language') else 'python',
                        "relevance_score": relevance_val,
                        "relevance_percent": f"{relevance_val:.1%}",
                        "preview": str(chunk.get('preview', 'N/A'))[:300] if chunk.get('preview') else 'N/A',
                        "chunk_id": str(chunk.get('chunk_id', 'unknown')) if chunk.get('chunk_id') else 'unknown',
                        "reranked": True,
                        "index": i + 1
                    })
                except Exception as e:
                    logger.debug(f"Error processing chunk {i}: {str(e)}")
                    continue

        # Add relationships with source marker
        # Add relationships with source marker
        if graph_context and len(graph_context) > 0:
            for i, rel in enumerate(graph_context):
                try:
                    if rel is None:
                        logger.debug(f"Skipping None relationship at index {i}")
                        continue
                    
                    deps = rel.get('dependencies', []) if rel and rel.get('dependencies') else []
                    deps = deps if isinstance(deps, list) else []
                    
                    dependents = rel.get('dependents', []) if rel and rel.get('dependents') else []
                    dependents = dependents if isinstance(dependents, list) else []
                    
                    # Get file path from relationship
                    file_path = rel.get('file_path', 'unknown') if rel and rel.get('file_path') else 'unknown'
                    module = rel.get('module', 'unknown') if rel and rel.get('module') else 'unknown'
                    line_number = rel.get('line_number', 0) if rel and rel.get('line_number') else 0
                    
                    all_context.append({
                        "type": "relationship",
                        "source": "Knowledge Graph (Neo4j)",
                        "file_path": str(file_path),
                        "file_name": file_path.split('/')[-1] if file_path != 'unknown' else 'unknown',
                        "module": str(module),
                        "line_number": line_number,
                        "entity": str(rel.get('entity', 'unknown')) if rel and rel.get('entity') else 'unknown',
                        "entity_type": str(rel.get('entity_type', 'unknown')) if rel and rel.get('entity_type') else 'unknown',
                        "dependencies": deps,
                        "used_by": dependents,
                        "documentation": str(rel.get('docstring', 'N/A'))[:150] if rel and rel.get('docstring') else 'N/A',
                        "reranked": False,
                        "relevance_score": 0,
                        "index": i + 1
                    })
                except Exception as e:
                    logger.debug(f"Error processing relationship {i}: {str(e)}")
                    continue
        
        logger.info(f"RAG chat response generated with {len(all_context)} context items")
        
        # Ensure all fields are safe before returning
        final_response = response_text if (response_text and isinstance(response_text, str) and response_text.strip()) else "Unable to generate response from context."
        final_agents = []
        if embeddings_context and len(embeddings_context) > 0:
            final_agents.append("embeddings")
        if graph_context and len(graph_context) > 0:
            final_agents.append("graph_query")
        if not final_agents:
            final_agents = ["graph_query"]
        
        return RAGChatResponse(
            session_id=session_id,
            response=final_response,
            retrieved_context=all_context,
            agents_used=final_agents,
            correlation_id=correlation_id,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "RAG chat request failed",
            error=str(e),
            correlation_id=correlation_id,
        )
        raise HTTPException(status_code=500, detail=str(e))