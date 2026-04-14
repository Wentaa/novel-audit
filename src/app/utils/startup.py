import asyncio
import logging
from typing import Dict, Any

from ..storage.database import create_tables, db_service
from ..storage.vector_store import vector_store
from ..utils.test_connections import test_all_connections
from ..config.settings import settings

logger = logging.getLogger(__name__)


async def initialize_system() -> Dict[str, Any]:
    """
    Initialize the entire system

    Returns:
        Dictionary with initialization results
    """
    logger.info("Starting system initialization...")

    results = {
        "database": {"status": "unknown"},
        "vector_store": {"status": "unknown"},
        "connections": {"status": "unknown"},
        "overall": {"status": "unknown"}
    }

    try:
        # 1. Initialize database
        logger.info("Initializing SQLite database...")
        create_tables()
        db_connected = db_service.test_connection()

        if db_connected:
            results["database"]["status"] = "success"
            logger.info("Database initialization successful")
        else:
            results["database"]["status"] = "failed"
            logger.error("Database connection test failed")

        # 2. Initialize vector store
        logger.info("Initializing ChromaDB vector store...")
        try:
            await vector_store.initialize()
            vector_connected = await vector_store.test_connection()

            if vector_connected:
                results["vector_store"]["status"] = "success"
                stats = await vector_store.get_collection_stats()
                results["vector_store"]["details"] = stats
                logger.info("Vector store initialization successful")
            else:
                results["vector_store"]["status"] = "failed"
                logger.error("Vector store connection test failed")

        except Exception as e:
            results["vector_store"]["status"] = "error"
            results["vector_store"]["error"] = str(e)
            logger.error(f"Vector store initialization error: {e}")

        # 3. Test all connections
        logger.info("Testing all service connections...")
        connection_results = await test_all_connections()
        results["connections"] = connection_results

        # 4. Determine overall status
        if (results["database"]["status"] == "success" and
            results["vector_store"]["status"] == "success" and
            connection_results["overall_status"] == "healthy"):
            results["overall"]["status"] = "success"
        else:
            results["overall"]["status"] = "partial"

        logger.info(f"System initialization completed - Status: {results['overall']['status']}")
        return results

    except Exception as e:
        logger.error(f"System initialization failed: {e}")
        results["overall"]["status"] = "error"
        results["overall"]["error"] = str(e)
        return results


async def health_check() -> Dict[str, Any]:
    """
    Perform system health check

    Returns:
        Dictionary with health check results
    """
    logger.info("Performing system health check...")

    health_results = {
        "timestamp": settings.data_path,
        "status": "unknown",
        "services": {}
    }

    try:
        # Check database
        db_healthy = db_service.test_connection()
        health_results["services"]["database"] = {
            "status": "healthy" if db_healthy else "unhealthy"
        }

        # Check vector store
        try:
            vector_healthy = await vector_store.test_connection()
            stats = await vector_store.get_collection_stats()
            health_results["services"]["vector_store"] = {
                "status": "healthy" if vector_healthy else "unhealthy",
                "details": stats
            }
        except Exception as e:
            health_results["services"]["vector_store"] = {
                "status": "error",
                "error": str(e)
            }

        # Check external connections
        connection_results = await test_all_connections()
        health_results["services"].update(connection_results["services"])

        # Determine overall health
        service_statuses = [
            service.get("status", "unknown")
            for service in health_results["services"].values()
        ]

        if all(status == "healthy" for status in service_statuses):
            health_results["status"] = "healthy"
        elif any(status == "error" for status in service_statuses):
            health_results["status"] = "error"
        else:
            health_results["status"] = "degraded"

        logger.info(f"Health check completed - Status: {health_results['status']}")
        return health_results

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        health_results["status"] = "error"
        health_results["error"] = str(e)
        return health_results


def create_sample_data():
    """
    Create sample data for testing
    """
    logger.info("Creating sample data...")

    try:
        # Create sample rule version
        sample_rules = {
            "version": "1.0.0",
            "prohibited_content": [
                "violence",
                "adult_content",
                "political_sensitive",
                "illegal_activities"
            ],
            "sensitive_keywords": [
                "血腥", "色情", "政治", "暴力"
            ],
            "severity_levels": {
                "minor": "轻微违规，需要修改",
                "major": "严重违规，需要拒绝",
                "critical": "极严重违规，需要立即处理"
            }
        }

        db_service.create_rule_version(
            version="1.0.0",
            rules_content=sample_rules,
            source_document="sample_rules.json",
            extracted_by="system_init",
            validated_by="system_init"
        )

        logger.info("Sample data created successfully")

    except Exception as e:
        logger.error(f"Failed to create sample data: {e}")


if __name__ == "__main__":
    # Run initialization directly
    async def main():
        results = await initialize_system()
        print("Initialization results:", results)

        # Create sample data
        create_sample_data()

        # Run health check
        health = await health_check()
        print("Health check results:", health)

    asyncio.run(main())