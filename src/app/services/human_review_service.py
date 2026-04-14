from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum
import json
import logging

from ..storage.database import db_service, SessionLocal, AuditRecord, SystemLog
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

logger = logging.getLogger(__name__)


class ReviewPriority(Enum):
    """Priority levels for human review"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewStatus(Enum):
    """Status of human review items"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ESCALATED = "escalated"


class HumanReviewService:
    """Service for managing human-in-the-loop content review process"""

    def __init__(self):
        self.session_factory = SessionLocal
        self.priority_weights = {
            ReviewPriority.CRITICAL: 1.0,
            ReviewPriority.HIGH: 0.8,
            ReviewPriority.MEDIUM: 0.5,
            ReviewPriority.LOW: 0.2
        }

    async def submit_for_human_review(
        self,
        content_text: str,
        audit_results: Dict[str, Any],
        escalation_reason: str,
        priority: ReviewPriority = ReviewPriority.MEDIUM,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submit content for human review

        Args:
            content_text: The content that needs human review
            audit_results: Complete audit analysis results
            escalation_reason: Why this needs human review
            priority: Review priority level
            metadata: Additional metadata

        Returns:
            Review submission details
        """
        try:
            logger.info(f"Submitting content for human review with priority: {priority.value}")

            # Create review record
            review_record = {
                "content_hash": self._generate_content_hash(content_text),
                "content_preview": content_text[:500] + "..." if len(content_text) > 500 else content_text,
                "full_content": content_text,
                "audit_results": audit_results,
                "escalation_reason": escalation_reason,
                "priority": priority.value,
                "status": ReviewStatus.PENDING.value,
                "submitted_at": datetime.now(),
                "metadata": metadata or {},
                "review_context": self._prepare_review_context(audit_results)
            }

            # Store in database with special human review flag
            audit_record = db_service.create_audit_record(
                content_hash=review_record["content_hash"],
                content_preview=review_record["content_preview"],
                result="pending_human_review",
                confidence=0.0,  # No automated confidence for human review
                reason=escalation_reason,
                violated_rules=self._extract_violated_rules(audit_results),
                processing_path=self._extract_processing_path(audit_results),
                metadata={
                    **review_record["metadata"],
                    "human_review": True,
                    "review_priority": priority.value,
                    "review_context": review_record["review_context"],
                    "full_audit_results": audit_results
                }
            )

            # Log the submission
            db_service.log_system_event(
                level="INFO",
                component="HumanReviewService",
                event="human_review_submitted",
                details={
                    "audit_record_id": audit_record.id,
                    "priority": priority.value,
                    "escalation_reason": escalation_reason,
                    "content_length": len(content_text)
                }
            )

            # Calculate estimated review time
            estimated_time = self._estimate_review_time(priority, audit_results)

            submission_result = {
                "review_id": audit_record.id,
                "status": "submitted",
                "priority": priority.value,
                "estimated_review_time": estimated_time,
                "submission_timestamp": datetime.now().isoformat(),
                "queue_position": await self._get_queue_position(priority),
                "review_context": review_record["review_context"]
            }

            logger.info(f"Human review submitted successfully: ID {audit_record.id}")
            return submission_result

        except Exception as e:
            logger.error(f"Failed to submit for human review: {e}")
            raise

    async def get_pending_reviews(
        self,
        priority_filter: Optional[ReviewPriority] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get pending human review items

        Args:
            priority_filter: Filter by priority level
            limit: Maximum items to return
            offset: Pagination offset

        Returns:
            List of pending review items
        """
        try:
            with self.session_factory() as db:
                query = db.query(AuditRecord).filter(
                    AuditRecord.result == "pending_human_review"
                )

                if priority_filter:
                    query = query.filter(
                        AuditRecord.metadata["review_priority"].astext == priority_filter.value
                    )

                # Order by priority and submission time
                total_count = query.count()

                records = query.order_by(
                    # Priority ordering (critical first)
                    desc(AuditRecord.metadata["review_priority"]),
                    AuditRecord.created_at
                ).offset(offset).limit(limit).all()

                # Format review items
                review_items = []
                for record in records:
                    metadata = record.metadata or {}
                    review_item = {
                        "review_id": record.id,
                        "content_preview": record.content_preview,
                        "escalation_reason": record.reason,
                        "priority": metadata.get("review_priority", "medium"),
                        "submitted_at": record.created_at.isoformat(),
                        "processing_path": record.processing_path,
                        "violated_rules": record.violated_rules,
                        "review_context": metadata.get("review_context", {}),
                        "estimated_complexity": self._assess_review_complexity(metadata)
                    }
                    review_items.append(review_item)

                return {
                    "pending_reviews": review_items,
                    "total_count": total_count,
                    "pagination": {
                        "limit": limit,
                        "offset": offset,
                        "has_more": offset + limit < total_count
                    },
                    "queue_statistics": await self._get_queue_statistics()
                }

        except Exception as e:
            logger.error(f"Failed to get pending reviews: {e}")
            return {"error": str(e), "pending_reviews": []}

    async def submit_human_decision(
        self,
        review_id: int,
        decision: str,
        reviewer_name: str,
        decision_reasoning: str,
        confidence_level: float = 1.0,
        additional_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submit human reviewer's decision

        Args:
            review_id: Review item ID
            decision: approved/rejected/needs_modification
            reviewer_name: Name of the human reviewer
            decision_reasoning: Explanation for the decision
            confidence_level: Reviewer's confidence in the decision
            additional_notes: Optional additional notes

        Returns:
            Decision submission result
        """
        try:
            with self.session_factory() as db:
                # Get the review record
                record = db.query(AuditRecord).filter(AuditRecord.id == review_id).first()
                if not record:
                    raise ValueError(f"Review record {review_id} not found")

                if record.result != "pending_human_review":
                    raise ValueError(f"Review record {review_id} is not pending human review")

                # Update the record with human decision
                record.result = decision
                record.confidence = confidence_level
                record.reason = f"Human Review Decision: {decision_reasoning}"
                record.updated_at = datetime.now()

                # Update metadata with human review details
                metadata = record.metadata or {}
                metadata.update({
                    "human_review_completed": True,
                    "reviewer_name": reviewer_name,
                    "review_completed_at": datetime.now().isoformat(),
                    "human_decision_reasoning": decision_reasoning,
                    "reviewer_confidence": confidence_level,
                    "additional_notes": additional_notes,
                    "review_status": "completed"
                })
                record.metadata = metadata

                db.commit()

                # Log the decision
                db_service.log_system_event(
                    level="INFO",
                    component="HumanReviewService",
                    event="human_decision_submitted",
                    details={
                        "review_id": review_id,
                        "decision": decision,
                        "reviewer": reviewer_name,
                        "confidence": confidence_level
                    }
                )

                # Update system learning (for future improvements)
                await self._update_system_learning(record, decision, confidence_level)

                decision_result = {
                    "review_id": review_id,
                    "status": "decision_recorded",
                    "final_decision": decision,
                    "reviewer": reviewer_name,
                    "confidence": confidence_level,
                    "decision_timestamp": datetime.now().isoformat(),
                    "processing_complete": True
                }

                logger.info(f"Human decision recorded for review {review_id}: {decision}")
                return decision_result

        except Exception as e:
            logger.error(f"Failed to submit human decision: {e}")
            raise

    async def get_review_details(self, review_id: int) -> Dict[str, Any]:
        """
        Get detailed information about a specific review item

        Args:
            review_id: Review item ID

        Returns:
            Detailed review information
        """
        try:
            with self.session_factory() as db:
                record = db.query(AuditRecord).filter(AuditRecord.id == review_id).first()
                if not record:
                    return {"error": f"Review {review_id} not found"}

                metadata = record.metadata or {}
                full_audit_results = metadata.get("full_audit_results", {})

                review_details = {
                    "review_id": record.id,
                    "content_hash": record.content_hash,
                    "content_preview": record.content_preview,
                    "escalation_reason": record.reason,
                    "priority": metadata.get("review_priority", "medium"),
                    "status": record.result,
                    "submitted_at": record.created_at.isoformat(),
                    "processing_history": record.processing_path,
                    "violated_rules": record.violated_rules,
                    "confidence_scores": full_audit_results.get("confidence_scores", []),
                    "agent_analyses": {
                        "initial_judgment": full_audit_results.get("initial_judgment", {}),
                        "routing_decision": full_audit_results.get("routing_decision", {}),
                        "rag_enhanced_judgment": full_audit_results.get("rag_enhanced_judgment", {}),
                        "expert_perspectives": full_audit_results.get("expert_perspectives", {}),
                        "arbitration_analysis": full_audit_results.get("arbitration_analysis", {})
                    },
                    "review_context": metadata.get("review_context", {}),
                    "complexity_assessment": self._assess_review_complexity(metadata)
                }

                # Add human review details if completed
                if metadata.get("human_review_completed"):
                    review_details["human_review"] = {
                        "reviewer": metadata.get("reviewer_name"),
                        "completed_at": metadata.get("review_completed_at"),
                        "decision_reasoning": metadata.get("human_decision_reasoning"),
                        "confidence": metadata.get("reviewer_confidence"),
                        "additional_notes": metadata.get("additional_notes")
                    }

                return review_details

        except Exception as e:
            logger.error(f"Failed to get review details: {e}")
            return {"error": str(e)}

    def _prepare_review_context(self, audit_results: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare context information to help human reviewers"""
        try:
            context = {
                "processing_summary": {
                    "total_agents": 0,
                    "confidence_progression": [],
                    "escalation_points": []
                },
                "key_concerns": [],
                "decision_factors": [],
                "similar_cases": [],
                "recommendation_conflicts": []
            }

            # Extract processing summary
            processing_path = audit_results.get("processing_path", [])
            context["processing_summary"]["total_agents"] = len(processing_path)

            # Extract confidence progression
            confidence_scores = audit_results.get("confidence_scores", [])
            context["processing_summary"]["confidence_progression"] = confidence_scores

            # Extract key concerns from different agents
            expert_perspectives = audit_results.get("expert_perspectives", {})
            for perspective_name, perspective_data in expert_perspectives.items():
                analysis = perspective_data.get("analysis", {})

                # Extract concerns based on perspective type
                if perspective_name == "legal_compliance":
                    legal_risks = analysis.get("legal_risks", [])
                    context["key_concerns"].extend([f"Legal: {risk.get('description', '')}" for risk in legal_risks])

                elif perspective_name == "social_impact":
                    concerns = analysis.get("concerns_identified", [])
                    context["key_concerns"].extend([f"Social: {concern.get('description', '')}" for concern in concerns])

                elif perspective_name == "platform_risk":
                    risks = analysis.get("identified_risks", [])
                    context["key_concerns"].extend([f"Risk: {risk.get('description', '')}" for risk in risks])

            # Extract arbitration analysis
            arbitration = audit_results.get("arbitration_analysis", {})
            decision_factors = arbitration.get("decision_factors", [])
            context["decision_factors"] = [factor.get("description", "") for factor in decision_factors]

            return context

        except Exception as e:
            logger.error(f"Failed to prepare review context: {e}")
            return {"error": "Context preparation failed"}

    def _extract_violated_rules(self, audit_results: Dict[str, Any]) -> List[str]:
        """Extract violated rules from audit results"""
        try:
            violated_rules = []

            # From initial judgment
            initial_judgment = audit_results.get("initial_judgment", {})
            violations = initial_judgment.get("violation_details", [])
            violated_rules.extend([v.get("rule_reference", "unknown") for v in violations])

            # From RAG enhanced judgment if available
            rag_judgment = audit_results.get("rag_enhanced_judgment", {})
            if rag_judgment:
                rag_violations = rag_judgment.get("violation_details", [])
                violated_rules.extend([v.get("rule_reference", "unknown") for v in rag_violations])

            return list(set(violated_rules))  # Remove duplicates

        except Exception as e:
            logger.error(f"Failed to extract violated rules: {e}")
            return []

    def _extract_processing_path(self, audit_results: Dict[str, Any]) -> List[str]:
        """Extract processing path from audit results"""
        try:
            return audit_results.get("processing_path", [])
        except Exception as e:
            logger.error(f"Failed to extract processing path: {e}")
            return []

    def _generate_content_hash(self, content: str) -> str:
        """Generate hash for content identification"""
        import hashlib
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _estimate_review_time(self, priority: ReviewPriority, audit_results: Dict[str, Any]) -> str:
        """Estimate human review time based on priority and complexity"""
        base_times = {
            ReviewPriority.CRITICAL: "1-2 hours",
            ReviewPriority.HIGH: "2-4 hours",
            ReviewPriority.MEDIUM: "4-8 hours",
            ReviewPriority.LOW: "1-2 days"
        }

        # Adjust based on complexity
        complexity = self._assess_review_complexity(audit_results)
        if complexity == "high":
            return base_times.get(priority, "4-8 hours") + " (complex case)"
        else:
            return base_times.get(priority, "4-8 hours")

    def _assess_review_complexity(self, metadata: Dict[str, Any]) -> str:
        """Assess complexity of review case"""
        try:
            complexity_factors = 0

            # Check number of violated rules
            violated_rules = metadata.get("violated_rules", [])
            if len(violated_rules) > 3:
                complexity_factors += 1

            # Check number of processing steps
            processing_path = metadata.get("processing_path", [])
            if len(processing_path) > 4:
                complexity_factors += 1

            # Check for conflicts in expert perspectives
            expert_perspectives = metadata.get("expert_perspectives", {})
            if len(expert_perspectives) > 2:
                complexity_factors += 1

            # Determine complexity level
            if complexity_factors >= 2:
                return "high"
            elif complexity_factors == 1:
                return "medium"
            else:
                return "low"

        except Exception as e:
            logger.error(f"Complexity assessment failed: {e}")
            return "medium"

    async def _get_queue_position(self, priority: ReviewPriority) -> int:
        """Get position in review queue"""
        try:
            with self.session_factory() as db:
                # Count items with higher or equal priority that were submitted earlier
                higher_priority_count = db.query(AuditRecord).filter(
                    and_(
                        AuditRecord.result == "pending_human_review",
                        AuditRecord.metadata["review_priority"].astext.in_(
                            [p.value for p in ReviewPriority if self.priority_weights[p] >= self.priority_weights[priority]]
                        )
                    )
                ).count()

                return higher_priority_count + 1

        except Exception as e:
            logger.error(f"Failed to get queue position: {e}")
            return 1

    async def _get_queue_statistics(self) -> Dict[str, Any]:
        """Get review queue statistics"""
        try:
            with self.session_factory() as db:
                # Count by priority
                priority_counts = {}
                for priority in ReviewPriority:
                    count = db.query(AuditRecord).filter(
                        and_(
                            AuditRecord.result == "pending_human_review",
                            AuditRecord.metadata["review_priority"].astext == priority.value
                        )
                    ).count()
                    priority_counts[priority.value] = count

                # Calculate average wait time (simplified)
                total_pending = sum(priority_counts.values())

                return {
                    "total_pending": total_pending,
                    "by_priority": priority_counts,
                    "estimated_processing_time": f"{total_pending * 2} hours" if total_pending > 0 else "No queue"
                }

        except Exception as e:
            logger.error(f"Failed to get queue statistics: {e}")
            return {"error": str(e)}

    async def _update_system_learning(
        self,
        record: AuditRecord,
        human_decision: str,
        confidence: float
    ):
        """Update system learning based on human decisions (for future AI improvements)"""
        try:
            # This is a placeholder for future machine learning improvements
            # Could be used to:
            # 1. Update agent confidence calibration
            # 2. Improve escalation thresholds
            # 3. Enhance rule matching accuracy
            # 4. Train better conflict resolution

            learning_data = {
                "content_hash": record.content_hash,
                "ai_processing_path": record.processing_path,
                "ai_confidence_scores": record.metadata.get("confidence_scores", []),
                "human_decision": human_decision,
                "human_confidence": confidence,
                "escalation_reason": record.reason,
                "learning_timestamp": datetime.now().isoformat()
            }

            # Log for future analysis
            db_service.log_system_event(
                level="INFO",
                component="SystemLearning",
                event="human_decision_logged",
                details=learning_data
            )

        except Exception as e:
            logger.error(f"System learning update failed: {e}")
            # Non-critical error, don't raise


# Global human review service instance
human_review_service = HumanReviewService()