import asyncio
import logging
from typing import Dict, Any

from ..services.openai_service import openai_service
from ..config.settings import settings

logger = logging.getLogger(__name__)


async def test_openai_connection() -> Dict[str, Any]:
    """
    Test OpenAI API connection and basic functionality

    Returns:
        Dictionary with test results
    """
    result = {
        "service": "OpenAI",
        "status": "unknown",
        "details": {}
    }

    try:
        # Test basic connection
        is_connected = await openai_service.test_connection()

        if is_connected:
            result["status"] = "healthy"
            result["details"]["connection"] = "success"

            # Test token counting
            test_text = "This is a test message for token counting."
            token_count = openai_service.count_tokens(test_text)
            result["details"]["token_counting"] = f"success ({token_count} tokens)"

            # Test embedding generation
            embeddings = await openai_service.generate_embeddings([test_text])
            result["details"]["embeddings"] = f"success ({len(embeddings[0])} dimensions)"

        else:
            result["status"] = "unhealthy"
            result["details"]["connection"] = "failed"

    except Exception as e:
        result["status"] = "error"
        result["details"]["error"] = str(e)
        logger.error(f"OpenAI connection test failed: {e}")

    return result


async def test_all_connections() -> Dict[str, Any]:
    """
    Test all service connections

    Returns:
        Dictionary with all test results
    """
    logger.info("Starting connection tests...")

    results = {
        "timestamp": settings.data_path,
        "overall_status": "unknown",
        "services": {}
    }

    # Test OpenAI
    openai_result = await test_openai_connection()
    results["services"]["openai"] = openai_result

    # TODO: Add ChromaDB test
    # TODO: Add SQLite database test

    # Determine overall status
    service_statuses = [service["status"] for service in results["services"].values()]
    if all(status == "healthy" for status in service_statuses):
        results["overall_status"] = "healthy"
    elif any(status == "error" for status in service_statuses):
        results["overall_status"] = "error"
    else:
        results["overall_status"] = "partial"

    logger.info(f"Connection tests completed - Overall status: {results['overall_status']}")
    return results


if __name__ == "__main__":
    # Run tests directly
    asyncio.run(test_all_connections())