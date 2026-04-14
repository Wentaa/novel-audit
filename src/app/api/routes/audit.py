from fastapi import APIRouter, HTTPException, File, UploadFile
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class AuditRequest(BaseModel):
    """Content audit request model"""
    content: str
    metadata: Optional[Dict[str, Any]] = None
    rule_version: Optional[str] = None


class AuditResult(BaseModel):
    """Content audit result model"""
    result: str  # "approved", "rejected", "uncertain"
    confidence: float
    reason: str
    violated_rules: List[str]
    processing_path: List[str]
    timestamp: datetime


class RuleExtractionRequest(BaseModel):
    """Rule extraction request model"""
    source_type: str  # "pdf", "docx", "text"
    validate: bool = True


@router.post("/audit/content", response_model=AuditResult)
async def audit_content(request: AuditRequest):
    """
    Audit novel chapter content
    Main entry point for content auditing workflow - Phase 3 Implementation
    """
    try:
        from ...workflows.content_audit_workflow import content_audit_workflow

        logger.info(f"Starting content audit for {len(request.content)} characters")

        # Run Phase 3 audit workflow (Agent3 + Agent4)
        workflow_result = await content_audit_workflow.run_audit_workflow(
            content_text=request.content,
            content_metadata=request.metadata or {}
        )

        # Check for workflow errors
        if workflow_result.get("workflow_status") == "error":
            error_details = "; ".join(workflow_result.get("errors", ["Unknown error"]))
            raise HTTPException(status_code=500, detail=f"Audit workflow failed: {error_details}")

        # Extract final result
        final_result = workflow_result.get("final_result", {})

        return AuditResult(
            result=final_result.get("result", "error"),
            confidence=final_result.get("confidence", 0.0),
            reason=final_result.get("reason", "No reason provided"),
            violated_rules=final_result.get("violated_rules", []),
            processing_path=final_result.get("processing_path", []),
            timestamp=datetime.now()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Content audit failed: {e}")
        raise HTTPException(status_code=500, detail="Audit processing failed")


@router.post("/rules/extract")
async def extract_rules(
    request: RuleExtractionRequest,
    file: UploadFile = File(...)
):
    """
    Extract rules from uploaded document
    Phase 2 implementation: Rule extraction workflow
    """
    try:
        # TODO: Implement rule extraction workflow
        # Agent1 + Agent2 orchestration

        return {
            "status": "pending",
            "message": "Rule extraction not yet implemented",
            "file_info": {
                "filename": file.filename,
                "content_type": file.content_type,
                "size": file.size
            }
        }

    except Exception as e:
        logger.error(f"Rule extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Rule extraction failed")


@router.get("/rules/current")
async def get_current_rules():
    """
    Get current rule set
    Returns the active rule configuration
    """
    try:
        # TODO: Load from rule database
        return {
            "version": "not_available",
            "rules": {},
            "last_updated": None
        }

    except Exception as e:
        logger.error(f"Failed to retrieve rules: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve rules")


@router.get("/audit/history")
async def get_audit_history(
    limit: int = 100,
    offset: int = 0,
    result_filter: Optional[str] = None,
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None
):
    """
    Get audit history with filtering options
    Returns paginated audit results for monitoring
    """
    try:
        from ...services.audit_tracking_service import audit_tracking_service

        history_data = audit_tracking_service.get_audit_history(
            limit=limit,
            offset=offset,
            result_filter=result_filter,
            min_confidence=min_confidence,
            max_confidence=max_confidence
        )

        if "error" in history_data:
            raise HTTPException(status_code=500, detail=history_data["error"])

        return {
            "items": history_data["records"],
            "total": history_data["pagination"]["total"],
            "limit": limit,
            "offset": offset,
            "has_more": history_data["pagination"]["has_more"],
            "filters_applied": history_data["filters_applied"]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve audit history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve history")


@router.get("/audit/statistics")
async def get_audit_statistics(
    days_back: int = 7,
    include_breakdown: bool = True
):
    """
    Get comprehensive audit statistics
    """
    try:
        from ...services.audit_tracking_service import audit_tracking_service

        stats = audit_tracking_service.get_audit_statistics(
            days_back=days_back,
            include_breakdown=include_breakdown
        )

        if "error" in stats:
            raise HTTPException(status_code=500, detail=stats["error"])

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")


@router.get("/audit/report")
async def generate_audit_report(days_back: int = 7):
    """
    Generate comprehensive audit system report
    """
    try:
        from ...services.audit_tracking_service import audit_tracking_service

        report = audit_tracking_service.generate_audit_report(days_back)

        if "error" in report:
            raise HTTPException(status_code=500, detail=report["error"])

        return report

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate audit report: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate report")