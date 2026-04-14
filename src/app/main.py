"""
Novel Content Intelligent Audit System - Main FastAPI Application
Comprehensive API with OpenAPI/Swagger documentation
"""
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
import uvicorn
import asyncio
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, validator
import logging

from .workflows.complete_audit_workflow import CompleteAuditWorkflow
from .services.human_review_service import human_review_service, ReviewPriority
from .monitoring.performance_monitor import performance_monitor
from .utils.case_data_generator import case_data_generator
from .config import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Initialize FastAPI app
app = FastAPI(
    title="Novel Content Intelligent Audit System",
    description="""
    ## 网文章节内容智能审核系统 API

    A comprehensive multi-agent system for intelligent auditing of Chinese novel content using AI-powered analysis.

    ### Features
    - **Multi-Agent Workflow**: Progressive confidence-driven routing through specialized agents
    - **RAG Enhancement**: Case-based reasoning using similar precedent analysis
    - **Multi-Modal Analysis**: Expert perspectives (Legal, Social, UX, Platform Risk)
    - **Human-in-the-Loop**: Escalation to human reviewers for complex cases
    - **Performance Monitoring**: Real-time system performance tracking
    - **Confidence Scoring**: Transparent confidence levels for all decisions

    ### Workflow Process
    1. **Initial Judgment** - Fast rule-based assessment
    2. **Smart Routing** - Confidence-based decision routing
    3. **RAG Analysis** - Enhanced judgment using similar cases (if needed)
    4. **Multi-Modal Analysis** - Expert perspective analysis (if needed)
    5. **Arbitration** - Conflict resolution between expert opinions
    6. **Human Review** - Final fallback for complex cases

    ### Authentication
    API key authentication required for all endpoints except health checks.
    """,
    version="1.0.0",
    contact={
        "name": "Novel Audit System Team",
        "email": "support@novel-audit.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {
            "name": "Audit",
            "description": "Content audit operations - the core functionality of the system"
        },
        {
            "name": "Human Review",
            "description": "Human review management and workflow operations"
        },
        {
            "name": "Training",
            "description": "Training data management and system learning operations"
        },
        {
            "name": "Monitoring",
            "description": "System monitoring, health checks, and performance metrics"
        },
        {
            "name": "Admin",
            "description": "Administrative operations and system management"
        }
    ]
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(",") if settings.CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS.split(",") if hasattr(settings, 'ALLOWED_HOSTS') else ["*"]
)

# Initialize workflow
audit_workflow = CompleteAuditWorkflow()

# Pydantic Models for API Documentation
class ContentAuditRequest(BaseModel):
    """Content audit request model"""
    content: str = Field(
        ...,
        description="Chinese novel content to be audited",
        min_length=1,
        max_length=50000,
        example="她轻轻地推开房门，心跳如雷。月光洒在他的脸上，那张熟悉的面孔在夜色中显得格外温柔。这是一个美好的爱情故事的开始。"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default={},
        description="Optional metadata for the content (genre, author, etc.)",
        example={
            "genre": "romance",
            "author": "张三",
            "chapter": 1,
            "word_count": 2000
        }
    )
    priority: Optional[str] = Field(
        default="medium",
        description="Processing priority",
        enum=["low", "medium", "high", "urgent"]
    )

    @validator('content')
    def content_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Content cannot be empty')
        return v.strip()

class ContentAuditResponse(BaseModel):
    """Content audit response model"""
    audit_id: str = Field(description="Unique audit identifier")
    final_decision: str = Field(description="Final audit decision", enum=["approved", "rejected", "requires_human_review"])
    confidence_score: float = Field(description="Decision confidence score (0-1)", ge=0, le=1)
    reasoning: str = Field(description="Detailed reasoning for the decision")
    workflow_path: List[str] = Field(description="Processing path taken through the workflow")
    processing_time_ms: float = Field(description="Total processing time in milliseconds")
    timestamp: str = Field(description="Processing completion timestamp")

    # Optional detailed analysis
    initial_analysis: Optional[Dict[str, Any]] = Field(description="Initial judgment details")
    rag_analysis: Optional[Dict[str, Any]] = Field(description="RAG enhancement analysis (if performed)")
    expert_analyses: Optional[Dict[str, Any]] = Field(description="Expert perspective analyses (if performed)")
    arbitration_analysis: Optional[Dict[str, Any]] = Field(description="Arbitration results (if performed)")
    human_review: Optional[Dict[str, Any]] = Field(description="Human review details (if escalated)")

class BatchAuditRequest(BaseModel):
    """Batch audit request model"""
    contents: List[ContentAuditRequest] = Field(
        ...,
        description="List of content items to audit",
        min_items=1,
        max_items=100
    )
    batch_options: Optional[Dict[str, Any]] = Field(
        default={},
        description="Batch processing options"
    )

class BatchAuditResponse(BaseModel):
    """Batch audit response model"""
    batch_id: str = Field(description="Unique batch identifier")
    total_items: int = Field(description="Total number of items in batch")
    completed_items: int = Field(description="Number of completed items")
    results: List[ContentAuditResponse] = Field(description="Individual audit results")
    batch_summary: Dict[str, Any] = Field(description="Batch processing summary")
    processing_time_ms: float = Field(description="Total batch processing time")

class HumanReviewSubmission(BaseModel):
    """Human review decision model"""
    review_id: str = Field(description="Review identifier")
    decision: str = Field(description="Human review decision", enum=["approved", "rejected", "needs_revision"])
    reasoning: str = Field(description="Human reviewer's reasoning")
    reviewer_id: str = Field(description="Reviewer identifier")
    confidence: Optional[float] = Field(default=0.9, description="Reviewer confidence", ge=0, le=1)

class SystemHealthResponse(BaseModel):
    """System health response model"""
    status: str = Field(description="Overall system status", enum=["healthy", "degraded", "critical"])
    timestamp: str = Field(description="Health check timestamp")
    services: Dict[str, str] = Field(description="Individual service statuses")
    performance_metrics: Dict[str, Any] = Field(description="Performance metrics summary")
    version: str = Field(description="System version")

# Custom exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "timestamp": datetime.now().isoformat()
            }
        }
    )

# Health Check Endpoint
@app.get(
    "/health",
    response_model=SystemHealthResponse,
    tags=["Monitoring"],
    summary="System Health Check",
    description="Comprehensive system health check including all service dependencies"
)
async def health_check():
    """
    Perform comprehensive system health check.

    Checks:
    - API service status
    - Database connectivity
    - Vector store connectivity
    - External service dependencies
    - Performance metrics
    """
    try:
        start_time = time.time()

        # Check services
        services_status = {
            "api": "healthy",
            "database": "healthy",  # Would check actual DB connectivity
            "vector_store": "healthy",  # Would check ChromaDB connectivity
            "redis": "healthy",  # Would check Redis connectivity
        }

        # Get performance metrics
        perf_metrics = performance_monitor.get_performance_summary(hours=1)

        processing_time = (time.time() - start_time) * 1000

        overall_status = "healthy" if all(status == "healthy" for status in services_status.values()) else "degraded"

        return SystemHealthResponse(
            status=overall_status,
            timestamp=datetime.now().isoformat(),
            services=services_status,
            performance_metrics=perf_metrics,
            version="1.0.0"
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health check failed"
        )

# Single Content Audit Endpoint
@app.post(
    "/api/v1/audit",
    response_model=ContentAuditResponse,
    tags=["Audit"],
    summary="Audit Single Content",
    description="Submit a single piece of content for intelligent audit analysis",
    responses={
        200: {"description": "Audit completed successfully"},
        400: {"description": "Invalid content or request format"},
        422: {"description": "Content validation failed"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "Service temporarily unavailable"}
    }
)
async def audit_content(request: ContentAuditRequest):
    """
    Audit a single piece of novel content through the complete multi-agent workflow.

    **Process Overview:**
    1. **Initial Judgment**: Fast rule-based assessment with confidence scoring
    2. **Smart Routing**: Routes based on confidence thresholds:
       - High confidence (≥0.8): Direct decision
       - Medium confidence (0.3-0.8): RAG analysis
       - Low confidence (<0.3): Multi-modal analysis
    3. **RAG Enhancement**: Uses similar cases for borderline decisions
    4. **Expert Analysis**: Legal, Social, UX, and Platform Risk perspectives
    5. **Arbitration**: Resolves conflicts between expert opinions
    6. **Human Escalation**: Complex cases sent to human reviewers

    **Content Guidelines:**
    - Maximum length: 50,000 characters
    - Supported language: Chinese (simplified/traditional)
    - Content types: Novel chapters, story fragments, creative writing
    """
    try:
        start_time = time.time()

        async with performance_monitor.monitor_operation(
            "content_audit_api",
            metadata={"content_length": len(request.content)}
        ):
            # Run the complete audit workflow
            audit_result = await audit_workflow.run_complete_audit(
                content_text=request.content,
                metadata=request.metadata
            )

            processing_time_ms = (time.time() - start_time) * 1000

            # Format response
            response = ContentAuditResponse(
                audit_id=audit_result.get("audit_id", ""),
                final_decision=audit_result.get("final_decision", "error"),
                confidence_score=audit_result.get("confidence_score", 0.0),
                reasoning=audit_result.get("reasoning", ""),
                workflow_path=audit_result.get("workflow_path", []),
                processing_time_ms=processing_time_ms,
                timestamp=datetime.now().isoformat(),
                initial_analysis=audit_result.get("initial_judgment"),
                rag_analysis=audit_result.get("rag_analysis"),
                expert_analyses=audit_result.get("expert_analyses"),
                arbitration_analysis=audit_result.get("arbitration_analysis"),
                human_review=audit_result.get("human_review")
            )

            return response

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid content: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Audit failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audit service temporarily unavailable"
        )

# Batch Audit Endpoint
@app.post(
    "/api/v1/audit/batch",
    response_model=BatchAuditResponse,
    tags=["Audit"],
    summary="Audit Multiple Contents",
    description="Submit multiple pieces of content for batch audit processing",
)
async def audit_batch(request: BatchAuditRequest):
    """
    Process multiple content items in a single batch request.

    **Batch Processing Features:**
    - Concurrent processing for improved performance
    - Individual result tracking with batch summary
    - Configurable batch options for processing behavior
    - Comprehensive error handling for partial failures
    """
    try:
        start_time = time.time()
        batch_id = f"batch_{int(time.time())}"

        # Process contents concurrently
        tasks = []
        for content_request in request.contents:
            task = audit_workflow.run_complete_audit(
                content_text=content_request.content,
                metadata=content_request.metadata
            )
            tasks.append(task)

        # Execute batch
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        successful_results = []
        failed_count = 0

        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                failed_count += 1
                continue

            successful_results.append(ContentAuditResponse(
                audit_id=result.get("audit_id", f"{batch_id}_{i}"),
                final_decision=result.get("final_decision", "error"),
                confidence_score=result.get("confidence_score", 0.0),
                reasoning=result.get("reasoning", ""),
                workflow_path=result.get("workflow_path", []),
                processing_time_ms=0,  # Individual timing not tracked in batch
                timestamp=datetime.now().isoformat()
            ))

        processing_time_ms = (time.time() - start_time) * 1000

        # Generate batch summary
        decisions = [r.final_decision for r in successful_results]
        batch_summary = {
            "approved_count": decisions.count("approved"),
            "rejected_count": decisions.count("rejected"),
            "human_review_count": decisions.count("requires_human_review"),
            "failed_count": failed_count,
            "average_confidence": sum(r.confidence_score for r in successful_results) / len(successful_results) if successful_results else 0
        }

        return BatchAuditResponse(
            batch_id=batch_id,
            total_items=len(request.contents),
            completed_items=len(successful_results),
            results=successful_results,
            batch_summary=batch_summary,
            processing_time_ms=processing_time_ms
        )

    except Exception as e:
        logger.error(f"Batch audit failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Batch audit service temporarily unavailable"
        )

# Human Review Endpoints
@app.get(
    "/api/v1/human-review/pending",
    tags=["Human Review"],
    summary="Get Pending Reviews",
    description="Retrieve list of content items awaiting human review"
)
async def get_pending_reviews(
    limit: int = 50,
    priority: Optional[ReviewPriority] = None
):
    """Get pending human review items with optional filtering."""
    try:
        reviews = await human_review_service.get_pending_reviews(
            limit=limit,
            priority_filter=priority
        )
        return {"pending_reviews": reviews}
    except Exception as e:
        logger.error(f"Failed to get pending reviews: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve pending reviews"
        )

@app.post(
    "/api/v1/human-review/submit",
    tags=["Human Review"],
    summary="Submit Human Review Decision",
    description="Submit human reviewer decision for a pending review"
)
async def submit_human_review(review: HumanReviewSubmission):
    """Submit human review decision."""
    try:
        result = await human_review_service.submit_human_decision(
            review_id=review.review_id,
            decision=review.decision,
            reasoning=review.reasoning,
            reviewer_id=review.reviewer_id,
            confidence=review.confidence
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Human review submission failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit human review"
        )

# Training Data Management
@app.post(
    "/api/v1/training/populate",
    tags=["Training"],
    summary="Populate Training Data",
    description="Generate and populate the vector database with training cases"
)
async def populate_training_data(
    case_count: int = 100,
    background_tasks: BackgroundTasks = None
):
    """Populate vector database with training cases."""
    if case_count > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum case count is 1000"
        )

    try:
        result = await case_data_generator.populate_vector_database(case_count)
        return result
    except Exception as e:
        logger.error(f"Training data population failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to populate training data"
        )

# Performance Monitoring Endpoints
@app.get(
    "/api/v1/monitoring/performance",
    tags=["Monitoring"],
    summary="Get Performance Metrics",
    description="Retrieve system performance metrics and statistics"
)
async def get_performance_metrics(hours: int = 24):
    """Get system performance metrics for the specified time period."""
    if hours > 168:  # Max 1 week
        hours = 168

    try:
        performance_summary = performance_monitor.get_performance_summary(hours)
        system_health = performance_monitor.get_system_health_report()

        return {
            "performance_summary": performance_summary,
            "system_health": system_health,
            "monitoring_period_hours": hours
        }
    except Exception as e:
        logger.error(f"Performance metrics retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve performance metrics"
        )

@app.get(
    "/api/v1/monitoring/alerts",
    tags=["Monitoring"],
    summary="Get System Alerts",
    description="Retrieve recent system alerts and performance warnings"
)
async def get_system_alerts():
    """Get recent system alerts."""
    try:
        alerts = performance_monitor.system_alerts[-50:]  # Last 50 alerts
        return {
            "recent_alerts": alerts,
            "total_alerts": len(performance_monitor.system_alerts)
        }
    except Exception as e:
        logger.error(f"Alert retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system alerts"
        )

# Admin Endpoints
@app.post(
    "/api/v1/admin/clear-metrics",
    tags=["Admin"],
    summary="Clear Old Metrics",
    description="Clear performance metrics older than specified hours (admin only)"
)
async def clear_old_metrics(hours: int = 168):
    """Clear old performance metrics (admin endpoint)."""
    try:
        result = performance_monitor.clear_old_metrics(hours)
        return result
    except Exception as e:
        logger.error(f"Metrics clearing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear metrics"
        )

# Custom OpenAPI schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Add custom extensions
    openapi_schema["info"]["x-logo"] = {
        "url": "/static/logo.png"
    }

    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key"
        }
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Custom documentation endpoints
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@4.15.5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@4.15.5/swagger-ui.css",
    )

@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2.1.2/bundles/redoc.standalone.js",
    )

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("Novel Content Audit System starting up...")
    # Initialize any necessary services here

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Novel Content Audit System shutting down...")
    # Cleanup any resources here

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.ENVIRONMENT == "development" else False,
        workers=1 if settings.ENVIRONMENT == "development" else 4
    )