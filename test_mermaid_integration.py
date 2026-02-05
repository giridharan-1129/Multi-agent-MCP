"""
Integration test for Mermaid tool in Orchestrator Service.

Tests:
1. Service initialization
2. Tool registration
3. Tool execution
4. Mermaid code generation
"""

import asyncio
import sys
import os

sys.path.insert(0, '/mnt/project')

from services.orchestrator_service.service import OrchestratorService
from src.shared.mcp_server import ToolResult

async def test_mermaid_integration():
    """Test the complete Mermaid tool integration."""
    
    print("\n" + "="*80)
    print("🧪 MERMAID TOOL INTEGRATION TEST")
    print("="*80)
    
    # TEST 1: Initialize Service
    print("\n[TEST 1] Initializing OrchestratorService...")
    try:
        service = OrchestratorService()
        await service.initialize()
        print("✅ Service initialized successfully")
    except Exception as e:
        print(f"❌ Service initialization failed: {e}")
        return False
    
    # TEST 2: Check Tool Registration
    print("\n[TEST 2] Checking tool registration...")
    try:
        tools = service.get_tools_schema()
        tool_names = [t['function']['name'] for t in tools]
        
        print(f"📋 Registered tools ({len(tool_names)}):")
        for name in tool_names:
            print(f"   - {name}")
        
        if "generate_mermaid" in tool_names:
            print("✅ generate_mermaid tool is registered")
        else:
            print("❌ generate_mermaid tool NOT found!")
            return False
    except Exception as e:
        print(f"❌ Failed to check tools: {e}")
        return False
    
    # TEST 3: Execute generate_mermaid tool
    print("\n[TEST 3] Testing generate_mermaid tool execution...")
    try:
        # Sample query results (from Neo4j)
        sample_results = [
            {
                "source": "FastAPI",
                "source_type": "Class",
                "target": "Starlette",
                "target_type": "Class",
                "relationship_type": "INHERITS_FROM"
            },
            {
                "source": "FastAPI",
                "source_type": "Class",
                "target": "APIRouter",
                "target_type": "Class",
                "relationship_type": "CONTAINS"
            },
            {
                "source": "APIRouter",
                "source_type": "Class",
                "target": "Route",
                "target_type": "Class",
                "relationship_type": "CONTAINS"
            }
        ]
        
        result = await service.execute_tool(
            "generate_mermaid",
            {
                "query_results": sample_results,
                "entity_name": "FastAPI",
                "entity_type": "Class"
            }
        )
        
        if isinstance(result, ToolResult):
            if result.success:
                print("✅ Tool executed successfully")
                print(f"   - Nodes count: {result.data.get('nodes_count', 0)}")
                print(f"   - Edges count: {result.data.get('edges_count', 0)}")
                
                mermaid_code = result.data.get('mermaid_code', '')
                if mermaid_code:
                    print(f"\n📊 Generated Mermaid Code ({len(mermaid_code)} chars):")
                    print("─" * 80)
                    print(mermaid_code)
                    print("─" * 80)
                    print("✅ Mermaid code generated successfully")
                else:
                    print("❌ No mermaid_code in response")
                    return False
            else:
                print(f"❌ Tool execution failed: {result.error}")
                return False
        else:
            print(f"❌ Unexpected response type: {type(result)}")
            return False
            
    except Exception as e:
        print(f"❌ Tool execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # TEST 4: Test with empty results
    print("\n[TEST 4] Testing with empty results...")
    try:
        result = await service.execute_tool(
            "generate_mermaid",
            {
                "query_results": [],
                "entity_name": "TestEntity",
                "entity_type": "Class"
            }
        )
        
        if result.success:
            print("✅ Tool handled empty results gracefully")
            print(f"   - Generated code for {result.data.get('nodes_count', 0)} nodes")
        else:
            print(f"⚠️  Tool returned error (expected): {result.error}")
            
    except Exception as e:
        print(f"❌ Empty results test failed: {e}")
        return False
    
    # TEST 5: Verify tool schema
    print("\n[TEST 5] Verifying tool schema...")
    try:
        tools_schema = service.get_tools_schema()
        mermaid_tool = None
        
        for tool in tools_schema:
            if tool['function']['name'] == 'generate_mermaid':
                mermaid_tool = tool
                break
        
        if mermaid_tool:
            print("✅ Tool schema found")
            print(f"   - Name: {mermaid_tool['function']['name']}")
            print(f"   - Description: {mermaid_tool['function']['description']}")
            
            params = mermaid_tool['function']['parameters']
            print(f"   - Required params: {params.get('required', [])}")
            print("✅ Tool schema is valid")
        else:
            print("❌ Tool schema not found")
            return False
            
    except Exception as e:
        print(f"❌ Schema verification failed: {e}")
        return False
    
    # Cleanup
    await service.shutdown()
    
    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED!")
    print("="*80)
    return True


async def main():
    """Run all tests."""
    success = await test_mermaid_integration()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())