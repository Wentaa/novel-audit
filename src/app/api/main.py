from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import logging

from ..config.settings import settings
from .routes import audit, health


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting Novel Content Audit System...")

    # Initialize services here
    try:
        # TODO: Initialize ChromaDB connection
        # TODO: Initialize rule database
        logger.info("Services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise

    yield

    logger.info("Shutting down Novel Content Audit System...")


# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(audit.router, prefix="/api/v1", tags=["Audit"])

# Import and include rules management router
from .routes import rules_management
app.include_router(rules_management.router, prefix="/api/v1", tags=["Rules Management"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Novel Content Audit System API",
        "version": settings.api_version,
        "status": "running"
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )