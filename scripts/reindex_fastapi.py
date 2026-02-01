import asyncio

from src.agents.indexer_agent import IndexRepositoryTool
from src.shared.neo4j_service import init_neo4j_service


async def main():
    # 1️⃣ Init Neo4j
    await init_neo4j_service()

    # 2️⃣ Create tool directly
    tool = IndexRepositoryTool()

    # 3️⃣ Clear DB
    neo4j = tool  # just to show intent
    from src.shared.neo4j_service import get_neo4j_service
    await get_neo4j_service().clear_database()
    print("✅ Database cleared")

    # 4️⃣ Reindex FastAPI
    result = await tool.execute(
        repo_url="https://github.com/tiangolo/fastapi",
        full_index=True,
    )

    print("✅ Reindex finished")
    print(result.data)


if __name__ == "__main__":
    asyncio.run(main())
