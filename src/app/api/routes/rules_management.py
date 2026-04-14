from fastapi import APIRouter, HTTPException, File, UploadFile, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from ..routes.audit import AuditResult  # Import from existing audit routes
from ...workflows.rule_extraction_workflow import rule_extraction_workflow
from ...utils.document_processor import document_processor
from ...storage.database import db_service, get_db, RuleVersion
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter()


class RuleExtractionStatus(BaseModel):
    """Rule extraction status model"""
    workflow_id: str
    status: str  # "running", "completed", "awaiting_human_review", "error"
    current_step: str
    progress_percentage: int
    human_review_required: bool
    message: str


class HumanReviewRequest(BaseModel):
    """Human review decision model"""
    rule_version_id: int
    decision: str  # "approve", "reject", "request_modifications"
    reviewer_name: str
    comments: Optional[str] = None
    modifications: Optional[Dict[str, Any]] = None


class RuleVersionResponse(BaseModel):
    """Rule version response model"""
    id: int
    version: str
    is_active: bool
    source_document: str
    created_at: datetime
    rules_content: Dict[str, Any]
    validation_summary: Optional[Dict[str, Any]] = None


@router.post("/rules/extract", response_model=RuleExtractionStatus)
async def extract_rules_from_document(
    file: UploadFile = File(...),
    validate: bool = True
):
    """
    Extract rules from uploaded policy document
    Phase 2 main endpoint: Document → Agent1 → Agent2 → Human Review
    """
    try:
        # Validate document
        is_valid, error_message = document_processor.validate_document(
            file.filename, file.size
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_message)

        logger.info(f"Starting rule extraction for: {file.filename}")

        # Process document
        file_content = await file.read()
        processed_doc = await document_processor.process_document(
            file_content, file.filename
        )

        if processed_doc["metadata"]["processing_status"] != "success":
            raise HTTPException(
                status_code=400,
                detail=f"Document processing failed: {processed_doc['metadata'].get('error', 'Unknown error')}"
            )

        # Run rule extraction workflow
        workflow_result = await rule_extraction_workflow.run_workflow(
            document_content=processed_doc["content"],
            document_type=processed_doc["metadata"]["detected_type"],
            source_filename=file.filename
        )

        # Prepare response based on workflow status
        if workflow_result["workflow_status"] == "error":
            raise HTTPException(
                status_code=500,
                detail=f"Rule extraction failed: {'; '.join(workflow_result['errors'])}"
            )

        # Calculate progress
        progress_map = {
            "running": 20,
            "extracting_rules": 40,
            "validating_rules": 70,
            "finalizing": 90,
            "completed": 100,
            "awaiting_human_review": 80
        }
        progress = progress_map.get(workflow_result["workflow_status"], 0)

        return RuleExtractionStatus(
            workflow_id=workflow_result["workflow_metadata"]["workflow_id"],
            status=workflow_result["workflow_status"],
            current_step=workflow_result["current_step"],
            progress_percentage=progress,
            human_review_required=workflow_result["human_review_required"],
            message=self._get_status_message(workflow_result)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rule extraction endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/rules/pending-review")
async def get_pending_reviews(db: Session = Depends(get_db)):
    """
    Get rule versions pending human review
    """
    try:
        pending_versions = db.query(RuleVersion).filter(
            RuleVersion.is_active == False,
            RuleVersion.activated_at.is_(None)
        ).order_by(RuleVersion.created_at.desc()).all()

        return [
            {
                "id": version.id,
                "version": version.version,
                "source_document": version.source_document,
                "created_at": version.created_at,
                "extracted_by": version.extracted_by,
                "rules_preview": self._create_rules_preview(version.rules_content)
            }
            for version in pending_versions
        ]

    except Exception as e:
        logger.error(f"Failed to get pending reviews: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve pending reviews")


@router.get("/rules/{rule_version_id}", response_model=RuleVersionResponse)
async def get_rule_version_details(
    rule_version_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific rule version
    For human review interface
    """
    try:
        version = db.query(RuleVersion).filter(RuleVersion.id == rule_version_id).first()
        if not version:
            raise HTTPException(status_code=404, detail="Rule version not found")

        # Create validation summary for human review
        validation_summary = self._create_validation_summary(version.rules_content)

        return RuleVersionResponse(
            id=version.id,
            version=version.version,
            is_active=version.is_active,
            source_document=version.source_document,
            created_at=version.created_at,
            rules_content=version.rules_content,
            validation_summary=validation_summary
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get rule version details: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve rule version")


@router.post("/rules/{rule_version_id}/review")
async def submit_human_review(
    rule_version_id: int,
    review_request: HumanReviewRequest,
    db: Session = Depends(get_db)
):
    """
    Submit human review decision for rule version
    Final step in Phase 2 workflow
    """
    try:
        # Get rule version
        version = db.query(RuleVersion).filter(RuleVersion.id == rule_version_id).first()
        if not version:
            raise HTTPException(status_code=404, detail="Rule version not found")

        if version.is_active:
            raise HTTPException(status_code=400, detail="Rule version is already active")

        logger.info(f"Processing human review for rule version {rule_version_id}: {review_request.decision}")

        # Process review decision
        if review_request.decision == "approve":
            # Deactivate current active version
            current_active = db.query(RuleVersion).filter(RuleVersion.is_active == True).first()
            if current_active:
                current_active.is_active = False

            # Activate this version
            version.is_active = True
            version.activated_at = datetime.utcnow()
            version.validated_by = review_request.reviewer_name

            # Apply modifications if provided
            if review_request.modifications:
                version.rules_content.update(review_request.modifications)

            db.commit()

            # Log approval
            db_service.log_system_event(
                level="INFO",
                component="HumanReview",
                event="rule_version_approved",
                details={
                    "rule_version_id": rule_version_id,
                    "reviewer": review_request.reviewer_name,
                    "comments": review_request.comments
                }
            )

            return {
                "status": "approved",
                "message": "Rule version has been approved and activated",
                "active_version": version.version
            }

        elif review_request.decision == "reject":
            # Mark as rejected (keep inactive)
            version.validated_by = review_request.reviewer_name
            db.commit()

            # Log rejection
            db_service.log_system_event(
                level="WARNING",
                component="HumanReview",
                event="rule_version_rejected",
                details={
                    "rule_version_id": rule_version_id,
                    "reviewer": review_request.reviewer_name,
                    "comments": review_request.comments
                }
            )

            return {
                "status": "rejected",
                "message": "Rule version has been rejected",
                "reason": review_request.comments
            }

        elif review_request.decision == "request_modifications":
            # Keep pending with modification request
            version.validated_by = f"modifications_requested_by_{review_request.reviewer_name}"
            db.commit()

            return {
                "status": "modifications_requested",
                "message": "Modifications have been requested",
                "requested_changes": review_request.modifications
            }

        else:
            raise HTTPException(status_code=400, detail="Invalid review decision")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Human review submission failed: {e}")
        raise HTTPException(status_code=500, detail="Review submission failed")


@router.get("/rules/current")
async def get_current_active_rules():
    """
    Get currently active rule set
    Updated from the placeholder in audit.py
    """
    try:
        active_version = db_service.get_active_rule_version()

        if not active_version:
            return {
                "version": "none",
                "rules": {},
                "last_updated": None,
                "message": "No active rule version found"
            }

        return {
            "version": active_version.version,
            "rules": active_version.rules_content,
            "last_updated": active_version.activated_at.isoformat() if active_version.activated_at else None,
            "source_document": active_version.source_document,
            "extracted_by": active_version.extracted_by,
            "validated_by": active_version.validated_by
        }

    except Exception as e:
        logger.error(f"Failed to retrieve current rules: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve current rules")


def _get_status_message(workflow_result: Dict[str, Any]) -> str:
    """Generate human-readable status message"""
    status = workflow_result["workflow_status"]

    messages = {
        "completed": "Rules extracted and validated successfully. Ready for use.",
        "awaiting_human_review": "Rules extracted but require human review due to validation concerns.",
        "error": f"Extraction failed: {'; '.join(workflow_result.get('errors', ['Unknown error']))}"
    }

    return messages.get(status, f"Processing in progress: {status}")


def _create_rules_preview(rules_content: Dict[str, Any]) -> Dict[str, Any]:
    """Create a preview summary of rules for listing"""
    try:
        return {
            "prohibited_categories": len(rules_content.get("prohibited_content", [])),
            "keyword_categories": len(rules_content.get("sensitive_keywords", {})),
            "severity_levels": len(rules_content.get("severity_levels", {})),
            "content_guidelines": len(rules_content.get("content_guidelines", {})),
            "total_keywords": sum(
                len(v) if isinstance(v, list) else 1
                for v in rules_content.get("sensitive_keywords", {}).values()
            )
        }
    except:
        return {"error": "Unable to generate preview"}


def _create_validation_summary(rules_content: Dict[str, Any]) -> Dict[str, Any]:
    """Create validation summary for human review"""
    try:
        # Extract validation metadata if available
        extraction_meta = rules_content.get("extraction_metadata", {})

        return {
            "extraction_info": {
                "extracted_at": extraction_meta.get("extracted_at"),
                "validation_passed": extraction_meta.get("validation_passed", True),
                "validation_error": extraction_meta.get("validation_error")
            },
            "content_analysis": {
                "total_prohibited_categories": len(rules_content.get("prohibited_content", [])),
                "total_keyword_groups": len(rules_content.get("sensitive_keywords", {})),
                "severity_levels_defined": len(rules_content.get("severity_levels", {})),
                "enforcement_actions_defined": len(rules_content.get("enforcement_actions", {}))
            },
            "completeness_check": {
                "has_prohibited_content": bool(rules_content.get("prohibited_content")),
                "has_keywords": bool(rules_content.get("sensitive_keywords")),
                "has_severity_levels": bool(rules_content.get("severity_levels")),
                "has_enforcement_actions": bool(rules_content.get("enforcement_actions"))
            }
        }
    except Exception as e:
        return {"error": f"Unable to create validation summary: {str(e)}"}