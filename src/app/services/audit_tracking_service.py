from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
import json
import logging

from ..storage.database import db_service, SessionLocal, AuditRecord, SystemLog
from ..config.settings import settings

logger = logging.getLogger(__name__)


class AuditTrackingService:
    """Service for tracking and analyzing audit results"""

    def __init__(self):
        self.session_factory = SessionLocal

    def get_audit_statistics(
        self,
        days_back: int = 7,
        include_breakdown: bool = True
    ) -> Dict[str, Any]:
        """
        Get comprehensive audit statistics

        Args:
            days_back: Number of days to look back
            include_breakdown: Whether to include detailed breakdowns

        Returns:
            Statistics dictionary
        """
        try:
            with self.session_factory() as db:
                cutoff_date = datetime.utcnow() - timedelta(days=days_back)

                # Basic counts
                total_audits = db.query(AuditRecord).filter(
                    AuditRecord.created_at >= cutoff_date
                ).count()

                approved_count = db.query(AuditRecord).filter(
                    and_(
                        AuditRecord.created_at >= cutoff_date,
                        AuditRecord.result == "approved"
                    )
                ).count()

                rejected_count = db.query(AuditRecord).filter(
                    and_(
                        AuditRecord.created_at >= cutoff_date,
                        AuditRecord.result == "rejected"
                    )
                ).count()

                pending_count = db.query(AuditRecord).filter(
                    and_(
                        AuditRecord.created_at >= cutoff_date,
                        AuditRecord.result == "pending_review"
                    )
                ).count()

                # Average confidence score
                avg_confidence = db.query(func.avg(AuditRecord.confidence)).filter(
                    AuditRecord.created_at >= cutoff_date
                ).scalar() or 0.0

                stats = {
                    "period": {
                        "days": days_back,
                        "start_date": cutoff_date.isoformat(),
                        "end_date": datetime.utcnow().isoformat()
                    },
                    "totals": {
                        "total_audits": total_audits,
                        "approved": approved_count,
                        "rejected": rejected_count,
                        "pending_review": pending_count,
                        "error_count": total_audits - (approved_count + rejected_count + pending_count)
                    },
                    "percentages": {
                        "approval_rate": (approved_count / total_audits * 100) if total_audits > 0 else 0,
                        "rejection_rate": (rejected_count / total_audits * 100) if total_audits > 0 else 0,
                        "escalation_rate": (pending_count / total_audits * 100) if total_audits > 0 else 0
                    },
                    "quality_metrics": {
                        "average_confidence": round(avg_confidence, 3),
                        "automation_rate": ((approved_count + rejected_count) / total_audits * 100) if total_audits > 0 else 0
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }

                if include_breakdown:
                    stats["breakdowns"] = self._get_detailed_breakdowns(db, cutoff_date)

                return stats

        except Exception as e:
            logger.error(f"Failed to get audit statistics: {e}")
            return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

    def _get_detailed_breakdowns(self, db: Session, cutoff_date: datetime) -> Dict[str, Any]:
        """Get detailed breakdowns for statistics"""
        try:
            breakdowns = {}

            # Confidence score distribution
            confidence_ranges = [
                ("very_high", 0.9, 1.0),
                ("high", 0.8, 0.9),
                ("medium", 0.6, 0.8),
                ("low", 0.4, 0.6),
                ("very_low", 0.0, 0.4)
            ]

            confidence_distribution = {}
            for range_name, min_conf, max_conf in confidence_ranges:
                count = db.query(AuditRecord).filter(
                    and_(
                        AuditRecord.created_at >= cutoff_date,
                        AuditRecord.confidence >= min_conf,
                        AuditRecord.confidence < max_conf
                    )
                ).count()
                confidence_distribution[range_name] = count

            breakdowns["confidence_distribution"] = confidence_distribution

            # Processing path analysis
            processing_paths = db.query(AuditRecord.processing_path).filter(
                AuditRecord.created_at >= cutoff_date
            ).all()

            path_counts = {}
            for (path,) in processing_paths:
                if isinstance(path, list):
                    path_key = " -> ".join(path)
                    path_counts[path_key] = path_counts.get(path_key, 0) + 1

            breakdowns["processing_paths"] = dict(sorted(path_counts.items(), key=lambda x: x[1], reverse=True)[:10])

            # Violation analysis
            violation_stats = self._analyze_violations(db, cutoff_date)
            breakdowns["violations"] = violation_stats

            return breakdowns

        except Exception as e:
            logger.error(f"Failed to get detailed breakdowns: {e}")
            return {}

    def _analyze_violations(self, db: Session, cutoff_date: datetime) -> Dict[str, Any]:
        """Analyze violation patterns"""
        try:
            records = db.query(AuditRecord.violated_rules).filter(
                and_(
                    AuditRecord.created_at >= cutoff_date,
                    AuditRecord.result == "rejected"
                )
            ).all()

            violation_counts = {}
            total_violations = 0

            for (violated_rules,) in records:
                if isinstance(violated_rules, list):
                    for rule in violated_rules:
                        violation_counts[rule] = violation_counts.get(rule, 0) + 1
                        total_violations += 1

            # Sort by frequency
            top_violations = dict(sorted(violation_counts.items(), key=lambda x: x[1], reverse=True)[:10])

            return {
                "total_violations": total_violations,
                "unique_rules_violated": len(violation_counts),
                "top_violated_rules": top_violations,
                "avg_violations_per_rejection": total_violations / len(records) if records else 0
            }

        except Exception as e:
            logger.error(f"Violation analysis failed: {e}")
            return {}

    def get_audit_history(
        self,
        limit: int = 100,
        offset: int = 0,
        result_filter: Optional[str] = None,
        min_confidence: Optional[float] = None,
        max_confidence: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Get paginated audit history with optional filters

        Args:
            limit: Maximum records to return
            offset: Number of records to skip
            result_filter: Filter by result type
            min_confidence: Minimum confidence score
            max_confidence: Maximum confidence score

        Returns:
            Paginated audit history
        """
        try:
            with self.session_factory() as db:
                query = db.query(AuditRecord)

                # Apply filters
                filters = []
                if result_filter:
                    filters.append(AuditRecord.result == result_filter)
                if min_confidence is not None:
                    filters.append(AuditRecord.confidence >= min_confidence)
                if max_confidence is not None:
                    filters.append(AuditRecord.confidence <= max_confidence)

                if filters:
                    query = query.filter(and_(*filters))

                # Get total count
                total_count = query.count()

                # Get paginated results
                records = query.order_by(desc(AuditRecord.created_at))\
                              .offset(offset)\
                              .limit(limit)\
                              .all()

                # Format results
                formatted_records = []
                for record in records:
                    formatted_records.append({
                        "id": record.id,
                        "content_hash": record.content_hash,
                        "content_preview": record.content_preview,
                        "result": record.result,
                        "confidence": record.confidence,
                        "reason": record.reason,
                        "violated_rules": record.violated_rules,
                        "processing_path": record.processing_path,
                        "created_at": record.created_at.isoformat(),
                        "metadata": record.metadata
                    })

                return {
                    "records": formatted_records,
                    "pagination": {
                        "total": total_count,
                        "limit": limit,
                        "offset": offset,
                        "has_more": offset + limit < total_count
                    },
                    "filters_applied": {
                        "result_filter": result_filter,
                        "min_confidence": min_confidence,
                        "max_confidence": max_confidence
                    }
                }

        except Exception as e:
            logger.error(f"Failed to get audit history: {e}")
            return {"error": str(e), "records": [], "pagination": {"total": 0}}

    def get_audit_record_by_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get audit record by content hash

        Args:
            content_hash: SHA-256 hash of content

        Returns:
            Audit record or None if not found
        """
        try:
            with self.session_factory() as db:
                record = db.query(AuditRecord).filter(
                    AuditRecord.content_hash == content_hash
                ).order_by(desc(AuditRecord.created_at)).first()

                if not record:
                    return None

                return {
                    "id": record.id,
                    "content_hash": record.content_hash,
                    "content_preview": record.content_preview,
                    "result": record.result,
                    "confidence": record.confidence,
                    "reason": record.reason,
                    "violated_rules": record.violated_rules,
                    "processing_path": record.processing_path,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat(),
                    "metadata": record.metadata
                }

        except Exception as e:
            logger.error(f"Failed to get audit record by hash: {e}")
            return None

    def get_performance_metrics(self, days_back: int = 30) -> Dict[str, Any]:
        """
        Get performance metrics for the audit system

        Args:
            days_back: Number of days to analyze

        Returns:
            Performance metrics
        """
        try:
            with self.session_factory() as db:
                cutoff_date = datetime.utcnow() - timedelta(days=days_back)

                # Processing time analysis (from metadata if available)
                records = db.query(AuditRecord.metadata).filter(
                    AuditRecord.created_at >= cutoff_date
                ).all()

                processing_times = []
                escalation_rates = {"total": 0, "escalated": 0}
                confidence_accuracy = []

                for (metadata,) in records:
                    if isinstance(metadata, dict):
                        # Extract processing time if available
                        if "processing_time_ms" in metadata:
                            processing_times.append(metadata["processing_time_ms"])

                        # Track escalations
                        escalation_rates["total"] += 1
                        if metadata.get("escalation_type", "none") != "none":
                            escalation_rates["escalated"] += 1

                        # Confidence accuracy (placeholder - would need ground truth data)
                        if "confidence_accuracy" in metadata:
                            confidence_accuracy.append(metadata["confidence_accuracy"])

                metrics = {
                    "period_days": days_back,
                    "performance_metrics": {
                        "total_processed": escalation_rates["total"],
                        "escalation_rate": (escalation_rates["escalated"] / escalation_rates["total"] * 100)
                                          if escalation_rates["total"] > 0 else 0,
                        "automation_effectiveness": ((escalation_rates["total"] - escalation_rates["escalated"]) /
                                                   escalation_rates["total"] * 100)
                                                  if escalation_rates["total"] > 0 else 0
                    },
                    "processing_times": {
                        "count": len(processing_times),
                        "average_ms": sum(processing_times) / len(processing_times) if processing_times else 0,
                        "min_ms": min(processing_times) if processing_times else 0,
                        "max_ms": max(processing_times) if processing_times else 0
                    } if processing_times else None,
                    "system_health": self._calculate_system_health_score(db, cutoff_date),
                    "timestamp": datetime.utcnow().isoformat()
                }

                return metrics

        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

    def _calculate_system_health_score(self, db: Session, cutoff_date: datetime) -> Dict[str, Any]:
        """Calculate overall system health score"""
        try:
            # Count errors from system logs
            error_count = db.query(SystemLog).filter(
                and_(
                    SystemLog.created_at >= cutoff_date,
                    SystemLog.level == "ERROR"
                )
            ).count()

            # Count total operations
            total_operations = db.query(AuditRecord).filter(
                AuditRecord.created_at >= cutoff_date
            ).count()

            # Calculate error rate
            error_rate = (error_count / total_operations * 100) if total_operations > 0 else 0

            # Calculate health score (0-100)
            health_score = max(0, 100 - error_rate * 10)  # Each 1% error reduces health by 10 points

            # Determine health status
            if health_score >= 90:
                status = "excellent"
            elif health_score >= 80:
                status = "good"
            elif health_score >= 70:
                status = "fair"
            elif health_score >= 60:
                status = "poor"
            else:
                status = "critical"

            return {
                "health_score": health_score,
                "status": status,
                "error_rate": error_rate,
                "total_operations": total_operations,
                "error_count": error_count
            }

        except Exception as e:
            logger.error(f"System health calculation failed: {e}")
            return {"health_score": 50, "status": "unknown", "error": str(e)}

    def export_audit_data(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        format_type: str = "json"
    ) -> Tuple[str, str]:
        """
        Export audit data for analysis

        Args:
            start_date: Start date for export
            end_date: End date for export
            format_type: Export format ("json", "csv")

        Returns:
            Tuple of (filename, content)
        """
        try:
            with self.session_factory() as db:
                query = db.query(AuditRecord)

                if start_date:
                    query = query.filter(AuditRecord.created_at >= start_date)
                if end_date:
                    query = query.filter(AuditRecord.created_at <= end_date)

                records = query.order_by(AuditRecord.created_at).all()

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                if format_type.lower() == "json":
                    filename = f"audit_export_{timestamp}.json"
                    data = []

                    for record in records:
                        data.append({
                            "id": record.id,
                            "content_hash": record.content_hash,
                            "result": record.result,
                            "confidence": record.confidence,
                            "reason": record.reason,
                            "violated_rules": record.violated_rules,
                            "processing_path": record.processing_path,
                            "created_at": record.created_at.isoformat(),
                            "metadata": record.metadata
                        })

                    content = json.dumps(data, indent=2, ensure_ascii=False)

                else:
                    raise ValueError(f"Unsupported export format: {format_type}")

                return filename, content

        except Exception as e:
            logger.error(f"Audit data export failed: {e}")
            raise

    def generate_audit_report(self, days_back: int = 7) -> Dict[str, Any]:
        """
        Generate comprehensive audit report

        Args:
            days_back: Number of days to include in report

        Returns:
            Comprehensive report
        """
        try:
            statistics = self.get_audit_statistics(days_back, include_breakdown=True)
            performance = self.get_performance_metrics(days_back)

            return {
                "report_metadata": {
                    "generated_at": datetime.utcnow().isoformat(),
                    "period_days": days_back,
                    "report_version": "v1.0.0"
                },
                "executive_summary": {
                    "total_audits": statistics["totals"]["total_audits"],
                    "automation_rate": statistics["quality_metrics"]["automation_rate"],
                    "average_confidence": statistics["quality_metrics"]["average_confidence"],
                    "system_health": performance.get("system_health", {}).get("status", "unknown")
                },
                "detailed_statistics": statistics,
                "performance_metrics": performance,
                "recommendations": self._generate_recommendations(statistics, performance)
            }

        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return {
                "error": str(e),
                "report_metadata": {
                    "generated_at": datetime.utcnow().isoformat(),
                    "status": "failed"
                }
            }

    def _generate_recommendations(
        self,
        statistics: Dict[str, Any],
        performance: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations based on audit analysis"""
        recommendations = []

        try:
            # Automation rate recommendations
            automation_rate = statistics.get("quality_metrics", {}).get("automation_rate", 0)
            if automation_rate < 70:
                recommendations.append("Consider improving rule clarity to increase automation rate")

            # Confidence recommendations
            avg_confidence = statistics.get("quality_metrics", {}).get("average_confidence", 0)
            if avg_confidence < 0.7:
                recommendations.append("Review confidence scoring parameters to improve decision quality")

            # Escalation rate recommendations
            escalation_rate = statistics.get("percentages", {}).get("escalation_rate", 0)
            if escalation_rate > 30:
                recommendations.append("High escalation rate - consider rule refinement or agent improvements")

            # System health recommendations
            health_status = performance.get("system_health", {}).get("status", "unknown")
            if health_status in ["poor", "critical"]:
                recommendations.append("System health requires attention - investigate error sources")

            # Performance recommendations
            error_rate = performance.get("system_health", {}).get("error_rate", 0)
            if error_rate > 5:
                recommendations.append("Error rate is elevated - review system logs and improve error handling")

            if not recommendations:
                recommendations.append("System performance is within normal parameters")

        except Exception as e:
            logger.error(f"Recommendation generation failed: {e}")
            recommendations.append("Unable to generate recommendations due to analysis error")

        return recommendations


# Global audit tracking service instance
audit_tracking_service = AuditTrackingService()