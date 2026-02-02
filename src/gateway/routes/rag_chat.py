"""
RAG Chat - Unified endpoint that retrieves from BOTH embeddings AND graph.

NOT a fallback. Both sources are queried in parallel for complete context:
1. Code chunks from embeddings (650-line chunks with reranking)
2. Relationships from Neo4j graph (how code is used across codebase)
"""

from fastapi import APIRouter, HTTPException
from openai import OpenAI
import os
import asyncio
from pydantic import BaseModel, ConfigDict
from typing import Optional
from ...shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ...shared.neo4j_service import get_neo4j_service
from ..dependencies import get_orchestrator

logger = get_logger(__name__)
router = APIRouter(tags=["rag_chat"], prefix="/api")


class RAGChatRequest(BaseModel):
    """RAG chat request."""
    query: str
    session_id: Optional[str] = None
    retrieve_limit: int = 5
    model_config = ConfigDict(extra="ignore")


class RAGChatResponse(BaseModel):
    """RAG chat response with BOTH embedding and graph context."""
    session_id: str
    response: str
    retrieved_context: list
    agents_used: list
    correlation_id: str


@router.post("/rag-chat", response_model=RAGChatResponse)
async def rag_chat(request: RAGChatRequest):
    """
    Unified RAG endpoint.
    
    Retrieves context from BOTH sources in parallel:
    1. Embeddings: Code chunks with semantic search + reranking
    2. Graph: Relationships (where code is used, inheritance, calls)
    
    User sees both code explanation AND usage context in one response.
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)
    
    try:
        orchestrator = get_orchestrator()
        neo4j = get_neo4j_service()
        
        logger.info(
            "RAG chat request received",
            query=request.query[:100],
            session_id=request.session_id,
        )
        
        # ========================================================================
        # PARALLEL RETRIEVAL: Both embeddings AND graph (NOT fallback)
        # ========================================================================
        
        retrieved_embeddings = []
        retrieved_relationships = []
        
        # Task 1: Get embeddings (code chunks with reranking)
        async def get_embeddings():
            try:
                from ...shared.pinecone_embeddings_service import get_embeddings_service
                embeddings_service = get_embeddings_service()
                
                logger.info("Searching embeddings for code chunks", query=request.query)
                results = await embeddings_service.search_with_reranking(
                    query=request.query,
                    repo_id="fastapi",  # Make configurable
                    top_k=request.retrieve_limit
                )
                
                logger.info("Embeddings retrieved", count=len(results))
                return results or []
            
            except Exception as e:
                logger.warning(f"Embedding search failed: {str(e)}")
                return []
        
        # Task 2: Get relationships from graph (how code is used)
        async def get_relationships():
            try:
                logger.info("Searching graph for relationships", query=request.query)
                
                # Extract entity names from query
                keywords = [
                    word.strip().lower()
                    for word in request.query.split()
                    if len(word) > 4
                ]
                
                all_relationships = []
                seen = set()
                
                for keyword in keywords:
                    # Find entities matching keyword
                    entities = await neo4j.search_entities(keyword, limit=3)
                    
                    for entity in entities:
                        entity_name = entity.get("name")
                        if entity_name and entity_name not in seen:
                            seen.add(entity_name)
                            
                            # Get dependencies and dependents
                            deps = await neo4j.get_dependencies(entity_name)
                            dependents = await neo4j.get_dependents(entity_name)
                            
                            all_relationships.append({
                                "entity_name": entity_name,
                                "entity_type": entity.get("type"),
                                "dependencies": deps[:3],  # Limit for brevity
                                "dependents": dependents[:3],
                                "docstring": entity.get("docstring", "")[:200]
                            })
                    
                    if len(all_relationships) >= request.retrieve_limit:
                        break
                
                logger.info("Relationships retrieved", count=len(all_relationships))
                return all_relationships
            
            except Exception as e:
                logger.warning(f"Graph search failed: {str(e)}")
                return []
        
        # Run both tasks in parallel
        retrieved_embeddings, retrieved_relationships = await asyncio.gather(
            get_embeddings(),
            get_relationships(),
            return_exceptions=False
        )
        
        # ========================================================================
        # SESSION MANAGEMENT
        # ========================================================================
        
        session_id = request.session_id
        if not session_id:
            create_result = await orchestrator.execute_tool(
                "create_conversation",
                {},
            )
            if create_result.success:
                session_id = create_result.data.get("session_id")
            else:
                raise HTTPException(status_code=500, detail="Failed to create session")
        
        # ========================================================================
        # QUERY ANALYSIS
        # ========================================================================
        
        analysis_result = await orchestrator.execute_tool(
            "analyze_query",
            {
                "query": request.query,
                "session_id": session_id,
            },
        )
        
        if not analysis_result.success:
            raise HTTPException(status_code=400, detail="Query analysis failed")
        
        analysis = analysis_result.data
        agents_used = analysis.get("required_agents", ["rag_orchestrator"])
        
        # Add user message to conversation
        await orchestrator.execute_tool(
            "add_conversation_message",
            {
                "session_id": session_id,
                "role": "user",
                "content": request.query,
            },
        )
        
        # ========================================================================
        # UNIFIED CONTEXT: Code chunks + Relationships
        # ========================================================================
        
        context_text = ""
        
        # Add code chunks from embeddings
        if retrieved_embeddings:
            context_text += "\n📝 CODE CHUNKS (Semantic Search):\n"
            context_text += "=" * 50 + "\n"
            for i, result in enumerate(retrieved_embeddings, 1):
                context_text += f"\n{i}. File: {result.get('file', 'Unknown')}\n"
                context_text += f"   Lines: {result.get('lines', '?')}\n"
                context_text += f"   Relevance Score: {result.get('relevance', 0):.2f}\n"
                context_text += f"   Preview:\n"
                context_text += f"   {result.get('preview', '')[:400]}\n"
        
        # Add relationships from graph
        if retrieved_relationships:
            context_text += "\n\n🔗 CODE RELATIONSHIPS (Usage & Dependencies):\n"
            context_text += "=" * 50 + "\n"
            for i, rel in enumerate(retrieved_relationships, 1):
                context_text += f"\n{i}. Entity: {rel.get('entity_name')} ({rel.get('entity_type')})\n"
                
                if rel.get('dependencies'):
                    context_text += f"   Depends on: {', '.join([d.get('target_name', 'unknown') for d in rel['dependencies']])}\n"
                
                if rel.get('dependents'):
                    context_text += f"   Used by: {', '.join([d.get('source_name', 'unknown') for d in rel['dependents']])}\n"
                
                if rel.get('docstring'):
                    context_text += f"   Docs: {rel['docstring']}\n"
        
        # ========================================================================
        # RESPONSE GENERATION
        # ========================================================================
        
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        system_prompt = (
            "You are a senior software engineer assistant analyzing codebases.\n\n"
            "You have access to TWO types of context:\n"
            "1. CODE CHUNKS: Actual code snippets with line numbers (from semantic search)\n"
            "2. RELATIONSHIPS: How code entities depend on each other (from knowledge graph)\n\n"
            "IMPORTANT:\n"
            "- FIRST: Explain WHAT the code does (using code chunks)\n"
            "- THEN: Explain WHERE and HOW it's used (using relationships)\n"
            "- Use line numbers from chunks to point to specific code\n"
            "- Reference relationships to show integration points\n"
            "- If information is missing, explicitly state what's not available\n\n"
            "Format your answer with clear sections for CODE EXPLANATION and USAGE CONTEXT."
        )

        user_prompt = f"""
        Question:
        {request.query}

        Available Context:
        {context_text if context_text else "⚠️ No code context found in repositories."}
        """

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )

        response_text = completion.choices[0].message.content

        # ========================================================================
        # SAVE TO CONVERSATION
        # ========================================================================
        
        await orchestrator.execute_tool(
            "add_conversation_message",
            {
                "session_id": session_id,
                "role": "assistant",
                "content": response_text,
                "agent_name": "rag_unified",
            },
        )
        
        # ========================================================================
        # FORMAT RESPONSE
        # ========================================================================
        
        formatted_context = []
        
        # Add embeddings
        if retrieved_embeddings:
            for result in retrieved_embeddings:
                formatted_context.append({
                    "type": "code_chunk",
                    "file": result.get('file', 'unknown'),
                    "lines": result.get('lines', '?'),
                    "relevance": result.get('relevance', 0),
                    "preview": result.get('preview', '')[:300]
                })
        
        # Add relationships
        if retrieved_relationships:
            for rel in retrieved_relationships:
                formatted_context.append({
                    "type": "relationship",
                    "entity": rel.get('entity_name'),
                    "entity_type": rel.get('entity_type'),
                    "dependencies": [d.get('target_name') for d in rel.get('dependencies', [])],
                    "used_by": [d.get('source_name') for d in rel.get('dependents', [])]
                })
        
        logger.info(
            "RAG chat response generated",
            session_id=session_id,
            embeddings_count=len(retrieved_embeddings),
            relationships_count=len(retrieved_relationships),
        )
        
        return RAGChatResponse(
            session_id=session_id,
            response=response_text,
            retrieved_context=formatted_context,
            agents_used=agents_used,
            correlation_id=correlation_id,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("RAG chat failed", error=str(e), correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail=str(e))